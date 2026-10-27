"""
SC01 데모 실행 저장 — 문서 한 행 + 이력.

* `sc01_demo_run` — 현재 문서. `row_version`으로 낙관적 잠금을 건다: 오래된 화면이나 다른
  워커가 먼저 쓴 뒤의 쓰기는 409다(ERR-04). 워커 안의 잠금만으로는 워커 사이가 막히지 않는다.
* `sc01_history` — 상태가 바뀔 때마다 문서 전체를 남긴다. 지난 시점 보기(되감기)는 이것을
  **읽기만** 한다 — Chaeksas 스냅샷은 현재 하나뿐이라 지난 시점이 따로 남지 않는다.

백엔드는 기존 엔진 저장소와 같은 DB를 쓴다(SQLite 파일 하나 / Postgres 풀).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any, Protocol


class StaleWrite(Exception):
    """기대한 row_version이 아니다 — 누가 먼저 썼다."""


class Sc01Store(Protocol):
    def insert(self, demo_run_id: str, doc: dict) -> None: ...
    def load(self, demo_run_id: str) -> tuple[dict, int] | None: ...
    def save(self, demo_run_id: str, doc: dict, expected: int, event: str) -> int: ...
    def history(self, demo_run_id: str) -> list[dict[str, Any]]: ...
    def at(self, demo_run_id: str, seq: int) -> dict | None: ...
    def list(self) -> list[dict[str, Any]]: ...
    def running_external(self, executor: str) -> list[str]: ...


def _sqlite_ddl(p: str) -> list[str]:
    return [
        f"""CREATE TABLE IF NOT EXISTS {p}_demo_run (
             id TEXT PRIMARY KEY, doc TEXT NOT NULL, row_version INTEGER NOT NULL,
             created_at TEXT DEFAULT CURRENT_TIMESTAMP)""",
        f"""CREATE TABLE IF NOT EXISTS {p}_history (
             demo_run_id TEXT NOT NULL, seq INTEGER NOT NULL, event TEXT NOT NULL,
             clock TEXT NOT NULL, doc TEXT NOT NULL, PRIMARY KEY (demo_run_id, seq))""",
    ]


def _postgres_ddl(p: str) -> list[str]:
    return [
        f"""CREATE TABLE IF NOT EXISTS {p}_demo_run (
             id TEXT PRIMARY KEY, doc JSONB NOT NULL, row_version INTEGER NOT NULL,
             created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
        f"""CREATE TABLE IF NOT EXISTS {p}_history (
             demo_run_id TEXT NOT NULL, seq INTEGER NOT NULL, event TEXT NOT NULL,
             clock TEXT NOT NULL, doc JSONB NOT NULL, PRIMARY KEY (demo_run_id, seq))""",
    ]


# : 장면마다 테이블 쌍이 따로다(`sc01_*` ~ `sc05_*`). 고정된 식별자만 받는다 — SQL에 그대로
# 들어간다.
PREFIXES = ("sc01", "sc02", "sc03", "sc04", "sc05")


def _prefix(value: str) -> str:
    if value not in PREFIXES:
        raise ValueError(f"모르는 저장 접두어: {value}")
    return value


def _index(value: Any) -> int:
    """각본 진행 지점. 아직 각본을 타지 않은 문서(S0·수동 조작)는 -1이다."""
    return -1 if value is None else int(value)


class SqliteSc01Store:
    """
    **연결 하나를 잠금으로 줄 세운다.** FastAPI 동기 엔드포인트는 스레드풀에서 돌고 SSE도
    스레드풀에서 읽는다 — `check_same_thread=False` 연결을 잠금 없이 나눠 쓰면 쓰는 도중의
    읽기가 빈 행을 받는다. 실제로 SSE 스트림이 그렇게 죽었다(`json.loads(None)`).
    LangGraph 체크포인터와도 연결을 나누지 않는다 — 그쪽은 자기 잠금을 따로 쥔다.
    """

    def __init__(self, conn: sqlite3.Connection, prefix: str = "sc01") -> None:
        self.conn = conn
        self.p = _prefix(prefix)
        self._lock = threading.Lock()
        with self._lock:
            for ddl in _sqlite_ddl(self.p):
                conn.execute(ddl)
            conn.commit()

    def insert(self, demo_run_id: str, doc: dict) -> None:
        body = json.dumps(doc, ensure_ascii=False)
        with self._lock:
            self.conn.execute(
                f"INSERT INTO {self.p}_demo_run (id, doc, row_version) VALUES (?,?,1)",
                (demo_run_id, body),
            )
            self.conn.execute(
                f"INSERT INTO {self.p}_history VALUES (?,1,?,?,?)",
                (demo_run_id, doc["step"], doc["clock"], body),
            )
            self.conn.commit()

    def load(self, demo_run_id: str) -> tuple[dict, int] | None:
        with self._lock:
            row = self.conn.execute(
                f"SELECT doc, row_version FROM {self.p}_demo_run WHERE id = ?", (demo_run_id,)
            ).fetchone()
        return (json.loads(row[0]), row[1]) if row else None

    def save(self, demo_run_id: str, doc: dict, expected: int, event: str) -> int:
        body = json.dumps(doc, ensure_ascii=False)
        with self._lock:
            cur = self.conn.execute(
                f"UPDATE {self.p}_demo_run SET doc = ?, row_version = row_version + 1 "
                "WHERE id = ? AND row_version = ?",
                (body, demo_run_id, expected),
            )
            if cur.rowcount != 1:
                self.conn.rollback()
                raise StaleWrite(demo_run_id)
            self.conn.execute(
                f"INSERT INTO {self.p}_history VALUES (?,?,?,?,?)",
                (demo_run_id, expected + 1, event, doc["clock"], body),
            )
            self.conn.commit()
        return expected + 1

    def history(self, demo_run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT seq, event, clock, json_extract(doc, '$.script_index') "
                f"FROM {self.p}_history WHERE demo_run_id = ? ORDER BY seq",
                (demo_run_id,),
            ).fetchall()
        return [
            {"seq": r[0], "event": r[1], "clock": r[2], "scriptIndex": _index(r[3])} for r in rows
        ]

    def at(self, demo_run_id: str, seq: int) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                f"SELECT doc FROM {self.p}_history WHERE demo_run_id = ? AND seq = ?",
                (demo_run_id, seq),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(
                f"SELECT id, row_version, created_at FROM {self.p}_demo_run "
                "ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [{"demoRunId": r[0], "rowVersion": r[1], "createdAt": str(r[2])} for r in rows]

    def running_external(self, executor: str) -> list[str]:
        """그 실행 위치에서 **도는** 데모 실행 id — Center 폴링이 문서를 다 읽지 않게(N3)."""
        with self._lock:
            rows = self.conn.execute(
                f"SELECT id FROM {self.p}_demo_run WHERE json_extract(doc, '$.bpm.executor') = ? "
                "AND json_extract(doc, '$.bpm.state') = 'running'",
                (executor,),
            ).fetchall()
        return [r[0] for r in rows]


class PostgresSc01Store:
    def __init__(self, pool: Any, prefix: str = "sc01") -> None:
        self.pool = pool
        self.p = _prefix(prefix)
        with pool.connection() as conn:
            for ddl in _postgres_ddl(self.p):
                conn.execute(ddl)

    def insert(self, demo_run_id: str, doc: dict) -> None:
        from psycopg.types.json import Jsonb

        with self.pool.connection() as conn, conn.transaction():
            conn.execute(
                f"INSERT INTO {self.p}_demo_run (id, doc, row_version) VALUES (%s,%s,1)",
                (demo_run_id, Jsonb(doc)),
            )
            conn.execute(
                f"INSERT INTO {self.p}_history VALUES (%s,1,%s,%s,%s)",
                (demo_run_id, doc["step"], doc["clock"], Jsonb(doc)),
            )

    def load(self, demo_run_id: str) -> tuple[dict, int] | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                f"SELECT doc, row_version FROM {self.p}_demo_run WHERE id = %s", (demo_run_id,)
            ).fetchone()
        return (row["doc"], row["row_version"]) if row else None

    def save(self, demo_run_id: str, doc: dict, expected: int, event: str) -> int:
        from psycopg.types.json import Jsonb

        # 풀이 autocommit이라 문서와 이력을 한 트랜잭션으로 묶는다.
        with self.pool.connection() as conn, conn.transaction():
            cur = conn.execute(
                f"UPDATE {self.p}_demo_run SET doc = %s, row_version = row_version + 1 "
                "WHERE id = %s AND row_version = %s",
                (Jsonb(doc), demo_run_id, expected),
            )
            if cur.rowcount != 1:
                raise StaleWrite(demo_run_id)
            conn.execute(
                f"INSERT INTO {self.p}_history VALUES (%s,%s,%s,%s,%s)",
                (demo_run_id, expected + 1, event, doc["clock"], Jsonb(doc)),
            )
        return expected + 1

    def history(self, demo_run_id: str) -> list[dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT seq, event, clock, doc->>'script_index' AS script_index "
                f"FROM {self.p}_history WHERE demo_run_id = %s ORDER BY seq",
                (demo_run_id,),
            ).fetchall()
        return [
            {
                "seq": r["seq"],
                "event": r["event"],
                "clock": r["clock"],
                "scriptIndex": _index(r["script_index"]),
            }
            for r in rows
        ]

    def at(self, demo_run_id: str, seq: int) -> dict | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                f"SELECT doc FROM {self.p}_history WHERE demo_run_id = %s AND seq = %s",
                (demo_run_id, seq),
            ).fetchone()
        return row["doc"] if row else None

    def list(self) -> list[dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                f"SELECT id, row_version, created_at FROM {self.p}_demo_run "
                "ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [
            {
                "demoRunId": r["id"],
                "rowVersion": r["row_version"],
                "createdAt": r["created_at"].isoformat(),
            }
            for r in rows
        ]

    def running_external(self, executor: str) -> list[str]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                f"SELECT id FROM {self.p}_demo_run WHERE doc->'bpm'->>'executor' = %s "
                "AND doc->'bpm'->>'state' = 'running'",
                (executor,),
            ).fetchall()
        return [r["id"] for r in rows]


def build_sc01_store(backend: Any, prefix: str = "sc01") -> Sc01Store:
    """엔진 백엔드와 같은 DB를 쓴다 — 파일·DB가 둘로 갈리면 한쪽만 지워지는 상태가 생긴다."""
    if backend.kind == "postgres":
        return PostgresSc01Store(backend.pool, prefix)
    # 같은 파일, **다른 연결**이다 — 연결을 나누면 체크포인터의 잠금과 우리 잠금이 서로를 모른다.
    return SqliteSc01Store(sqlite3.connect(backend.sqlite_path, check_same_thread=False), prefix)
