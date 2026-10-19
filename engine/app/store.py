"""
저장 백엔드 — SQLite(로컬) / PostgreSQL(운영).

**둘을 함께 두는 이유.** 로컬 개발에서 DB를 띄우라고 요구하면 "엔진 없이도 앱이 뜬다"는
마찰 없는 시작이 깨진다. `DATABASE_URL`이 있으면 Postgres, 없으면 파일 SQLite를 쓴다 —
켜는 쪽이 선택이고 기본값은 마찰이 없는 쪽이다.

**SQLite로는 운영할 수 없다.** 여러 워커·인스턴스로 띄우면 각자 다른 파일을 보거나 쓰기가
잠긴다. 그래서 docker-compose·CI·운영계는 Postgres를 쓴다.

여기서는 **연결만** 준비한다. 테이블은 쓰는 쪽이 만든다(`sc01/store.py`) — 예전에는
LangGraph 체크포인터가 이 자리를 차지했지만 BPM이 Chaeksas로 바뀌며 걷어냈다.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_SQLITE_PATH = "engine-state.sqlite"


@dataclass
class Backend:
    kind: str  # sqlite | postgres
    #: 사람이 읽는 설명. `/health`에 그대로 싣는다 — 어느 백엔드로 돌고 있는지 알 수 없으면
    #: "SQLite로 운영에 올렸다"를 눈치챌 방법이 없다. 자격증명은 들어 있지 않다.
    describe: str
    #: SQLite 파일 경로. 저장소가 **자기 연결**을 연다(연결을 나누면 잠금이 서로를 모른다).
    sqlite_path: str | None = None
    #: Postgres 연결 풀. `autocommit=True`·`dict_row` — 저장소가 컬럼 이름으로 읽는다.
    pool: Any = None

    def close(self) -> None:
        if self.pool is not None:
            self.pool.close()


def build_sqlite_backend(path: str = DEFAULT_SQLITE_PATH) -> Backend:
    return Backend("sqlite", f"sqlite:{path}", sqlite_path=path)


def build_postgres_backend(url: str, *, max_size: int = 10) -> Backend:
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(
        url,
        min_size=1,
        max_size=max_size,
        open=True,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )
    # 자격증명이 로그·응답에 새지 않도록 호스트만 남긴다.
    return Backend("postgres", f"postgres:{_safe_host(url)}", pool=pool)


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
    운영에 올렸는데 DB가 안 붙었다면 그 사실이 즉시 드러나야 한다. 조용히 파일로 떨어지면
    데모 실행이 워커마다 갈라진 채로 돈다.
    """
    url = os.getenv("DATABASE_URL")
    if url:
        log.info("Postgres 백엔드로 시작한다: %s", _safe_host(url))
        return build_postgres_backend(url)
    path = os.getenv("NOWVIEW_ENGINE_DB", DEFAULT_SQLITE_PATH)
    log.info("SQLite 백엔드로 시작한다: %s (운영에는 부적합)", path)
    return build_sqlite_backend(path)
