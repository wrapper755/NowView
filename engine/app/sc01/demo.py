"""
SC01 기본 시연 각본 — S0 → EV01~EV07 (통합 가상 데이터 설계 「업무이력」 시트).

**단계 진행은 실제 상태 전환을 실행한다**(구현명세 2장). 각본은 "누가 언제 무엇을 했나"만
들고 있고, 실행은 사람이 버튼을 누른 것과 같은 경로(`Sc01Process.receive`·`act`)를 탄다 —
역할 검사·업무 규칙을 건너뛰는 지름길이 없다. 이미 끝난 단계를 다시 실행하면 아무것도 새로
만들지 않고 현재 문서를 돌려준다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app import scenarios
from app.sc01 import domain, view
from app.sc01.domain import DomainError, parse_at
from app.sc01.process import Sc01Process


@dataclass(frozen=True)
class Step:
    code: str
    at: str  # KST 가상시각
    actor: str
    node_id: str | None  # None이면 원천 수신
    answer: dict[str, Any] = field(default_factory=dict)
    label: str = ""


#: 기본 시연(EV01~EV07) — 각본의 원본은 Company1 `scenarios/sc01.json`이고 여기는 사본을 읽는다
#: (`app/scenarios.py`). 운영·로컬에서는 회사 사이트가 이 각본으로 몬다 — 이 실행기는 시험 전용이다.
BASE: list[Step] = scenarios.steps(1, Step)


def run_step(process: Sc01Process, demo_run_id: str, index: int) -> dict:
    """각본의 `index`번째 단계를 실행한다. 이미 지나간 단계면 현재 문서를 돌려준다."""
    if not 0 <= index < len(BASE):
        raise DomainError(f"각본에 없는 단계: {index}", 404)
    doc = process.get(demo_run_id)
    if domain.executor_of(doc) == "studio":
        # Studio 시험 실행의 결재는 Studio 대화상자만 받는다. Center는 각본이 대리 답한다(N3).
        raise DomainError(
            "Studio 시험 실행의 데모 실행은 각본을 돌리지 않는다 — 결재는 Studio에서 답한다",
            409,
        )
    done = doc.get("script_index", -1)
    if index <= done:
        return doc
    if index != done + 1:
        raise DomainError(f"단계를 건너뛸 수 없다 — 다음은 {done + 1}번이다", 409)
    step = BASE[index]
    if parse_at(step.at) > parse_at(doc["clock"]):
        process.set_clock(demo_run_id, step.at, actor="u-demo", event_code=step.code)
    if step.node_id is None:
        received = process.receive(
            demo_run_id,
            step.answer["fixture_id"],
            actor=step.actor,
            event_code=step.code,
            script_index=index,
        )
        if (received["bpm"] or {}).get("executor") != "center":
            return received
        return _await_next_approval(process, demo_run_id, None)
    since = max((a["seq"] for a in process.get(demo_run_id)["audit"]), default=0)
    done_doc = process.act(
        demo_run_id,
        step.node_id,
        step.answer,
        actor=step.actor,
        event_code=step.code,
        script_index=index,
    )
    if (done_doc["bpm"] or {}).get("executor") != "center":
        return done_doc
    return _await_own_record(process, demo_run_id, step.node_id, since)


#: 결재의 기록이 들어왔다는 감사 이력 — 계산 실행 확인(Confirm_Calc)은 기록 작업 없이 계산이 남긴다
_LANDED = ("answer_recorded", "calculation_requested", "answer_rejected")


def _await_own_record(process: Sc01Process, demo_run_id: str, node_id: str, since: int) -> dict:
    """
    Center 실행이면 이 단계 결재의 기록이 들어올 때까지(또는 거절될 때까지) 기다린다.

    대리 답은 결재만 닫고 기록 작업은 서버 실행기가 따로 부른다 — 기다리지 않으면 다음 단계가
    시계를 먼저 옮겨 기록이 뒤 시각으로 적혔다(로컬 Center 실측 2026-11-01: 원천 확인 10:00 →
    10:10, 생산·자재 인수 11:30 → 11:45). 장면 2~5의 같은 이름 함수와 같은 뜻이다. 끝내 오지
    않으면 지금 문서를 돌려준다 — 다음 단계의 대기가 거절 사유를 낸다.
    """
    deadline = time.monotonic() + process.center_wait_s * 3
    while True:
        doc = process.get(demo_run_id)
        for a in doc["audit"]:
            if a["seq"] <= since or (a.get("detail") or {}).get("node_id") != node_id:
                continue
            if a["action"] == "answer_rejected":
                return doc
            if a["action"] in _LANDED:
                return _await_next_approval(process, demo_run_id, node_id)
        if time.monotonic() >= deadline:
            return doc
        time.sleep(min(1.0, process.center_wait_s))


def _await_next_approval(process: Sc01Process, demo_run_id: str, node_id: str | None) -> dict:
    """
    기록 뒤 이 결재 다음에 열릴 결재가 보일 때까지(폴러가 읽어 업무를 열 때까지) 기다린다.

    내장 실행은 결재가 열리는 순간 업무를 연다(앞 기록 시각). Center 실행은 폴러가 결재를 읽을 때
    여는데, 각본이 그 전에 시계를 옮기면 업무가 다음 단계 시각에 열렸다(로컬 Center 실측: DQ 09:00 →
    10:00, 생산·자재 11:00 → 11:30, 경영관리 11:05 → 11:30). 기다릴 결재는 그림에서 찾는다 —
    합류에서 멈추는 갈래(생산·자재 인수)는 열 것이 없어 바로 돌아온다. 조건으로 가지 않은 갈래가
    있으면 `center_wait_s`까지만 기다린다.
    """
    expected = _next_approvals(process, node_id or "Start")
    if not expected:
        return process.get(demo_run_id)
    deadline = time.monotonic() + process.center_wait_s
    while True:
        doc = process.get(demo_run_id)
        bpm = doc["bpm"] or {}
        if bpm.get("state") not in ("not_started", "running") or any(
            w["node_id"] in expected for w in bpm.get("waiting", [])
        ):
            return doc
        if time.monotonic() >= deadline:
            return doc
        time.sleep(min(1.0, process.center_wait_s))


def _next_approvals(process: Sc01Process, node_id: str) -> set[str]:
    """`node_id`에서 흐름을 따라 다음 사람 결재까지 — 합류·메시지 대기·종료에서 멈춘다."""
    topo = view.topology(process.process)
    kinds = {n["id"]: n["kind"] for n in topo["nodes"]}
    after: dict[str, list[str]] = {}
    incoming: dict[str, int] = {}
    for f in topo["flows"]:
        after.setdefault(f["source"], []).append(f["target"])
        incoming[f["target"]] = incoming.get(f["target"], 0) + 1
    found: set[str] = set()
    seen = {node_id}
    todo = list(after.get(node_id, []))
    while todo:
        n = todo.pop()
        if n in seen:
            continue
        seen.add(n)
        kind = kinds.get(n)
        if kind == "userTask":
            found.add(n)
            continue
        joins = kind in ("parallelGateway", "inclusiveGateway") and incoming.get(n, 0) > 1
        if kind in ("receiveTask", "endEvent") or joins:
            continue
        todo.extend(after.get(n, []))
    return found
