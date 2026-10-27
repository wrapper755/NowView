"""
SC03 HTTP 경계 — `/sc03/*`. Next의 `/api/engine/sc03/*`가 그대로 중계한다(BFF).

장면 1·2와 같은 규칙이다. 행위자는 `X-Demo-Actor` 헤더 — 신뢰 경계가 아니다(5.4). 오류 코드: 권한
403 ·
없음 404 · 상태·버전·멱등키 충돌 409 · 필수조건·계산 실패 422(구현명세 11장). 완료 조건 미충족은
422에
`error_code`·`blocking_items`를 싣는다 — 화면이 남은 항목을 그대로 보인다. 쓰기의
`Idempotency-Key`도 같다.
시스템 작업(`/operations/{이름}`)은 바깥 Chaeksas가 부르고 키를 검사한다(N6).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException
from fastapi.requests import Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.events import KEEPALIVE_SECONDS, Hub
from app.sc01.auth import SystemAuth
from app.sc01.domain import DomainError
from app.sc03 import demo, domain
from app.sc03.process import Sc03Process
from app.sc03.view import topology
from app.sc03.view import view as render

_BODY = Body(default_factory=dict)


class CreateBody(BaseModel):
    #: 이어 갈 데모 실행(장면 1·2와 같은 id). 없으면 장면 1부터 새로 만들어 장면 2 인수까지 돌린다.
    sc01_demo_run_id: str | None = Field(default=None, alias="sc01DemoRunId")
    case_id: str = Field(default="BASE", alias="caseId")
    #: center(기본) | studio. 화면은 내장을 고르지 않는다(2026-10-27 결정).
    executor: str = "center"
    model_config = {"populate_by_name": True}


class ResetBody(BaseModel):
    executor: str | None = None


class ActBody(BaseModel):
    answer: dict[str, Any] = Field(default_factory=dict)
    #: 화면이 본 보고버전(`report`)·배정버전(`assignment`) — 오래된 것의 확정·인수를 막는다.
    expect: dict[str, Any] | None = None


class RecordBody(BaseModel):
    record_type: str = Field(alias="type")
    subject: str = ""
    content: str
    related: str = ""
    model_config = {"populate_by_name": True}


class AgentBody(BaseModel):
    kind: str = "AG31"


class TaskDraftBody(BaseModel):
    changes: dict[str, Any]
    reason: str


class RevisionBody(BaseModel):
    reason: str


class ClockBody(BaseModel):
    at: str


def build_router(process: Sc03Process, hub: Hub, auth: SystemAuth | None = None) -> APIRouter:
    r = APIRouter(prefix="/sc03", tags=["sc03"])
    system_auth = auth or SystemAuth.from_env()

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
    def create(body: CreateBody, x_demo_actor: str | None = Header(default=None)) -> dict[str, Any]:
        return view(
            guard(
                process.create,
                sc01_demo_run_id=body.sc01_demo_run_id,
                case_id=body.case_id,
                actor=x_demo_actor or "u-demo",
                executor=body.executor,
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

    @r.post("/demo-runs/{demo_run_id}/start")
    def start(
        demo_run_id: str,
        x_demo_actor: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """S31 착수 — 같은 검토건의 재착수는 기존 결과를 돌려준다(T31)."""
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

    @r.post("/demo-runs/{demo_run_id}/meetings/MT31/records")
    def meeting_record(
        demo_run_id: str, body: RecordBody, x_demo_actor: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """회의 질의·답변·설명 — 참석자만(BPM 밖의 회의 기록)."""
        return view(
            guard(
                process.meeting_record,
                demo_run_id,
                record_type=body.record_type,
                subject=body.subject,
                content=body.content,
                related=body.related,
                actor=actor_of(x_demo_actor),
            )
        )

    @r.post("/demo-runs/{demo_run_id}/agent-drafts")
    def agent(
        demo_run_id: str, body: AgentBody, x_demo_actor: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return view(guard(process.agent, demo_run_id, body.kind, actor=actor_of(x_demo_actor)))

    @r.post("/demo-runs/{demo_run_id}/agent-outputs/{output_id}/adopt")
    def adopt(
        demo_run_id: str, output_id: str, x_demo_actor: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return view(guard(process.adopt, demo_run_id, output_id, actor=actor_of(x_demo_actor)))

    @r.post("/demo-runs/{demo_run_id}/tasks/{task_id}/draft")
    def task_draft(
        demo_run_id: str,
        task_id: str,
        body: TaskDraftBody,
        x_demo_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """과제 초안 수정(배정 전) — 전후값을 남긴다. 배정된 과제는 재배정 결재로만 바꾼다."""
        return view(
            guard(
                process.edit_task,
                demo_run_id,
                task_id,
                body.changes,
                reason=body.reason,
                actor=actor_of(x_demo_actor),
            )
        )

    @r.post("/demo-runs/{demo_run_id}/forecast-revisions")
    def revision(
        demo_run_id: str, body: RevisionBody, x_demo_actor: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """E34 새 전망 버전 — 확정본은 그대로, 별도 실행·보고버전(REVISION_PENDING)."""
        return view(
            guard(
                process.revise_forecast,
                demo_run_id,
                reason=body.reason,
                actor=actor_of(x_demo_actor),
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
        """선택 실행만 D30으로. 실행 위치를 바꿀 수 있다. 사례를 바꾸려면 새 데모 실행이다."""
        return view(
            guard(
                process.reset,
                demo_run_id,
                actor=actor_of(x_demo_actor),
                executor=body.executor if body else None,
            )
        )

    @r.post("/demo-runs/{demo_run_id}/operations/{operation}")
    def operate(
        demo_run_id: str,
        operation: str,
        body: dict[str, Any] = _BODY,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """
        시스템 작업 — 바깥 BPM(외부 확장 `nowview-sc03`)이 서비스 태스크에서 부른다. 행위자 헤더가
        없다.
        `chaeksas_run_id`가 데모 실행을 그 실행에 묶고, 키가 실행 위치를 말한다(N6).
        """
        via = guard(system_auth.executor_of, authorization)
        rest = dict(body)
        run_id, node_id = rest.pop("chaeksas_run_id", None), rest.pop("chaeksas_node_id", None)
        return guard(
            process.operate,
            demo_run_id,
            operation,
            rest,
            external_run_id=run_id,
            node_id=node_id,
            via=via,
        )

    @r.get("/demo-runs/{demo_run_id}/events")
    async def events(request: Request, demo_run_id: str) -> StreamingResponse:
        """변경을 SSE로 민다 — 장면 1·2와 같은 모양(snapshot → ready → snapshot…)."""
        await run_in_threadpool(guard, process.get, demo_run_id)
        channel = f"sc03:{demo_run_id}"

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
