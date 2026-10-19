"""
FastAPI — BPM 엔진의 HTTP 경계.

Next의 `/api/engine/*`가 이것을 프록시한다(BFF). 브라우저가 직접 부르지 않는다 —
CORS를 만들지 않고, LLM 자격증명을 서버에만 두고, 화면이 계속 `/api/*`만 알게 하려는
것이다. 실엔진 ↔ Mock 전환도 BFF 한 곳에 꽂힌다.

**무상태 계산기가 아니다.** 기존 `/api/bpm/state?step=N`은 진행 지점을 받아 계산해
돌려줬지만, 여기서는 인스턴스가 서버에 살아 있고 식별자가 `instanceId`다.
"""

from __future__ import annotations

import asyncio
import json as jsonlib
import logging
import os
import threading
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .agents import AgentContractError, make_runner
from .events import KEEPALIVE_SECONDS, hub
from .instances import InstanceStore, config_for, snapshot
from .notify import build_notifier
from .sc01.api import build_router as build_sc01_router
from .sc01.process import Sc01Process
from .sc01.store import build_sc01_store
from .seek import SeekError, seek
from .spec import ProcessSpec
from .store import build_backend

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "kimi-k3:cloud")

app = FastAPI(
    title="NowView BPM Engine",
    version="0.1.0",
    description="LangGraph StateGraph 기반 BPM 런타임. 토폴로지는 요청으로 받는다.",
)

# `DATABASE_URL`이 있으면 Postgres, 없으면 파일 SQLite다. 연결 실패를 SQLite로
# 되돌리지 않는다 — 운영에서 DB가 안 붙었다면 즉시 드러나야 한다(store.py 참조).
backend = build_backend()
store = InstanceStore(
    backend,
    runner_factory=lambda mode: make_runner(mode, model=OLLAMA_MODEL, base_url=OLLAMA_URL),
)

# 변경 전파. Postgres면 LISTEN/NOTIFY로 **다른 워커까지** 간다(notify.py).
notifier = build_notifier(hub, backend, os.getenv("DATABASE_URL"))

# SC01 — Chaeksas BPM 엔진 위의 장면 1(app/sc01). 같은 저장소·같은 알림 경로를 쓴다.
sc01 = Sc01Process(build_sc01_store(backend), publish=notifier.publish)
app.include_router(build_sc01_router(sc01, hub))


class CreateRequest(BaseModel):
    spec: ProcessSpec
    #: `mock`이 기본이다 — 데모가 결정론적이어야 하고, LLM 호출은 비용·지연이 있다.
    agent_mode: str = Field(default="mock", alias="agentMode")
    #: true면 첫 사람 대기 지점 또는 종료까지 진행한다 — **배경에서** 한다.
    #: 응답은 기다리지 않으므로 `status`는 `created`로 돌아온다.
    advance: bool = True

    model_config = {"populate_by_name": True}


class ResumeRequest(BaseModel):
    """
    사람의 입력으로 멈춘 그래프를 재개한다.

    승인 노드면 `{alternativeId, leverValue, rationale}`, 확인 노드면 아무 객체나 된다.
    검증은 엔진이 한다 — UI 버튼 비활성은 강제가 아니다.
    """

    payload: dict[str, Any] = Field(default_factory=dict)


@app.on_event("startup")
async def _start_notifications() -> None:
    # 변경 알림은 스레드풀(동기 엔드포인트)에서 오므로 루프 참조가 필요하다.
    hub.bind_loop(asyncio.get_running_loop())
    await notifier.start()


@app.on_event("shutdown")
async def _stop_notifications() -> None:
    # LISTEN 연결을 정리하지 않으면 재시작 때 Postgres에 유령 세션이 남는다.
    await notifier.stop()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        # 어느 백엔드로 돌고 있는지 드러내지 않으면 "SQLite로 운영에 올렸다"를
        # 눈치챌 방법이 없다. 자격증명은 빼고 호스트·DB만 싣는다.
        "storage": {"kind": backend.kind, "describe": backend.describe},
        "ollama": {"url": OLLAMA_URL, "model": OLLAMA_MODEL},
        "instances": len(store.list_ids()),
        "eventSubscribers": hub.subscriber_count,
        # 전파 방식을 드러내지 않으면 "여러 워커인데 알림이 로컬"인 상태를 눈치챌 수 없다.
        "notify": {
            "kind": notifier.kind,
            "listening": getattr(notifier, "listening", None),
        },
    }


@app.get("/instances")
def list_instances() -> dict[str, Any]:
    return {"instances": store.list_ids()}


@app.post("/instances", status_code=201)
def create_instance(body: CreateRequest, background: BackgroundTasks) -> dict[str, Any]:
    """
    인스턴스를 만들고 **즉시** 돌려준다. 진행은 배경에서 한다(`_advance_later`).

    **요청 안에서 첫 대기까지 밀어붙이지 않는다.** LLM 모드는 Agent 3개를 연달아 돌려
    120초를 넘고 Cloudflare가 약 100초에 끊어 524가 됐다 — 게다가 엔진은 끝까지 돌아
    인스턴스를 남기므로 클라이언트가 id를 못 받은 **고아**가 생겼다(CLAUDE.md 5.4).
    id를 먼저 주면 화면이 붙어 놓고 SSE로 진행을 받는다.

    그래서 응답의 `status`는 `created`다 — 첫 대기 지점은 조금 뒤에 온다. Mock 모드도
    같은 경로로 돈다. 모드마다 다르게 하면 "LLM에서만 나는 버그"가 생긴다.
    """
    try:
        instance = store.create(body.spec, agent_mode=body.agent_mode)
    except ValueError as exc:
        # 명세 자체가 그래프로 성립하지 않는 경우다 — 400이 맞다.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if body.advance:
        background.add_task(_advance_later, instance)
    notifier.publish(instance.id)
    return snapshot(instance)


@app.get("/instances/{instance_id}")
def get_instance(instance_id: str) -> dict[str, Any]:
    return snapshot(_lookup(instance_id))


@app.post("/instances/{instance_id}/resume")
def resume_instance(instance_id: str, body: ResumeRequest) -> dict[str, Any]:
    from langgraph.types import Command

    instance = _lookup(instance_id)
    current = snapshot(instance)
    if current["pendingApproval"] is None:
        raise HTTPException(
            status_code=409,
            detail=f"멈춰 있지 않은 인스턴스다 (상태: {current['status']}). 재개할 지점이 없다.",
        )
    _run(instance, Command(resume=body.payload))
    notifier.publish(instance_id)
    after = snapshot(instance)
    # 입력이 반려되면 같은 지점에 error를 달고 다시 멈춘다 — 400이 아니라 그 상태를
    # 그대로 돌려준다. 클라이언트가 무엇이 틀렸는지 읽고 다시 보내면 된다.
    return after


class SeekRequest(BaseModel):
    """
    장면 이동 — 목표 노드가 현재 지점이 되게 한다.

    뒤로 가면 체크포인트를 되감고(승인도 함께 사라진다), 앞으로 가면 사람 대기마다
    주어진 입력을 넣어 진행한다. 승인 노드를 통과해야 한다면 `decision`이 필요하다 —
    엔진이 임의로 승인하면 Human-in-the-Loop이 무너진다.
    """

    target_node_id: str = Field(alias="targetNodeId")
    decision: dict[str, Any] | None = None
    acknowledged_by: str | None = Field(default=None, alias="acknowledgedBy")

    model_config = {"populate_by_name": True}


@app.post("/instances/{instance_id}/seek")
def seek_instance(instance_id: str, body: SeekRequest) -> dict[str, Any]:
    instance = _lookup(instance_id)
    try:
        # 생성의 배경 진행과 겹칠 수 있다 — 같은 `thread_id`에 두 진행이 동시에 돌면
        # 체크포인트가 엉킨다. 데모 플레이어가 생성 직후 장면을 찍으면 실제로 겹친다.
        with _lock_for(instance_id):
            result = seek(
                instance,
                target_node_id=body.target_node_id,
                decision=body.decision,
                acknowledged_by=body.acknowledged_by,
            )
        # 되감기는 인스턴스를 바꾸지 않지만, 앞으로 갈 때는 바뀐다. 구분하지 않고
        # 알린다 — 구독자가 다시 읽어도 같은 값이면 화면은 그대로다.
        notifier.publish(instance_id)
        return result
    except SeekError as exc:
        # 요청 자체가 성립하지 않는다(없는 노드, 미실행 분기, 결정 누락) — 400이다.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AgentContractError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/instances/{instance_id}/history")
def instance_history(instance_id: str) -> dict[str, Any]:
    """
    체크포인트 이력 — 어디로 되감을 수 있는지 보여 준다.

    최신순이다. 되감았다가 다시 진행하면 같은 노드의 체크포인트가 여러 개 생긴다.
    """
    instance = _lookup(instance_id)
    entries = []
    for state in instance.graph.get_state_history(config_for(instance.id)):
        values = state.values or {}
        entries.append({
            "checkpointId": state.config["configurable"].get("checkpoint_id"),
            "next": list(state.next or ()),
            "visited": list(values.get("visited") or []),
            "hasDecision": values.get("decision") is not None,
        })
    return {"instanceId": instance_id, "history": entries}


@app.get("/events")
async def events(
    request: Request,
    instances: str = Query(description="쉼표로 구분한 인스턴스 id 목록"),
) -> StreamingResponse:
    """
    인스턴스 변경을 SSE로 밀어 준다.

    **여러 인스턴스를 한 스트림으로 합친다.** 인스턴스마다 연결을 열면 브라우저의
    동시 연결 한도(HTTP/1.1에서 도메인당 6개)를 SSE가 잡아먹어 다른 요청이 굶는다.

    보내는 것:
    * `event: snapshot` — 그 인스턴스의 현재 스냅샷. 연결 직후 전부 한 번 보낸다.
    * `event: ready` — 초기 버스트가 끝났다는 표시. **클라이언트가 이걸 기다려야 한다** —
      스냅샷이 하나씩 오므로 언제 "전부 받았는지"를 알 방법이 따로 필요하다.
    * `: keepalive` 주석 — 프록시가 조용한 연결을 끊지 않게 한다.

    스냅샷 만들기는 동기(DB 접근)이므로 스레드풀에서 돌린다 — 이벤트 루프를 막으면
    다른 요청이 함께 늦어진다.
    """
    ids = [x for x in (i.strip() for i in instances.split(",")) if x]
    if not ids:
        raise HTTPException(status_code=400, detail="instances가 비어 있다")
    for instance_id in ids:
        _lookup(instance_id)  # 없는 인스턴스면 스트림을 열기 전에 404

    async def emit(instance_id: str) -> str:
        instance = await run_in_threadpool(store.get, instance_id)
        payload = await run_in_threadpool(snapshot, instance)
        return f"event: snapshot\ndata: {jsonlib.dumps(payload, ensure_ascii=False)}\n\n"

    async def generate():
        # 연결 직후 현재 상태를 전부 보낸다 — 클라이언트가 따로 조회하지 않아도 되게.
        for instance_id in ids:
            yield await emit(instance_id)
        yield f"event: ready\ndata: {jsonlib.dumps({'instances': ids})}\n\n"

        last_keepalive = asyncio.get_running_loop().time()
        # `async with`라서 연결이 끊겨 break하든 취소되든 구독이 반드시 해제된다.
        async with hub.subscribe(ids) as queue:
            while True:
                changed = await hub.wait(queue)
                if await request.is_disconnected():
                    break
                if changed is not None:
                    yield await emit(changed)
                else:
                    # 안전망: 알림을 놓쳤을 수 있으니 전부 다시 보낸다(events.py 참조).
                    for instance_id in ids:
                        yield await emit(instance_id)
                now = asyncio.get_running_loop().time()
                if now - last_keepalive >= KEEPALIVE_SECONDS:
                    last_keepalive = now
                    yield ": keepalive\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # nginx 계열이 버퍼링하면 이벤트가 몰려서 늦게 도착한다.
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/instances/{instance_id}", status_code=204)
def delete_instance(instance_id: str) -> None:
    _lookup(instance_id)
    store.delete(instance_id)
    notifier.publish(instance_id)


# ------------------------------------------------------------------ 내부


def _lookup(instance_id: str):
    try:
        return store.get(instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"없는 인스턴스: {instance_id}") from exc


#: 인스턴스별 진행 잠금. 같은 `thread_id`에 두 진행이 겹치면 체크포인트가 엉킨다 —
#: 생성의 배경 진행이 도는 동안 사람이 되감기를 누를 수 있으므로 실제로 겹칠 수 있다.
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(instance_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(instance_id, threading.Lock())


def _advance(instance, command: Any) -> None:
    """
    그래프를 다음 사람 대기 지점 또는 종료까지 돌린다.

    `interrupt`는 예외가 아니라 정상 종료다 — LangGraph가 체크포인트를 남기고 스트림이
    끝난다. 그래서 여기서 나갈 예외는 Agent 계약 위반뿐이고, **그것을 HTTP로 번역하지
    않는다** — 이 함수는 배경에서도 불리고 그때는 받을 응답이 없다. 번역은 호출자가 한다.

    **`invoke`가 아니라 `stream`이다.** 노드가 끝날 때마다 알리면 화면이 진행을 점진적으로
    받는다(SSE는 4.19). `invoke`는 전부 끝나야 돌아오므로, LLM 모드에서 2분 동안 아무
    변화가 없다가 한꺼번에 바뀐다 — 그러면 배경 진행이 고장난 것과 구분되지 않는다.
    """
    # 노드 사이에서는 `next`가 비어 있어 스냅샷이 `done`으로 파생된다 — 도는 중임을
    # 표시해 두지 않으면 그 거짓이 알림을 타고 화면까지 간다(`instances.Instance.advancing`).
    instance.advancing = True
    try:
        for _ in instance.graph.stream(
            command if command is not None else {"scenario_id": instance.spec.scenario_id},
            config_for(instance.id),
        ):
            notifier.publish(instance.id)
    finally:
        instance.advancing = False


def _run(instance, command: Any) -> None:
    """요청 안에서 진행한다 — 계약 위반을 502로 번역한다."""
    with _lock_for(instance.id):
        try:
            _advance(instance, command)
        except AgentContractError as exc:
            # 지어낸 산출물로 메우지 않는다. 어느 Agent가 왜 실패했는지 그대로 알린다.
            raise HTTPException(status_code=502, detail=str(exc)) from exc


def _advance_later(instance) -> None:
    """
    배경에서 첫 사람 대기 지점까지 진행한다 — `POST /instances`가 쓴다.

    **요청 안에서 돌리면 프록시가 끊는다.** LLM 모드의 생성은 Agent를 3개 연달아 돌려
    120초를 넘는데, Cloudflare의 원본 응답 타임아웃은 약 100초다(CLAUDE.md 5.4). 그래서
    생성은 id만 즉시 돌려주고 진행은 여기서 한다 — 화면은 SSE로 변화를 받는다.

    실패를 인스턴스에 남기고 알린다. 받을 응답이 없으니 502를 던질 곳이 없는데, 조용히
    넘기면 화면이 `running`에 멈춘 인스턴스를 영원히 기다린다.
    """
    with _lock_for(instance.id):
        try:
            _advance(instance, None)
        except AgentContractError as exc:
            instance.failure = str(exc)
            log.error("배경 진행이 실패했다 (%s): %s", instance.id, exc)
        except Exception as exc:  # noqa: BLE001 — 배경에서는 무엇이든 삼켜지면 안 된다
            instance.failure = f"진행 중 예기치 못한 오류: {exc}"
            log.exception("배경 진행이 실패했다 (%s)", instance.id)
        finally:
            notifier.publish(instance.id)
