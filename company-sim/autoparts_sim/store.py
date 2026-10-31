"""
세계(world) 저장소 — 시연을 처음부터 다시 돌릴 수 있게 회사의 **변하는 기록**만 세계마다 따로 둔다:
세계 시각, 고객 생산계획 수신함(받은 원천과 그 확인 상태), 상태 이력. 세계 id = NowView 데모 실행
id다(`docs/worker-interfaces.md` Q1).

세계 하나 = JSON 문서 하나(SQLite 행 하나). 같은 파일을 여러 스레드가 쓰므로 잠금으로 줄
세운다(NowView 엔진 SC01 저장소와 같은 이유).
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "sim-state.sqlite"


class WorldStore:
    def __init__(self, path: str | Path | None = None) -> None:
        where = str(path or os.getenv("AUTOPARTS_SIM_DB") or DEFAULT_PATH)
        self._db = sqlite3.connect(where, check_same_thread=False)
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
