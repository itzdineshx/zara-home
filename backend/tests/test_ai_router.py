from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.config import Settings
from app.services.ai_router import AIRouterService


@dataclass
class StubOpenRouterClient:
    response: str = "online response"
    should_fail: bool = False
    calls: list[tuple[str, list[dict[str, str]] | None, str | None]] | None = None

    async def chat(self, text: str, history: list[dict[str, str]] | None = None, response_language: str | None = None):
        if self.calls is None:
            self.calls = []
        self.calls.append((text, history, response_language))
        if self.should_fail:
            raise RuntimeError("openrouter unavailable")
        return self.response


@dataclass
class StubOllamaClient:
    response: str = "local response"
    calls: list[tuple[str, str | None]] | None = None

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        response_language: str | None = None,
        timeout_s: float | None = None,
    ):
        if self.calls is None:
            self.calls = []
        self.calls.append((prompt, response_language))
        return self.response


def test_smart_mode_uses_online_ai_first():
    settings = Settings()
    openrouter = StubOpenRouterClient(response="online answer")
    ollama = StubOllamaClient(response="local answer")
    router = AIRouterService(settings, openrouter, ollama)

    answer, source = asyncio.run(router.route_request("What is AI?", mode="smart", response_language="English"))

    assert answer == "online answer"
    assert source == "openrouter"
    assert openrouter.calls is not None and len(openrouter.calls) == 1
    assert ollama.calls is None


def test_online_mode_falls_back_to_local_ai_on_cloud_failure():
    settings = Settings()
    openrouter = StubOpenRouterClient(should_fail=True)
    ollama = StubOllamaClient(response="local backup answer")
    router = AIRouterService(settings, openrouter, ollama)

    answer, source = asyncio.run(router.route_request("What is AI?", mode="online", response_language="English"))

    assert answer == "local backup answer"
    assert source == "ollama"
    assert openrouter.calls is not None and len(openrouter.calls) == 1
    assert ollama.calls is not None and len(ollama.calls) == 1


def test_offline_mode_skips_cloud_ai():
    settings = Settings()
    openrouter = StubOpenRouterClient(response="should not be used")
    ollama = StubOllamaClient(response="offline answer")
    router = AIRouterService(settings, openrouter, ollama)

    answer, source = asyncio.run(router.route_request("What is AI?", mode="offline", response_language="English"))

    assert answer == "offline answer"
    assert source == "ollama"
    assert openrouter.calls is None
    assert ollama.calls is not None and len(ollama.calls) == 1
