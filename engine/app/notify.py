"""
프로세스 경계를 넘는 변경 전파 — Postgres `LISTEN`/`NOTIFY`.

**왜 필요한가.** 허브(`events.py`)는 자기 프로세스의 SSE 구독자에게만 전달한다. uvicorn을
워커 여러 개로 띄우거나 엔진을 여러 대로 늘리면 A 워커에서 승인한 것이 B 워커에 연결된
브라우저에 가지 않는다 — 그 브라우저는 안전망 재조회(20초)를 기다려야 한다.

Postgres를 거치면 **모든 워커가 같은 알림을 받는다.**

```
승인(워커 A) → SELECT pg_notify('nowview_instance', id)
                 → Postgres → LISTEN 중인 모든 워커 → 각자 hub.fanout(id) → SSE
```

**`NOTIFY`가 아니라 `pg_notify`를 쓴다.** `NOTIFY`는 유틸리티 문이라 바인드 파라미터를
받지 못한다 — 인스턴스 id를 문자열로 붙이면 따옴표 처리를 직접 해야 하고, 그건 틀리기
쉬운 종류다.

**전송은 동기, 수신은 비동기다.** 변경은 `def` 엔드포인트(스레드풀)에서 일어나므로 전송은
기존 커넥션 풀로 그냥 보낸다. 수신은 `LISTEN` 전용 연결을 하나 붙들고 있어야 해서 별도
async 태스크로 돈다.

**전송 실패는 변경을 실패시키지 않는다.** 알림은 부수 효과다 — 여기서 터지면 승인이
실패하는 셈이 되고, 그건 알림을 놓치는 것보다 훨씬 나쁘다. 놓친 알림은 안전망이 덮는다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

from .events import Hub

log = logging.getLogger(__name__)

#: 알림 채널. Postgres 식별자라 소문자·밑줄만 쓴다.
CHANNEL = "nowview_instance"

#: LISTEN 연결이 끊겼을 때 다시 붙기까지 기다리는 시간.
RECONNECT_DELAY_SECONDS = 2.0

#: `notifies()`를 다시 진입하는 주기. 이 간격마다 종료 요청을 확인한다.
LISTEN_POLL_SECONDS = 1.0


class Notifier(Protocol):
    """변경 전파 방식. 어느 구현이든 `publish`는 동기이고 실패해도 조용하다."""

    kind: str

    def publish(self, instance_id: str) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...


class LocalNotifier:
    """
    한 프로세스 안에서만 전달한다 — SQLite 백엔드(로컬 개발)용.

    SQLite는 애초에 여러 워커로 운영할 수 없으므로(워커마다 파일이 갈라진다) 프로세스
    경계를 넘길 이유가 없다.
    """

    kind = "local"

    def __init__(self, hub: Hub) -> None:
        self._hub = hub

    def publish(self, instance_id: str) -> None:
        self._hub.fanout(instance_id)

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


class PostgresNotifier:
    """
    Postgres를 거쳐 모든 워커에 전달한다.

    **보낸 프로세스도 자기 알림을 되받는다.** `LISTEN`은 별도 연결이고 Postgres는 채널을
    듣는 모든 연결에 보내기 때문이다. 그래서 여기서는 로컬 전달을 따로 하지 않는다 —
    하면 같은 변경이 두 번 전달된다(스냅샷을 다시 읽는 것이라 틀린 값이 되지는 않지만
    쓸모없는 왕복이다).
    """

    kind = "postgres"

    def __init__(self, hub: Hub, url: str, *, pool: Any) -> None:
        self._hub = hub
        self._url = url
        self._pool = pool
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self._listening = False

    @property
    def listening(self) -> bool:
        """LISTEN 연결이 서 있는가. `/health`가 이 값을 알려 준다."""
        return self._listening

    def publish(self, instance_id: str) -> None:
        try:
            with self._pool.connection() as conn:
                conn.execute("SELECT pg_notify(%s, %s)", (CHANNEL, instance_id))
        except Exception:  # noqa: BLE001 — 알림 실패가 변경을 실패시키면 안 된다
            log.warning("알림 전송 실패 (%s) — 안전망 재조회가 덮는다", instance_id, exc_info=True)

    async def start(self) -> None:
        self._stopping.clear()
        self._task = asyncio.create_task(self._listen_forever(), name="pg-listen")

    async def stop(self) -> None:
        self._stopping.set()
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._listening = False

    async def _listen_forever(self) -> None:
        """
        끊기면 다시 붙는다.

        끊겼다 붙는 사이의 알림은 사라진다 — 그 구간은 안전망 재조회가 덮는다. 여기서
        놓친 것을 되살리려 하면 Postgres의 알림 큐를 우리가 다시 구현하는 셈이 된다.
        """
        import psycopg

        while not self._stopping.is_set():
            conn = None
            try:
                conn = await psycopg.AsyncConnection.connect(self._url, autocommit=True)
                await conn.execute(f"LISTEN {CHANNEL}")
                self._listening = True
                log.info("Postgres 알림 수신 시작 (채널 %s)", CHANNEL)

                while not self._stopping.is_set():
                    # timeout으로 다시 진입해 종료 요청을 확인한다. timeout이 없으면
                    # 취소될 때까지 영원히 매달려 있어 종료가 지저분해진다.
                    async for notice in conn.notifies(timeout=LISTEN_POLL_SECONDS):
                        if notice.payload:
                            self._hub.fanout(notice.payload)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.warning("Postgres 알림 연결이 끊겼다 — 다시 붙는다", exc_info=True)
            finally:
                self._listening = False
                if conn is not None:
                    try:
                        await conn.close()
                    except Exception:  # noqa: BLE001
                        pass
            if not self._stopping.is_set():
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)


def build_notifier(hub: Hub, backend: Any, url: str | None) -> Notifier:
    """
    저장 백엔드에 맞는 전파 방식을 고른다.

    Postgres인데 알림만 로컬로 두면, 여러 워커로 띄웠을 때 한쪽에서 승인한 것이 다른
    쪽 브라우저에 20초 늦게 도착한다 — 그 상태를 "실시간"이라고 부를 수 없다.
    """
    if backend.kind == "postgres" and url:
        return PostgresNotifier(hub, url, pool=backend.pool)
    return LocalNotifier(hub)
