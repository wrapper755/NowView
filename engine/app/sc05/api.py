"""
SC05 HTTP 경계 — `/sc05/*`. Next의 `/api/engine/sc05/*`가 그대로 중계한다(BFF).

장면 1~4와 같은 규칙이다. 행위자는 `X-Demo-Actor` 헤더 — 신뢰 경계가 아니다(5.4). 오류 코드: 권한
403 · 없음
404 · 상태·버전·멱등키 충돌 409 · 필수조건·검증 실패 422(구현명세 19장). 계획
누락(PLAN_INCOMPLETE)·착수 요건
(START_BLOCKED)·예산 초과(BUDGET_EXCEEDED)·결과 미확인(RESULT_INCOMPLETE)·전망
대사(FORECAST_INVALID)·종료 요건
(COMPLETION_BLOCKED)은 422에 `error_code`·`blocking_items`를 싣는다. 쓰기의 `Idempotency-Key`도
같다.
시스템 작업은 HTTP로 받지 않는다 — 엔진의 C15 일꾼이 Center에서 가져간다(`app/consumer.py`).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException, Response
from fastapi.requests import Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.events import KEEPALIVE_SECONDS, Hub
from app.preparation import Preparations, begin_scene, preparing
from app.sc01.domain import DomainError
from app.sc05 import demo, domain
from app.sc05.process import Sc05Process
from app.sc05.view import topology
from app.sc05.view import view as render

_BODY = Body(default_factory=dict)


class CreateBody(BaseModel):
    #: 이어 갈 데모 실행(장면 1~4와 같은 id). 없으면 장면 1부터 새로 만들어 장면 4 완료까지 돌린다.
    sc01_demo_run_id: str | None = Field(default=None, alias="sc01DemoRunId")
    case_id: str = Field(default="BASE", alias="caseId")
    #: center(기본) | studio. 화면은 내장을 고르지 않는다(2026-10-27 결정).
    executor: str = "center"
    model_config = {"populate_by_name": True}


class ResetBody(BaseModel):
    executor: str | None = None


class ActBody(BaseModel):
    answer: dict[str, Any] = Field(default_factory=dict)
    #: 화면이 본 계획(`plan`)·검토안(`forecast`)·산정본(`run`) — 오래된 것의 확정·승인을 막는다.
    expect: dict[str, Any] | None = None


class AgentBody(BaseModel):
    kind: str = "AG51"


class ReviewBody(BaseModel):
    note: str = ""


class ClockBody(BaseModel):
    at: str


def build_router(
    process: Sc05Process,
    hub: Hub,
    preparations: Preparations | None = None,
) -> APIRouter:
    r = APIRouter(prefix="/sc05", tags=["sc05"])
    prep = preparations or Preparations()

    def view(doc: dict, **kwargs: Any) -> dict[str, Any]:
        return render(doc, center=process.center.config, **kwargs)

    def guard(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except domain.PrerequisiteError as exc:
            raise HTTPException(
                status_code=exc.status,
                detail={"message": str(exc), "error_code": exc.code, "blocking_items": exc.items},
            ) from exc
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
                "kind": s.kind,
                "nodeId": s.node_id,
                "label": s.label,
                "event": s.event,
            }
            for i, s in enumerate(demo.steps_for(case_id, process.seed))
        ]

    @r.post("/demo-runs", status_code=201)
    def create(
        body: CreateBody, response: Response, x_demo_actor: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """
        시작 — 앞 장면이 끝나 있지 않으면 각본으로 끝까지 실행한다. 오래 걸리면 202와 준비
        상태를 돌려주고 배경에서 잇는다(`app.preparation`). 화면은 `…/preparation`을 읽는다.
        """
        actor = x_demo_actor or "u-demo"

        def make(rid: str) -> dict:
            return process.create(
                sc01_demo_run_id=rid,
                case_id=body.case_id,
                actor=actor,
                executor=body.executor,
            )

        doc, rid = guard(
            begin_scene,
            prep,
            "sc05",
            process,
            demo_run_id=body.sc01_demo_run_id,
            case_id=body.case_id,
            cases=domain.CASES,
            actor=actor,
            executor=body.executor,
            create=make,
        )
        if doc is None:
            response.status_code = 202
            return guard(preparing, prep, "sc05", process, rid)
        return view(doc)

    @r.get("/demo-runs/{demo_run_id}/preparation")
    def preparation(demo_run_id: str) -> dict[str, Any]:
        """시작 준비 상태 — 진행 중(앞 장면들의 지금 단계)·끝남·실패(사유·상태 코드)."""
        return guard(preparing, prep, "sc05", process, demo_run_id)

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

    @r.post("/demo-runs/{demo_run_id}/start")
    def start(
        demo_run_id: str,
        x_demo_actor: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """S01 착수 — 재착수는 기존 결과를 돌려준다(장면 중복 생성 금지)."""
        return view(
            guard(
                process.start,
                demo_run_id,
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

    @r.get("/demo-runs/{demo_run_id}/start-check")
    def start_check(demo_run_id: str) -> dict[str, Any]:
        """착수 요건(M502) — 계산만 한다. 상태를 바꾸지 않는다."""
        return domain.start_requirements(guard(process.get, demo_run_id))

    @r.get("/demo-runs/{demo_run_id}/completion-check")
    def completion_check(demo_run_id: str) -> dict[str, Any]:
        """종료 요건(CT513) — 공식본·증거·후속 책임·기한. 상태를 바꾸지 않는다."""
        doc = guard(process.get, demo_run_id)
        return domain.completion_conditions(doc)

    @r.post("/demo-runs/{demo_run_id}/agent-drafts")
    def agent(
        demo_run_id: str, body: AgentBody, x_demo_actor: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return view(guard(process.agent, demo_run_id, body.kind, actor=actor_of(x_demo_actor)))

    @r.post("/demo-runs/{demo_run_id}/agent-outputs/{output_id}/review")
    def review(
        demo_run_id: str,
        output_id: str,
        body: ReviewBody | None = None,
        x_demo_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """제안 검토 기록 — 원 초안은 그대로다. 업무 확인·승인을 대신하지 않는다."""
        return view(
            guard(
                process.review_agent,
                demo_run_id,
                output_id,
                actor=actor_of(x_demo_actor),
                note=body.note if body else "",
            )
        )

    @r.post("/demo-runs/{demo_run_id}/clock")
    def clock(demo_run_id: str, body: ClockBody, x_demo_actor: str | None = Header(default=None)):
        return view(guard(process.set_clock, demo_run_id, body.at, actor=actor_of(x_demo_actor)))

    @r.post("/demo-runs/{demo_run_id}/script/{index}")
    def step(demo_run_id: str, index: int) -> dict[str, Any]:
        """시연 단계 실행 — 각본의 행위자로 실제 전환을 실행한다. 지난 단계 재실행은 무해하다."""
        return view(guard(demo.run_step, process, demo_run_id, index))

    @r.post("/demo-runs/{demo_run_id}/reset")
    def reset(
        demo_run_id: str,
        body: ResetBody | None = None,
        x_demo_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """선택 실행만 D500으로. 실행 위치를 바꿀 수 있다. 사례를 바꾸려면 새 데모 실행이다."""
        return view(
            guard(
                process.reset,
                demo_run_id,
                actor=actor_of(x_demo_actor),
                executor=body.executor if body else None,
            )
        )

    @r.get("/demo-runs/{demo_run_id}/events")
    async def events(request: Request, demo_run_id: str) -> StreamingResponse:
        """변경을 SSE로 민다 — 장면 1~4와 같은 모양(snapshot → ready → snapshot…)."""
        await run_in_threadpool(guard, process.get, demo_run_id)
        channel = f"sc05:{demo_run_id}"

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
