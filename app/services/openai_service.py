import logging
from pathlib import Path
from typing import TypeVar

import openai
from openai import AsyncOpenAI
from openai.types.responses import ResponseInputParam
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.schemas.answer import AnswerAnalysis
from app.schemas.knowledge import KnowledgeItem, StarExample
from app.schemas.question import InterviewQuestion, QuestionSet
from app.schemas.vacancy import VacancyAnalysis
from app.services.exceptions import LLMServiceError
from app.schemas.session_summary import InterviewSummary
from app.services.prompt_context import (
    build_answer_context,
    build_questions_context,
    build_summary_context,
)
from app.services.session_statistics import AnsweredQuestion, SessionStatistics

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
VACANCY_ANALYSIS_PROMPT = (PROMPTS_DIR / "vacancy_analysis.txt").read_text(encoding="utf-8")
QUESTIONS_PROMPT = (PROMPTS_DIR / "questions.txt").read_text(encoding="utf-8")
ANSWER_ANALYSIS_PROMPT = (PROMPTS_DIR / "answer_analysis.txt").read_text(encoding="utf-8")
SESSION_SUMMARY_PROMPT = (PROMPTS_DIR / "session_summary.txt").read_text(encoding="utf-8")

ModelT = TypeVar("ModelT", bound=BaseModel)


class OpenAIService:
    def __init__(self, client: AsyncOpenAI | None = None, model: str | None = None):
        self.client = client
        self.model = model or settings.openai_model

    @classmethod
    def from_settings(cls) -> "OpenAIService":
        if not settings.openai_api_key:
            logger.warning("OPENAI_API_KEY is not set; LLM features are disabled")
            return cls()
        client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout,
            max_retries=0,
        )
        return cls(client=client)

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()

    async def analyze_vacancy(self, vacancy_text: str) -> VacancyAnalysis:
        return await self._parse(
            [
                {"role": "system", "content": VACANCY_ANALYSIS_PROMPT},
                {"role": "user", "content": vacancy_text},
            ],
            VacancyAnalysis,
        )

    async def generate_questions(
        self,
        vacancy_analysis: VacancyAnalysis,
        knowledge_items: list[KnowledgeItem],
    ) -> QuestionSet:
        return await self._parse(
            [
                {"role": "system", "content": QUESTIONS_PROMPT},
                {
                    "role": "user",
                    "content": build_questions_context(vacancy_analysis, knowledge_items),
                },
            ],
            QuestionSet,
        )

    async def analyze_answer(
        self,
        question: InterviewQuestion,
        answer: str,
        vacancy_analysis: VacancyAnalysis,
        star_examples: list[StarExample] | None = None,
    ) -> AnswerAnalysis:
        return await self._parse(
            [
                {"role": "system", "content": ANSWER_ANALYSIS_PROMPT},
                {
                    "role": "user",
                    "content": build_answer_context(
                        question, answer, vacancy_analysis, star_examples
                    ),
                },
            ],
            AnswerAnalysis,
        )

    async def summarize_session(
        self,
        vacancy_analysis: VacancyAnalysis,
        answered: list[AnsweredQuestion],
        statistics: SessionStatistics,
    ) -> InterviewSummary:
        return await self._parse(
            [
                {"role": "system", "content": SESSION_SUMMARY_PROMPT},
                {
                    "role": "user",
                    "content": build_summary_context(vacancy_analysis, answered, statistics),
                },
            ],
            InterviewSummary,
        )

    async def _parse(self, input_messages: ResponseInputParam, text_format: type[ModelT]) -> ModelT:
        if self.client is None:
            raise LLMServiceError("OpenAI client is not configured")
        name = text_format.__name__
        try:
            response = await self.client.responses.parse(
                model=self.model,
                input=input_messages,
                text_format=text_format,
                store=False,
            )
        except openai.AuthenticationError as exc:
            raise self._failure("authentication failed", exc) from exc
        except openai.APITimeoutError as exc:
            raise self._failure("request timed out", exc) from exc
        except openai.APIConnectionError as exc:
            raise self._failure("connection failed", exc) from exc
        except openai.APIStatusError as exc:
            raise self._failure(f"API returned status {exc.status_code}", exc) from exc
        except openai.OpenAIError as exc:
            raise self._failure("SDK error", exc) from exc
        except ValidationError as exc:
            raise self._failure(f"response does not match {name}", exc) from exc
        except Exception as exc:
            logger.exception("OpenAI request failed with unexpected error")
            raise LLMServiceError("Unexpected error during OpenAI request") from exc

        request_id = getattr(response, "_request_id", None)
        result = response.output_parsed
        if not isinstance(result, text_format):
            logger.warning(
                "OpenAI request failed: no parsed output (status=%s, request_id=%s)",
                response.status,
                request_id,
            )
            raise LLMServiceError(f"OpenAI returned no {name}")
        logger.info("OpenAI request completed (%s, request_id=%s)", name, request_id)
        return result

    @staticmethod
    def _failure(reason: str, exc: Exception) -> LLMServiceError:
        # SDK messages may echo a masked API key or request body, so only the type is logged.
        logger.warning(
            "OpenAI request failed: %s (%s, request_id=%s)",
            reason,
            type(exc).__name__,
            getattr(exc, "request_id", None),
        )
        return LLMServiceError(f"OpenAI request failed: {reason}")
