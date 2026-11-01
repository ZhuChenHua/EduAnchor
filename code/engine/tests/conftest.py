from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def offline_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit tests deterministic even when a local model server is running."""
    monkeypatch.setenv("EDUANCHOR_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("EDUANCHOR_LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("EDUANCHOR_LLM_MODEL", "offline-test")
    monkeypatch.setenv("EDUANCHOR_EMBED_BACKEND", "hash")
