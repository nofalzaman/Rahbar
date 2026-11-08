"""Ollama provider: ollama-host or ollama-incluster (section 3.5)."""

from __future__ import annotations

import httpx

from ... import telemetry
from ...config import Settings
from ...schemas import Answer, Passage
from .base import ProviderError
from .prompt import build_messages, parse_answer


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(self, question: str, passages: list[Passage]) -> Answer:
        response = httpx.post(
            f"{self.settings.ollama_url}/api/chat",
            json={
                "model": self.settings.llm_model,
                "messages": build_messages(question, passages),
                "stream": False,
                "format": Answer.model_json_schema(),   # Ollama enforces the schema
                "options": {"temperature": self.settings.temperature},
            },
            timeout=self.settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        telemetry.TOKENS.labels("in").inc(body.get("prompt_eval_count", 0))
        telemetry.TOKENS.labels("out").inc(body.get("eval_count", 0))
        try:
            content = body["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise ProviderError("unexpected reply shape from Ollama") from exc
        return parse_answer(content)