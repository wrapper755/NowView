"""
회사 시스템 쌍둥이(엔진 시험 전용) — autopart1 기간계(`legacy/`)의 HTTP 계약
(`docs/worker-interfaces.md` §4.2)을 같은 프로세스에서 흉내 낸다. 원본은 autopart1 리포다.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


class WorldStore:
    def __init__(self, path: str | Path) -> None:
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        self._mutate = threading.RLock()
        with self._lock:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS world (id TEXT PRIMARY KEY, doc TEXT NOT NULL)"
            )
            self._db.commit()

    def get(self, world_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT doc FROM world WHERE id = ?", (world_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, doc: dict[str, Any]) -> None:
        body = json.dumps(doc, ensure_ascii=False)
        with self._lock:
            self._db.execute(
                "INSERT INTO world (id, doc) VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET doc = excluded.doc",
                (doc["world_id"], body),
            )
            self._db.commit()

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM world").fetchone()[0]

    def lock(self) -> threading.RLock:
        """읽고-바꾸고-쓰기를 한 번에 — 수신 번호가 겹치지 않게."""
        return self._mutate
