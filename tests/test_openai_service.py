import inspect
import json
import logging
from collections.abc import Callable

import httpx
import pytest
from openai import AsyncOpenAI

from app.schemas.knowledge import KnowledgeItem
from app.schemas.question import InterviewQuestion, QuestionSet
from app.schemas.vacancy import VacancyAnalysis
from app.services import openai_service as openai_service_module
from app.services.exceptions import LLMServiceError
from app.services.openai_service import (
    QUESTIONS_PROMPT,
    VACANCY_ANALYSIS_PROMPT,
    OpenAIService,
)

TEST_API_KEY = "sk-test-not-a-real-key"
VACANCY_TEXT = "Ищем бизнес-аналитика: SQL, BPMN, REST API, сбор требований. " * 3
ANALYSIS = VacancyAnalysis(
    position="Бизнес-аналитик",
    company=None,
    hard_skills=["SQL", "BPMN", "REST API"],
    soft_skills=["коммуникация"],
    experience=["сбор требований"],
    responsibilities=["анализ требований"],
    interview_topics=["SQL", "системный анализ"],
)

Handler = Callable[[httpx.Request], httpx.Response]


def response_body(content: list[dict]) -> dict:
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 0,
        "model": "gpt-test",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": "msg_test",
                "role": "assistant",
                "status": "completed",
                "content": content,
            }
        ],
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
    }


def output_text(text: str) -> httpx.Response:
    return httpx.Response(
        200, json=response_body([{"type": "output_text", "text": text, "annotations": []}])
    )


def make_service(handler: Handler) -> OpenAIService:
    client = AsyncOpenAI(
        api_key=TEST_API_KEY,
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return OpenAIService(client=client, model="gpt-test")


def error_response(status_code: int, message: str) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code, json={"error": {"message": message, "type": "error", "code": None}}
        )

    return handler


async def test_successful_structured_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return output_text(ANALYSIS.model_dump_json())

    service = make_service(handler)
    result = await service.analyze_vacancy(VACANCY_TEXT)
    await service.close()

    assert isinstance(result, VacancyAnalysis)
    assert result == ANALYSIS

    [request] = requests
    assert request.url.path.endswith("/responses")
    body = json.loads(request.content)
    assert body["model"] == "gpt-test"
    assert body["store"] is False
    assert body["input"] == [
        {"role": "system", "content": VACANCY_ANALYSIS_PROMPT},
        {"role": "user", "content": VACANCY_TEXT},
    ]
    text_format = body["text"]["format"]
    assert text_format["type"] == "json_schema"
    assert text_format["name"] == "VacancyAnalysis"
    assert text_format["strict"] is True
    assert set(text_format["schema"]["required"]) == set(VacancyAnalysis.model_fields)


async def test_authentication_error_is_wrapped_without_leaking_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = make_service(
        error_response(401, f"Incorrect API key provided: {TEST_API_KEY}")
    )

    with caplog.at_level(logging.DEBUG), pytest.raises(LLMServiceError) as exc_info:
        await service.analyze_vacancy(VACANCY_TEXT)

    assert "authentication" in str(exc_info.value)
    assert TEST_API_KEY not in str(exc_info.value)
    assert TEST_API_KEY not in caplog.text
    assert "OpenAI request failed" in caplog.text


@pytest.mark.parametrize("status_code", [400, 429, 500, 503])
async def test_api_status_error_is_wrapped(status_code: int) -> None:
    service = make_service(error_response(status_code, "boom"))

    with pytest.raises(LLMServiceError, match=str(status_code)):
        await service.analyze_vacancy(VACANCY_TEXT)


async def test_timeout_is_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(LLMServiceError, match="timed out"):
        await make_service(handler).analyze_vacancy(VACANCY_TEXT)


async def test_connection_error_is_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(LLMServiceError, match="connection"):
        await make_service(handler).analyze_vacancy(VACANCY_TEXT)


@pytest.mark.parametrize(
    "text",
    [
        "not json at all",
        '{"position": "QA"}',
        json.dumps(ANALYSIS.model_dump(mode="json") | {"salary": "100k"}),
        '{"position": "QA", "company": null, "hard_skills": "SQL"',
    ],
)
async def test_malformed_response_is_wrapped(text: str) -> None:
    service = make_service(lambda request: output_text(text))

    with pytest.raises(LLMServiceError, match="does not match"):
        await service.analyze_vacancy(VACANCY_TEXT)


async def test_refusal_is_wrapped() -> None:
    refusal = httpx.Response(
        200, json=response_body([{"type": "refusal", "refusal": "I can't help with that"}])
    )
    service = make_service(lambda request: refusal)

    with pytest.raises(LLMServiceError, match="no VacancyAnalysis"):
        await service.analyze_vacancy(VACANCY_TEXT)


async def test_unexpected_error_is_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("unexpected")

    with pytest.raises(LLMServiceError):
        await make_service(handler).analyze_vacancy(VACANCY_TEXT)


async def test_missing_client_raises_llm_error() -> None:
    with pytest.raises(LLMServiceError, match="not configured"):
        await OpenAIService().analyze_vacancy(VACANCY_TEXT)


KB_ITEM = KnowledgeItem(
    id="4",
    profession="analyst",
    category="technical",
    question="Какие SQL JOIN вы знаете?",
    difficulty="easy",
    keywords=["SQL", "JOIN"],
)
QUESTION_SET = QuestionSet(
    questions=[
        InterviewQuestion(
            id="Q-01",
            question="Как вы используете SQL для проверки требований?",
            category="technical",
            difficulty="medium",
        ),
        InterviewQuestion(
            id="Q-02",
            question="Расскажите о конфликте требований.",
            category="behavioral",
            difficulty="medium",
            star_required=True,
        ),
    ]
)


async def generate(handler: Handler) -> QuestionSet:
    return await make_service(handler).generate_questions(ANALYSIS, [KB_ITEM])


async def test_generate_questions_structured_request_and_result() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return output_text(QUESTION_SET.model_dump_json())

    result = await generate(handler)

    assert isinstance(result, QuestionSet)
    assert result == QUESTION_SET
    [request] = requests
    body = json.loads(request.content)
    assert body["model"] == "gpt-test"
    assert body["store"] is False
    system, user = body["input"]
    assert system == {"role": "system", "content": QUESTIONS_PROMPT}
    assert user["role"] == "user"
    assert "<vacancy_analysis>" in user["content"] and "Бизнес-аналитик" in user["content"]
    assert "<knowledge_base>" in user["content"] and "[KB-4]" in user["content"]
    assert "Какие SQL JOIN вы знаете?" not in system["content"]
    text_format = body["text"]["format"]
    assert text_format["type"] == "json_schema"
    assert text_format["name"] == "QuestionSet"
    assert text_format["strict"] is True
    questions_schema = text_format["schema"]["properties"]["questions"]
    assert (questions_schema["minItems"], questions_schema["maxItems"]) == (1, 10)


async def test_generate_questions_refusal() -> None:
    refusal = httpx.Response(
        200, json=response_body([{"type": "refusal", "refusal": "I can't help with that"}])
    )

    with pytest.raises(LLMServiceError, match="no QuestionSet"):
        await generate(lambda request: refusal)


async def test_generate_questions_api_error() -> None:
    with pytest.raises(LLMServiceError, match="500"):
        await generate(error_response(500, "boom"))


async def test_generate_questions_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(LLMServiceError, match="timed out"):
        await generate(handler)


async def test_generate_questions_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(LLMServiceError, match="connection"):
        await generate(handler)


async def test_generate_questions_invalid_json() -> None:
    with pytest.raises(LLMServiceError, match="does not match QuestionSet"):
        await generate(lambda request: output_text('{"questions": [{"id": "Q-01"}]}'))


def test_openai_service_does_not_parse_json_manually() -> None:
    source = inspect.getsource(openai_service_module)

    assert "json.loads" not in source
    assert "output_text" not in source
    assert "output_parsed" in source
