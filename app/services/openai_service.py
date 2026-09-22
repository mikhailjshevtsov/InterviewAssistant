import logging
from pathlib import Path

import openai
from openai import AsyncOpenAI
from pydantic import ValidationError

from app.config import settings
from app.schemas.answer import AnswerAnalysis
from app.schemas.question import InterviewQuestion, QuestionSet
from app.schemas.vacancy import VacancyAnalysis
from app.services.exceptions import LLMServiceError

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
VACANCY_ANALYSIS_PROMPT = (PROMPTS_DIR / "vacancy_analysis.txt").read_text(encoding="utf-8")


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
        if self.client is None:
            raise LLMServiceError("OpenAI client is not configured")
        try:
            response = await self.client.responses.parse(
                model=self.model,
                input=[
                    {"role": "system", "content": VACANCY_ANALYSIS_PROMPT},
                    {"role": "user", "content": vacancy_text},
                ],
                text_format=VacancyAnalysis,
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
            raise self._failure("response does not match VacancyAnalysis", exc) from exc
        except Exception as exc:
            logger.exception("OpenAI request failed with unexpected error")
            raise LLMServiceError("Unexpected error during OpenAI request") from exc

        result = response.output_parsed
        if not isinstance(result, VacancyAnalysis):
            logger.warning(
                "OpenAI request failed: no parsed output (status=%s, request_id=%s)",
                response.status,
                getattr(response, "_request_id", None),
            )
            raise LLMServiceError("OpenAI returned no VacancyAnalysis")
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

    async def generate_questions(
        self,
        vacancy_analysis: VacancyAnalysis,
        knowledge_items: list[InterviewQuestion],
    ) -> QuestionSet:
        raise NotImplementedError

    async def analyze_answer(
        self,
        question: InterviewQuestion,
        answer: str,
        vacancy_analysis: VacancyAnalysis,
    ) -> AnswerAnalysis:
        raise NotImplementedError
