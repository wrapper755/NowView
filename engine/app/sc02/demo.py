"""
SC02 기본 시연 각본 — D00 → D01~D12 (통합 가상 데이터 「업무이력」 시트), 그리고 X 사례의 변형.

SC01 각본(`app/sc01/demo.py`)과 같다: **단계 진행은 실제 상태 전환을 실행한다.** 각본은 누가·언제·
무엇을 했나만 들고, 실행은 사람이 버튼을 누른 것과 같은 길(`Sc02Process.receive`·`act`)이다.

**단가·기한은 시드에서 읽는다**(설정 시트의 내부제시가·협상가·기안가·협상기한) — 각본에 숫자를 옮겨
적지 않는다. X 사례는 그 값을 바꿔 같은 길을 탄다(ERR-21: 별도 데모 실행).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any

from app import scenarios
from app.sc01.domain import DomainError, parse_at
from app.sc02.process import Sc02Process
from app.sc02.seed import Seed, load_seed


@dataclass(frozen=True)
class Step:
    code: str
    at: str  # KST 가상시각
    actor: str
    node_id: str | None  # None이면 요청 접수
    answer: dict[str, Any] = field(default_factory=dict)
    label: str = ""
    expect_proposal: bool = False


def base_steps(seed: Seed | None = None) -> list[Step]:
    """
    기본 시연 — 각본의 원본은 Company1 `scenarios/sc02.json`이고 여기는 사본을 읽는다
    (`app/scenarios.py`). 운영·로컬에서는 회사 사이트가 이 각본으로 몬다 — 이 실행기는
    시험 전용이다.
    """
    return scenarios.steps(2, Step)


def _answer(steps: list[Step], node: str, **change: Any) -> list[Step]:
    return [replace(s, answer={**s.answer, **change}) if s.node_id == node else s for s in steps]


def _until(steps: list[Step], code: str) -> list[Step]:
    """그 단계 코드까지 — 예외 사례는 거기서 끝난다."""
    last = max(i for i, s in enumerate(steps) if s.code == code)
    return steps[: last + 1]


def steps_for(case_id: str, seed: Seed | None = None) -> list[Step]:
    seed = seed or load_seed()
    steps = base_steps(seed)
    if case_id == "X01":
        # D08 기본 승인 대신 추가 협상지시 — 승인 완료로 남지 않는다(ERR-21). 원문은 INSTR-RENEG01.
        steps = _answer(
            _until(steps, "D08"),
            "Approve_Exec",
            결정="추가협상지시",
            결재의견=seed.evidence["INSTR-RENEG01"]["내용"],
            지시요구조건="대체 공급처 견적과 인상 사유 증빙 확보",
            지시기한="2027-06-25T18:00:00+09:00",
        )
        return [
            replace(s, code="X01", label="추가 협상지시") if s.node_id == "Approve_Exec" else s
            for s in steps
        ]
    if case_id == "X02":
        # 협상·기안 2,050원 — 12개월 증가 7,840,600원, 대표 비대상(임원 최종 승인)
        steps = _answer(steps, "Record_Negotiation", 협상단가=2050)
        steps = _answer(steps, "Draft_Proposal", 기안단가=2050)
        return [s for s in steps if s.node_id != "Approve_CEO"]
    if case_id == "X04":
        steps = _answer(steps, "Record_Negotiation", 협상적용일="2027-08-01")
        return _answer(steps, "Draft_Proposal", 기안적용일="2027-08-01")
    if case_id == "X05":
        return _answer(
            steps,
            "Draft_Proposal",
            기안단가=2130,
            차이사유="공급사 회신 지연분 반영 — 협상가와 다르다",
        )
    if case_id == "X06":
        steps = _answer(
            _until(steps, "D04"),
            "Record_Negotiation",
            협상결과="미합의",
            협상단가=None,
            미합의사항="공급사가 2,200원 유지 — 팀장 협의 필요",
        )
        return steps
    if case_id == "X07J":
        return _answer(
            _until(steps, "D07"), "Approve_Lead", 결정="반려", 결재의견="인상 사유 증빙 부족 — 반려"
        )
    if case_id == "X07R":
        # 팀장 보완 → 같은 조건으로 재상신(PROP01-v2) → 팀장부터 다시. 이전 승인은 승계하지 않는다.
        head = _until(steps, "D07")
        head = _answer(head, "Approve_Lead", 결정="보완", 결재의견="물량 가정 근거를 첨부해 재상신")
        draft = next(s for s in steps if s.node_id == "Draft_Proposal")
        lead = next(s for s in steps if s.node_id == "Approve_Lead")
        tail = [s for s in steps if s.code in ("D08", "D09", "D10", "D11", "D12")]
        return [
            *head,
            replace(
                draft,
                code="X07",
                at="2027-06-22T16:00:00+09:00",
                label="보완 재상신",
                answer={
                    **draft.answer,
                    "인상필요성": draft.answer["인상필요성"] + " (물량 가정 근거 첨부)",
                },
            ),
            replace(lead, code="X07", at="2027-06-22T17:00:00+09:00", label="재상신 팀장 승인"),
            *tail,
        ]
    if case_id in ("X09A", "X10"):
        # 12개월 물량 누락·중복 — 분석은 미산출로 남는다. 각본은 재분석에서 멈춘다: 상신은 409로
        # 막히므로(T33) 화면에서 기안을 눌러 거절 사유를 본다.
        return _until(steps, "D05")
    return steps


def run_step(process: Sc02Process, demo_run_id: str, index: int) -> dict:
    """각본의 `index`번째 단계. 이미 지나간 단계면 현재 문서를 돌려준다(SC01과 같다)."""
    doc = process.get(demo_run_id)
    if (doc["bpm"] or {}).get("executor") == "studio":
        # Studio 시험 실행의 결재는 Studio 대화상자만 받는다. Center는 각본이 대리 답한다.
        raise DomainError(
            "Studio 시험 실행의 데모 실행은 각본을 돌리지 않는다 — 결재는 Studio에서 답한다", 409
        )
    steps = steps_for(doc["case_id"], process.seed)
    if not 0 <= index < len(steps):
        raise DomainError(f"각본에 없는 단계: {index}", 404)
    done = doc.get("script_index", -1)
    if index <= done:
        return doc
    if index != done + 1:
        raise DomainError(f"단계를 건너뛸 수 없다 — 다음은 {done + 1}번이다", 409)
    step = steps[index]
    if parse_at(step.at) > parse_at(doc["clock"]):
        process.set_clock(demo_run_id, step.at, actor="u-demo", event_code=step.code)
    if step.node_id is None:
        return process.receive(
            demo_run_id,
            step.answer["fixture_id"],
            actor=step.actor,
            event_code=step.code,
            script_index=index,
        )
    expect = None
    if step.expect_proposal:
        current = process.get(demo_run_id)["proposals"]
        key = max(current.values(), key=lambda p: p["seq"])["proposal_key"] if current else None
        expect = {"proposal": key}
    answer = {k: v for k, v in step.answer.items() if v is not None and v != ""}
    since = max((a["seq"] for a in process.get(demo_run_id)["audit"]), default=0)
    done_doc = process.act(
        demo_run_id,
        step.node_id,
        answer,
        actor=step.actor,
        expect=expect,
        event_code=step.code,
        script_index=index,
    )
    if (done_doc["bpm"] or {}).get("executor") != "center":
        return done_doc
    return _await_own_record(process, demo_run_id, step.node_id, since)


def _await_own_record(process: Sc02Process, demo_run_id: str, node_id: str, since: int) -> dict:
    """
    Center 실행이면 이 단계 결재의 업무가 끝날 때까지(또는 기록이 거절될 때까지) 기다린다.

    대리 답은 결재만 닫고 기록·계산 작업은 서버 실행기가 따로 부른다 — 기다리지 않으면 다음 단계가
    시계를 먼저 옮겨 기록이 뒤 시각으로 적혔다(운영 Center 실측: 업무 완료 시각이 전부 다음 단계
    시각, 협상 업무에 거짓 지연 알림). 장면 4·5의 같은 이름 함수와 같은 뜻인데, 확인 결재(요청안
    분석·재분석)는 `answer_via`를 남기지 않아 업무 완료로 본다. 끝내 오지 않으면 지금 문서를
    돌려준다 — 다음 단계의 대기가 거절 사유를 낸다.
    """
    deadline = time.monotonic() + process.center_wait_s * 3
    while True:
        doc = process.get(demo_run_id)
        for a in doc["audit"]:
            if a["seq"] <= since:
                continue
            detail = a.get("detail") or {}
            if a["action"] == "answer_rejected" and detail.get("node_id") == node_id:
                return doc
            if a["action"] == "task_completed":
                task = doc["tasks"].get(detail.get("task_id")) or {}
                if task.get("node_id") == node_id:
                    return doc
        if time.monotonic() >= deadline:
            return doc
        time.sleep(min(1.0, process.center_wait_s))
