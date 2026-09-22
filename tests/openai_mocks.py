import json
from collections.abc import Callable

import httpx
from openai import AsyncOpenAI

from app.services.openai_service import OpenAIService

Handler = Callable[[httpx.Request], httpx.Response]


def output_text_response(text: str) -> httpx.Response:
    return _message_response([{"type": "output_text", "text": text, "annotations": []}])


def refusal_response() -> httpx.Response:
    return _message_response([{"type": "refusal", "refusal": "I can't help with that"}])


def error_response(status_code: int) -> httpx.Response:
    return httpx.Response(
        status_code, json={"error": {"message": "boom", "type": "error", "code": None}}
    )


def _message_response(content: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
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
        },
    )


class RecordingTransport:
    """Serves canned responses and records every request the SDK sends."""

    def __init__(self, handler: Handler):
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)

    def bodies(self) -> list[dict]:
        return [json.loads(request.content) for request in self.requests]


def make_openai_service(handler: Handler) -> tuple[OpenAIService, RecordingTransport]:
    transport = RecordingTransport(handler)
    client = AsyncOpenAI(
        api_key="sk-test-not-a-real-key",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)),
    )
    return OpenAIService(client=client, model="gpt-test"), transport
