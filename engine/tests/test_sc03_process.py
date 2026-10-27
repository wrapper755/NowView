"""
SC03 업무 흐름 — Chaeksas BPM 위에서 기본 시연(D30~D41)과 예외(E31~E37)·권한·버전·멱등을 잠근다.

검수 기준은 구현명세 14장 T31~T42다. 시험 이름 옆에 대응 ID를 적었다. 끝난 문서는 통합가상데이터
v0.3의 장면 3 시트(기본 시연 종료 시점의 완성 레코드)와 대조한다 — 값을 시험에 옮겨 적지 않는다.
흐름은 내장 실행기로 돈다(같은 그림·같은 작업 함수). 바깥 실행은 `test_sc03_external.py`가 본다.
"""

from __future__ import annotations

import json
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
from app.sc02.process import Sc02Process
from app.sc03 import demo, domain
from app.sc03.api import build_router
from app.sc03.process import PROCESS_PATH, Sc03Process
from app.sc03.seed import kst, load_seed
from app.sc03.view import topology, view
from app.store import build_postgres_backend

TABLES = "sc01_demo_run, sc01_history, sc02_demo_run, sc02_history, sc03_demo_run, sc03_history"


@pytest.fixture(params=["sqlite", "postgres"])
def proc(request) -> Iterator[Sc03Process]:
    """두 백엔드에서 같은 흐름 — 장면 1·2·3 저장소는 같은 DB의 다른 테이블이다."""
    backend = None
    if request.param == "postgres":
        backend = build_postgres_backend(require_postgres())
        stores = [PostgresSc01Store(backend.pool, p) for p in ("sc01", "sc02", "sc03")]
        with backend.pool.connection() as conn:
            conn.execute(f"TRUNCATE {TABLES}")
    else:
        stores = [
            SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), p)
            for p in ("sc01", "sc02", "sc03")
        ]
    published: list[str] = []
    sc02 = Sc02Process(stores[1], Sc01Process(stores[0], inline_agent=True))
    p = Sc03Process(stores[2], sc02, publish=published.append)
    p.published = published  # type: ignore[attr-defined]
    try:
        yield p
    finally:
        if backend is not None:
            with backend.pool.connection() as conn:
                conn.execute(f"TRUNCATE {TABLES}")
            backend.close()


def play(proc: Sc03Process, case: str = "BASE", until: str | None = None) -> dict:
    """각본을 `until` 노드(또는 단계 코드)를 실행한 직후까지."""
    doc = proc.create(case_id=case)
    for i, step in enumerate(demo.steps_for(case)):
        doc = demo.run_step(proc, doc["demo_run_id"], i)
        if until is not None and until in (step.node_id, step.code, step.answer.get("kind")):
            break
    return doc


def waiting(doc: dict) -> list[str]:
    return sorted(p["node_id"] for p in doc["bpm"]["snapshot"]["pendings"].values())


SEED = load_seed()


# ─────────────────────────── 착수 (D30·D31 · T31) ───────────────────────────


def test_d30_starts_from_the_sc02_handoff_and_exposes_nothing_ahead(proc: Sc03Process) -> None:
    """T40 — D30은 장면 2 인수 완료·장면 3 미착수. 미래의 회신·결론·과제·인수가 없다."""
    doc = proc.create()
    assert doc["review"]["state"] == "PENDING" and doc["bpm"] is None
    for key in ("runs", "reports", "facts", "questions", "candidates", "assignments", "minutes"):
        assert doc[key] == {}, key
    assert doc["decision"] is None and doc["handoff"] is None
    assert doc["clock"] == "2027-06-24T10:00:00+09:00"  # 장면 2 인수 시각
    b = doc["sc02"]
    assert b["price"]["new_price"] == "2120" and b["cost"]["cost_version_id"] == "C02-APP01"
    assert [i["issue_id"] for i in doc["review"]["links"]] == ["ISSUE-B07", "ISSUE-COST01"]
    assert domain.statuses(doc) | {} == {
        "review": "PENDING",
        "outcome": None,
        "risk": "OPEN",
        "forecast": "REVIEW_PENDING",
        "target": "UNCHANGED",
        "scene": "PENDING",
    }


def test_t31_start_twice_returns_the_same_result(proc: Sc03Process) -> None:
    """T31 — 같은 검토건의 재착수는 새 BPM 실행·이벤트 없이 같은 결과다. 경영관리 담당만
    착수한다."""
    rid = proc.create()["demo_run_id"]
    with pytest.raises(DomainError) as exc:
        proc.start(rid, actor="u-fin-exec")
    assert exc.value.status == 403
    first = proc.start(rid, actor="u-fin")
    again = proc.start(rid, actor="u-fin")
    assert first["bpm"]["run_id"] == again["bpm"]["run_id"]
    assert len(again["audit"]) == len(first["audit"])
    assert waiting(again) == ["Save_Analysis"]


def test_sc02_must_be_handed_off_base(proc: Sc03Process) -> None:
    """CT31 — 장면 2 인수 완료가 출발점이다. 다른 사례의 장면 2에서는 시작하지 않는다."""
    sc02 = proc.sc02.create(case_id="X01")
    with pytest.raises(DomainError) as exc:
        proc.create(sc01_demo_run_id=sc02["demo_run_id"])
    assert exc.value.status == 409


def test_unknown_case_is_422(proc: Sc03Process) -> None:
    with pytest.raises(DomainError) as exc:
        proc.create(case_id="E99")
    assert exc.value.status == 422


# ─────────────────────────── 기본 시연 끝 (D41 · T35·T36·T39·T41) ───────────────────────────


def test_base_demo_ends_in_sc03_completed_with_the_data_records(proc: Sc03Process) -> None:
    """
    D30~D41 — 완료 상태가 「SC03」 시트들의 완성 레코드와 같다: 사실 7건(분류·상태·확인자), 쟁점 2건
    (비차단·담당·기한), 후보 6건(4 포함·2 제외·사유·판단자), 과제 4건(책임자·인수 시각), 인계 필드.
    """
    doc = play(proc)
    assert doc["review"]["state"] == "SC03_COMPLETED"
    assert doc["review"]["outcome"] == "CONDITIONAL_ACCEPT"
    for row in SEED.rows("SC03사실확인"):
        f = doc["facts"][row["fact_id"]]
        assert (f["category"], f["state"]) == (row["category"], row["state"]), row["fact_id"]
        assert f["statement"] == row["statement"]
        assert f["reviewer"] == domain.ACCOUNTS[row["reviewer"]]
    for row in SEED.rows("SC03쟁점"):
        q = doc["questions"][row["question_id"]]
        assert q["blocking"] is row["blocking"] and q["state"] == row["state"]
        assert q["owner"] == domain.ACCOUNTS[row["owner"]] and q["due_at"] == kst(row["due_at"])
        assert q["fact_ref"] == row["fact_ref"] and q["treatment"] == row["treatment"]
        # 판단은 한 명령(EV31-08 17:05)이라 두 쟁점이 같은 시각이다 — 시트의 Q31 17:00은 개별 기록
        # 시각이다(회신 F31 11:00 · F32 11:05도 같은 사정, EV31-04 한 번에 회신한다).
        assert q["decided_at"] == kst(SEED.by_id("SC03이벤트")["EV31-08"]["event_at_KST"])
    for row in SEED.rows("SC03후보"):
        c = doc["candidates"][row["candidate_id"]]
        assert c["decision"] == row["decision"] and c["decision_reason"] == row["decision_reason"]
        assert c["task_id"] == row["task_id"]
        assert c["decided_by"] == "u-fin-exec" and c["decided_at"] == kst(row["decided_at"])
        assert c["effect_2027"] is None and c["effect_12m"] is None  # 미산정 — 0이 아니다
    for row in SEED.rows("SC03과제"):
        a = doc["assignments"][row["task_id"]]
        assert a["state"] == "ACCEPTED" and a["owner"] == domain.ACCOUNTS[row["owner_id"]]
        assert a["accepted_at"] == kst(row["accepted_at"])
        assert a["assigned_at"] == kst(row["assigned_at"]) and a["due_at"] == kst(row["due_at"])
        assert a["candidate_refs"] == [c for c in str(row["candidate_refs"] or "").split(";") if c]
    h = doc["handoff"]
    want = {r["field"]: r["value"] for r in SEED.rows("SC03인계")}
    assert h["handoff_id"] == want["handoff_id"] and h["review_id"] == want["review_id"]
    assert h["report_version"] == want["report_version"] and h["minutes_version"] == "MIN31-v1"
    assert ";".join(t["task_id"] for t in h["accepted_tasks"]) == want["accepted_tasks"]
    assert ";".join(h["open_questions"]) == want["open_questions"]
    assert (
        ";".join(c["candidate_id"] for c in h["excluded_candidates"]) == want["excluded_candidates"]
    )
    assert (h["risk_status"], h["forecast_status"], h["target_status"]) == (
        want["risk_status"],
        want["forecast_status"],
        want["target_status"],
    )
    assert h["analysis_due"] == kst(want["analysis_due"])
    assert h["consolidation_due"] == kst(want["consolidation_due"])
    assert h["as_of"] == kst(want["as_of"])
    assert h["next_meeting"] == {"meeting_id": "MT41", "at": "2027-07-12T10:00:00+09:00"}
    # M40 — 경과 145h25m · 영업 37h25m (SC03검증 V40·V41)
    assert (h["elapsed_minutes"], h["business_minutes"]) == (145 * 60 + 25, 37 * 60 + 25)
    # T39 — 장면 완료가 위험·전망·목표를 바꾸지 않는다
    s = domain.statuses(doc)
    assert (s["scene"], s["risk"], s["forecast"], s["target"]) == (
        "SC03_COMPLETED",
        "OPEN",
        "REVIEW_PENDING",
        "UNCHANGED",
    )
    assert doc["bpm"]["state"] == "done"


def test_events_follow_the_sc03_event_sheet(proc: Sc03Process) -> None:
    """SC03이벤트 EV31-01~22의 시각 — 회신·판단·확정·결론·회의록·인수·종료가 그 시각에 기록된다."""
    doc = play(proc)
    at = {e["event_id"]: kst(e["event_at_KST"]) for e in SEED.rows("SC03이벤트")}
    coded = {
        a["event_code"]: a["at"]
        for a in doc["audit"]
        if a["event_code"] and a["event_code"].startswith("EV31")
    }
    for code in (
        "EV31-01",
        "EV31-02",
        "EV31-03",
        "EV31-07",
        "EV31-08",
        "EV31-09",
        "EV31-10",
        "EV31-11",
        "EV31-12",
        "EV31-13",
        "EV31-14",
        "EV31-22",
    ):
        assert coded[code] == at[code], code
    replies = {r["dept"]: r["at"] for r in doc["replies"]}
    assert replies == {"SALES": at["EV31-04"], "BUY": at["EV31-05"], "PROD": at["EV31-06"]}
    m = doc["meetings"]["MT31"]
    assert [a["actor"] for a in m["attendance"]] == list(domain.ATTENDEES)
    assert "u-qa-lead" not in [a["actor"] for a in m["attendance"]]  # 자동 삽입 금지
    assert [r["record_id"] for r in m["records"]] == ["QA31", "QA32", "QA33", "QA34"]
    assert doc["meetings"]["MT41"]["state"] == "PLANNED"


def test_t36_c32_c33_share_at32_and_at34_has_no_candidate(proc: Sc03Process) -> None:
    """T36 — C32·C33은 AT32 한 건. AT34는 후보 없는 원인분석(Q32). 제외 2건에는 과제가 없다(T35)."""
    doc = play(proc, until="Decide_Review")
    a = doc["assignments"]
    assert sorted(a) == ["AT31", "AT32", "AT33", "AT34"]
    assert a["AT32"]["candidate_refs"] == ["C32", "C33"] and a["AT34"]["candidate_refs"] == []
    assert all(a[t]["state"] == "DRAFT" for t in a)
    assert (
        doc["candidates"]["C35"]["task_id"] is None and doc["candidates"]["C36"]["task_id"] is None
    )


# ─────────────────────────── 확인·차단 (T33·T34) ───────────────────────────


def test_t33_freeze_is_blocked_without_department_replies(proc: Sc03Process) -> None:
    """T33 — 무응답은 동의가 아니다. 회신이 없으면 자료 확정 차단(사유 목록)."""
    doc = play(proc, until="Confirm_Sales")
    problems = domain.freeze_problems(doc)
    assert "구매 확인 미회신" in problems and "생산 확인 미회신" in problems
    assert [d["state"] for d in view(doc)["departments"]] == ["RESPONDED", "PENDING", "PENDING"]


def test_only_the_department_head_replies(proc: Sc03Process) -> None:
    """자기 부서만 회신 — 다른 사람은 403이고 입력·상태가 그대로다."""
    doc = play(proc, until="Request_Confirm")
    rid = doc["demo_run_id"]
    answer = next(s for s in demo.steps_for("BASE") if s.node_id == "Confirm_Buy").answer
    with pytest.raises(DomainError) as exc:
        proc.act(rid, "Confirm_Buy", answer, actor="u-sales-lead")
    assert exc.value.status == 403
    assert proc.get(rid)["replies"] == []


def test_t34_non_blocking_needs_owner_due_and_treatment(proc: Sc03Process) -> None:
    """T34 — 비차단 처리에는 담당·기한·처리방향이 필수다. 빠지면 422, 미확인 상태가 그대로다."""
    doc = play(proc, until="Register_Gap")
    rid = doc["demo_run_id"]
    judge = next(s for s in demo.steps_for("BASE") if s.node_id == "Judge_Questions").answer
    with pytest.raises(DomainError) as exc:
        proc.act(rid, "Judge_Questions", {**judge, "Q31기한": ""}, actor="u-fin-exec")
    assert exc.value.status == 422
    assert proc.get(rid)["questions"]["Q31"]["state"] == "OPEN"


def test_blocking_judgement_returns_to_analysis(proc: Sc03Process) -> None:
    """CT35 — 차단이면 회의 확정을 보류하고 재분석·재확인으로 돌아간다(새 초안 → 부서 확인
    STALE)."""
    doc = play(proc, until="Register_Gap")
    rid = doc["demo_run_id"]
    judge = next(s for s in demo.steps_for("BASE") if s.node_id == "Judge_Questions").answer
    doc = proc.act(rid, "Judge_Questions", {**judge, "Q31차단": "차단"}, actor="u-fin-exec")
    assert waiting(doc) == ["Save_Analysis"]
    assert doc["questions"]["Q31"]["state"] == "BLOCKING"
    assert "Q31 차단 쟁점" in domain.freeze_problems(doc)


# ─────────────────────────── 결론·후보 (T35) ───────────────────────────


def test_t35_missing_exclusion_reason_saves_nothing(proc: Sc03Process) -> None:
    """구현명세 11장 — 제외 사유가 빠지면 결론과 후보 판단 **전체**를 저장하지 않는다."""
    doc = play(proc, until="AG31")
    rid = doc["demo_run_id"]
    decide = next(s for s in demo.steps_for("BASE") if s.node_id == "Decide_Review").answer
    with pytest.raises(DomainError) as exc:
        proc.act(
            rid,
            "Decide_Review",
            {**decide, "C35사유": ""},
            actor="u-fin-exec",
            expect={"report": "REP31-v1"},
        )
    assert exc.value.status == 422 and "C35" in str(exc.value)
    after = proc.get(rid)
    assert after["decision"] is None and all(
        c["decision"] is None for c in after["candidates"].values()
    )


def test_only_the_chair_decides_and_stale_report_is_409(proc: Sc03Process) -> None:
    doc = play(proc, until="AG31")
    rid = doc["demo_run_id"]
    decide = next(s for s in demo.steps_for("BASE") if s.node_id == "Decide_Review").answer
    with pytest.raises(DomainError) as role:
        proc.act(rid, "Decide_Review", decide, actor="u-fin")
    assert role.value.status == 403
    with pytest.raises(DomainError) as stale:
        proc.act(rid, "Decide_Review", decide, actor="u-fin-exec", expect={"report": "REP31-v0"})
    assert stale.value.status == 409


def test_meeting_records_only_by_attendees(proc: Sc03Process) -> None:
    """MT31 참석자만 기록한다 — 품질·대표는 참석자가 아니다."""
    doc = play(proc, until="Report_Meeting")
    with pytest.raises(DomainError) as exc:
        proc.meeting_record(
            doc["demo_run_id"],
            record_type="QUESTION",
            subject="x",
            content="질문",
            related="",
            actor="u-qa-lead",
        )
    assert exc.value.status == 403


# ─────────────────────────── 과제·인수 (T37·T38 · E35) ───────────────────────────


def test_t37_three_of_four_blocks_completion_with_the_missing_item(proc: Sc03Process) -> None:
    """
    T37 — 3/4(75%) 인수에서 종료는 422 COMPLETION_PREREQUISITE_FAILED와 남은 항목. 장면·인계는
    그대로.
    타부서 인수는 403. 전건 인수 뒤 같은 종료가 된다.
    """
    doc = play(proc, until="Accept_AT33")
    rid = doc["demo_run_id"]
    assert domain.acceptance_rate(doc) == {"assigned": 4, "accepted": 3, "rate": "0.75"}
    with pytest.raises(domain.PrerequisiteError) as exc:
        proc.act(rid, "Complete_Scene", {"완료메모": "x"}, actor="u-fin")
    assert exc.value.code == "COMPLETION_PREREQUISITE_FAILED"
    assert exc.value.items == ["AT34 현재 배정버전 미인수 (오세린)"]
    assert proc.get(rid)["handoff"] is None
    with pytest.raises(DomainError) as other:
        proc.act(rid, "Accept_AT34", {"AT34결정": "인수"}, actor="u-sales-lead")
    assert other.value.status == 403
    proc.act(rid, "Accept_AT34", {"AT34결정": "인수"}, actor="u-fin-lead", expect={"assignment": 1})
    done = proc.act(rid, "Complete_Scene", {"완료메모": "x"}, actor="u-fin")
    assert done["review"]["state"] == "SC03_COMPLETED"


def test_e35_another_department_cannot_accept_at31(proc: Sc03Process) -> None:
    """E35 — 타부서(영업) AT31 인수는 403, AT31 상태 변화 없음. 임원도 대신 인수하지 못한다."""
    doc = play(proc, until="Assign_Tasks")
    rid = doc["demo_run_id"]
    for actor in ("u-sales-lead", "u-fin-exec"):
        with pytest.raises(DomainError) as exc:
            proc.act(rid, "Accept_AT31", {"AT31결정": "인수"}, actor=actor)
        assert exc.value.status == 403
    assert proc.get(rid)["assignments"]["AT31"]["state"] == "ASSIGNED"


def test_e35m_assignment_without_owner_holds_every_task(proc: Sc03Process) -> None:
    """E35-M · CT38 — 책임자 NULL이 하나라도 있으면 전건 배정 보류(422, 행별 오류). 분모에 넣지
    않는다."""
    doc = play(proc, until="Confirm_Minutes")
    rid = doc["demo_run_id"]
    proc.edit_task(rid, "AT31", {"owner": None}, reason="E35-M 재현", actor="u-fin")
    with pytest.raises(DomainError) as exc:
        proc.act(rid, "Assign_Tasks", {"통보메모": "x"}, actor="u-fin-exec")
    assert exc.value.status == 422 and "AT31: 책임자 없음" in str(exc.value)
    after = proc.get(rid)
    assert all(a["state"] == "DRAFT" for a in after["assignments"].values())
    assert domain.acceptance_rate(after)["rate"] is None  # N/A — 0%가 아니다


def test_t38_old_assignment_version_cannot_be_accepted(proc: Sc03Process) -> None:
    """T38 · E32 — 반려 → 재배정(버전 2) 뒤 구버전(1) 인수는 409, 새 버전 인수는 된다."""
    doc = play(proc, case="E32", until="Reassign_AT31")
    rid = doc["demo_run_id"]
    a = doc["assignments"]["AT31"]
    assert a["assignment_version"] == 2 and a["state"] == "ASSIGNED"
    assert [h["state"] for h in a["history"]][-3:] == ["ASSIGNED", "RETURNED", "ASSIGNED"]
    assert a["dependency"] == "Q31 · AT32 외주비 자료(구매 협조)"
    with pytest.raises(DomainError) as exc:
        proc.act(
            rid, "Accept_AT31", {"AT31결정": "인수"}, actor="u-prod-lead", expect={"assignment": 1}
        )
    assert exc.value.status == 409
    doc = proc.act(
        rid, "Accept_AT31", {"AT31결정": "인수"}, actor="u-prod-lead", expect={"assignment": 2}
    )
    assert doc["assignments"]["AT31"]["accepted_version"] == 2


def test_return_needs_a_reason(proc: Sc03Process) -> None:
    doc = play(proc, until="Assign_Tasks")
    with pytest.raises(DomainError) as exc:
        proc.act(
            doc["demo_run_id"],
            "Accept_AT31",
            {"AT31결정": "반려", "AT31사유": ""},
            actor="u-prod-lead",
        )
    assert exc.value.status == 422


def test_idempotency_key_replays_and_conflicts(proc: Sc03Process) -> None:
    """구현명세 10장 — 같은 키·같은 본문은 최초 결과, 같은 키·다른 본문은 409."""
    doc = play(proc, until="Assign_Tasks")
    rid = doc["demo_run_id"]
    body = {"AT31결정": "인수", "AT31사유": ""}
    first = proc.act(rid, "Accept_AT31", body, actor="u-prod-lead", idempotency_key="SC03-AT31-1")
    again = proc.act(rid, "Accept_AT31", body, actor="u-prod-lead", idempotency_key="SC03-AT31-1")
    assert len(again["audit"]) == len(first["audit"])
    with pytest.raises(DomainError) as exc:
        proc.act(
            rid,
            "Accept_AT31",
            {**body, "AT31사유": "x"},
            actor="u-prod-lead",
            idempotency_key="SC03-AT31-1",
        )
    assert exc.value.status == 409


# ─────────────────────────── 예외 사례 (T40·T42) ───────────────────────────


def test_e31_dispute_blocks_then_new_version_and_reconfirm(proc: Sc03Process) -> None:
    """E31 — 구매 이견 → 차단 쟁점 → 보완(새 버전, 구매 확인 STALE) → 재확인 후 해제. 승인 원천
    유지."""
    doc = play(proc, case="E31", until="Revise_Buy")
    assert doc["reports"]["REP31-v0"]["basis_text"].startswith("승인단가 2,120원 · 8/1")
    assert doc["reports"]["REP31-v0.1"]["basis_text"].startswith("승인단가 2,120원 · 7/1")
    assert doc["questions"]["QD31"]["state"] == "REVISED" and doc["questions"]["QD31"]["blocking"]
    assert domain.dept_status(doc, "BUY")["state"] == "STALE"
    assert domain.dept_status(doc, "SALES")["state"] == "RESPONDED"  # 범위 밖 부서는 유지
    assert "구매 확인 재확인 필요" in domain.freeze_problems(doc)
    assert doc["sc02"]["price"]["effective_date"] == "2027-07-01"
    end = play(proc, case="E31")
    assert end["questions"]["QD31"]["state"] == "RESOLVED"
    disputed = [f for f in end["facts"].values() if f["state"] == "DISPUTED"]
    assert len(disputed) == 1  # 원 의견은 보존된다
    assert end["review"]["state"] == "SC03_COMPLETED"


def test_e33_calculation_error_blocks_the_request(proc: Sc03Process) -> None:
    """E33 — 정합 실패면 부서 확인 요청이 안 열린다. 실패 실행은 보존하고 정정 뒤 새 실행이다."""
    doc = play(proc, case="E33", until="Save_Analysis")
    assert waiting(doc) == ["Fix_Calc"]
    assert doc["runs"]["RUN-SC03-01"]["status"] == "CALCULATION_BLOCKED"
    assert doc["reports"] == {}
    with pytest.raises(DomainError) as exc:
        proc.act(
            doc["demo_run_id"],
            "Request_Confirm",
            {"회신기한": "2027-06-28T18:00:00+09:00"},
            actor="u-fin",
        )
    assert exc.value.status == 409
    doc = play(proc, case="E33", until="Fix_Calc")
    assert doc["runs"]["RUN-SC03-02"]["status"] == "CALCULATED"
    assert doc["reports"]["REP31-v0"]["run_id"] == "RUN-SC03-02"


def test_e34_new_forecast_keeps_the_frozen_report(proc: Sc03Process) -> None:
    """E34 — 확정 뒤 새 전망은 별도 실행·보고버전(REVISION_PENDING). REP31-v1·기본 F02는 그대로."""
    doc = play(proc, case="E34", until="E34")
    [rev] = doc["revisions"]
    assert rev["report_id"] == "REP31-v2-E34" and rev["status"] == "REVISION_PENDING"
    year = next(c for c in rev["changes"] if c["kind"] == "year")
    assert year["diff"] == "-1988000" and year["after"] == "3297998680"
    assert doc["reports"]["REP31-v1"]["kpis"]["combined"] == "3299986680"
    assert doc["meetings"]["MT31"]["report_version"] == "REP31-v1"
    with pytest.raises(DomainError) as base:
        proc.revise_forecast(
            play(proc, until="Distribute")["demo_run_id"], reason="x", actor="u-fin"
        )
    assert base.value.status == 409  # 기본 시연에는 섞지 않는다


def test_e36_agent_failure_falls_back_to_manual(proc: Sc03Process) -> None:
    """E36·T42 — 초안 실패는 수동 입력으로 간다. 원 계산·회신·기록은 그대로, 0원으로 채우지
    않는다."""
    doc = play(proc, case="E36")
    assert {o["status"] for o in doc["agent_outputs"].values()} == {"FAILED"}
    assert all(o["draft"] is None for o in doc["agent_outputs"].values())
    assert doc["review"]["state"] == "SC03_COMPLETED"
    assert doc["runs"]["RUN-SC03-01"]["result"]["periods"]["year"]["combined"] == "3299986680"


def test_agent_drafts_cite_only_inputs(proc: Sc03Process) -> None:
    """구현명세 12장 — 초안의 숫자는 입력에 있고, 근거 id가 붙는다. 주재자 판단을 대신하지
    않는다."""
    doc = play(proc, until="AG31")
    ag30, ag31 = sorted(doc["agent_outputs"].values(), key=lambda o: o["seq"])
    assert ag30["status"] == ag31["status"] == "SUCCEEDED"
    assert "153,939,000원" in ag30["draft"]["findings"][0]["text"]
    assert "주재자 판단" in ag31["draft"]["summary"]
    assert ag31["source_version"] == "RUN-SC03-01"
    assert doc["decision"] is None  # 초안은 결론이 아니다


def test_e37_late_submission_alerts_without_undoing_completion(proc: Sc03Process) -> None:
    """E37·T41 — 7/6 18:01 미제출은 지연 알림(경영관리·책임자). 과거 장면 3 완료는 그대로다."""
    doc = play(proc, case="E37")
    assert (
        doc["review"]["state"] == "SC03_COMPLETED" and doc["handoff"]["handoff_id"] == "HANDOFF31"
    )
    assert domain.delayed_tasks(doc) == ["AT31", "AT32", "AT33", "AT34"]
    at31 = next(a for a in doc["alerts"] if a["target"] == "AT31:submit")
    assert set(at31["to"]) == {"u-prod-lead", "u-fin"}
    assert doc["handoff"]["as_of"] == "2027-06-30T11:30:00+09:00"


# ─────────────────────────── 시계 · 초기화 · 각본 ───────────────────────────


def test_clock_alone_does_not_decide_or_accept(proc: Sc03Process) -> None:
    doc = play(proc, until="Assign_Tasks")
    doc = proc.set_clock(doc["demo_run_id"], "2027-06-30T13:00:00+09:00", actor="u-demo")
    assert all(a["state"] == "ASSIGNED" for a in doc["assignments"].values())
    accept = [a for a in doc["alerts"] if a["target"].endswith(":accept")]
    assert len(accept) == 4 and all("u-fin" in a["to"] for a in accept)  # 인수 지연 알림


def test_reset_returns_only_this_run_to_d30(proc: Sc03Process) -> None:
    doc = play(proc, until="Request_Confirm")
    rid = doc["demo_run_id"]
    doc = proc.reset(rid, actor="u-demo")
    assert doc["review"]["state"] == "PENDING" and doc["runs"] == {} and doc["bpm"] is None
    assert proc.sc02.get(rid)["scene"] == "HANDED_OFF"  # 장면 2는 그대로
    assert any(a["action"] == "demo_run_reset" for a in doc["audit"])


def test_script_cannot_skip_and_rerun_is_harmless(proc: Sc03Process) -> None:
    rid = proc.create()["demo_run_id"]
    with pytest.raises(DomainError) as exc:
        demo.run_step(proc, rid, 2)
    assert exc.value.status == 409
    first = demo.run_step(proc, rid, 0)
    assert demo.run_step(proc, rid, 0)["audit"] == first["audit"]


def test_changes_are_published_on_the_sc03_channel(proc: Sc03Process) -> None:
    rid = play(proc, until="Save_Analysis")["demo_run_id"]
    assert f"sc03:{rid}" in proc.published  # type: ignore[attr-defined]


def test_history_keeps_each_step_for_read_only_past(proc: Sc03Process) -> None:
    rid = play(proc, until="Request_Confirm")["demo_run_id"]
    entries = proc.store.history(rid)
    assert len(entries) >= 4
    first = proc.store.at(rid, entries[0]["seq"])
    assert first is not None and first["review"]["state"] == "PENDING"


# ─────────────────────────── BPMN ↔ 역할표 ───────────────────────────


def test_every_user_task_has_a_role_and_matching_assignees() -> None:
    """NODE_ROLES와 BPMN이 갈라지면 화면 역할 검사와 결재 담당자가 어긋난다(장면 1·2와 같은
    그물)."""
    process = read_process(Path(PROCESS_PATH).read_bytes())
    users = [n.id for n in process.all_nodes() if n.kind == "userTask"]
    assert sorted(users) == sorted(domain.NODE_ROLES)
    for node in process.all_nodes():
        if node.kind != "userTask":
            continue
        role = domain.NODE_ROLES[node.id]["role"]
        assignees = node.prop("approval").assignees
        if isinstance(assignees, list):
            assert {u["role"] for u in USERS.values() if u["name"] in assignees} == {role}, node.id
        else:
            task = domain.NODE_ROLES[node.id]["owner_of"]
            assert assignees == f"{task}책임자", node.id


# ─────────────────────────── HTTP ───────────────────────────


def test_http_errors_and_shapes(proc: Sc03Process) -> None:
    app = FastAPI()
    app.include_router(build_router(proc, Hub()))
    client = TestClient(app)
    created = client.post("/sc03/demo-runs", json={"executor": "embedded"})
    assert created.status_code == 201
    body = created.json()
    rid = body["demoRunId"]
    assert body["status"]["risk"] == "OPEN" and body["completion"]["met"] is False
    assert client.get("/sc03/demo-runs/nope").status_code == 404
    assert client.post(f"/sc03/demo-runs/{rid}/start").status_code == 403
    ok = client.post(f"/sc03/demo-runs/{rid}/start", headers={"x-demo-actor": "u-fin"})
    assert ok.status_code == 200 and ok.json()["bpm"]["waiting"][0]["nodeId"] == "Save_Analysis"
    wrong = client.post(
        f"/sc03/demo-runs/{rid}/actions/Request_Confirm",
        json={"answer": {}},
        headers={"x-demo-actor": "u-fin"},
    )
    assert wrong.status_code == 409
    early = client.post(
        f"/sc03/demo-runs/{rid}/actions/Complete_Scene",
        json={"answer": {"완료메모": "x"}},
        headers={"x-demo-actor": "u-fin"},
    )
    assert early.status_code == 422
    detail = early.json()["detail"]
    assert detail["error_code"] == "COMPLETION_PREREQUISITE_FAILED" and detail["blocking_items"]
    script = client.get("/sc03/script", params={"case_id": "E32"}).json()
    assert [s["nodeId"] for s in script].count("Accept_AT31") == 2
    topo = client.get("/sc03/process").json()
    assert {n["recordOf"] for n in topo["nodes"] if n["recordOf"]} >= {
        "Save_Analysis",
        "Decide_Review",
        "Accept_AT31",
        "Complete_Scene",
    }


def test_ts_topology_fixture_is_the_bpmn(proc: Sc03Process) -> None:
    """
    화면 테스트의 토폴로지 사본(`tests/fixtures/sc03-process.json`) = BPMN. BPMN을 고치면 실패한다
    — 다시
    만든다: `curl -s localhost:8077/sc03/process | python3 -m json.tool --indent 1`
    `> tests/fixtures/sc03-process.json`
    """
    fixture = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sc03-process.json"
    assert json.loads(fixture.read_text(encoding="utf-8")) == topology(proc.process)


# ─────────────────────── 화면 직접 진행의 단계 추적(2026-10-28) ───────────────────────


def test_screen_answers_move_the_script_marker_even_out_of_order(proc: Sc03Process) -> None:
    """
    화면에서 직접 답해도 플레이어의 단계(`step`·`script_index`)가 따라온다 — 예전에는 끝까지
    「단계 1/26 D30」에 머물렀다. 병렬 확인은 순서가 바뀌어도 되고(생산 → 영업 → 구매), 사이의
    조회(D33)는 건너뛴다. 따라온 뒤에는 각본(「다음 단계」)이 남은 단계부터 잇는다.
    """
    rid = proc.create()["demo_run_id"]
    steps = demo.steps_for("BASE")
    answer = {s.node_id: dict(s.answer) for s in steps if s.node_id}
    actor = {s.node_id: s.actor for s in steps if s.node_id}

    def act(node: str) -> dict:
        return proc.act(rid, node, answer[node], actor=actor[node])

    proc.set_clock(rid, steps[0].at, actor="u-demo")
    doc = proc.start(rid, actor="u-fin")
    assert (doc["step"], doc["script_index"]) == ("D31", 0)
    assert act("Save_Analysis")["script_index"] == 1
    assert act("Request_Confirm")["script_index"] == 3  # D33 조회를 건너뛴다
    assert act("Confirm_Prod")["script_index"] == 3  # 영업·구매가 먼저인 각본 — 아직
    assert act("Confirm_Sales")["script_index"] == 4
    doc = act("Confirm_Buy")
    assert (doc["step"], doc["script_index"]) == ("D35", 6)  # 구매·생산을 함께 지나간다
    assert doc["script_follow"]["ahead"] == []
    for index in range(7, len(steps)):
        doc = demo.run_step(proc, rid, index)
    assert doc["review"]["state"] == "SC03_COMPLETED"
