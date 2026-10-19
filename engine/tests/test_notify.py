"""
프로세스 경계를 넘는 변경 전파 (`notify.py`).

**여기서 잠그는 것은 "다른 워커에도 간다"다.** 허브만으로는 자기 프로세스의 SSE
구독자에게만 전달되므로, 워커를 여럿 띄우면 A에서 승인한 것이 B에 연결된 브라우저에
가지 않는다. 그래서 허브를 **둘** 만들어 서로 다른 프로세스처럼 쓰고, 한쪽에서 알린 것이
다른 쪽에 도착하는지 본다 — 같은 프로세스 안이지만 연결이 다르므로 Postgres를 실제로
거친다.

전송 실패가 변경을 실패시키지 않는다는 것도 잠근다. 알림은 부수 효과다 — 여기서 터지면
승인이 실패하는 셈이 되고, 그건 알림을 놓치는 것보다 훨씬 나쁘다.
"""

from __future__ import annotations

import asyncio

import pytest
from conftest import require_postgres

from app.events import Hub
from app.notify import CHANNEL, LocalNotifier, PostgresNotifier, build_notifier


class _FakeBackend:
    def __init__(self, kind: str, pool: object | None = None) -> None:
        self.kind = kind
        self.pool = pool


class TestLocalNotifier:
    def test_같은_허브로_바로_전달한다(self):
        hub = Hub()
        delivered: list[str] = []
        hub.fanout = delivered.append  # type: ignore[method-assign]

        LocalNotifier(hub).publish("inst-a")

        assert delivered == ["inst-a"]

    def test_SQLite_백엔드는_로컬_전파를_쓴다(self):
        # SQLite는 애초에 여러 워커로 운영할 수 없다 — 프로세스 경계를 넘길 이유가 없다.
        notifier = build_notifier(Hub(), _FakeBackend("sqlite"), None)
        assert notifier.kind == "local"

    def test_URL이_없으면_Postgres여도_로컬이다(self):
        # DATABASE_URL 없이 Postgres 백엔드가 되는 경로는 없지만, 있으면 조용히
        # 로컬로 떨어지는 것이 맞다 — 알림이 없다고 승인이 실패해서는 안 된다.
        notifier = build_notifier(Hub(), _FakeBackend("postgres"), None)
        assert notifier.kind == "local"


@pytest.mark.asyncio
class TestPostgresNotifier:
    async def test_다른_허브에도_전달된다(self):
        """
        **이것이 LISTEN/NOTIFY를 도입한 이유다.** 허브가 둘(= 워커가 둘)인데 한쪽에서
        알린 것이 다른 쪽에 도착해야 한다.
        """
        url = require_postgres()
        from psycopg_pool import ConnectionPool

        received: list[str] = []
        listener_hub = Hub()
        listener_hub.bind_loop(asyncio.get_running_loop())
        listener_hub.fanout = received.append  # type: ignore[method-assign]

        pool = ConnectionPool(url, min_size=1, max_size=2, open=True, kwargs={"autocommit": True})
        listener = PostgresNotifier(listener_hub, url, pool=pool)
        sender = PostgresNotifier(Hub(), url, pool=pool)  # 허브가 다르다 = 다른 워커

        await listener.start()
        try:
            # LISTEN 연결이 실제로 설 때까지 기다린다.
            for _ in range(100):
                if listener.listening:
                    break
                await asyncio.sleep(0.05)
            assert listener.listening

            sender.publish("inst-cross-worker")

            for _ in range(100):
                if received:
                    break
                await asyncio.sleep(0.05)
        finally:
            await listener.stop()
            pool.close()

        assert received == ["inst-cross-worker"]

    async def test_전송_실패는_조용히_넘긴다(self):
        # 알림은 부수 효과다. 여기서 예외가 나가면 승인이 실패하는 셈이 된다.
        class _BrokenPool:
            def connection(self):
                raise RuntimeError("DB가 끊겼다")

        notifier = PostgresNotifier(Hub(), "postgresql://nowhere/x", pool=_BrokenPool())
        notifier.publish("inst-a")  # 예외가 나가면 이 테스트가 실패한다

    async def test_stop_후에는_수신하지_않는다(self):
        url = require_postgres()
        from psycopg_pool import ConnectionPool

        received: list[str] = []
        hub = Hub()
        hub.bind_loop(asyncio.get_running_loop())
        hub.fanout = received.append  # type: ignore[method-assign]

        pool = ConnectionPool(url, min_size=1, max_size=2, open=True, kwargs={"autocommit": True})
        notifier = PostgresNotifier(hub, url, pool=pool)
        await notifier.start()
        for _ in range(100):
            if notifier.listening:
                break
            await asyncio.sleep(0.05)

        await notifier.stop()
        assert notifier.listening is False

        # 멈춘 뒤 보낸 것은 받지 않는다 — 유령 세션이 남아 있으면 여기서 드러난다.
        PostgresNotifier(Hub(), url, pool=pool).publish("inst-after-stop")
        await asyncio.sleep(0.6)
        pool.close()

        assert received == []


def test_채널_이름이_Postgres_식별자_규칙을_지킨다():
    # 대문자·하이픈이 섞이면 따옴표 처리가 필요해지고, LISTEN 문을 f-string으로 쓰는
    # 지금 구현에서는 조용히 깨진다.
    assert CHANNEL.islower()
    assert CHANNEL.replace("_", "").isalnum()
