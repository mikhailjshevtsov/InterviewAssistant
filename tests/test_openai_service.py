import json
import logging
from collections.abc import Callable

import httpx
import pytest
from openai import AsyncOpenAI

from app.schemas.vacancy import VacancyAnalysis
from app.services.exceptions import LLMServiceError
from app.services.openai_service import VACANCY_ANALYSIS_PROMPT, OpenAIService

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
