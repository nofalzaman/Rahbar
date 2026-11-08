"""Hosted free-tier provider (Groq, Google AI Studio, OpenRouter): any OpenAI-compatible API.

The key arrives as LLM_API_KEY from a Kubernetes Secret created on the command
line. It never appears in a file you commit, and never in a log line.
"""

from __future__ import annotations

import httpx

from ... import telemetry
from ...config import Settings
from ...schemas import Answer, Passage
from .base import ProviderError
from .prompt import build_messages, parse_answer


class HostedProvider:
    name = "hosted"

    def __init__(self, settings: Settings) -> None:
        if not settings.hosted_base_url or not settings.llm_api_key:
            raise ValueError("LLM_PROVIDER=hosted needs HOSTED_BASE_URL and LLM_API_KEY")
        self.settings = settings

    def generate(self, question: str, passages: list[Passage]) -> Answer:
        response = httpx.post(
            f"{self.settings.hosted_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
            json={
                "model": self.settings.llm_model,
                "messages": build_messages(question, passages),
                "temperature": self.settings.temperature,
                "response_format": {"type": "json_object"},
            },
            timeout=self.settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        usage = body.get("usage") or {}
        telemetry.TOKENS.labels("in").inc(usage.get("prompt_tokens", 0))
        telemetry.TOKENS.labels("out").inc(usage.get("completion_tokens", 0))
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("unexpected reply shape from the hosted provider") from exc
        return parse_answer(content)