"""
인스턴스 변경 알림 — SSE의 원천.

**왜 push가 성립하는가.** 이 엔진에서 상태가 바뀌는 계기는 전부 우리 코드를 지나간다 —
인스턴스 생성, 승인 재개, 장면 이동. LangGraph가 몰래 진행하는 일은 없다(Agent 노드도
그 호출 안에서 돈다). 그래서 그 지점에서 알리면 폴링 없이 즉시 전파된다.

**한 프로세스 안에서만 성립한다.** uvicorn을 워커 여러 개로 띄우거나 엔진을 여러 대로
늘리면, 다른 프로세스가 일으킨 변경은 이 허브를 지나가지 않는다. 그래서 스트림에
**안전망 재조회**를 함께 둔다(`SAFETY_RESYNC_SECONDS`) — 알림을 놓쳐도 그 주기 안에
따라잡는다. 진짜로 여러 워커를 쓸 때는 Postgres `LISTEN`/`NOTIFY`로 바꿔야 한다.

`publish`는 **동기 코드에서 불린다.** FastAPI의 `def` 엔드포인트는 스레드풀에서 돌기
때문에 이벤트 루프를 직접 만질 수 없다 — `call_soon_threadsafe`로 넘긴다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

log = logging.getLogger(__name__)

#: 알림을 놓쳤을 때 따라잡는 주기. 폴링이 아니라 안전망이다 — 평소에는 알림이 먼저 온다.
SAFETY_RESYNC_SECONDS = 20.0

#: 프록시·로드밸런서가 조용한 연결을 끊지 않게 주석을 보내는 주기.
KEEPALIVE_SECONDS = 15.0


class Hub:
    """인스턴스 id → 구독자 큐."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: dict[str, set[asyncio.Queue[str]]] = {}

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """서버 시작 시 이벤트 루프를 붙인다 — 스레드풀에서 알릴 때 필요하다."""
        self._loop = loop

    def publish(self, instance_id: str) -> None:
        """
        변경을 알린다. **동기 코드에서 호출해도 안전하다.**

        루프가 아직 없거나(테스트) 구독자가 없으면 조용히 넘긴다 — 알림은 부수 효과이지
        변경의 일부가 아니다. 여기서 터지면 승인이 실패하는 셈이 된다.
        """
        loop = self._loop
        if loop is None:
            return
        queues = list(self._subscribers.get(instance_id, ()))
        if not queues:
            return
        for queue in queues:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, instance_id)
            except RuntimeError:  # 루프가 이미 닫혔다
                pass

    @asynccontextmanager
    async def subscribe(self, instance_ids: list[str]) -> AsyncIterator[asyncio.Queue[str]]:
        """
        구독을 열고 **빠져나갈 때 반드시 정리한다.**

        async generator로 만들었다가 구독이 누적되는 버그를 겪었다 —
        `async for`를 `break`/`return`으로 빠져나가면 generator의 `finally`가 즉시 돌지
        않는다(닫히거나 GC될 때까지 미룬다). SSE 엔드포인트는 클라이언트 연결이 끊기면
        `break`하므로, 연결이 끊길 때마다 구독자가 남아 알림 비용과 메모리가 계속 늘었다.
        컨텍스트 매니저로 바꿔 해제 시점을 확정했다.
        """
        queue: asyncio.Queue[str] = asyncio.Queue()
        for instance_id in instance_ids:
            self._subscribers.setdefault(instance_id, set()).add(queue)
        try:
            yield queue
        finally:
            for instance_id in instance_ids:
                subs = self._subscribers.get(instance_id)
                if subs is None:
                    continue
                subs.discard(queue)
                if not subs:
                    self._subscribers.pop(instance_id, None)

    @staticmethod
    async def wait(queue: asyncio.Queue[str]) -> str | None:
        """
        변경된 인스턴스 id를 기다린다. 안전망 주기가 지나면 `None`.

        `None`은 "알림은 없었지만 한 번 다시 읽어라"는 뜻이다.
        """
        try:
            return await asyncio.wait_for(queue.get(), timeout=SAFETY_RESYNC_SECONDS)
        except TimeoutError:
            return None

    @property
    def subscriber_count(self) -> int:
        return sum(len(s) for s in self._subscribers.values())


hub = Hub()
