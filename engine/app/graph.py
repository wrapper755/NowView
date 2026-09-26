"""
명세 → LangGraph StateGraph 조립.

**이 파일이 이번 작업의 본질이다.** 지금까지 BPM "상태 머신"은 배열 인덱스였다 —
분기도 사람 승인도 실제로 일어나지 않고 파생될 뿐이었다(CLAUDE.md 4.5). 여기서는
그래프가 진짜로 멈추고(`interrupt`) 진짜로 재개된다(`Command(resume=...)`).

경로가 바뀐다는 점이 가장 중요하다. TS의 `sequence`는 **미리 선언된** 경로였는데,
여기서는 게이트웨이가 Agent의 판정을 읽어 그때 고른다. 같은 명세로 두 경로가 나온다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .agents import AgentRunner
from .spec import ProcessSpec
from .state import ProcessState

log = logging.getLogger(__name__)


@dataclass
class BuiltGraph:
    graph: Any
    #: 조립 중 발견한 명세의 문제. 조용히 삼키지 않고 API 응답에 싣는다.
    warnings: list[str] = field(default_factory=list)


def required_flags_for(spec: ProcessSpec, node_id: str) -> list[str]:
    """
    이 노드가 만들어 줘야 하는 판정 플래그.

    노드에서 **바로 이어지는** 게이트웨이가 읽는 플래그다. 전체 게이트웨이의
    플래그를 모든 Agent에 요구하면 관계없는 판정을 억지로 하게 된다.
    """
    flags: list[str] = []
    for edge in spec.outgoing(node_id):
        gateway = spec.gateway(edge.target)
        if gateway and gateway.flag not in flags:
            flags.append(gateway.flag)
    return flags


def build_graph(
    spec: ProcessSpec,
    *,
    runner: AgentRunner,
    checkpointer: BaseCheckpointSaver,
) -> BuiltGraph:
    warnings: list[str] = []
    builder: StateGraph = StateGraph(ProcessState)

    for node in spec.nodes:
        builder.add_node(node.id, _make_node(spec, node, runner))

    # 시작점 — `start` 종류 노드가 있으면 그것, 없으면 들어오는 엣지가 없는 노드.
    entry = next((n.id for n in spec.nodes if n.kind == "start"), None)
    if entry is None:
        targets = {e.target for e in spec.edges}
        candidates = [n.id for n in spec.nodes if n.id not in targets]
        if len(candidates) != 1:
            raise ValueError(f"시작 노드를 특정할 수 없다: {candidates}")
        entry = candidates[0]
        warnings.append(f"`start` 종류 노드가 없어 {entry}를 시작점으로 썼다.")
    builder.add_edge(START, entry)

    for node in spec.nodes:
        outgoing = spec.outgoing(node.id)
        gateway = spec.gateway(node.id)

        if gateway is not None:
            missing = [
                t for t in (gateway.when_true, gateway.when_false)
                if t not in {n.id for n in spec.nodes}
            ]
            if missing:
                raise ValueError(f"게이트웨이 {node.id}의 분기 대상이 명세에 없다: {missing}")
            builder.add_conditional_edges(
                node.id,
                _make_router(gateway.flag, gateway.when_true, gateway.when_false),
                {gateway.when_true: gateway.when_true, gateway.when_false: gateway.when_false},
            )
            continue

        if node.kind == "end":
            builder.add_edge(node.id, END)
            continue

        if not outgoing:
            # 실엔진이 드러내는 명세의 구멍이다. TS에서는 이 노드가 `sequence`에
            # 없어 `skipped`로 조용히 넘어가므로 아무도 눈치채지 못한다.
            warnings.append(
                f"{node.id}({node.label})에 나가는 엣지가 없어 END로 연결했다. "
                "분기 종료 경로가 명세에 정의되지 않았다."
            )
            builder.add_edge(node.id, END)
            continue

        if len(outgoing) > 1:
            raise ValueError(
                f"{node.id}에 엣지가 {len(outgoing)}개인데 게이트웨이 규칙이 없다 — "
                "분기 조건을 명세에 넣어야 한다."
            )
        builder.add_edge(node.id, outgoing[0].target)

    return BuiltGraph(graph=builder.compile(checkpointer=checkpointer), warnings=warnings)


# ------------------------------------------------------------------ 노드 구현


def _make_node(spec: ProcessSpec, node, runner: AgentRunner):
    if node.kind == "agent-task":
        return _agent_node(spec, node, runner)
    if node.kind == "user-task":
        return _user_node(spec, node)
    return _passthrough_node(node)


def _passthrough_node(node):
    """`start` · `end` · `service-task` · `gateway` — 지나간 사실만 남긴다."""

    def run(_state: ProcessState) -> dict[str, Any]:
        return {"visited": [node.id]}

    run.__name__ = f"node_{node.id.replace('-', '_')}"
    return run


def _agent_node(spec: ProcessSpec, node, runner: AgentRunner):
    required = required_flags_for(spec, node.id)

    def run(state: ProcessState) -> dict[str, Any]:
        agent = next((a for a in spec.agents if a.id == node.agent_id), None)
        result = runner.run(
            spec=spec, node=node, agent=agent, required_flags=required, state=dict(state)
        )
        flags = result.pop("flags", {})
        return {"visited": [node.id], "runs": [result], "flags": flags}

    run.__name__ = f"agent_{node.id.replace('-', '_')}"
    return run


def _user_node(spec: ProcessSpec, node):
    """
    사람이 수행하는 노드. **여기서 그래프가 실제로 멈춘다.**

    승인 노드면 대안 선택을 받고, 아니면 확인만 받는다. 어느 쪽인지는 명세가
    알려 준다 — 단계 이름으로 짚으면 시나리오마다 깨진다.
    """
    is_decision = spec.decision_node_id == node.id
    min_length = spec.decision_rules.rationale_min_length

    def run(_state: ProcessState) -> dict[str, Any]:
        request: dict[str, Any] = {
            "kind": "decision" if is_decision else "acknowledgement",
            "nodeId": node.id,
            "label": node.label,
            "actor": node.actor,
            # 대기 사유다 — 완료된 산출물이 아니다(CLAUDE.md 4.5).
            "note": node.outcome,
        }
        if is_decision:
            request["alternatives"] = [a.model_dump() for a in spec.alternatives]
            request["rationaleMinLength"] = min_length

        # 잘못된 입력에 죽지 않고 다시 묻는다. 스레드를 깨뜨리면 진행 중인
        # 인스턴스를 되살릴 방법이 없다.
        while True:
            answer = interrupt(request)
            problem = _validate_answer(answer, is_decision, spec, min_length)
            if problem is None:
                break
            log.info("%s 승인 입력 반려: %s", node.id, problem)
            request = {**request, "error": problem}

        if not is_decision:
            return {"visited": [node.id], "acknowledged": [node.id]}
        return {
            "visited": [node.id],
            "decision": {
                "nodeId": node.id,
                "alternativeId": answer["alternativeId"],
                "leverValue": answer.get("leverValue"),
                "rationale": answer["rationale"].strip(),
                "decidedBy": answer.get("decidedBy") or node.actor,
                # 결정 시각은 "무슨 일이 일어났는가"의 일부이므로 엔진이 남긴다.
                # 화면이 찍으면 새로고침할 때마다 값이 달라진다.
                "decidedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
            },
        }

    run.__name__ = f"user_{node.id.replace('-', '_')}"
    return run


def _validate_answer(
    answer: Any, is_decision: bool, spec: ProcessSpec, min_length: int
) -> str | None:
    """
    승인 입력 검증. **UI 버튼 비활성은 강제가 아니다** — API를 직접 부르면 우회되므로
    엔진에서도 막는다(CLAUDE.md 4.3과 같은 이유).
    """
    if not isinstance(answer, dict):
        return "응답이 객체가 아니다."
    if not is_decision:
        return None
    if not answer.get("alternativeId"):
        return "대안을 선택해야 한다."
    allowed = {a.id for a in spec.alternatives}
    if allowed and answer["alternativeId"] not in allowed:
        return f"명세에 없는 대안이다: {answer['alternativeId']}"
    rationale = (answer.get("rationale") or "").strip()
    if len(rationale) < min_length:
        return f"결정 사유를 {min_length}자 이상 적어야 한다 (현재 {len(rationale)}자)."
    return None


def _make_router(flag: str, when_true: str, when_false: str):
    """
    결정론적 분기. 플래그가 없으면 `when_false`다 — 판정되지 않은 것을 "조정 필요"로
    보면 에스컬레이션이 기본값이 되어 현업 통제 경로가 죽는다.
    """

    def route(state: ProcessState) -> str:
        return when_true if (state.get("flags") or {}).get(flag) else when_false

    return route
