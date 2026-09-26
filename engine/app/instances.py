"""
프로세스 인스턴스의 생명주기.

**상태 소유권이 여기로 넘어온다.** TS 쪽에서는 클라이언트(Zustand)가 진행 지점을
들고 있고 서버는 무상태 계산기였다(CLAUDE.md 4.3). 여기서는 LangGraph checkpointer가
인스턴스를 소유한다 — 생성·조회·재개·종료라는 개념이 처음으로 생긴다.

명세도 함께 저장한다. 체크포인트만 남기면 프로세스를 재시작한 뒤 그래프를 다시
조립할 수 없어 진행 중인 인스턴스가 되살아나지 않는다.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

from .agents import AgentRunner
from .graph import build_graph
from .spec import ProcessSpec

#: 노드 상태. TS의 `BpmNodeStatus`와 같은 어휘를 쓴다.
NodeStatus = str


@dataclass
class Instance:
    id: str
    spec: ProcessSpec
    graph: Any
    warnings: list[str]
    agent_mode: str


class InstanceStore:
    """
    `runner_factory`를 받는 이유: 재개할 때 **생성 시와 같은 Agent 모드**로 그래프를
    다시 조립해야 한다. Mock으로 시작한 인스턴스를 LLM으로 재개하면 앞뒤 산출물의
    출처가 섞여 어느 것이 실제 호출인지 알 수 없게 된다.
    """

    def __init__(
        self,
        db_path: str = ":memory:",
        *,
        runner_factory: Callable[[str], AgentRunner],
    ) -> None:
        self._runner_factory = runner_factory
        # check_same_thread=False — FastAPI의 동기 엔드포인트는 스레드풀에서 돈다.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS instance_spec ("
            "  id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, spec TEXT NOT NULL,"
            "  agent_mode TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        self._conn.commit()
        self.checkpointer = SqliteSaver(self._conn)
        self.checkpointer.setup()
        self._cache: dict[str, Instance] = {}

    # --------------------------------------------------------------- 생명주기

    def create(self, spec: ProcessSpec, *, agent_mode: str) -> Instance:
        instance_id = f"inst-{uuid.uuid4().hex[:12]}"
        runner = self._runner_factory(agent_mode)
        built = build_graph(spec, runner=runner, checkpointer=self.checkpointer)
        self._conn.execute(
            "INSERT INTO instance_spec (id, scenario_id, spec, agent_mode) VALUES (?,?,?,?)",
            (instance_id, spec.scenario_id, spec.model_dump_json(), agent_mode),
        )
        self._conn.commit()
        instance = Instance(
            id=instance_id,
            spec=spec,
            graph=built.graph,
            warnings=built.warnings,
            agent_mode=agent_mode,
        )
        self._cache[instance_id] = instance
        return instance

    def get(self, instance_id: str) -> Instance:
        cached = self._cache.get(instance_id)
        if cached is not None:
            return cached
        row = self._conn.execute(
            "SELECT spec, agent_mode FROM instance_spec WHERE id = ?", (instance_id,)
        ).fetchone()
        if row is None:
            raise KeyError(instance_id)
        # 재시작 후 복구 경로. 명세를 저장해 둔 값이 여기서 나온다.
        spec = ProcessSpec.model_validate_json(row[0])
        built = build_graph(
            spec, runner=self._runner_factory(row[1]), checkpointer=self.checkpointer
        )
        instance = Instance(
            id=instance_id, spec=spec, graph=built.graph, warnings=built.warnings, agent_mode=row[1]
        )
        self._cache[instance_id] = instance
        return instance

    def list_ids(self) -> list[dict[str, str]]:
        rows = self._conn.execute(
            "SELECT id, scenario_id, agent_mode, created_at FROM instance_spec "
            "ORDER BY created_at DESC"
        ).fetchall()
        return [
            {"instanceId": r[0], "scenarioId": r[1], "agentMode": r[2], "createdAt": r[3]}
            for r in rows
        ]

    def delete(self, instance_id: str) -> None:
        self._conn.execute("DELETE FROM instance_spec WHERE id = ?", (instance_id,))
        self._conn.commit()
        self._cache.pop(instance_id, None)
        try:
            self.checkpointer.delete_thread(instance_id)
        except Exception:  # noqa: BLE001 — checkpointer 구현에 따라 없을 수 있다
            pass


def config_for(instance_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": instance_id}}


# --------------------------------------------------------------- 스냅샷 파생


def derive_node_statuses(
    spec: ProcessSpec, visited: list[str], frontier: list[str], waiting: set[str]
) -> dict[str, NodeStatus]:
    """
    노드 상태를 파생한다. 저장하지 않는다 — TS와 같은 원칙이다(CLAUDE.md 4.5).

    **미실행 판정이 TS보다 정확하다.** TS는 `sequence`에 없는 노드를 처음부터
    `skipped`로 봤지만, 실제로는 게이트웨이가 돌기 전까지 그 분기는 아직
    `pending`이다. 분기가 확정된 뒤에야 미실행이 된다.
    """
    # 대기 중인 노드도 출발점에 넣는다. 승인 입력이 반려되어 같은 지점에 다시 멈추면
    # LangGraph가 `next`를 비워 주는데, 그것만 쓰면 뒤 노드 전체가 `skipped`로
    # 떨어진다 — 반려는 아무것도 건너뛰지 않았으므로 틀린 표시다.
    reachable = _reachable_from(spec, [*frontier, *sorted(waiting)])
    statuses: dict[str, NodeStatus] = {}
    for node in spec.nodes:
        if node.id in waiting:
            statuses[node.id] = "waiting"
        elif node.id in visited:
            statuses[node.id] = "done"
        elif node.id in frontier:
            statuses[node.id] = "active"
        elif node.id in reachable:
            statuses[node.id] = "pending"
        else:
            statuses[node.id] = "skipped"
    return statuses


def _reachable_from(spec: ProcessSpec, frontier: list[str]) -> set[str]:
    """
    현재 지점에서 앞으로 도달할 수 있는 노드.

    아직 돌지 않은 게이트웨이는 양쪽 다 도달 가능으로 본다 — 어느 쪽으로 갈지는
    Agent 판정에 달려 있어 아직 모른다. 이미 지난 게이트웨이의 안 간 쪽은 자연히
    도달 불가가 되어 `skipped`로 떨어진다.
    """
    seen: set[str] = set()
    queue = deque(frontier)
    while queue:
        current = queue.popleft()
        for edge in spec.outgoing(current):
            if edge.target not in seen:
                seen.add(edge.target)
                queue.append(edge.target)
        gateway = spec.gateway(current)
        if gateway:
            for target in (gateway.when_true, gateway.when_false):
                if target not in seen:
                    seen.add(target)
                    queue.append(target)
    return seen


def snapshot(instance: Instance) -> dict[str, Any]:
    state = instance.graph.get_state(config_for(instance.id))
    values: dict[str, Any] = state.values or {}
    visited: list[str] = list(values.get("visited") or [])
    frontier: list[str] = list(state.next or [])

    pending = _pending_interrupt(state)
    waiting = {pending["nodeId"]} if pending and pending.get("nodeId") else set()

    if pending is not None:
        status = "waiting"
    elif frontier:
        status = "running"
    else:
        status = "done" if visited else "created"

    return {
        "instanceId": instance.id,
        "scenarioId": instance.spec.scenario_id,
        "subject": instance.spec.subject,
        "riskId": instance.spec.risk_id,
        # 산출물이 Mock인지 실제 호출인지 화면이 구분할 수 있어야 한다 —
        # 기획안 2.3의 "시나리오 설정값과 시스템 실행 결과를 구분한다"와 같은 이유다.
        "agentMode": instance.agent_mode,
        "status": status,
        "visited": visited,
        "next": frontier,
        "nodeStatuses": derive_node_statuses(instance.spec, visited, frontier, waiting),
        # 완료된 Agent의 산출물만 들어 있다 — 노드가 돌기 전에는 기록 자체가 없다.
        # TS에서는 "숨기는" 규칙이었는데 여기서는 구조적으로 존재하지 않는다.
        "runs": values.get("runs") or [],
        "flags": values.get("flags") or {},
        "decision": values.get("decision"),
        "acknowledged": values.get("acknowledged") or [],
        "pendingApproval": pending,
        "specWarnings": instance.warnings,
    }


def _pending_interrupt(state: Any) -> dict[str, Any] | None:
    for task in state.tasks or ():
        for intr in getattr(task, "interrupts", ()) or ():
            value = getattr(intr, "value", None)
            if isinstance(value, dict):
                return value
            if value is not None:
                return {"value": value}
    return None


def dump_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)
