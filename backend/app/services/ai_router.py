from __future__ import annotations

import asyncio
import re
from typing import Literal

import httpx
from cachetools import TTLCache

from app.config import Settings
from app.schemas import ModeLiteral
from app.services.ollama_client import OllamaClient
from app.services.openrouter_client import OpenRouterClient

RouteSource = Literal["openrouter", "ollama"]


class AIRouterService:
    """
    Production-grade request router implementing three AI strategies:
    
    1. ONLINE MODE: Use only Gemini Flash 2.0 (cloud) for best quality.
    2. SMART MODE (default): Gemini Flash 2.0 primary with automatic local fallback (Gemma E2B)
       - Tries cloud first (faster + smarter)
       - Falls back to Ollama on timeout/error for resilience
       - Caches responses to reduce repeated cloud calls
    3. OFFLINE MODE: Gemma E2B local only (for testing, privacy, or when cloud unavailable)
    
    The router prioritizes cost, speed, and reliability: cloud-first for quality,
    local fallback for resilience, offline-only for development/testing.
    """

    _LANGUAGE_REFUSAL_RE = re.compile(
        (
            r"\b("
            r"do not understand this language|"
            r"don't understand this language|"
            r"dont understand this language|"
            r"cannot understand this language|"
            r"do not understand|"
            r"don't understand|"
            r"dont understand|"
            r"i am sorry[, ]+i (do not|don't|dont) understand|"
            r"i'm sorry[, ]+i (do not|don't|dont) understand|"
            r"only understand english|"
            r"i only understand english|"
            r"please use english|"
            r"please speak english|"
            r"please speak in english|"
            r"could you please speak in english|"
            r"please speak in english[, ]+hindi[, ]+tamil[, ]+telugu[, ]+or[ ,]+malayalam|"
            r"please use english[, ]+hindi[, ]+tamil[, ]+telugu[, ]+or[ ,]+malayalam"
            r")\b"
        ),
        flags=re.IGNORECASE,
    )

    def __init__(
        self,
        settings: Settings,
        openrouter_client: OpenRouterClient,
        ollama_client: OllamaClient,
    ) -> None:
        self.settings = settings
        self.openrouter_client = openrouter_client
        self.ollama_client = ollama_client
        self.cache: TTLCache[str, str] = TTLCache(
            maxsize=settings.cache_max_entries,
            ttl=settings.cache_ttl_seconds,
        )
        self._cache_lock = asyncio.Lock()

    async def route_request(
        self,
        text: str,
        mode: ModeLiteral,
        history: list[dict[str, str]] | None = None,
        response_language: str | None = None,
    ) -> tuple[str, RouteSource]:
        normalized = " ".join(text.strip().split())
        if not normalized:
            return "Please share a valid prompt.", "openrouter"

        language_key = (response_language or "auto").strip().lower()
        cache_key = f"{mode}:{language_key}:{normalized.lower()}"
        cached = await self._cache_get(cache_key)
        if cached is not None:
            if self._is_language_refusal(cached):
                await self._cache_delete(cache_key)
            else:
                return cached, "openrouter"

        if mode == "offline":
            answer, source = await self._offline_only(normalized, response_language=response_language)
        else:
            answer, source = await self._online_primary_with_local_fallback(
                normalized,
                history,
                response_language=response_language,
            )

        if self._is_language_refusal(answer):
            recovered = await self._recover_from_language_refusal(
                text=normalized,
                source=source,
                history=history,
                response_language=response_language,
            )
            if recovered is not None:
                answer, source = recovered

        if self._is_language_refusal(answer):
            answer = self._fallback_clarification(response_language)

        if not self._is_language_refusal(answer):
            await self._cache_set(cache_key, answer)

        return answer, source

    async def _cache_get(self, key: str) -> str | None:
        async with self._cache_lock:
            return self.cache.get(key)

    async def _cache_set(self, key: str, value: str) -> None:
        async with self._cache_lock:
            self.cache[key] = value

    async def _cache_delete(self, key: str) -> None:
        async with self._cache_lock:
            self.cache.pop(key, None)

    async def _offline_only(self, text: str, response_language: str | None = None) -> tuple[str, RouteSource]:
        """Offline mode: Use local Gemma E2B (Ollama) only, skip cloud entirely."""
        primary_model = self.settings.ollama_model
        secondary_model = self.settings.ollama_fallback_model

        # Small local models often underperform for Indic languages; try the fallback model first there.
        if self._is_non_english_target(response_language):
            primary_model, secondary_model = secondary_model, primary_model

        try:
            response = await self.ollama_client.generate(
                text,
                model=primary_model,
                timeout_s=self.settings.ollama_timeout_s,
                response_language=response_language,
            )
            return response, "ollama"
        except Exception:
            try:
                fallback_response = await self.ollama_client.generate(
                    text,
                    model=secondary_model,
                    timeout_s=self.settings.ollama_timeout_s,
                    response_language=response_language,
                )
                return fallback_response, "ollama"
            except Exception:
                return (
                    "Offline model is unavailable right now. Please try online mode.",
                    "ollama",
                )

    async def _online_primary_with_local_fallback(
        self,
        text: str,
        history: list[dict[str, str]] | None,
        response_language: str | None = None,
    ) -> tuple[str, RouteSource]:
        """
        Smart mode: Gemini Flash 2.0 (cloud) primary with automatic Gemma E2B (local) fallback.
        
        Strategy:
        - Try Gemini Flash 2.0 via OpenRouter first (best quality + fastest for short queries)
        - If cloud timeout/error occurs, immediately fall back to local Gemma E2B
        - Never wait for cloud if it's slow; respond fast with local model instead
        
        This gives you cloud-quality responses when available, but never breaks on cloud outages.
        """
        try:
            # Attempt Gemini Flash 2.0 (cloud) first with strict timeout
            response = await asyncio.wait_for(
                self.openrouter_client.chat(text, history=history, response_language=response_language),
                timeout=self.settings.openrouter_timeout_s,
            )
            return response, "openrouter"
        except (asyncio.TimeoutError, httpx.HTTPError, RuntimeError):
            # Cloud failed or timed out; fall back to local Gemma E2B (Ollama)
            offline_response, _ = await self._offline_only(text, response_language=response_language)
            return offline_response, "ollama"

    async def _smart_route(
        self,
        text: str,
        history: list[dict[str, str]] | None,
        response_language: str | None = None,
    ) -> tuple[str, RouteSource]:
        return await self._online_primary_with_local_fallback(text, history, response_language=response_language)

    def _is_simple_query(self, text: str) -> bool:
        stripped = text.strip()
        words = stripped.split()
        if len(words) <= 10 and len(stripped) < 75:
            return True

        complexity_markers = re.compile(
            r"\b(compare|analyze|explain|architecture|optimize|design|code|debug|tradeoff|strategy)\b",
            flags=re.IGNORECASE,
        )
        if complexity_markers.search(stripped):
            return False

        sentence_count = stripped.count(".") + stripped.count("?") + stripped.count("!")
        return sentence_count <= 1 and len(words) <= 14

    def _is_language_refusal(self, text: str) -> bool:
        normalized = " ".join(text.strip().split())
        if not normalized:
            return False

        # Keep this check focused on short refusal templates to avoid false positives.
        if len(normalized) > 320:
            return False

        lowered = normalized.lower()

        if self._LANGUAGE_REFUSAL_RE.search(lowered):
            return True

        refusal_markers = (
            "i am sorry",
            "i'm sorry",
            "i do not understand",
            "i don't understand",
            "cannot understand",
            "can't understand",
            "only understand",
            "only respond",
            "cannot respond",
            "can't respond",
            "please speak",
            "please use",
        )

        has_refusal_marker = any(marker in lowered for marker in refusal_markers)
        if not has_refusal_marker:
            return False

        supported_language_names = ("english", "hindi", "tamil", "telugu", "malayalam")
        mentioned_languages = sum(1 for name in supported_language_names if name in lowered)

        return mentioned_languages >= 2

    async def _recover_from_language_refusal(
        self,
        text: str,
        source: RouteSource,
        history: list[dict[str, str]] | None,
        response_language: str | None,
    ) -> tuple[str, RouteSource] | None:
        if source == "ollama":
            try:
                response = await asyncio.wait_for(
                    self.openrouter_client.chat(text, history=history, response_language=response_language),
                    timeout=min(6.0, self.settings.openrouter_timeout_s),
                )
                if response and not self._is_language_refusal(response):
                    return response, "openrouter"
            except Exception:
                return None
            return None

        try:
            response = await asyncio.wait_for(
                self.ollama_client.generate(
                    text,
                    model=self.settings.ollama_model,
                    timeout_s=min(4.0, self.settings.ollama_timeout_s),
                    response_language=response_language,
                ),
                timeout=4.2,
            )
            if response and not self._is_language_refusal(response):
                return response, "ollama"
        except Exception:
            return None

        return None

    def _fallback_clarification(self, response_language: str | None) -> str:
        language_name = (response_language or "English").strip()
        return (
            "I could not catch that clearly from the audio. "
            f"Please say it again in a short sentence (I will respond in {language_name})."
        )

    def _is_non_english_target(self, response_language: str | None) -> bool:
        if not response_language:
            return False

        normalized = response_language.strip().lower()
        if not normalized:
            return False

        if normalized in {"en", "en-us", "en-gb", "english"}:
            return False

        return normalized in {"hi", "ta", "te", "ml", "hindi", "tamil", "telugu", "malayalam"}
