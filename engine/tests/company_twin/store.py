"""
회사 시스템 쌍둥이(엔진 시험 전용) — Company1 기간계(`legacy/`)의 HTTP 계약
(`docs/worker-interfaces.md` §4.2)을 같은 프로세스에서 흉내 낸다. 원본은 Company1 리포다.
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
            # 경영 기록은 세계 문서 밖에 둔다 — 문서 안에 두면 판마다·시계 이동마다 모든 기록(지난
            # 판 포함)을 다시 썼다(NowView 3단계 실측, 판 하나 약 0.1초에서 갈수록 늘었다).
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS record (world_id TEXT NOT NULL, key TEXT NOT NULL, "
                "seq INTEGER NOT NULL, scene INTEGER NOT NULL, doc TEXT NOT NULL, "
                "PRIMARY KEY (world_id, key))"
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

    def records(self, world_id: str, scene: int | None = None) -> dict[str, dict[str, Any]]:
        sql = "SELECT key, doc FROM record WHERE world_id = ?"
        args: tuple[Any, ...] = (world_id,)
        if scene is not None:
            sql, args = sql + " AND scene = ?", (world_id, scene)
        with self._lock:
            rows = self._db.execute(sql, args).fetchall()
        return {k: json.loads(d) for k, d in rows}

    def record(self, world_id: str, key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT doc FROM record WHERE world_id = ? AND key = ?", (world_id, key)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def max_record_seq(self, world_id: str) -> int:
        with self._lock:
            row = self._db.execute(
                "SELECT MAX(seq) FROM record WHERE world_id = ?", (world_id,)
            ).fetchone()
        return row[0] or 0

    def put_records(self, world_id: str, records: dict[str, dict[str, Any]]) -> None:
        """기록 여럿을 한 트랜잭션으로(전부 또는 하나도)."""
        if not records:
            return
        rows = [
            (world_id, k, r["seq"], r["scene"], json.dumps(r, ensure_ascii=False))
            for k, r in records.items()
        ]
        with self._lock:
            self._db.executemany(
                "INSERT INTO record (world_id, key, seq, scene, doc) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(world_id, key) DO UPDATE SET doc = excluded.doc",
                rows,
            )
            self._db.commit()

    def delete_records(self, world_id: str, scene: int | None = None) -> int:
        """그 세계의(장면을 주면 그 장면의) 기록을 지운다 — 지운 개수."""
        sql, args = "DELETE FROM record WHERE world_id = ?", (world_id,)
        if scene is not None:
            sql, args = sql + " AND scene = ?", (world_id, scene)
        with self._lock:
            n = self._db.execute(sql, args).rowcount
            self._db.commit()
        return n

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM world").fetchone()[0]

    def lock(self) -> threading.RLock:
        """읽고-바꾸고-쓰기를 한 번에 — 수신 번호가 겹치지 않게."""
        return self._mutate
