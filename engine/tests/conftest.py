"""
테스트 고정물 — 두 저장 백엔드를 고르는 규칙.

**`REQUIRE_POSTGRES`가 켜져 있으면 건너뛰지 않고 실패한다.** CI에서 환경 변수 이름을
오타내면 Postgres 테스트가 전부 skip되는데, 초록색 체크만 보고는 "검증했다"와
"건너뛰었다"를 구분할 수 없다. 조용한 미검증이 가장 나쁘다.
"""

from __future__ import annotations

import os

import pytest


def postgres_url() -> str | None:
    return os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


def require_postgres() -> str:
    """Postgres URL을 돌려주거나, 없으면 건너뛴다(REQUIRE_POSTGRES면 실패)."""
    url = postgres_url()
    if url:
        return url
    if os.getenv("REQUIRE_POSTGRES"):
        pytest.fail("REQUIRE_POSTGRES가 켜져 있는데 TEST_DATABASE_URL이 없다")
    pytest.skip("TEST_DATABASE_URL이 없다 (Postgres 백엔드 검증 생략)")
