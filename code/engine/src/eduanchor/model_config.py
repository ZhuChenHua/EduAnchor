from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

PROVIDERS: dict[str, dict[str, Any]] = {
    "ollama": {
        "label": "Ollama (local)",
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "qwen3:8b",
        "requires_key": False,
        "local": True,
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "requires_key": True,
        "local": False,
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "requires_key": True,
        "local": False,
    },
    "dashscope": {
        "label": "Alibaba Cloud DashScope (Qwen)",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "requires_key": True,
        "local": False,
    },
    "moonshot": {
        "label": "Moonshot (Kimi)",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "requires_key": True,
        "local": False,
    },
    "siliconflow": {
        "label": "SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen3-8B",
        "requires_key": True,
        "local": False,
    },
    "custom": {
        "label": "Custom OpenAI-compatible endpoint",
        "base_url": "http://127.0.0.1:8000/v1",
        "model": "",
        "requires_key": False,
        "local": False,
    },
}

DEFAULT_PROVIDER = "ollama"
_ENV_KEYS = {
    "EDUANCHOR_LLM_PROVIDER": "provider",
    "EDUANCHOR_LLM_BASE_URL": "base_url",
    "EDUANCHOR_LLM_MODEL": "model",
    "EDUANCHOR_LLM_API_KEY": "api_key",
    "EDUANCHOR_LLM_TIMEOUT": "timeout",
}


def provider_info(provider: str) -> dict[str, Any]:
    return PROVIDERS.get(provider, PROVIDERS["custom"])


@dataclass(slots=True)
class ModelConfig:
    provider: str = DEFAULT_PROVIDER
    base_url: str = "http://127.0.0.1:11434/v1"
    model: str = "qwen3:8b"
    api_key: str = ""
    temperature: float = 0.2
    max_tokens: int = 900
    timeout: float = 180.0

    def __post_init__(self) -> None:
        if self.provider not in PROVIDERS:
            self.provider = "custom"
        if not self.base_url:
            self.base_url = provider_info(self.provider)["base_url"]
        if self.temperature < 0:
            self.temperature = 0.0
        self.max_tokens = max(self.max_tokens, 16)
        if self.timeout < 5:
            self.timeout = 5.0

    @property
    def is_local(self) -> bool:
        return self.provider == "ollama" or any(
            host in self.base_url for host in ("127.0.0.1", "localhost", "0.0.0.0")
        )

    @property
    def requires_key(self) -> bool:
        return bool(provider_info(self.provider).get("requires_key"))

    def public(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("api_key", None)
        payload["has_api_key"] = bool(self.api_key)
        payload["is_local"] = self.is_local
        payload["requires_key"] = self.requires_key
        return payload

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> ModelConfig:
        allowed = {field.name for field in fields(cls)}
        return cls(**{key: value for key, value in payload.items() if key in allowed})

    @classmethod
    def load(cls, data_dir: Path) -> ModelConfig:
        path = data_dir / "model.json"
        if path.exists():
            try:
                config = cls.from_mapping(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError):
                config = cls()
        else:
            config = cls()
        overridden = False
        for env_key, field_name in _ENV_KEYS.items():
            if env_key in os.environ and os.environ[env_key] != "":
                raw = os.environ[env_key]
                if field_name == "timeout":
                    try:
                        setattr(config, field_name, float(raw))
                    except ValueError:
                        continue
                else:
                    setattr(config, field_name, raw)
                overridden = True
        if overridden:
            config.__post_init__()
        return config

    def save(self, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / "model.json"
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def apply_preset(self, provider: str) -> ModelConfig:
        info = provider_info(provider)
        return ModelConfig(
            provider=provider,
            base_url=info["base_url"],
            model=info["model"],
            api_key=self.api_key,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
        )


def _models_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/models"


def _auth_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def probe_endpoint(config: ModelConfig, timeout: float = 2.5) -> bool:
    request = urllib.request.Request(
        _models_url(config.base_url),
        headers=_auth_headers(config.api_key),
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status < 500
    except urllib.error.HTTPError as exc:
        # A 404/405 means the host is reachable but does not expose /models;
        # many custom OpenAI-compatible servers behave this way.
        return exc.code not in (401, 403, 500, 502, 503, 504)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False
