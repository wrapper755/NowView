"""
SC02 업무 흐름 — Chaeksas BPM 위에서 기본 시연(D00~D12)과 예외(X01~X10)·권한·버전·멱등을 잠근다.

검수 기준은 구현명세 14장 T21~T36이다. 각 테스트 이름 옆에 대응 ID를 적었다. 숫자는 통합 가상
데이터의 기대값이고 계산 대조는 `test_sc02_calc.py`가 따로 한다 — 여기서는 흐름이 그 값을 **그대로
싣는지** 본다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from chaeksas.contracts.bpmn_ext import read_process
from conftest import require_postgres
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.events import Hub
from app.sc01.domain import USERS, DomainError
from app.sc01.process import Sc01Process
from app.sc01.store import PostgresSc01Store, SqliteSc01Store
from app.sc02 import demo, domain
from app.sc02.api import build_router
from app.sc02.process import PROCESS_PATH, Sc02Process
from app.sc02.view import view
from app.store import build_postgres_backend


@pytest.fixture(params=["sqlite", "postgres"])
def proc(request) -> Iterator[Sc02Process]:
    """두 백엔드에서 같은 흐름 — 장면 1·2 저장소는 같은 DB의 다른 테이블이다."""
    backend = None
    if request.param == "postgres":
        backend = build_postgres_backend(require_postgres())
        s1, s2 = PostgresSc01Store(backend.pool), PostgresSc01Store(backend.pool, "sc02")
        _truncate(backend)
    else:
        s1 = SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False))
        s2 = SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), "sc02")
    published: list[str] = []
    p = Sc02Process(s2, Sc01Process(s1, inline_agent=True), publish=published.append)
    p.published = published  # type: ignore[attr-defined]
    try:
        yield p
    finally:
        if backend is not None:
            _truncate(backend)
            backend.close()


def _truncate(backend) -> None:
    with backend.pool.connection() as conn:
        conn.execute("TRUNCATE sc01_demo_run, sc01_history, sc02_demo_run, sc02_history")


def play(proc: Sc02Process, case: str = "BASE", until: str | None = None) -> dict:
    doc = proc.create(case_id=case)
    for i, step in enumerate(demo.steps_for(case)):
        doc = demo.run_step(proc, doc["demo_run_id"], i)
        if until is not None and step.code == until:
            break
    return doc


def waiting(doc: dict) -> list[str]:
    return [p["node_id"] for p in doc["bpm"]["snapshot"]["pendings"].values()]


def result(doc: dict, run_id: str) -> dict:
    return doc["runs"][run_id]["result"]


def period(doc: dict, run_id: str, kind: str) -> dict:
    return next(p for p in result(doc, run_id)["periods"] if p["kind"] == kind)


def step_index(case: str, code: str) -> int:
    return max(i for i, s in enumerate(demo.steps_for(case)) if s.code == code)


# ─────────────────────────── 시작 (D00 · T21) ───────────────────────────


def test_d00_starts_from_the_sc01_handoff_and_exposes_nothing_ahead(proc: Sc02Process) -> None:
    """T21·DEMO-01 — 장면 1 인계 결과만 있다. 요청·협상·승인·원가·인계는 아직 없다."""
    doc = proc.create()
    sc01 = proc.sc01.get(doc["demo_run_id"])
    assert sc01["scene"] == "HANDED_OFF"  # 장면 1 각본을 실제로 끝까지 돌렸다
    assert doc["sc01"]["run_id"] == "RUN-F02-001"
    assert doc["sc01"]["forecast_approval"] == "UNDER_REVIEW"
    assert doc["sc01"]["issue"]["issue_id"] == "ISSUE-B07"
    assert doc["sc01"]["issue"]["risk"] == "CRITICAL" and doc["sc01"]["issue"]["status"] == "OPEN"
    assert doc["request"] is None and doc["runs"] == {} and doc["proposals"] == {}
    assert doc["price_versions"] == {} and doc["cost_versions"] == {} and doc["handoff"] is None
    assert doc["bpm"] is None and doc["clock"].startswith("2027-06-17T08:50")


def test_same_demo_run_id_as_sc01_and_create_is_idempotent(proc: Sc02Process) -> None:
    """DATA-22 — execution_id = 장면 1의 demo_run_id. 이미 있으면 그대로, 다른 사례면 409."""
    sc01 = proc.sc01.create()
    demo_id = sc01["demo_run_id"]
    doc = proc.create(sc01_demo_run_id=demo_id)
    assert doc["demo_run_id"] == demo_id
    assert proc.create(sc01_demo_run_id=demo_id)["demo_run_id"] == demo_id
    with pytest.raises(DomainError) as exc:
        proc.create(sc01_demo_run_id=demo_id, case_id="X01")
    assert exc.value.status == 409


def test_sc01_with_a_different_f02_is_refused(proc: Sc02Process) -> None:
    """데이터가 상충하면 임의 보정하지 않는다(구현명세 1장) — 장면 2 기대값은 기본 F02 기준이다."""
    doc = proc.sc01.create()
    from app.sc01 import demo as sc01_demo

    for i in range(len(sc01_demo.BASE)):
        doc = sc01_demo.run_step(proc.sc01, doc["demo_run_id"], i)
    run = doc["calc_runs"][doc["handoff"]["run_id"]]
    forecast = doc["forecasts"][run["versions"]["latest"]]
    forecast["quantities"][0][2] += 1
    with pytest.raises(DomainError) as exc:
        domain.baseline_from_sc01(doc, proc.seed)
    assert exc.value.status == 409


def test_unknown_case_is_422(proc: Sc02Process) -> None:
    with pytest.raises(DomainError) as exc:
        proc.create(case_id="X99")
    assert exc.value.status == 422


# ─────────────────────────── 기본 시연 (D01~D12) ───────────────────────────


def test_d01_d02_receive_verify_and_report(proc: Sc02Process) -> None:
    """T22 — 사람 원문 확인, 구두보고 결론 저장. 별도 승인 단계를 늘리지 않는다."""
    doc = play(proc, until="D02")
    req = doc["request"]
    assert req["status"] == "PRE_REVIEW" and req["verified_by"] == "u-buy"
    assert req["items"][0]["old_price"] == "2000" and req["items"][0]["requested_price"] == "2200"
    assert doc["report"]["need"] == "검토진행" and doc["report"]["conclusion"]
    # 요청가는 승인 원가가 아니다 — 요청안 단가 버전만 생겼다
    assert list(doc["price_versions"]) == ["PV-REQ01"]
    assert waiting(doc) == ["Confirm_Analysis"]


def test_d03_request_analysis_numbers_and_cost_issue(proc: Sc02Process) -> None:
    """T23 — 12개월 수량 156,812 · 증가 31,362,400원 · 위험 중요. ISSUE-COST01은 하나만(WF-25)."""
    doc = play(proc, until="D03")
    r = result(doc, "RUN-REQ01")
    assert r["next12"]["purchase_qty"] == 156812
    assert r["next12"]["increase"] == "31362400"
    assert r["remaining"]["increase"] == "15607200"
    assert r["risk"] == "CRITICAL" and r["ceo_required"] is True
    offer = result(doc, "RUN-OFFER01")
    assert offer["rate_risk"] == "ATTENTION" and offer["next12"]["increase"] == "15681200"
    assert doc["issue"]["issue_id"] == "ISSUE-COST01"
    assert [h["run_id"] for h in doc["issue"]["history"]] == ["RUN-REQ01", "RUN-OFFER01"]
    assert doc["request"]["status"] == "NEGOTIATION_READY"
    # 외부 협상기한은 담당자가 넣은 값 — 협상 업무의 기한이 그것이다(U23-02)
    task = next(t for t in doc["tasks"].values() if t["type"] == "NEGOTIATION")
    assert task["due_at"] == "2027-06-21T18:00:00+09:00"


def test_d05_negotiation_reanalysis(proc: Sc02Process) -> None:
    """T24 — 6% · 18,817,440원 · 요청 대비 부담 감소 12,544,960원 · 대표 대상."""
    doc = play(proc, until="D05")
    r = result(doc, "RUN-NEG01")
    assert r["rate"] == "0.06" and r["next12"]["increase"] == "18817440"
    assert r["comparison"]["reduction"] == "12544960"
    assert r["risk"] == "CRITICAL" and r["rate_risk"] == "ATTENTION"
    assert r["ceo_required"] is True
    assert doc["request"]["status"] == "PROPOSAL_READY"
    assert doc["negotiations"]["NEG01"]["analysis_required"] is False


def test_d06_to_d09_sequential_approval_with_ceo(proc: Sc02Process) -> None:
    """T25 — 팀장 → 임원 → 대표. 같은 기안 버전(PROP01-v1)을 승인한다. 승인안 PV-APP01·RUN-APP01."""
    doc = play(proc, until="D09")
    prop = doc["proposals"]["PROP01-v1"]
    assert prop["status"] == "APPROVED" and prop["run_id"] == "RUN-PROP01"
    assert [(d["step"], d["decision"], d["proposal_key"]) for d in doc["decisions"]] == [
        ("TEAM", "승인", "PROP01-v1"),
        ("EXEC", "승인", "PROP01-v1"),
        ("CEO", "승인", "PROP01-v1"),
    ]
    assert prop["authority"]["required"] is True and prop["authority"]["amount"] == "18817440"
    assert "PV-APP01" in doc["price_versions"] and "RUN-APP01" in doc["runs"]
    assert waiting(doc) == ["Register_Cost"]


def test_d10_cost_registration_replaces_only_the_part(proc: Sc02Process) -> None:
    """T26 · COST-01·02 — a 75,120 · b 95,120 · c~e 그대로. 적용일 전이면 적용 예정."""
    doc = play(proc, until="D10")
    cv = doc["cost_versions"]["C02-APP01"]
    after = {m["model_id"]: m["outsource_after"] for m in cv["models"]}
    assert after == {"A-a": "75120", "A-b": "95120", "A-c": "60000", "A-d": "65000", "A-e": "50000"}
    assert cv["parent_cost_version"] == "C01" and cv["effective_from"] == "2027-07-01"
    assert view(doc)["status"]["cost"] == "REGISTERED_FUTURE"
    # 적용일 도래는 사람 승인·전망 승인 이벤트가 아니다 — 시계에서 파생할 뿐이다
    doc = proc.set_clock(doc["demo_run_id"], "2027-07-01T09:00:00+09:00", actor="u-demo")
    assert view(doc)["status"]["cost"] == "EFFECTIVE"
    assert view(doc)["status"]["forecast"] == "REVIEW_PENDING"


def test_d11_d12_handoff_and_end_state(proc: Sc02Process) -> None:
    """
    T27~T30 — 2027 물량 −1,400만 · 원가 −9,364,320 · 통합 3,299,986,680. 끝나도 위험·전망은 그대로.
    """
    doc = play(proc)
    year = period(doc, "RUN-APP01", "year")
    assert year["volume_effect"] == "-14000000" and year["cost_effect"] == "-9364320"
    assert year["profit_combined"] == "3299986680" and year["target_gap"] == "177303320"
    q3 = next(p for p in result(doc, "RUN-APP01")["periods"] if p["label"] == "2027 Q3")
    assert q3["profit_combined"] == "788967800"
    next12 = period(doc, "RUN-APP01", "next12")
    assert next12["profit_combined"] == "3173163560" and next12["target_gap"] is None

    h = doc["handoff"]
    assert h["status"] == "HANDED_OFF" and h["accepted_by"] == "u-fin" and not h["provisional"]
    assert h["selected_run"] == "RUN-APP01" and h["sc03_due_at"] == "2027-06-28T18:00:00+09:00"
    links = {link["issue_id"]: link for link in doc["review"]["links"]}
    assert links["ISSUE-B07"]["issue_type"] == "VOLUME" and links["ISSUE-B07"]["latest_run_id"] == (
        "RUN-F02-001"
    )
    assert links["ISSUE-COST01"]["issue_type"] == "COST"
    assert links["ISSUE-COST01"]["latest_run_id"] == "RUN-APP01"
    s = view(doc)["status"]
    assert (s["approval"], s["risk"], s["forecast"], s["handoff"]) == (
        "APPROVED",
        "OPEN",
        "REVIEW_PENDING",
        "HANDED_OFF",
    )
    assert s["sceneCode"] == "SC02_HANDED_OFF / SC03_PENDING"
    assert doc["bpm"]["state"] == "done"
    assert all(t["status"] == "COMPLETED" for t in doc["tasks"].values())


def test_task_deadlines_follow_the_business_calendar(proc: Sc02Process) -> None:
    """
    WF-22 — 일반 다음 영업일 18시, 분석 두 번째 영업일 18시(6/19·20은 주말). 업무이력 due_at과 같다.
    """
    doc = play(proc)
    due = {t["type"]: t["due_at"][:16] for t in doc["tasks"].values()}
    assert due["VERIFY"] == "2027-06-18T18:00"
    assert due["ANALYSIS"] == "2027-06-21T18:00"
    assert due["REANALYSIS"] == "2027-06-23T18:00"
    assert due["PROPOSAL"] == "2027-06-23T18:00"
    assert due["APPROVE_EXEC"] == "2027-06-23T18:00"
    assert due["APPROVE_CEO"] == "2027-06-24T18:00"
    assert due["ACCEPT"] == "2027-06-24T18:00"


# ─────────────────────────── 권한 · 순서 · 버전 (T25·T35) ───────────────────────────


def test_only_the_current_approver_can_decide(proc: Sc02Process) -> None:
    """T25 · AUTH-03 — 다른 역할은 403. 차례가 아닌 결재는 409. 입력은 보존된다(상태 그대로)."""
    doc = play(proc, until="D06")
    rid = doc["demo_run_id"]
    ok = {"결정": "승인", "결재의견": "검토 완료"}
    for actor in ("u-buy", "u-buy-exec", "u-ceo"):
        with pytest.raises(DomainError) as exc:
            proc.act(rid, "Approve_Lead", ok, actor=actor)
        assert exc.value.status == 403
    with pytest.raises(DomainError) as exc:
        proc.act(rid, "Approve_Exec", ok, actor="u-buy-exec")
    assert exc.value.status == 409  # 순서 위반 — 팀장 차례
    assert proc.get(rid)["approval_status"] == "TEAM_APPROVAL_PENDING"


def test_stale_proposal_version_is_refused(proc: Sc02Process) -> None:
    """U25-03 — 오래된 기안 버전에 대한 승인은 거절."""
    doc = play(proc, until="D06")
    with pytest.raises(DomainError) as exc:
        proc.act(
            doc["demo_run_id"],
            "Approve_Lead",
            {"결정": "승인", "결재의견": "ok"},
            actor="u-buy-lead",
            expect={"proposal": "PROP01-v0"},
        )
    assert exc.value.status == 409


def test_team_lead_cannot_order_renegotiation(proc: Sc02Process) -> None:
    doc = play(proc, until="D06")
    with pytest.raises(DomainError) as exc:
        proc.act(
            doc["demo_run_id"],
            "Approve_Lead",
            {"결정": "추가협상지시", "결재의견": "더 깎자"},
            actor="u-buy-lead",
        )
    assert exc.value.status == 422


def test_idempotency_key_replays_and_conflicts(proc: Sc02Process) -> None:
    """T35 · ERR-22 — 같은 키·같은 본문은 다시 실행하지 않고, 같은 키·다른 본문은 409."""
    doc = play(proc, until="D06")
    rid = doc["demo_run_id"]
    body = {"결정": "승인", "결재의견": "ok"}
    first = proc.act(rid, "Approve_Lead", body, actor="u-buy-lead", idempotency_key="k1")
    again = proc.act(rid, "Approve_Lead", body, actor="u-buy-lead", idempotency_key="k1")
    assert len(again["decisions"]) == len(first["decisions"]) == 1
    with pytest.raises(DomainError) as exc:
        proc.act(
            rid, "Approve_Lead", {**body, "결재의견": "x"}, actor="u-buy-lead", idempotency_key="k1"
        )
    assert exc.value.status == 409


def test_accept_only_by_the_assigned_finance_user(proc: Sc02Process) -> None:
    """D12 — 지정 담당자만 인수한다(HAND-01). 오래된 자료 해시면 409."""
    doc = play(proc, until="D11")
    rid = doc["demo_run_id"]
    with pytest.raises(DomainError) as exc:
        proc.act(rid, "Accept_Handoff", {"인수의견": "ok"}, actor="u-buy")
    assert exc.value.status == 403
    with pytest.raises(DomainError) as exc:
        proc.act(rid, "Accept_Handoff", {"인수의견": "ok"}, actor="u-fin", expect={"bundle": "old"})
    assert exc.value.status == 409


def test_handoff_conditions_list_what_is_missing(proc: Sc02Process) -> None:
    """T29 — 승인·등록·근거·담당·인수가 하나라도 없으면 완료 불가."""
    doc = play(proc, until="D09")
    check = domain.handoff_conditions(doc)
    assert not check["met"] and "C02 원가 미등록" in check["reasons"]
    doc = play(proc, until="D06")
    check = domain.handoff_conditions(doc)
    assert not check["conditions"]["approved"]


# ─────────────────────────── 예외 (X01~X10) ───────────────────────────


def test_x01_renegotiation_blocks_cost_and_handoff(proc: Sc02Process) -> None:
    """
    T31 · X01 — NEEDS_RENEGOTIATION, 사유·담당·기한 저장, C02·최종 인계 금지. 잠정 자료만 연결.
    """
    doc = play(proc, "X01")
    assert doc["approval_status"] == "NEEDS_RENEGOTIATION"
    ins = doc["instruction"]
    assert ins["assignee"] == "u-buy" and ins["due_at"] == "2027-06-25T18:00:00+09:00"
    assert ins["reason"] and ins["condition"]
    assert doc["cost_versions"] == {} and doc["handoff"] is None
    assert "PV-APP01" not in doc["price_versions"]
    assert doc["bpm"]["state"] == "done" and doc["scene"] == "RENEGOTIATION"
    assert [b["provisional"] for b in doc["review"]["bundles"]] == [True]
    assert not domain.handoff_conditions(doc)["met"]
    reneg = next(t for t in doc["tasks"].values() if t["type"] == "RENEG")
    assert reneg["assigned_to"] == "u-buy" and reneg["status"] == "ASSIGNED"


def test_x02_not_a_ceo_case_exec_is_final(proc: Sc02Process) -> None:
    """X02 · AUTH-02 — 12개월 7,840,600원 → 대표 비대상. 근거 금액·권한표 버전을 남긴다."""
    doc = play(proc, "X02")
    prop = doc["proposals"]["PROP01-v1"]
    assert prop["authority"] == {
        **prop["authority"],
        "amount": "7840600",
        "required": False,
        "authority_version": "AUTH02-v1",
    }
    assert prop["final_step"] == "EXEC" and [d["step"] for d in doc["decisions"]] == [
        "TEAM",
        "EXEC",
    ]
    assert result(doc, "RUN-APP01")["amount_risk"] == "ATTENTION"
    assert doc["handoff"]["status"] == "HANDED_OFF"


def test_x04_august_effective_date(proc: Sc02Process) -> None:
    """
    X04 — 8/1 협상안은 [2027-08, 2028-08)로 다시 잰다. 부담 감소는 요청안 12개월에서 가격·연기
    효과로.
    """
    doc = play(proc, "X04")
    r = result(doc, "RUN-NEG01")
    assert r["effective_date"] == "2027-08-01" and r["next12"]["to"] == "2028-08-01"
    cmp = r["comparison"]
    assert cmp["from"] == "2027-07-01" and int(cmp["deferral_effect"]) > 0
    assert doc["handoff"]["status"] == "HANDED_OFF"


def test_x05_proposal_price_differs_needs_reason_and_new_run(proc: Sc02Process) -> None:
    """
    X05 · U24-01 — 협상가와 다르면 차이 사유가 필요하다(입력 보존 422). 새 RUN-PROP01은 2,130원.
    """
    doc = play(proc, "BASE", until="D05")
    rid = doc["demo_run_id"]
    answer = {"기안단가": 2130, "기안적용일": "2027-07-01", "인상필요성": "공급 안정"}
    with pytest.raises(DomainError) as exc:
        proc.act(rid, "Draft_Proposal", answer, actor="u-buy")
    assert exc.value.status == 422
    assert proc.get(rid)["proposals"] == {}
    doc = proc.act(rid, "Draft_Proposal", {**answer, "차이사유": "회신 반영"}, actor="u-buy")
    assert result(doc, "RUN-PROP01")["new_price"] == "2130"
    assert doc["proposals"]["PROP01-v1"]["diff_reason"] == "회신 반영"


def test_x06_unresolved_negotiation_ends_without_proposal(proc: Sc02Process) -> None:
    """X06 — 미합의는 단가 NULL, 상신 없음. 미합의에 단가를 넣으면 422(0원 대체 금지)."""
    doc = play(proc, "BASE", until="D03")
    with pytest.raises(DomainError) as exc:
        proc.act(
            doc["demo_run_id"],
            "Record_Negotiation",
            {"협상결과": "미합의", "협상단가": 0, "협상적용일": "2027-07-01", "협상참석자": "x"},
            actor="u-buy",
        )
    assert exc.value.status == 422
    doc = play(proc, "X06")
    assert doc["request"]["status"] == "NEGOTIATION_UNRESOLVED"
    assert doc["negotiations"]["NEG01"]["price"] is None
    assert "PV-NEG01" not in doc["price_versions"] and doc["proposals"] == {}
    assert doc["bpm"]["state"] == "done"


def test_x07r_return_creates_a_new_version_from_team_lead(proc: Sc02Process) -> None:
    """
    T31 · X07 — 보완은 새 기안 버전·새 run, 팀장부터 다시. 이전 결정은 보존하되 승계하지 않는다.
    """
    doc = play(proc, "X07R")
    assert doc["proposals"]["PROP01-v1"]["status"] == "RETURNED"
    v2 = doc["proposals"]["PROP01-v2"]
    assert v2["status"] == "APPROVED" and v2["run_id"] == "RUN-PROP02"
    assert [(d["proposal_key"], d["step"], d["decision"]) for d in doc["decisions"]] == [
        ("PROP01-v1", "TEAM", "보완"),
        ("PROP01-v2", "TEAM", "승인"),
        ("PROP01-v2", "EXEC", "승인"),
        ("PROP01-v2", "CEO", "승인"),
    ]
    # 만든 순서(seq) — Postgres JSONB는 키 순서를 바꾼다(CLAUDE.md 4.5)
    proposal_tasks = domain.tasks_of(doc, "PROPOSAL")
    assert [t["task_id"] for t in proposal_tasks] == ["TASK-PROPOSAL", "TASK-PROPOSAL-2"]
    assert proposal_tasks[1]["reopens"] == "TASK-PROPOSAL"


def test_x07j_reject_is_a_separate_end(proc: Sc02Process) -> None:
    """X07 — 반려는 별도 종결. 원가 등록·기본 인계 완료 불가."""
    doc = play(proc, "X07J")
    assert doc["approval_status"] == "REJECTED" and doc["scene"] == "REJECTED"
    assert doc["cost_versions"] == {} and doc["handoff"] is None and doc["bpm"]["state"] == "done"


@pytest.mark.parametrize("case", ["X09A", "X10"])
def test_x09a_x10_data_errors_block_the_proposal(proc: Sc02Process, case: str) -> None:
    """
    T33 — 다음 해 물량 누락·중복 키는 12개월 미산출, 상신 차단(409). 0이나 합산으로 메우지 않는다.
    """
    doc = play(proc, case)
    run = doc["runs"]["RUN-NEG01"]
    assert run["status"] == "BLOCKED" and run["result"]["next12"]["increase"] is None
    assert run["result"]["ceo_required"] is None
    code = "MISSING_QTY" if case == "X09A" else "DUPLICATE_KEY"
    assert code in {p["code"] for p in run["result"]["problems"]}
    with pytest.raises(DomainError) as exc:
        proc.act(
            doc["demo_run_id"],
            "Draft_Proposal",
            {"기안단가": 2120, "기안적용일": "2027-07-01", "인상필요성": "x"},
            actor="u-buy",
        )
    assert exc.value.status == 409
    assert proc.get(doc["demo_run_id"])["proposals"] == {}


def test_x09b_agent_failure_does_not_block_the_flow(proc: Sc02Process) -> None:
    """T34 — Agent 실패만 있으면 수동 검토로 끝까지 간다. 자동 승인 없음."""
    doc = play(proc, "X09B")
    assert {o["status"] for o in doc["agent_outputs"].values()} == {"FAILED"}
    assert doc["handoff"]["status"] == "HANDED_OFF"


def test_agent_drafts_cite_only_rule_results(proc: Sc02Process) -> None:
    """AG-21·22 — 초안의 숫자는 규칙 결과에 있다. 채택은 구매담당이 하고 원본은 그대로다(AG-23)."""
    doc = play(proc, until="D05")
    outputs = list(doc["agent_outputs"].values())
    assert [o["kind"] for o in outputs] == ["AG21", "AG22"]
    assert all(o["status"] == "SUCCEEDED" for o in outputs)
    assert "18,817,440원" in outputs[1]["draft"]["summary"]
    rid = doc["demo_run_id"]
    with pytest.raises(DomainError) as exc:
        proc.adopt(rid, outputs[1]["output_id"], actor="u-buy-lead")
    assert exc.value.status == 403
    doc = proc.adopt(rid, outputs[1]["output_id"], actor="u-buy")
    assert doc["agent_outputs"][outputs[1]["output_id"]]["adopted_by"] == "u-buy"


# ─────────────────────────── 기한 · 시계 · 초기화 (T36) ───────────────────────────


def test_negotiation_due_change_keeps_history_and_alerts(proc: Sc02Process) -> None:
    """T36 · U23-02 · WF-24 — 기한 변경 이력 보존, 넘기면 담당·검토자 알림(중복 없음)."""
    doc = play(proc, until="D03")
    rid = doc["demo_run_id"]
    doc = proc.change_due(
        rid, due="2027-06-22T18:00:00+09:00", reason="공급사 회신 지연", actor="u-buy"
    )
    hist = doc["request"]["negotiation_due"]["history"]
    assert [h["due_at"][:16] for h in hist] == ["2027-06-21T18:00", "2027-06-22T18:00"]
    assert hist[1]["previous"].startswith("2027-06-21") and hist[1]["reason"]
    doc = proc.set_clock(rid, "2027-06-22T18:30:00+09:00", actor="u-demo")
    alerts = [a for a in doc["alerts"] if a["task_id"] == "TASK-NEGOTIATION"]
    assert len(alerts) == 1 and alerts[0]["to"] == ["u-buy", "u-buy-lead"]
    doc = proc.set_clock(rid, "2027-06-22T19:00:00+09:00", actor="u-demo")
    assert len([a for a in doc["alerts"] if a["task_id"] == "TASK-NEGOTIATION"]) == 1


def test_clock_alone_does_not_approve(proc: Sc02Process) -> None:
    """ROLE-01 — 가상시계 이동만으로 승인·인수하지 않는다."""
    doc = play(proc, until="D06")
    doc = proc.set_clock(doc["demo_run_id"], "2027-06-30T18:00:00+09:00", actor="u-demo")
    assert doc["approval_status"] == "TEAM_APPROVAL_PENDING" and waiting(doc) == ["Approve_Lead"]


def test_reset_returns_only_this_run_to_d00(proc: Sc02Process) -> None:
    """ERR-21 — 선택 실행만 D00. 장면 1 기준·다른 실행은 그대로. 이력(감사)은 남는다."""
    a = play(proc, until="D05")
    b = play(proc, until="D03")
    doc = proc.reset(a["demo_run_id"], actor="u-demo")
    assert doc["request"] is None and doc["runs"] == {} and doc["step"] == "D00"
    assert doc["sc01"] == a["sc01"]
    assert any(e["action"] == "demo_run_reset" for e in doc["audit"])
    assert proc.get(b["demo_run_id"])["request"]["status"] == "NEGOTIATION_READY"
    with pytest.raises(DomainError) as exc:
        proc.reset(a["demo_run_id"], actor="u-buy")
    assert exc.value.status == 403


def test_script_cannot_skip_and_rerun_is_harmless(proc: Sc02Process) -> None:
    doc = proc.create()
    rid = doc["demo_run_id"]
    with pytest.raises(DomainError) as exc:
        demo.run_step(proc, rid, 2)
    assert exc.value.status == 409
    demo.run_step(proc, rid, 0)
    again = demo.run_step(proc, rid, 0)
    assert again["request"]["revision"] == 1


def test_changes_are_published_on_the_sc02_channel(proc: Sc02Process) -> None:
    doc = play(proc, until="D01")
    assert f"sc02:{doc['demo_run_id']}" in proc.published  # type: ignore[attr-defined]


def test_history_keeps_each_step_for_read_only_past(proc: Sc02Process) -> None:
    doc = play(proc, until="D06")
    hist = proc.store.history(doc["demo_run_id"])
    first = next(h for h in hist if h["scriptIndex"] == step_index("BASE", "D03"))
    past = proc.store.at(doc["demo_run_id"], first["seq"])
    assert "RUN-REQ01" in past["runs"] and past["proposals"] == {}


# ─────────────────────────── BPMN ↔ 역할표 ───────────────────────────


def test_every_user_task_has_a_role_and_matching_assignees() -> None:
    """NODE_ROLES와 BPMN이 갈라지면 화면 역할 검사와 결재 담당자가 어긋난다(SC01과 같은 그물)."""
    process = read_process(Path(PROCESS_PATH).read_bytes())
    for node in process.all_nodes():
        if node.kind != "userTask":
            continue
        assert node.id in domain.NODE_ROLES, node.id
        role = domain.NODE_ROLES[node.id]["role"]
        assignees = node.prop("approval").assignees
        if isinstance(assignees, list):
            assert {u["role"] for u in USERS.values() if u["name"] in assignees} == {role}, node.id
        else:
            assert assignees == "경영관리담당자명"


# ─────────────────────────── HTTP (API-23) ───────────────────────────


def test_http_errors_and_shapes(proc: Sc02Process) -> None:
    app = FastAPI()
    app.include_router(build_router(proc, Hub()))
    client = TestClient(app)
    created = client.post("/sc02/demo-runs", json={"executor": "embedded"})
    assert created.status_code == 201
    rid = created.json()["demoRunId"]
    assert created.json()["status"]["risk"] == "OPEN"
    assert client.get("/sc02/demo-runs/nope").status_code == 404
    assert client.post(f"/sc02/demo-runs/{rid}/requests/receive", json={}).status_code == 403
    ok = client.post(
        f"/sc02/demo-runs/{rid}/requests/receive", json={}, headers={"x-demo-actor": "u-buy"}
    )
    assert ok.status_code == 200 and ok.json()["bpm"]["waiting"][0]["nodeId"] == "Verify_Request"
    wrong = client.post(
        f"/sc02/demo-runs/{rid}/actions/Report_Lead",
        json={"answer": {}},
        headers={"x-demo-actor": "u-buy"},
    )
    assert wrong.status_code == 409
    rules = client.get("/sc02/rules").json()
    assert rules["ceo_threshold"] == "10000000"
    assert (
        len(client.get("/sc02/script", params={"case_id": "X01"}).json())
        == step_index("X01", "X01") + 1
    )
    topo = client.get("/sc02/process").json()
    assert {n["recordOf"] for n in topo["nodes"] if n["recordOf"]} >= {
        "Approve_Lead",
        "Accept_Handoff",
    }


def test_ts_topology_fixture_is_the_bpmn(proc: Sc02Process) -> None:
    """
    화면 테스트의 토폴로지 사본(`tests/fixtures/sc02-process.json`) = BPMN. BPMN을 고치면 여기서
    실패한다 — 저장소 루트에서 다시 만든다:
    `curl -s localhost:8077/sc02/process | python3 -m json.tool --indent 1`
    `> tests/fixtures/sc02-process.json`
    """
    import json

    from app.sc02.view import topology

    fixture = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sc02-process.json"
    assert json.loads(fixture.read_text(encoding="utf-8")) == topology(proc.process)

