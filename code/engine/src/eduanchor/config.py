from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_data_dir() -> Path:
    raw = os.environ.get("EDUANCHOR_DATA_DIR")
    if raw:
        return Path(raw).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "EduAnchor"
    return Path.home() / ".eduanchor"


@dataclass(slots=True)
class Settings:
    data_dir: Path = field(default_factory=_default_data_dir)
    embed_backend: str = field(
        default_factory=lambda: os.environ.get("EDUANCHOR_EMBED_BACKEND", "auto")
    )
    embed_model_path: str = field(
        default_factory=lambda: os.environ.get("EDUANCHOR_EMBED_MODEL", "BAAI/bge-m3")
    )
    rerank_model_path: str = field(
        default_factory=lambda: os.environ.get("EDUANCHOR_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    )
    top_k: int = 6
    chunk_chars: int = 520
    chunk_overlap: int = 80
    coverage_threshold: float = field(
        default_factory=lambda: float(os.environ.get("EDUANCHOR_COVERAGE_THRESHOLD", "0.15"))
    )
    support_threshold: float = 0.45
    temperature: float = field(
        default_factory=lambda: float(os.environ.get("EDUANCHOR_TEMPERATURE", "0.15"))
    )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "eduanchor.sqlite3"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    @property
    def session_dir(self) -> Path:
        return self.data_dir / "sessions"

    def ensure_dirs(self) -> None:
        for directory in (self.data_dir, self.index_dir, self.session_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def describe(self) -> dict:
        return {
            "data_dir": str(self.data_dir),
            "embed_backend": self.embed_backend,
            "embed_model": self.embed_model_path,
            "top_k": self.top_k,
        }


def package_data_dir() -> Path:
    """Locate bundled data both in the source tree and in a PyInstaller bundle."""
    import sys

    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        candidate = base / "eduanchor" / "data"
        return candidate if candidate.exists() else base / "data"
    return Path(__file__).resolve().parent / "data"


def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings

