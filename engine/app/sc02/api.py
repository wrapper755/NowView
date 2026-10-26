"""
SC02 HTTP 경계 — `/sc02/*`. Next의 `/api/engine/sc02/*`가 그대로 중계한다(BFF).

SC01(`app/sc01/api.py`)과 같은 규칙이다. 행위자는 `X-Demo-Actor` 헤더 — 신뢰 경계가 아니다(5.4).
오류 코드: 권한 403 · 없음 404 · 상태·버전·멱등키 충돌 409 · 입력·기간·매핑 오류 422(API-23).
쓰기의 `Idempotency-Key`도 같다. 시스템 작업(바깥 Chaeksas가 부르는 HTTP 길)은 아직 없다 — 내장
실행만 돈다.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.requests import Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.events import KEEPALIVE_SECONDS, Hub
from app.sc01.domain import DomainError
from app.sc02 import demo, domain
from app.sc02.process import Sc02Process
from app.sc02.view import topology, view


class CreateBody(BaseModel):
    #: 이어 갈 장면 1 데모 실행. 없으면 장면 1을 새로 만들어 인계까지 돌린다.
    sc01_demo_run_id: str | None = Field(default=None, alias="sc01DemoRunId")
    case_id: str = Field(default="BASE", alias="caseId")
    model_config = {"populate_by_name": True}


class ReceiveBody(BaseModel):
    fixture_id: str = Field(default=domain.REQUEST_ID, alias="fixtureId")
    model_config = {"populate_by_name": True}


class ActBody(BaseModel):
    answer: dict[str, Any] = Field(default_factory=dict)
    #: 화면이 본 기안 버전(`proposal`)·인계 자료 해시(`bundle`) — 오래된 버전의 결재·인수를 막는다.
    expect: dict[str, Any] | None = None


class DueBody(BaseModel):
    due: str
    reason: str


class ClockBody(BaseModel):
    at: str


def build_router(process: Sc02Process, hub: Hub) -> APIRouter:
    r = APIRouter(prefix="/sc02", tags=["sc02"])

    def guard(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except DomainError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc

    def actor_of(value: str | None) -> str:
        if not value:
            raise HTTPException(status_code=403, detail="X-Demo-Actor 헤더가 필요하다")
        return value

    @r.get("/process")
    def get_process() -> dict[str, Any]:
        return topology(process.process)

    @r.get("/cases")
    def cases() -> list[dict[str, str]]:
        return [{"caseId": k, "label": v} for k, v in domain.CASES.items()]

    @r.get("/script")
    def script(case_id: str = "BASE") -> list[dict[str, Any]]:
        if case_id not in domain.CASES:
            raise HTTPException(422, f"모르는 시연 사례: {case_id}")
        return [
            {
                "index": i,
                "code": s.code,
                "at": s.at,
                "actor": s.actor,
                "nodeId": s.node_id,
                "label": s.label,
            }
            for i, s in enumerate(demo.steps_for(case_id, process.seed))
        ]

    @r.get("/rules")
    def rules() -> dict[str, str]:
        """R02-v1·AUTH02-v1 기준값 — 화면이 기준을 따로 적지 않게 한다(설정 시트)."""
        keys = (
            "rate_attention",
            "rate_critical",
            "amount_attention",
            "amount_critical",
            "ceo_threshold",
        )
        return {k: str(process.seed.settings[k]) for k in keys}

    @r.get("/parts")
    def parts() -> list[dict[str, str]]:
        """부품-모델 매핑(U21 하단) — a·b 각 1개, c~e는 명시적 0. 시드 그대로."""
        return [
            {
                "modelId": p.model_id,
                "partId": p.part_id,
                "supplierId": p.supplier_id,
                "qtyPer": str(p.qty_per),
            }
            for p in sorted(process.seed.parts, key=lambda p: p.model_id)
        ]

    @r.post("/demo-runs", status_code=201)
    def create(body: CreateBody, x_demo_actor: str | None = Header(default=None)) -> dict[str, Any]:
        return view(
            guard(
                process.create,
                sc01_demo_run_id=body.sc01_demo_run_id,
                case_id=body.case_id,
                actor=x_demo_actor or "u-demo",
            )
        )

    @r.get("/demo-runs/{demo_run_id}")
    def get(demo_run_id: str) -> dict[str, Any]:
        return view(guard(process.get, demo_run_id))

    @r.get("/demo-runs/{demo_run_id}/history")
    def history(demo_run_id: str) -> list[dict[str, Any]]:
        guard(process.get, demo_run_id)
        return process.store.history(demo_run_id)

    @r.get("/demo-runs/{demo_run_id}/history/{seq}")
    def at(demo_run_id: str, seq: int) -> dict[str, Any]:
        doc = process.store.at(demo_run_id, seq)
        if doc is None:
            raise HTTPException(status_code=404, detail=f"없는 시점: {seq}")
        return view(doc, historical=True)

    @r.post("/demo-runs/{demo_run_id}/requests/receive")
    def receive(
        demo_run_id: str,
        body: ReceiveBody,
        x_demo_actor: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return view(
            guard(
                process.receive,
                demo_run_id,
                body.fixture_id,
                actor=actor_of(x_demo_actor),
                idempotency_key=idempotency_key,
            )
        )

    @r.post("/demo-runs/{demo_run_id}/actions/{node_id}")
    def act(
        demo_run_id: str,
        node_id: str,
        body: ActBody,
        x_demo_actor: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        return view(
            guard(
                process.act,
                demo_run_id,
                node_id,
                body.answer,
                actor=actor_of(x_demo_actor),
                expect=body.expect,
                idempotency_key=idempotency_key,
            )
        )

    @r.post("/demo-runs/{demo_run_id}/negotiation-due")
    def negotiation_due(
        demo_run_id: str, body: DueBody, x_demo_actor: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return view(
            guard(
                process.change_due,
                demo_run_id,
                due=body.due,
                reason=body.reason,
                actor=actor_of(x_demo_actor),
            )
        )

    @r.post("/demo-runs/{demo_run_id}/agent-outputs/{output_id}/adopt")
    def adopt(
        demo_run_id: str, output_id: str, x_demo_actor: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return view(guard(process.adopt, demo_run_id, output_id, actor=actor_of(x_demo_actor)))

    @r.post("/demo-runs/{demo_run_id}/clock")
    def clock(demo_run_id: str, body: ClockBody, x_demo_actor: str | None = Header(default=None)):
        return view(guard(process.set_clock, demo_run_id, body.at, actor=actor_of(x_demo_actor)))

    @r.post("/demo-runs/{demo_run_id}/script/{index}")
    def step(demo_run_id: str, index: int) -> dict[str, Any]:
        """시연 단계 실행 — 각본의 행위자로 실제 전환을 실행한다. 지난 단계 재실행은 무해하다."""
        return view(guard(demo.run_step, process, demo_run_id, index))

    @r.post("/demo-runs/{demo_run_id}/reset")
    def reset(demo_run_id: str, x_demo_actor: str | None = Header(default=None)) -> dict[str, Any]:
        """선택 실행만 D00로. 사례를 바꾸려면 새 데모 실행을 만든다(ERR-21)."""
        return view(guard(process.reset, demo_run_id, actor=actor_of(x_demo_actor)))

    @r.get("/demo-runs/{demo_run_id}/events")
    async def events(request: Request, demo_run_id: str) -> StreamingResponse:
        """변경을 SSE로 민다 — SC01과 같은 모양(snapshot → ready → snapshot…)."""
        await run_in_threadpool(guard, process.get, demo_run_id)
        channel = f"sc02:{demo_run_id}"

        async def emit() -> str:
            doc = await run_in_threadpool(process.get, demo_run_id)
            return f"event: snapshot\ndata: {json.dumps(view(doc), ensure_ascii=False)}\n\n"

        async def generate():
            yield await emit()
            yield f"event: ready\ndata: {json.dumps({'demoRunId': demo_run_id})}\n\n"
            last = asyncio.get_running_loop().time()
            async with hub.subscribe([channel]) as queue:
                while True:
                    await hub.wait(queue)
                    if await request.is_disconnected():
                        break
                    yield await emit()
                    now = asyncio.get_running_loop().time()
                    if now - last >= KEEPALIVE_SECONDS:
                        yield ": keepalive\n\n"
                        last = now

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return r
