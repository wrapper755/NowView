"""
SC01 HTTP 경계 — `/sc01/*`. Next의 `/api/engine/*`가 프록시한다(BFF, 기존과 같다).

**행위자는 `X-Demo-Actor` 헤더로 온다.** 시연 환경의 역할 전환이다(설계서 2.3). 구현명세는
"actor는 로그인 세션에서 결정하고 클라이언트 역할값을 신뢰하지 않는다"(API-01)를 요구하지만
이 데모에는 인증이 없다(CLAUDE.md 5.4) — 헤더는 **신뢰 경계가 아니다.** 서버가 하는 일은
"그 사용자가 그 업무를 할 역할·담당인가"를 검사하는 것까지다. 인증이 붙으면 헤더 대신
세션에서 사용자를 꺼내면 되고, 검사 코드는 그대로다.

오류 코드는 API-03을 따른다: 권한 403 · 없음 404 · 상태·버전 충돌 409 · 입력 오류 422.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.events import KEEPALIVE_SECONDS, Hub
from app.sc01 import demo, domain
from app.sc01.domain import USERS, DomainError
from app.sc01.process import RECORD_OF_NODE, Sc01Process
from app.sc01.view import dashboard, topology, view


class CreateBody(BaseModel):
    case_id: str = Field(default="BASE", alias="caseId")
    #: BPMN을 누가 도는가 — embedded | studio | center (N2). 바깥이면 내장 BPM은 돌지 않는다.
    executor: str = "embedded"
    model_config = {"populate_by_name": True}


class ReceiveBody(BaseModel):
    fixture_id: str = Field(default="CP02", alias="fixtureId")
    model_config = {"populate_by_name": True}


class ActBody(BaseModel):
    answer: dict[str, Any] = Field(default_factory=dict)


class ResetBody(BaseModel):
    case_id: str | None = Field(default=None, alias="caseId")
    executor: str | None = None
    model_config = {"populate_by_name": True}


class ClockBody(BaseModel):
    at: str


def build_router(process: Sc01Process, hub: Hub) -> APIRouter:
    r = APIRouter(prefix="/sc01", tags=["sc01"])

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

    @r.get("/users")
    def users() -> list[dict[str, str]]:
        return [{"userId": k, **v} for k, v in USERS.items()]

    @r.get("/cases")
    def cases() -> list[dict[str, str]]:
        return [
            {"caseId": "BASE", "label": "기본 시연"},
            {"caseId": "EX08", "label": "EX08 Agent 응답 실패"},
        ]

    @r.get("/script")
    def script() -> list[dict[str, Any]]:
        return [
            {
                "index": i,
                "code": s.code,
                "at": s.at,
                "actor": s.actor,
                "nodeId": s.node_id,
                "label": s.label,
            }
            for i, s in enumerate(demo.BASE)
        ]

    @r.post("/demo-runs", status_code=201)
    def create(body: CreateBody, x_demo_actor: str | None = Header(default=None)) -> dict[str, Any]:
        return view(
            guard(
                process.create,
                case_id=body.case_id,
                actor=x_demo_actor or "u-demo",
                executor=body.executor,
            )
        )

    @r.get("/demo-runs")
    def list_runs() -> list[dict[str, Any]]:
        return process.store.list()

    @r.get("/demo-runs/{demo_run_id}")
    def get(demo_run_id: str) -> dict[str, Any]:
        return view(guard(process.get, demo_run_id))

    @r.get("/rules")
    def rules() -> dict[str, str]:
        """R01-v1 임계값. 화면이 기준을 따로 적지 않게 한다 — 시드가 바뀌면 함께 바뀐다."""
        return {k: str(v) for k, v in process.seed.rules.items()}

    @r.get("/customer-plans/{plan_id}")
    def customer_plan(plan_id: str) -> list[dict[str, Any]]:
        """시드의 고객계획 원천(CP01 등). UI02 변경 비교의 "직전 원천"이다."""
        rows = process.seed.customer_plans.get(plan_id)
        if rows is None:
            raise HTTPException(status_code=404, detail=f"없는 고객계획: {plan_id}")
        return [
            {"modelId": r.model_id, "period": r.period.isoformat(), "quantity": r.quantity}
            for r in rows
        ]

    @r.get("/demo-runs/{demo_run_id}/dashboard")
    def get_dashboard(
        demo_run_id: str,
        period: str = "연간",
        month: int = Query(7, ge=1, le=12),
        seq: int | None = Query(None, description="지난 시점(이력 seq)의 대시보드"),
    ):
        if seq is None:
            doc = guard(process.get, demo_run_id)
        else:
            doc = process.store.at(demo_run_id, seq)
            if doc is None:
                raise HTTPException(status_code=404, detail=f"없는 시점: {seq}")
        return guard(dashboard, doc, process.seed, period=period, month=month)

    @r.get("/demo-runs/{demo_run_id}/history")
    def history(demo_run_id: str) -> list[dict[str, Any]]:
        guard(process.get, demo_run_id)
        return process.store.history(demo_run_id)

    @r.get("/demo-runs/{demo_run_id}/history/{seq}")
    def at(demo_run_id: str, seq: int) -> dict[str, Any]:
        """지난 시점 — **읽기만** 한다. 실행을 되돌리지 않는다(4.6과 같은 원칙)."""
        doc = process.store.at(demo_run_id, seq)
        if doc is None:
            raise HTTPException(status_code=404, detail=f"없는 시점: {seq}")
        return view(domain.upgrade(doc), historical=True)

    # 쓰기 요청의 `Idempotency-Key` — 타임아웃 뒤 같은 키로 다시 보내면 다시 실행하지 않고 지금
    # 상태를 돌려준다. 같은 키에 다른 본문이면 409다(API-01·03).
    @r.post("/demo-runs/{demo_run_id}/sources/receive")
    def receive(
        demo_run_id: str,
        body: ReceiveBody,
        x_demo_actor: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ):
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
                idempotency_key=idempotency_key,
            )
        )

    # 시스템 작업 — 바깥 BPM(Chaeksas 외부 확장 `nowview-sc01`, HTTP 어댑터)이 서비스 태스크에서
    # 부른다. 내장 BPM의 `_InProcessCalls`와 같은 함수·같은 출력이다(`process.run_operation`).
    # 사람의 업무가 아니라서 행위자 헤더를 받지 않는다 — 감사 이력에는 `system`으로 남는다.
    # 본문에는 언제나 바깥 실행의 `chaeksas_run_id`(`{{run_id}}`)와 `chaeksas_node_id`
    # (`{{node_id}}`)가 실린다 — 데모 실행을 그 실행에 묶는 열쇠다(N2).
    def operate(demo_run_id: str, operation: str, body: dict[str, Any], **args: Any):
        rest = dict(body)
        run_id, node_id = rest.pop("chaeksas_run_id", None), rest.pop("chaeksas_node_id", None)
        return guard(
            process.operate,
            demo_run_id,
            operation,
            {**rest, **args},
            external_run_id=run_id,
            node_id=node_id,
        )

    link = Body(default_factory=dict)

    @r.post("/demo-runs/{demo_run_id}/sources/{source_id}/validation")
    def validate_source(
        demo_run_id: str, source_id: str, body: dict[str, Any] = link
    ) -> dict[str, Any]:
        """원천 자동 검증(UI03-01) → `{passed, error_count}`."""
        return operate(demo_run_id, "validate_source", body, source_id=source_id)

    @r.post("/demo-runs/{demo_run_id}/sources/{source_id}/comparison")
    def compare(demo_run_id: str, source_id: str, body: dict[str, Any] = link) -> dict[str, Any]:
        """확인된 원천으로 전망 생성·지표 계산 → `{run_id, risk, issue_id}`. 확인 전이면 409."""
        return operate(demo_run_id, "compare", body, source_id=source_id)

    @r.post("/demo-runs/{demo_run_id}/calc-runs/{run_id}/agent-draft")
    def request_agent_draft(
        demo_run_id: str, run_id: str, body: dict[str, Any] = link
    ) -> dict[str, Any]:
        """Agent 검토 초안 요청(AG-01) → `{output_id}`. 기다리지 않는다 — 초안은 배경에서 만든다."""
        return operate(demo_run_id, "request_agent_draft", body, run_id=run_id)

    @r.post("/demo-runs/{demo_run_id}/calc-runs/{run_id}/handoff")
    def hand_off(demo_run_id: str, run_id: str, body: dict[str, Any] = link) -> dict[str, Any]:
        """장면 인계 기록(UI06-01) → `{handed_off}`. 조건 미충족이면 409."""
        return operate(demo_run_id, "hand_off", body, run_id=run_id)

    @r.post("/demo-runs/{demo_run_id}/answers/{node_id}")
    def record_answer(
        demo_run_id: str, node_id: str, body: dict[str, Any] = link
    ) -> dict[str, Any]:
        """
        사람 결정의 기록(N1) — 결재 뒤의 서비스 태스크가 부른다. 결재가 Studio·Center 어디서
        닫혔든 업무 효과(원천 확인·검토 의견·배정·인수)가 이 길로 난다. 업무 규칙 위반은 409·422다.
        """
        operation = RECORD_OF_NODE.get(node_id)
        if operation is None:
            raise HTTPException(404, f"기록할 결재가 아니다: {node_id}")
        return operate(demo_run_id, operation, body, node_id=node_id)

    @r.post("/demo-runs/{demo_run_id}/agent/{run_id}/regenerate")
    def regenerate(
        demo_run_id: str, run_id: str, x_demo_actor: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Agent 초안 재생성(AG-01). 이전 초안은 보존된다."""
        return view(guard(process.regenerate, demo_run_id, run_id, actor=actor_of(x_demo_actor)))

    @r.post("/demo-runs/{demo_run_id}/agent-outputs/{output_id}/adopt")
    def adopt(
        demo_run_id: str, output_id: str, x_demo_actor: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """초안 채택 기록(AG-03)."""
        return view(guard(process.adopt, demo_run_id, output_id, actor=actor_of(x_demo_actor)))

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
        """S0로 되돌린다. `caseId`를 주면 그 시연 사례로 다시 시작한다(BASE · EX08)."""
        case = body.case_id if body else None
        where = body.executor if body else None
        return view(
            guard(
                process.reset,
                demo_run_id,
                actor=actor_of(x_demo_actor),
                case_id=case,
                executor=where,
            )
        )

    @r.get("/demo-runs/{demo_run_id}/events")
    async def events(request: Request, demo_run_id: str) -> StreamingResponse:
        """변경을 SSE로 민다. 모양은 `/events`와 같다(snapshot → ready → snapshot…)."""
        await run_in_threadpool(guard, process.get, demo_run_id)
        channel = f"sc01:{demo_run_id}"

        async def emit() -> str:
            doc = await run_in_threadpool(process.get, demo_run_id)
            return f"event: snapshot\ndata: {json.dumps(view(doc), ensure_ascii=False)}\n\n"

        async def generate():
            yield await emit()
            yield f"event: ready\ndata: {json.dumps({'demoRunId': demo_run_id})}\n\n"
            last = asyncio.get_running_loop().time()
            async with hub.subscribe([channel]) as queue:
                while True:
                    # 알림이든 안전망 재조회(None)든 같은 것을 보낸다 — 채널이 하나뿐이다.
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
