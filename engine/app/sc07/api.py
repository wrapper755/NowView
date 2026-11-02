"""
SC07 HTTP 경계 — `/sc07/*`. Next의 `/api/engine/sc07/*`가 그대로 중계한다(BFF).

**조회 서비스는 읽기 전용이고 멱등이다**(구현명세 6장) — 보기 전환·새로고침으로 승인·배포·적용
이벤트가
생기지 않는다(AT712). 모든 조회 응답에 `dataset_version`·`improvement_id`·`version_bundle`·`as_of`를
싣는다.
오류는 `error_code`를 함께 낸다: 403 ACCESS_DENIED(근거 본문·상세 사유를 싣지 않는다) · 404
NOT_FOUND · 409
VERSION_MISMATCH · 422 DATA_INVALID.

**확인·적용 절차는 BPM이다**(`processes/sc07.bpmn`) — 착수·결재 답·각본·초기화는 장면 1~6과 같은
경로이고,
시스템 작업은 엔진의 C15 일꾼이 Center에서 가져간다(`app/consumer.py`). 설정 확인의 「일치」가
연결된 레코드와
어긋나면 422 `SETTING_MISMATCH`에 `blocking_items`를 싣는다. 행위자는 `X-Demo-Actor` 헤더다 — 신뢰
경계가 아니다(5.4).

경로는 구현명세 6장의 논리 조회에 데모 실행을 앞에 붙였다(`/demo-runs/{id}/improvements/IMP71` …) —
데모 실행끼리는 서로 보지 않는다(DATA-05).
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
from app.sc07 import confirm, demo, domain
from app.sc07.process import Sc07Process
from app.sc07.view import topology
from app.sc07.view import view as render

_BODY = Body(default_factory=dict)


class CreateBody(BaseModel):
    #: 이어 갈 데모 실행(장면 1~6과 같은 id). 없으면 장면 1부터 새로 만들어 장면 6 대표 보고까지
    #: 돌린다.
    sc01_demo_run_id: str | None = Field(default=None, alias="sc01DemoRunId")
    case_id: str = Field(default="BASE", alias="caseId")
    #: 확인·적용 절차를 돌릴 곳(장면 1~6이 아직 없으면 그 장면들도) — center(기본) | studio. 화면은
    #: 내장을 고르지 않는다(2026-10-27 결정).
    executor: str = "center"
    model_config = {"populate_by_name": True}


class ResetBody(BaseModel):
    executor: str | None = None


class ActBody(BaseModel):
    answer: dict[str, Any] = Field(default_factory=dict)


def build_router(
    process: Sc07Process,
    hub: Hub | None = None,
    preparations: Preparations | None = None,
) -> APIRouter:
    r = APIRouter(prefix="/sc07", tags=["sc07"])
    prep = preparations or Preparations()
    events_hub = hub or Hub()

    def guard(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except confirm.PrerequisiteError as exc:
            raise HTTPException(
                status_code=exc.status,
                detail={"message": str(exc), "error_code": exc.code, "blocking_items": exc.items},
            ) from exc
        except domain.ReadError as exc:
            raise HTTPException(
                status_code=exc.status, detail={"message": str(exc), "error_code": exc.code}
            ) from exc
        except DomainError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc

    def meta(doc: dict, **kwargs: Any) -> dict[str, Any]:
        """
        문서 머리 — 개선건·버전 묶음·확인·적용 절차(대기·결재 폼·기록). 내용은 조회 서비스로 받는다.
        """
        return render(doc, center=process.center.config, **kwargs)

    def actor_of(value: str | None) -> str:
        if not value:
            raise HTTPException(status_code=403, detail="X-Demo-Actor 헤더가 필요하다")
        return value

    @r.get("/process")
    def get_process() -> dict[str, Any]:
        return topology(process.process)

    @r.get("/script")
    def script(case_id: str = "BASE") -> list[dict[str, Any]]:
        if case_id not in domain.CASES:
            raise HTTPException(422, f"모르는 시연 사례: {case_id}")
        return [
            {
                "index": i,
                "code": s.code,
                "actor": s.actor,
                "kind": s.kind,
                "nodeId": s.node_id,
                "label": s.label,
                "record": s.record,
            }
            for i, s in enumerate(demo.steps_for(case_id, process.seed))
        ]

    @r.get("/cases")
    def cases() -> list[dict[str, str]]:
        return [{"caseId": k, "label": v} for k, v in domain.CASES.items()]

    @r.post("/demo-runs", status_code=201)
    def create(body: CreateBody, response: Response) -> dict[str, Any]:
        """
        시작 — 앞 장면이 끝나 있지 않으면 각본으로 끝까지 실행한다. 오래 걸리면 202와 준비 상태를
        돌려주고 배경에서 잇는다(`app.preparation`). 화면은 `…/preparation`을 읽는다.
        """
        actor = "u-demo"

        def make(rid: str) -> dict:
            return process.create(
                sc01_demo_run_id=rid,
                case_id=body.case_id,
                executor=body.executor,
            )

        doc, rid = guard(
            begin_scene,
            prep,
            "sc07",
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
            return guard(preparing, prep, "sc07", process, rid)
        return meta(doc)

    @r.get("/demo-runs/{demo_run_id}/preparation")
    def preparation(demo_run_id: str) -> dict[str, Any]:
        """시작 준비 상태 — 진행 중(앞 장면들의 지금 단계)·끝남·실패(사유·상태 코드)."""
        return guard(preparing, prep, "sc07", process, demo_run_id)

    @r.get("/demo-runs/{demo_run_id}")
    def get(demo_run_id: str) -> dict[str, Any]:
        return meta(guard(process.get, demo_run_id))

    @r.get("/demo-runs/{demo_run_id}/improvements/{improvement_id}")
    def improvement(
        demo_run_id: str,
        improvement_id: str,
        dataset_version: str | None = None,
        x_demo_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """U701 상태 A — 개선 사유·기존 검토(AG62 원본)·개선한 검토 방식·기준·절차."""
        guard(domain.check_improvement, improvement_id)
        doc = guard(process.get, demo_run_id)
        return guard(domain.improvement, doc, actor=x_demo_actor, dataset_version=dataset_version)

    @r.get("/demo-runs/{demo_run_id}/improvements/{improvement_id}/verification")
    def verification(
        demo_run_id: str,
        improvement_id: str,
        dataset_version: str | None = None,
        x_demo_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """U701 상태 B 왼쪽 — TC701 상세와 TC702~708 요약(미실행이면 미실행)."""
        guard(domain.check_improvement, improvement_id)
        doc = guard(process.get, demo_run_id)
        return guard(domain.verification, doc, actor=x_demo_actor, dataset_version=dataset_version)

    @r.get("/demo-runs/{demo_run_id}/applications/{application_id}")
    def application(
        demo_run_id: str,
        application_id: str,
        dataset_version: str | None = None,
        x_demo_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """U701 상태 B 오른쪽 — 범위·버전·확인 이력·설정 반영·운영 실행(미확인)·후속 점검."""
        guard(domain.check_application, application_id)
        doc = guard(process.get, demo_run_id)
        return guard(domain.application, doc, actor=x_demo_actor, dataset_version=dataset_version)

    @r.get("/demo-runs/{demo_run_id}/evidence/{evidence_id}")
    def evidence(
        demo_run_id: str, evidence_id: str, x_demo_actor: str | None = Header(default=None)
    ) -> dict[str, Any]:
        doc = guard(process.get, demo_run_id)
        return guard(domain.evidence, doc, evidence_id, actor=x_demo_actor)

    @r.get("/demo-runs/{demo_run_id}/history")
    def history(demo_run_id: str) -> list[dict[str, Any]]:
        guard(process.get, demo_run_id)
        return process.store.history(demo_run_id)

    @r.get("/demo-runs/{demo_run_id}/history/{seq}")
    def at(demo_run_id: str, seq: int) -> dict[str, Any]:
        doc = process.store.at(demo_run_id, seq)
        if doc is None:
            raise HTTPException(status_code=404, detail=f"없는 시점: {seq}")
        return meta(doc, historical=True)

    @r.post("/demo-runs/{demo_run_id}/start")
    def start(
        demo_run_id: str,
        x_demo_actor: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """확인 착수 — 재착수는 기존 결과를 돌려준다(두 번째 절차를 만들지 않는다)."""
        return meta(
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
        return meta(
            guard(
                process.act,
                demo_run_id,
                node_id,
                body.answer,
                actor=actor_of(x_demo_actor),
                idempotency_key=idempotency_key,
            )
        )

    @r.post("/demo-runs/{demo_run_id}/script/{index}")
    def step(demo_run_id: str, index: int) -> dict[str, Any]:
        """시연 단계 실행 — 각본의 행위자로 실제 전환을 실행한다. 지난 단계 재실행은 무해하다."""
        return meta(guard(demo.run_step, process, demo_run_id, index))

    @r.post("/demo-runs/{demo_run_id}/reset")
    def reset(
        demo_run_id: str,
        body: ResetBody | None = None,
        x_demo_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """확인 절차만 확인 전으로 — 적재(개선·입력·근거)는 그대로다. 실행 위치를 바꿀 수 있다."""
        return meta(
            guard(
                process.reset,
                demo_run_id,
                actor=actor_of(x_demo_actor),
                executor=body.executor if body else None,
            )
        )

    @r.get("/demo-runs/{demo_run_id}/events")
    async def events(request: Request, demo_run_id: str) -> StreamingResponse:
        """변경을 SSE로 민다 — 장면 1~6과 같은 모양(snapshot → ready → snapshot…).
        조회는 변경이 아니다."""
        await run_in_threadpool(guard, process.get, demo_run_id)
        channel = f"sc07:{demo_run_id}"

        async def emit() -> str:
            doc = await run_in_threadpool(process.get, demo_run_id)
            return f"event: snapshot\ndata: {json.dumps(meta(doc), ensure_ascii=False)}\n\n"

        async def generate():
            yield await emit()
            yield f"event: ready\ndata: {json.dumps({'demoRunId': demo_run_id})}\n\n"
            last = asyncio.get_running_loop().time()
            async with events_hub.subscribe([channel]) as queue:
                while True:
                    await events_hub.wait(queue)
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
