"""
Center 실행의 각본 한 단계 — 앞 결재의 기록 작업을 기다린다(장면 3~5).

대리 답은 Center 결재를 닫을 뿐이고, 그 뒤의 기록 작업(회의 열기·배정·인수…)은 서버
실행기가 따로 부른다. 각본이 곧바로 다음 단계를 넣으면 그 기록보다 먼저 들어가 「진행 중인
회의가 없다」·「본 배정버전(0)이 최신(1)이 아니다」(409)·「미인수」(완료 조건 422)였다
(장면 3 로컬 Center 실측). 그래서 Center 실행이면 그 거절을 `center_wait_s`까지 다시 해
보고, 그래도 거절이면 그 사유를 낸다. 화면에서 사람이 누를 때는 이 대기가 없다 — 거절
사유가 그대로 보인다.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from app.sc01.domain import DomainError


def after_record(
    wait_s: float,
    center: bool,
    run: Callable[[], dict],
    *,
    gated: tuple[type[DomainError], ...] = (),
) -> dict:
    """`run`을 한다. Center 실행이면 409와 `gated`(요건 미충족 422)를 `wait_s`까지 다시 해 본다."""
    deadline = time.monotonic() + (wait_s if center else 0)
    while True:
        try:
            return run()
        except DomainError as exc:
            waiting = exc.status == 409 or isinstance(exc, gated)
            if not waiting or time.monotonic() >= deadline:
                raise
        time.sleep(min(1.0, wait_s))
