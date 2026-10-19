"""
상태 저장 백엔드 — SQLite(로컬) / PostgreSQL(운영).

**둘을 함께 두는 이유.** 로컬 개발에서 DB를 띄우라고 요구하면 "엔진이 없어도 앱은
전부 동작한다"는 성질이 깨진다. `DATABASE_URL`이 있으면 Postgres, 없으면 파일
SQLite를 쓴다 — 켜는 쪽이 선택이고 기본값은 마찰이 없는 쪽이다.

**SQLite로는 운영할 수 없다.** 여러 워커·인스턴스로 띄우면 각자 다른 파일을 보거나
쓰기가 잠긴다. 그래서 docker-compose와 CI는 Postgres를 쓴다.

저장할 것이 둘이다:
* **체크포인트** — LangGraph가 소유한다(`checkpoint*` 테이블, `setup()`이 만든다).
* **프로세스 명세** — 우리가 소유한다(`instance_spec`). 체크포인트만 남기면 재시작
  후 그래프를 다시 조립할 수 없어 진행 중인 인스턴스가 되살아나지 않는다.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from langgraph.checkpoint.base import BaseCheckpointSaver

log = logging.getLogger(__name__)

DEFAULT_SQLITE_PATH = "engine-state.sqlite"

_CREATE_SQLITE = """
CREATE TABLE IF NOT EXISTS instance_spec (
  id          TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  spec        TEXT NOT NULL,
  agent_mode  TEXT NOT NULL,
  created_at  TEXT DEFAULT CURRENT_TIMESTAMP
)
"""

_CREATE_POSTGRES = """
CREATE TABLE IF NOT EXISTS instance_spec (
  id          TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL,
  spec        TEXT NOT NULL,
  agent_mode  TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def _as_iso(value: Any) -> str:
    """
    `created_at`을 두 백엔드에서 같은 모양으로 돌려준다.

    SQLite는 문자열을, Postgres는 datetime을 준다 — 경계에서 맞추지 않으면 JSON
    직렬화 결과가 백엔드에 따라 갈린다.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class SpecStore(Protocol):
    def save(self, instance_id: str, scenario_id: str, spec_json: str, agent_mode: str) -> None: ...
    def load(self, instance_id: str) -> tuple[str, str] | None: ...
    def list(self) -> list[dict[str, str]]: ...
    def delete(self, instance_id: str) -> None: ...
    def close(self) -> None: ...


class SqliteSpecStore:
    def __init__(self, path: str) -> None:
        # check_same_thread=False — FastAPI의 동기 엔드포인트는 스레드풀에서 돈다.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute(_CREATE_SQLITE)
        self.conn.commit()

    def save(self, instance_id: str, scenario_id: str, spec_json: str, agent_mode: str) -> None:
        self.conn.execute(
            "INSERT INTO instance_spec (id, scenario_id, spec, agent_mode) VALUES (?,?,?,?)",
            (instance_id, scenario_id, spec_json, agent_mode),
        )
        self.conn.commit()

    def load(self, instance_id: str) -> tuple[str, str] | None:
        row = self.conn.execute(
            "SELECT spec, agent_mode FROM instance_spec WHERE id = ?", (instance_id,)
        ).fetchone()
        return (row[0], row[1]) if row else None

    def list(self) -> list[dict[str, str]]:
        rows = self.conn.execute(
            "SELECT id, scenario_id, agent_mode, created_at FROM instance_spec "
            "ORDER BY created_at DESC, id DESC"
        ).fetchall()
        return [
            {"instanceId": r[0], "scenarioId": r[1], "agentMode": r[2], "createdAt": _as_iso(r[3])}
            for r in rows
        ]

    def delete(self, instance_id: str) -> None:
        self.conn.execute("DELETE FROM instance_spec WHERE id = ?", (instance_id,))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


class PostgresSpecStore:
    def __init__(self, pool: Any) -> None:
        self.pool = pool
        with self.pool.connection() as conn:
            conn.execute(_CREATE_POSTGRES)

    def save(self, instance_id: str, scenario_id: str, spec_json: str, agent_mode: str) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO instance_spec (id, scenario_id, spec, agent_mode) "
                "VALUES (%s,%s,%s,%s)",
                (instance_id, scenario_id, spec_json, agent_mode),
            )

    def load(self, instance_id: str) -> tuple[str, str] | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT spec, agent_mode FROM instance_spec WHERE id = %s", (instance_id,)
            ).fetchone()
        # 풀 연결이 dict_row라 컬럼 이름으로 읽는다 (PostgresSaver가 요구하는 설정이다).
        return (row["spec"], row["agent_mode"]) if row else None

    def list(self) -> list[dict[str, str]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, scenario_id, agent_mode, created_at FROM instance_spec "
                "ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [
            {
                "instanceId": r["id"],
                "scenarioId": r["scenario_id"],
                "agentMode": r["agent_mode"],
                "createdAt": _as_iso(r["created_at"]),
            }
            for r in rows
        ]

    def delete(self, instance_id: str) -> None:
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM instance_spec WHERE id = %s", (instance_id,))

    def close(self) -> None:
        self.pool.close()


@dataclass
class Backend:
    kind: str
    checkpointer: BaseCheckpointSaver
    specs: SpecStore
    #: 사람이 읽는 설명. `/health`에 그대로 싣는다 — 어느 백엔드로 돌고 있는지
    #: 알 수 없으면 "SQLite로 운영에 올렸다"를 눈치챌 방법이 없다.
    describe: str
    #: SQLite 파일 경로. 다른 저장소가 **같은 파일에 자기 연결**을 열 때 쓴다(sc01/store.py).
    sqlite_path: str | None = None

    def close(self) -> None:
        self.specs.close()


def build_sqlite_backend(path: str = DEFAULT_SQLITE_PATH) -> Backend:
    from langgraph.checkpoint.sqlite import SqliteSaver

    specs = SqliteSpecStore(path)
    # 체크포인터와 명세가 같은 연결을 쓴다 — 파일이 둘로 갈리면 한쪽만 지워지는 상태가 생긴다.
    checkpointer = SqliteSaver(specs.conn)
    checkpointer.setup()
    return Backend("sqlite", checkpointer, specs, f"sqlite:{path}", sqlite_path=path)


def build_postgres_backend(url: str, *, max_size: int = 10) -> Backend:
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    # **autocommit=True와 row_factory=dict_row는 PostgresSaver의 요구사항이다.**
    # 빠뜨리면 setup()이나 첫 쓰기에서 터진다 — 문서에만 있고 타입으로는 드러나지 않는다.
    pool = ConnectionPool(
        url,
        min_size=1,
        max_size=max_size,
        open=True,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    specs = PostgresSpecStore(pool)
    # 자격증명이 로그·응답에 새지 않도록 호스트만 남긴다.
    return Backend("postgres", checkpointer, specs, f"postgres:{_safe_host(url)}")


def _safe_host(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or "?"
    port = f":{parsed.port}" if parsed.port else ""
    database = parsed.path.lstrip("/") or "?"
    return f"{host}{port}/{database}"


def build_backend() -> Backend:
    """
    환경에서 백엔드를 고른다.

    `DATABASE_URL`이 있으면 Postgres다. **연결 실패를 SQLite로 조용히 되돌리지 않는다** —
    운영에 올렸는데 DB가 안 붙었다면 그 사실이 즉시 드러나야 한다. 조용히 파일로
    떨어지면 인스턴스가 워커마다 갈라진 채로 돈다.
    """
    url = os.getenv("DATABASE_URL")
    if url:
        log.info("Postgres 백엔드로 시작한다: %s", _safe_host(url))
        return build_postgres_backend(url)
    path = os.getenv("NOWVIEW_ENGINE_DB", DEFAULT_SQLITE_PATH)
    log.info("SQLite 백엔드로 시작한다: %s (운영에는 부적합)", path)
    return build_sqlite_backend(path)
