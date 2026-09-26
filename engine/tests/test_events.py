"""
변경 알림 허브 — SSE가 push로 성립하는 근거.

**폴링이 아니라 push인 이유**: 이 엔진에서 상태가 바뀌는 계기는 전부 우리 코드를
지나간다(생성·승인·장면 이동). 그 지점에서 알리면 즉시 전파된다.

여기서 잠그는 것:
* 구독자에게 실제로 전달된다.
* **알림이 실패해도 변경은 성공한다** — 알림은 부수 효과이지 변경의 일부가 아니다.
  여기서 터지면 승인이 실패하는 셈이 된다.
* **구독이 끝나면 즉시 정리된다** — 처음에 async generator로 만들었다가 이 테스트가
  누적 버그를 잡았다. `async for`를 `break`로 빠져나가면 generator의 `finally`가 즉시
  돌지 않아, 연결이 끊길 때마다 구독자가 남는다.
"""

from __future__ import annotations

import asyncio

import pytest

from app.events import SAFETY_RESYNC_SECONDS, Hub


@pytest.mark.asyncio
async def test_구독자에게_전달된다():
    hub = Hub()
    hub.bind_loop(asyncio.get_running_loop())
    received: list[str | None] = []

    async def listen():
        async with hub.subscribe(["inst-a"]) as queue:
            received.append(await hub.wait(queue))

    task = asyncio.create_task(listen())
    await asyncio.sleep(0)  # 구독이 등록될 틈을 준다
    hub.publish("inst-a")
    await asyncio.wait_for(task, timeout=2)

    assert received == ["inst-a"]


@pytest.mark.asyncio
async def test_구독하지_않은_인스턴스는_전달되지_않는다():
    hub = Hub()
    hub.bind_loop(asyncio.get_running_loop())
    received: list[str | None] = []

    async def listen():
        async with hub.subscribe(["inst-a"]) as queue:
            received.append(await hub.wait(queue))

    task = asyncio.create_task(listen())
    await asyncio.sleep(0)
    hub.publish("inst-b")
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(asyncio.shield(task), timeout=0.2)
    task.cancel()

    assert received == []


@pytest.mark.asyncio
async def test_한_스트림이_여러_인스턴스를_받는다():
    # 인스턴스마다 연결을 열면 브라우저의 동시 연결 한도를 SSE가 잡아먹는다.
    hub = Hub()
    hub.bind_loop(asyncio.get_running_loop())
    received: list[str | None] = []

    async def listen():
        async with hub.subscribe(["inst-a", "inst-b"]) as queue:
            received.append(await hub.wait(queue))
            received.append(await hub.wait(queue))

    task = asyncio.create_task(listen())
    await asyncio.sleep(0)
    hub.publish("inst-a")
    hub.publish("inst-b")
    await asyncio.wait_for(task, timeout=2)

    assert set(received) == {"inst-a", "inst-b"}


@pytest.mark.asyncio
async def test_구독이_끝나면_정리된다():
    hub = Hub()
    hub.bind_loop(asyncio.get_running_loop())

    async def listen():
        async with hub.subscribe(["inst-a"]) as queue:
            await hub.wait(queue)

    task = asyncio.create_task(listen())
    await asyncio.sleep(0)
    assert hub.subscriber_count == 1
    hub.publish("inst-a")
    await asyncio.wait_for(task, timeout=2)

    # 끊길 때마다 쌓이면 메모리와 알림 비용이 계속 늘어난다.
    assert hub.subscriber_count == 0


def test_루프가_없으면_조용히_넘긴다():
    # 알림은 부수 효과다. 여기서 터지면 승인이 실패하는 셈이 된다.
    hub = Hub()
    hub.publish("inst-a")  # bind_loop 전
    assert hub.subscriber_count == 0


@pytest.mark.asyncio
async def test_구독자가_없어도_조용히_넘긴다():
    hub = Hub()
    hub.bind_loop(asyncio.get_running_loop())
    hub.publish("inst-없음")
    assert hub.subscriber_count == 0


def test_안전망_주기가_설정되어_있다():
    """
    알림은 한 프로세스 안에서만 성립한다 — 워커가 여럿이면 다른 프로세스의 변경은
    허브를 지나가지 않는다. 그래서 스트림이 주기적으로 한 번씩 다시 읽어야 한다.
    """
    assert SAFETY_RESYNC_SECONDS > 0
