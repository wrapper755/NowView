"""
Center 진행 폴러(N3) — 도는 center 데모 실행의 실행 기록을 2초마다 읽는다.

Center에는 바깥으로 쏘는 길이 없다(요청서 R3 거절 — 연결은 클라이언트가 먼저 건다, ADR-0007).
그래서 엔진이 묻는다. 바뀐 것은 `Sc01Process.sync_center`가 저장하고 기존 notifier로 SSE를 낸다 —
화면은 내장 실행과 같은 길로 받는다.

**연동용 키가 없으면 돌지 않는다**(물을 수 없다). 여러 워커면 워커마다 돈다 — 같은 기록을 읽어
같은 결과를 쓰고, 부딪히면 `row_version`이 한쪽을 409로 돌려보내 다음 주기에 다시 본다.
"""

from __future__ import annotations

import logging
import threading

from app.sc01.process import Sc01Process

log = logging.getLogger(__name__)

INTERVAL_S = 2.0


class CenterPoller:
    def __init__(self, process: Sc01Process, *, interval_s: float = INTERVAL_S) -> None:
        self.process = process
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        if self.process.center.config.missing(integration=True):
            log.info("Center 연동 설정이 없어 진행 폴러를 띄우지 않는다")
            return
        self._stop.clear()
        # 데몬 — 종료가 폴링 한 주기(최대 HTTP 제한 시간)를 기다리지 않게 한다.
        self._thread = threading.Thread(target=self._loop, name="sc01-center-poll", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            try:
                self.process.poll_center()
            except Exception:  # noqa: BLE001 — 폴러가 죽으면 진행이 조용히 멈춘다
                log.exception("Center 진행 폴링 실패")
