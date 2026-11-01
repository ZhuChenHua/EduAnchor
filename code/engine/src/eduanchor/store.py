from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from .config import Settings
from .schemas import Answer, Chunk, Document, KnowledgeCard


class Store:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.ensure_dirs()
        self.path = settings.db_path
        self.init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id, ordinal);
                CREATE TABLE IF NOT EXISTS cards (
                    id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_cards_doc ON cards(doc_id, ordinal);
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_doc ON sessions(doc_id, created_at DESC);
                """
            )

    def save_document(self, document: Document, chunks: list[Chunk], cards: list[KnowledgeCard]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO documents(id, title, created_at, payload) VALUES (?,?,?,?)",
                (document.id, document.title, document.created_at, document.model_dump_json()),
            )
            conn.execute("DELETE FROM chunks WHERE doc_id=?", (document.id,))
            conn.execute("DELETE FROM cards WHERE doc_id=?", (document.id,))
            conn.executemany(
                "INSERT INTO chunks(id, doc_id, ordinal, payload) VALUES (?,?,?,?)",
                [
                    (chunk.id, chunk.doc_id, chunk.ordinal, chunk.model_dump_json())
                    for chunk in chunks
                ],
            )
            conn.executemany(
                "INSERT INTO cards(id, doc_id, ordinal, payload) VALUES (?,?,?,?)",
                [
                    (card.id, card.doc_id, index, card.model_dump_json())
                    for index, card in enumerate(cards)
                ],
            )
            conn.commit()

    def list_documents(self) -> list[Document]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM documents ORDER BY created_at DESC").fetchall()
        return [Document.model_validate_json(row["payload"]) for row in rows]

    def get_document(self, doc_id: str) -> Document | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM documents WHERE id=?", (doc_id,)).fetchone()
        return Document.model_validate_json(row["payload"]) if row else None

    def list_chunks(self, doc_id: str) -> list[Chunk]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM chunks WHERE doc_id=? ORDER BY ordinal", (doc_id,)
            ).fetchall()
        return [Chunk.model_validate_json(row["payload"]) for row in rows]

    def list_cards(self, doc_id: str) -> list[KnowledgeCard]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM cards WHERE doc_id=? ORDER BY ordinal", (doc_id,)
            ).fetchall()
        return [KnowledgeCard.model_validate_json(row["payload"]) for row in rows]

    def delete_document(self, doc_id: str) -> None:
        with self._connect() as conn:
            for table in ("documents", "chunks", "cards", "sessions"):
                conn.execute(f"DELETE FROM {table} WHERE {'id' if table == 'documents' else 'doc_id'}=?", (doc_id,))
            conn.commit()
        vector_path = self.settings.index_dir / f"{doc_id}.npz"
        if vector_path.exists():
            vector_path.unlink()

    def save_vectors(
        self, doc_id: str, chunk_ids: list[str], matrix: np.ndarray, backend: str
    ) -> None:
        path = self.settings.index_dir / f"{doc_id}.npz"
        np.savez_compressed(
            path,
            ids=np.array(chunk_ids),
            vectors=matrix.astype(np.float32),
            backend=np.array(backend),
        )

    def load_vectors(self, doc_id: str) -> tuple[list[str], np.ndarray, str] | None:
        path = self.settings.index_dir / f"{doc_id}.npz"
        if not path.exists():
            return None
        data = np.load(path, allow_pickle=False)
        backend = str(data["backend"].tolist()) if "backend" in data.files else ""
        return (
            [str(value) for value in data["ids"].tolist()],
            data["vectors"].astype(np.float32),
            backend,
        )

    def save_session(self, answer: Answer) -> None:
        if not answer.session_id:
            return
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions(id, doc_id, created_at, payload) VALUES (?,?,?,?)",
                (
                    answer.session_id,
                    answer.doc_id,
                    answer.created_at,
                    answer.model_dump_json(),
                ),
            )
            conn.commit()

    def list_sessions(self, doc_id: str | None = None, limit: int = 30) -> list[Answer]:
        with self._connect() as conn:
            if doc_id:
                rows = conn.execute(
                    "SELECT payload FROM sessions WHERE doc_id=? ORDER BY rowid DESC LIMIT ?",
                    (doc_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT payload FROM sessions ORDER BY rowid DESC LIMIT ?", (limit,)
                ).fetchall()
        return [Answer.model_validate_json(row["payload"]) for row in rows]

    def count(self) -> dict[str, int]:
        with self._connect() as conn:
            return {
                "documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
                "chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
                "cards": conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0],
                "sessions": conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
            }


def vector_path(settings: Settings, doc_id: str) -> Path:
    return settings.index_dir / f"{doc_id}.npz"
