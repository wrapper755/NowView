"""
FastAPI — BPM 엔진의 HTTP 경계.

Next의 `/api/engine/*`가 이것을 프록시한다(BFF). 브라우저가 직접 부르지 않는다 —
CORS를 만들지 않고, LLM 자격증명을 서버에만 두고, 화면이 계속 `/api/*`만 알게 하려는
것이다. 실엔진 ↔ Mock 전환도 BFF 한 곳에 꽂힌다.

**무상태 계산기가 아니다.** 기존 `/api/bpm/state?step=N`은 진행 지점을 받아 계산해
돌려줬지만, 여기서는 인스턴스가 서버에 살아 있고 식별자가 `instanceId`다.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .agents import AgentContractError, make_runner
from .instances import InstanceStore, config_for, snapshot
from .spec import ProcessSpec

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger(__name__)

DB_PATH = os.getenv("NOWVIEW_ENGINE_DB", "engine-state.sqlite")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "kimi-k3:cloud")

app = FastAPI(
    title="NowView BPM Engine",
    version="0.1.0",
    description="LangGraph StateGraph 기반 BPM 런타임. 토폴로지는 요청으로 받는다.",
)

store = InstanceStore(
    DB_PATH,
    runner_factory=lambda mode: make_runner(mode, model=OLLAMA_MODEL, base_url=OLLAMA_URL),
)


class CreateRequest(BaseModel):
    spec: ProcessSpec
    #: `mock`이 기본이다 — 데모가 결정론적이어야 하고, LLM 호출은 비용·지연이 있다.
    agent_mode: str = Field(default="mock", alias="agentMode")
    #: true면 첫 사람 대기 지점 또는 종료까지 바로 진행한다.
    advance: bool = True

    model_config = {"populate_by_name": True}


class ResumeRequest(BaseModel):
    """
    사람의 입력으로 멈춘 그래프를 재개한다.

    승인 노드면 `{alternativeId, leverValue, rationale}`, 확인 노드면 아무 객체나 된다.
    검증은 엔진이 한다 — UI 버튼 비활성은 강제가 아니다.
    """

    payload: dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "db": DB_PATH,
        "ollama": {"url": OLLAMA_URL, "model": OLLAMA_MODEL},
        "instances": len(store.list_ids()),
    }


@app.get("/instances")
def list_instances() -> dict[str, Any]:
    return {"instances": store.list_ids()}


@app.post("/instances", status_code=201)
def create_instance(body: CreateRequest) -> dict[str, Any]:
    try:
        instance = store.create(body.spec, agent_mode=body.agent_mode)
    except ValueError as exc:
        # 명세 자체가 그래프로 성립하지 않는 경우다 — 400이 맞다.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if body.advance:
        _run(instance, None)
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
    after = snapshot(instance)
    # 입력이 반려되면 같은 지점에 error를 달고 다시 멈춘다 — 400이 아니라 그 상태를
    # 그대로 돌려준다. 클라이언트가 무엇이 틀렸는지 읽고 다시 보내면 된다.
    return after


@app.delete("/instances/{instance_id}", status_code=204)
def delete_instance(instance_id: str) -> None:
    _lookup(instance_id)
    store.delete(instance_id)


# ------------------------------------------------------------------ 내부


def _lookup(instance_id: str):
    try:
        return store.get(instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"없는 인스턴스: {instance_id}") from exc


def _run(instance, command: Any) -> None:
    """
    그래프를 다음 사람 대기 지점 또는 종료까지 돌린다.

    `interrupt`는 예외가 아니라 정상 종료다 — LangGraph가 체크포인트를 남기고
    invoke가 반환된다. 그래서 여기서 잡을 것은 Agent 계약 위반뿐이다.
    """
    try:
        instance.graph.invoke(
            command if command is not None else {"scenario_id": instance.spec.scenario_id},
            config_for(instance.id),
        )
    except AgentContractError as exc:
        # 지어낸 산출물로 메우지 않는다. 어느 Agent가 왜 실패했는지 그대로 알린다.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
