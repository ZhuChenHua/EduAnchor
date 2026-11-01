from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

from .model_config import ModelConfig, probe_endpoint


class LLM:
    name = "extractive"
    available = False
    provider = "fallback"

    def chat(
        self,
        system: str,
        user: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        raise RuntimeError("LLM is not available")

    def test(self) -> dict:
        return {"ok": False, "message": "LLM is not configured", "latency_ms": 0.0}


class RemoteLLM(LLM):
    """Any OpenAI-compatible chat endpoint (local or remote)."""

    def __init__(self, config: ModelConfig, probe: bool = True) -> None:
        self.config = config
        self.name = config.model or config.provider
        self.provider = config.provider
        self.available = probe_endpoint(config) if probe else False

    def chat(
        self,
        system: str,
        user: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.config.base_url.rstrip('/')}/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key or 'eduanchor'}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        self.available = True
        return _strip_thinking(content)

    def test(self) -> dict:
        started = time.perf_counter()
        try:
            text = self.chat(
                "You are a health check. Reply with OK.",
                "Reply with OK.",
                temperature=0.0,
                max_tokens=16,
            )
            latency = round((time.perf_counter() - started) * 1000, 2)
            return {"ok": True, "message": text.strip()[:80] or "OK", "latency_ms": latency}
        except Exception as exc:  # noqa: BLE001 - surfaced to the settings UI
            latency = round((time.perf_counter() - started) * 1000, 2)
            return {"ok": False, "message": _friendly_error(exc), "latency_ms": latency}


class NullLLM(LLM):
    name = "extractive"
    available = False
    provider = "fallback"


def _strip_thinking(text: str) -> str:
    return re.sub(r" thinking.*?</think>", "", text, flags=re.DOTALL).strip()


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in (401, 403):
            return f"authentication failed (HTTP {exc.code}); check the API key"
        return f"provider returned HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return f"cannot reach endpoint: {exc.reason}"
    if isinstance(exc, TimeoutError):
        return "request timed out"
    return str(exc) or exc.__class__.__name__


def build_llm(config: ModelConfig) -> LLM:
    if not config.base_url or not config.model:
        return NullLLM()
    if config.requires_key and not config.api_key:
        return RemoteLLM(config, probe=False)
    return RemoteLLM(config, probe=True)


def test_model_config(config: ModelConfig) -> dict:
    return RemoteLLM(config, probe=False).test()
