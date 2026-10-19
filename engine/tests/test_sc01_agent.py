"""
SC01 Agent 검토 지원 — 구현명세 11장(AG-01~03)과 EX08.

**검증이 핵심이다.** 그럴듯한 숫자 하나가 틀려도 눈으로는 안 잡힌다. 여기서는 (1) 규칙 결과와
다른 숫자·없는 근거 ID·빠진 항목을 실패로 잡는지, (2) 실패가 업무를 멈추거나 자동 완료시키지
않는지, (3) 재생성·채택·지연이 기록으로 남는지를 본다. LLM 실호출은 `-m llm`으로만 돈다.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest

from app.sc01 import agent, demo
from app.sc01.domain import DomainError
from app.sc01.process import Sc01Process
from app.sc01.store import SqliteSc01Store
from app.sc01.view import view


def make(**kw) -> Sc01Process:
    store = SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False))
    kw.setdefault("inline_agent", True)
    return Sc01Process(store, **kw)


def play(proc: Sc01Process, until: int, case: str = "BASE") -> dict:
    doc = proc.create(case_id=case)
    for i in range(until + 1):
        doc = demo.run_step(proc, doc["demo_run_id"], i)
    return doc


def payload_of(doc: dict) -> dict:
    return next(iter(doc["agent_outputs"].values()))["input"]


class _Fixed:
    """정해진 응답을 돌려주는 러너 — 검증이 무엇을 거르는지 본다."""

    def __init__(self, output: dict, calls: list | None = None) -> None:
        self.output, self.calls = output, calls if calls is not None else []

    def run(self, payload: dict) -> agent.Draft:
        self.calls.append(1)
        return agent.Draft(self.output, "llm:test", "test", 5)


# ─────────────────────────── 기본 경로 ───────────────────────────


def test_calculation_requests_a_draft_and_it_passes_validation() -> None:
    """계산 직후 초안이 요청되고, mock 초안도 계약 검증을 그대로 통과해야 화면에 나온다."""
    doc = play(make(), until=2)
    [out] = doc["agent_outputs"].values()
    assert out["status"] == "SUCCEEDED" and out["provenance"] == "mock"
    assert out["run_id"] == "RUN-F02-001" and out["attempts"] == 1
    draft = out["draft"]
    assert "8,800대분" in draft["summary"] and "1,400만원" in draft["summary"]
    assert "RUN-F02-001:A-b:2027-07:KRI02" in draft["evidence_refs"]
    assert {t["type"] for t in draft["suggested_tasks"]} == {"PROD", "MAT", "FIN"}
    assert out["prompt_version"] == agent.PROMPT_VERSION and out["input_hash"]


def test_the_review_does_not_wait_for_the_agent() -> None:
    """BPM은 초안을 기다리지 않는다 — 초안 요청 노드를 지나 곧바로 영업 검토에 멈춘다."""
    doc = play(make(), until=2)
    waiting = {p["node_id"] for p in doc["bpm"]["snapshot"]["pendings"].values()}
    assert waiting == {"Approve_Sales"}
    assert "Task_AgentRequest" in doc["bpm"]["visited"]


def test_the_review_remembers_which_draft_it_saw() -> None:
    doc = play(make(), until=3)
    assert doc["reviews"]["RUN-F02-001"]["agent_output"] == "AGT-001"


def test_the_expected_explanation_numbers_match_the_rules() -> None:
    """구현명세 11장의 기대 설명 문장 자체가 검증을 통과해야 한다."""
    doc = play(make(), until=2)
    expected = (
        "7월 b모델의 공급 전망이 직전 승인 전망 9,500대분에서 8,800대분으로 700대분 감소했습니다. "
        "목표 달성률은 88%이며, 기준 단위 공헌이익 20,000원 적용 시 추가 공헌이익 감소는 "
        "1,400만원입니다. 감소율·감소액·목표 부족률이 모두 중요 기준에 해당합니다."
    )
    out = {**doc["agent_outputs"]["AGT-001"]["draft"], "summary": expected}
    assert agent.validate(out, payload_of(doc)) == []


# ─────────────────────────── 계약 검증 ───────────────────────────


@pytest.fixture
def good() -> tuple[dict, dict]:
    doc = play(make(), until=2)
    return dict(doc["agent_outputs"]["AGT-001"]["draft"]), payload_of(doc)


def test_a_wrong_amount_fails(good) -> None:
    out, payload = good
    out["summary"] = "추가 공헌이익 감소는 1,500만원이다."
    assert any("규칙 결과에 없는 숫자" in e for e in agent.validate(out, payload))


def test_a_wrong_percentage_fails_but_display_rounding_passes(good) -> None:
    out, payload = good
    out["findings"] = ["감소율 7.4%로 중요다."]  # 7.368421% → 7.4는 표시 반올림
    assert agent.validate(out, payload) == []
    out["findings"] = ["감소율 8.1%로 중요다."]
    assert agent.validate(out, payload)


def test_an_invented_quantity_fails(good) -> None:
    out, payload = good
    out["questions"] = ["8월에도 600대분이 더 줄어드는가?"]  # 600은 어디에도 없다
    assert agent.validate(out, payload)


def test_an_unknown_evidence_id_fails(good) -> None:
    out, payload = good
    out["evidence_refs"] = ["RUN-F09-001"]
    assert any("없는 근거 ID" in e for e in agent.validate(out, payload))


def test_missing_fields_and_bad_tasks_fail(good) -> None:
    out, payload = good
    assert agent.validate({k: v for k, v in out.items() if k != "limitations"}, payload)
    assert agent.validate({**out, "suggested_tasks": [{"type": "APPROVE", "reason": "x"}]}, payload)
    assert agent.validate({**out, "findings": []}, payload)
    assert agent.validate("산문", payload) == ["응답이 JSON 객체가 아니다"]


def test_ids_with_digits_are_not_read_as_numbers(good) -> None:
    out, payload = good
    out["findings"] = ["ISSUE-B07과 RUN-F02-001, SRC02, R01-v1 기준이다."]
    assert agent.validate(out, payload) == []


# ─────────────────────────── 실패 (EX08) ───────────────────────────


def test_ex08_failure_is_recorded_and_the_flow_still_hands_off() -> None:
    """Agent가 실패해도 규칙 계산·검토·인계는 그대로다. 실패가 업무를 자동 완료시키지 않는다."""
    proc = make()
    doc = play(proc, until=2, case="EX08")
    [out] = doc["agent_outputs"].values()
    assert out["status"] == "FAILED" and out["attempts"] == 2  # 한 번 자동 재시도
    assert out["draft"] is None and len(out["errors"]) == 2
    assert doc["tasks"]["TASK-SALES"]["status"] == "ASSIGNED"  # 자동 완료 없음
    for i in range(3, len(demo.BASE)):
        doc = demo.run_step(proc, doc["demo_run_id"], i)
    assert doc["scene"] == "HANDED_OFF"


def test_an_invalid_answer_is_never_shown_as_a_draft() -> None:
    bad = {
        "summary": "감소액은 2,000만원이다.",
        "findings": ["x"],
        "evidence_refs": [],
        "questions": [],
        "suggested_tasks": [],
        "limitations": [],
    }
    calls: list = []
    proc = make(agent_factory=lambda _m: _Fixed(bad, calls))
    doc = play(proc, until=2)
    out = doc["agent_outputs"]["AGT-001"]
    assert out["status"] == "FAILED" and len(calls) == 2
    assert out["draft"] is None and out["rejected"] == bad
    shown = view(doc)["agentOutputs"][0]
    assert "rejected" not in shown and "input" not in shown  # 실패한 응답은 화면으로 나가지 않는다


# ─────────────────────────── 재생성·채택·지연 ───────────────────────────


def test_regenerate_keeps_the_old_draft() -> None:
    proc = make()
    doc = play(proc, until=2)
    doc = proc.regenerate(doc["demo_run_id"], "RUN-F02-001", actor="u-sales-lead")
    assert list(doc["agent_outputs"]) == ["AGT-001", "AGT-002"]
    assert all(o["status"] == "SUCCEEDED" for o in doc["agent_outputs"].values())
    with pytest.raises(DomainError) as e:
        proc.regenerate(doc["demo_run_id"], "RUN-F02-001", actor="u-prod")
    assert e.value.status == 403


def test_adoption_is_recorded_without_touching_the_draft() -> None:
    proc = make()
    doc = play(proc, until=2)
    before = dict(doc["agent_outputs"]["AGT-001"]["draft"])
    doc = proc.adopt(doc["demo_run_id"], "AGT-001", actor="u-sales-lead")
    out = doc["agent_outputs"]["AGT-001"]
    assert out["adopted_by"] == "u-sales-lead" and out["draft"] == before


def test_a_failed_draft_cannot_be_adopted() -> None:
    proc = make()
    doc = play(proc, until=2, case="EX08")
    with pytest.raises(DomainError) as e:
        proc.adopt(doc["demo_run_id"], "AGT-001", actor="u-sales-lead")
    assert e.value.status == 409


def test_a_slow_draft_shows_as_delayed() -> None:
    """30초를 넘기면 지연으로 보인다(AG-02). 실제 시간 기준이다."""
    doc = play(make(), until=2)
    out = doc["agent_outputs"]["AGT-001"]
    out.update(
        status="RUNNING", requested_real=(datetime.now(UTC) - timedelta(seconds=45)).isoformat()
    )
    assert view(doc)["agentOutputs"][0]["delayed"] is True


def test_drafts_run_outside_the_lock() -> None:
    """초안 작업이 도는 동안에도 같은 데모 실행의 조작이 막히지 않는다(배경 실행)."""
    release = threading.Event()

    class Slow:
        def run(self, payload: dict) -> agent.Draft:
            release.wait(5)
            return agent.MockRunner().run(payload)

    proc = make(agent_factory=lambda _m: Slow(), inline_agent=False)
    doc = proc.create()
    rid = doc["demo_run_id"]
    for i in range(3):
        doc = demo.run_step(proc, rid, i)
    assert doc["agent_outputs"]["AGT-001"]["status"] == "RUNNING"
    started = time.monotonic()
    doc = demo.run_step(proc, rid, 3)  # 영업 검토 — 초안을 기다리지 않는다
    assert time.monotonic() - started < 2
    release.set()
    for _ in range(50):
        if proc.get(rid)["agent_outputs"]["AGT-001"]["status"] == "SUCCEEDED":
            break
        time.sleep(0.1)
    assert proc.get(rid)["agent_outputs"]["AGT-001"]["status"] == "SUCCEEDED"


@pytest.mark.llm
def test_ollama_draft_satisfies_the_contract() -> None:
    """실호출 — 비결정적이라 값이 아니라 계약만 본다. `pytest -m llm`."""
    if not os.getenv("OLLAMA_URL"):
        pytest.skip("OLLAMA_URL이 없다")
    doc = play(make(), until=2)
    runner = agent.runner_for("llm")
    draft = runner.run(payload_of(doc))
    assert agent.validate(draft.output, payload_of(doc)) == []


def test_quoting_the_raw_ratio_is_the_same_value(good) -> None:
    """
    실제 모델(kimi-k3:cloud)이 입력의 비율값을 그대로 인용했다(0.07368421, 임계값 0.05). 같은
    값이므로 통과해야 한다 — 처음에는 이것을 10건 거절했다. 다른 비율은 여전히 거절한다.
    """
    out, payload = good
    out["findings"] = ["감소율 KRI01 0.07368421, 부족률 0.12000000, 중요 기준 0.05."]
    assert agent.validate(out, payload) == []
    out["findings"] = ["부족률 0.15."]
    assert agent.validate(out, payload)
