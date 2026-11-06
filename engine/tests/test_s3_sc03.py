"""
시나리오 3 장면 3 — 팀장 보고 및 승인(`app/s3/sc03/`, `docs/s3/sc03.md`).

* 구현명세 §4 인수시험 01~09. 장면 1(`company1.s3.sc01`)을 인계까지, 장면 2(`company1.s3.sc02`)를
  상신(HAND-S3-02)까지 진짜 BPM 엔진으로 돌린 뒤 장면 3 그림(`processes/s3-sc03.bpmn`)을 돌린다.
  서비스 태스크는 C15 일꾼의 수행기를 지난다(Studio 흉내). 회계팀장의 결정·인계 재시도와
  회계담당자의 보완 처리·재검토는 결재 답이다. 회사 시스템은 기간계 쌍둥이다(첨부·후속 업무
  등록·장애 스위치).
* 숫자는 장면 2 상신본의 것이다(새로 계산하지 않는다) — 보완 재계산만 같은 계산 기능을 다시 부른다.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from chaeksas.core.engine import State
from test_s3_sc02 import _answer, _base, _pending, _scene1, _start

from app import company as company_mod
from app.s3.sc01.process import S3Sc01Process
from app.s3.sc02.process import S3Sc02Process
from app.s3.sc03.process import S3Sc03Process, current
from app.s3.sc03.records import dashboard
from app.sc01.domain import DomainError
from app.sc01.store import build_sc01_store
from app.store import build_sqlite_backend

LEAD, OWNER, CLOSE = "회계팀장", "회계담당", "S3-CLOSE-01"
REASON = "A사 평가 행에서 수정계획의 회차와 영업 확인 기록을 추적할 수 있도록 참조를 보강해 주세요."
NOTE = "A사 개별평가 행에 PLAN-A-26 1~3회차(각 20)·CONF-26-S·CONF-26-F 참조를 붙였다"


@pytest.fixture()
def company():
    return company_mod.default_client()


@pytest.fixture()
def procs(tmp_path, company):
    backend = build_sqlite_backend(str(tmp_path / "engine.sqlite"))
    s1 = S3Sc01Process(build_sc01_store(backend, "s3sc01"), company=company)
    s2 = S3Sc02Process(build_sc01_store(backend, "s3sc02"), company=company, sc01=s1)
    s3 = S3Sc03Process(build_sc01_store(backend, "s3sc03"), company=company, sc01=s1, sc02=s2)
    return s1, s2, s3


@pytest.fixture()
def rid(procs) -> str:
    """장면 1 인계 → 장면 2 상신(HAND-S3-02)까지 — 장면 3을 열 수 있는 회차."""
    s1, s2, _ = procs
    rid = f"s3-{uuid.uuid4().hex[:8]}"
    s1.create(rid, executor="studio")
    _scene1(s1, rid)
    s2.create(rid, executor="studio")
    _base(s1, s2, rid)
    return rid


@pytest.fixture()
def opened(procs, rid) -> str:
    procs[2].create(rid, executor="studio")
    return rid


def _run(s3, rid: str):
    return _start(s3, rid, "company1.s3.sc03")


def _decide(engine, run, s3, rid, decision="승인", *, version=None, by=LEAD, **extra) -> State:
    answer = {"결정보고버전": str(version or current(s3.get(rid))["version"]), "결정": decision}
    if extra.get("target"):
        answer["보완대상"] = extra["target"]
    if extra.get("reason"):
        answer["보완사유"] = extra["reason"]
    return _answer(engine, run, "Approve_Report", answer, by)


def _revise(engine, run, s3, rid, action: str, note: str | None = None) -> State:
    answer = {"보완보고버전": str(current(s3.get(rid))["version"]), "보완처리": action}
    if note:
        answer["변경내역"] = note
    return _answer(engine, run, "Revise_Report", answer)


def _return(engine, run, s3, rid) -> None:
    _decide(engine, run, s3, rid, "보완 요청", target="대손충당금", reason=REASON)
    assert _pending(run) == ["Revise_Report"]


def _relink(procs, company, rid, *variants: str) -> str:
    """자료 담당자가 입력을 다시 연결했다 — 세계 따라가기처럼 장면 1~3에 넘긴다."""
    got = company.link_close_inputs(rid, list(variants))
    for p in procs:
        p.receive_inputs(rid)
    return got["version"]


def _rows(doc: dict) -> dict:
    return {r["item_id"]: r for r in dashboard(doc)["rows"]}


# ─────────────────────────── 인수시험 01~09 ───────────────────────────


def test_t01_scene_opens_only_after_scene2_submits(procs) -> None:
    s1, s2, s3 = procs
    rid = f"s3-{uuid.uuid4().hex[:8]}"
    s1.create(rid, executor="studio")
    _scene1(s1, rid)
    s2.create(rid, executor="studio")
    with pytest.raises(DomainError) as early:
        s3.create(rid, executor="studio")
    assert early.value.status == 409 and "HAND-S3-02" in str(early.value)
    assert s3.store.load(rid) is None


def test_t01_inbox_and_both_rows_open_the_same_report_and_viewing_approves_nothing(
    procs, opened
) -> None:
    """
    01 — 수신함과 두 체크리스트 행이 같은 보고·버전·첨부를 연다. 열람(보고 열기)만으로 승인 건수는
    늘지 않는다 — 승인 대기 2항목 · 승인 0건.
    """
    _, s2, s3 = procs
    rid = opened
    engine, run = _run(s3, rid)
    assert _pending(run) == ["Approve_Report"]
    doc = s3.get(rid)
    ver = current(doc)
    sent = s2.get(rid)["report"]
    assert (ver["report_id"], ver["version"], ver["state"]) == ("REP-S3-01", 1, "WAITING")
    assert ver["result_version"] == sent["result_version"]
    assert ver["attachment"]["file_id"] == sent["attachment"]["file_id"] == "WP-S3-v1"
    assert doc["entry"]["opened_at"] is not None and doc["decisions"] == []
    board = dashboard(doc)
    assert {(r["report_id"], r["report_version"]) for r in board["rows"]} == {("REP-S3-01", 1)}
    assert (board["waiting_approval"], board["approved"], board["reports_approved"]) == (
        2,
        {"done": 0, "of": 2},
        0,
    )
    vars_ = run.variables
    assert (vars_["보고ID"], vars_["보고버전"], vars_["첨부ID"]) == ("REP-S3-01", 1, "WP-S3-v1")


def test_t02_submitted_evidence_is_the_report_as_submitted(procs, opened) -> None:
    """
    02 — A사 행·근거·주석: 회수액 60(PLAN-A-26 3회 × 20, 영업 CONF-26-S·회계 CONF-26-F), A사
    증가 15, 전체 증가 10, 추가 설정 30. 상각비 요청 50. 원 보고·버전과 같다.
    """
    _, _, s3 = procs
    ver = current(s3.get(opened))
    items = {i["item_id"]: i for i in ver["items"]}
    assert [
        (i["prior"], i["current"], i["change"], i["book"], i["request"]) for i in ver["items"]
    ] == [
        ("1120", "1200", "80", "1150", "50"),
        ("100", "110", "10", "80", "30"),
    ]
    assert (items["DEP"]["request_label"], items["ALW"]["request_label"]) == (
        "추가 계상",
        "추가 설정",
    )
    ev = ver["evidence"]
    a26 = next(i for i in ev["individual"] if i["as_of"] == "2026-12-31")
    a25 = next(i for i in ev["individual"] if i["as_of"] == "2025-12-31")
    assert (a26["recovery"], a25["recovery"]) == ("60", "75")
    assert (a25["allowance"], a26["allowance"]) == ("25", "40")
    assert [r["amount"] for r in a26["plan_rounds"]] == ["20", "20", "20"]
    assert (a26["sales_confirmation"], a26["accounting_confirmation"]) == ("CONF-26-S", "CONF-26-F")
    conf = {c["confirmation_id"]: c for c in ev["confirmations"]}
    assert {k: (c["plan_ref"], c["amount"]) for k, c in conf.items() if k != "CONF-25"} == {
        "CONF-26-S": ("PLAN-A-26", "60"),
        "CONF-26-F": ("PLAN-A-26", "60"),
    }
    methods = {m["method"]: m for m in ev["methods"]}
    assert (methods["개별"]["change"], methods["집합"]["change"], methods["합계"]["change"]) == (
        "15",
        "-5",
        "10",
    )
    note = ev["allowance_note"]
    assert (note["opening"], note["written_off"], note["provision"], note["ending"]) == (
        "100",
        "20",
        "30",
        "110",
    )
    assert ev["depreciation_note"]["closing"] == "8700"
    alloc = {a["group"]: a["current"] for a in ev["allocation"]}
    assert (alloc["제조원가"], alloc["판매관리비"], alloc["귀속 합계"]) == ("1020", "180", "1200")
    assert {a["asset_id"]: a["change"] for a in ev["asset_changes"]} == {"E2": "100", "E3": "-20"}


def test_t03_normal_approval_hands_the_approved_report_to_both_roles(
    procs, company, opened
) -> None:
    """
    03 — 지정 팀장이 승인 → 결정 1건, 승인 2/2. 전표 반영 담당·주석 취합 담당에게 같은 승인본이
    넘어가고 전표·주석 완료는 각각 0/2다(인계 HAND-S3-03).
    """
    _, _, s3 = procs
    rid = opened
    engine, run = _run(s3, rid)
    assert _decide(engine, run, s3, rid) is State.DONE
    doc = s3.get(rid)
    [dec] = doc["decisions"]
    assert (dec["decision_id"], dec["decision"], dec["decided_by"], dec["report_version"]) == (
        "DEC-S3-01",
        "APPROVED",
        LEAD,
        1,
    )
    board = dashboard(doc)
    assert board["approved"] == {"done": 2, "of": 2} and board["reports_approved"] == 1
    assert (board["posting"], board["notes"]) == ({"done": 0, "of": 2}, {"done": 0, "of": 2})
    assert board["handed"] == {"done": 2, "of": 2}
    rows = _rows(doc)
    assert [(r["posting"]["state_label"], r["notes"]["state_label"]) for r in rows.values()] == [
        ("반영 대기", "취합 대기"),
        ("반영 대기", "취합 대기"),
    ]
    assert rows["DEP"]["notes"]["note_sheet"] == "유형자산주석"
    assert rows["ALW"]["notes"]["note_sheet"] == "충당금주석"
    assert rows["ALW"]["posting"]["assignee"]["name"] == "전표반영담당"
    assert rows["ALW"]["notes"]["assignee"]["name"] == "주석취합담당"
    stored = company.close_followups(rid)
    assert [(r["path"], r["report_version"], r["decision_id"]) for r in stored] == [
        ("POSTING", 1, "DEC-S3-01"),
        ("NOTES", 1, "DEC-S3-01"),
    ]
    assert sorted(t["task_id"] for r in stored for t in r["tasks"]) == [
        "FUP-S3-NOTE-ALW",
        "FUP-S3-NOTE-DEP",
        "FUP-S3-POST-ALW",
        "FUP-S3-POST-DEP",
    ]
    posting = next(r for r in stored if r["path"] == "POSTING")
    assert [(t["item_id"], t["request"]) for t in posting["tasks"]] == [
        ("DEP", "50"),
        ("ALW", "30"),
    ]
    assert {r["attachment"]["file_id"] for r in stored} == {"WP-S3-v1"}
    h = doc["handoff"]
    assert (h["handoff_id"], h["report_version"], h["approved_by"]) == ("HAND-S3-03", 1, LEAD)
    assert doc["bpm"]["visited"][-1] == "End" and doc["bpm"]["state"] == "done"


def test_t04_return_needs_target_and_reason_and_holds_the_handoff(procs, company, opened) -> None:
    """
    04 — 충당금만 골라 사유를 적은 보완 요청만 받는다(대상·사유 누락은 같은 결재로). 충당금 행에
    사유·회계담당, 상각비는 검토 완료·공통 보고 보완 대기, 보고 전체 보완 중, 승인·후속 인계 0건.
    """
    _, _, s3 = procs
    rid = opened
    engine, run = _run(s3, rid)
    _decide(engine, run, s3, rid, "보완 요청", reason=REASON)
    assert _pending(run) == ["Approve_Report"] and s3.get(rid)["decisions"] == []
    _decide(engine, run, s3, rid, "보완 요청", target="대손충당금")
    assert _pending(run) == ["Approve_Report"] and s3.get(rid)["decisions"] == []
    _return(engine, run, s3, rid)
    doc = s3.get(rid)
    assert current(doc)["state"] == "RETURNED"
    rows = _rows(doc)
    assert (rows["ALW"]["state"], rows["DEP"]["state"]) == ("NEEDS_REVISION", "REVIEWED_WAIT")
    assert rows["ALW"]["revision"]["reason"] == REASON
    assert rows["ALW"]["revision"]["owner"] == OWNER and rows["DEP"]["revision"] is None
    assert rows["DEP"]["state_label"] == "검토 완료 · 공통 보고 보완 대기"
    board = dashboard(doc)
    assert board["approved"] == {"done": 0, "of": 2} and board["handed"]["done"] == 0
    assert company.close_followups(rid) == [] and doc["handoff"] is None
    [rev] = doc["revisions"]
    assert (rev["targets"], rev["base_version"], rev["state"]) == (["ALW"], 1, "OPEN")


def test_t05_reference_only_resubmits_a_new_version_with_the_same_amounts(procs, opened) -> None:
    """
    05 — 참조만 보강해 재상신: 금액 동일, 같은 보고 ID의 새 버전(v2). 팀장은 변경 전후와 이전 보완
    사유를 본다. 이전 버전(v1)과 결정은 이력으로 남는다. 변경 내역 없는 참조 보강은 같은 결재로
    돌아간다.
    """
    _, _, s3 = procs
    rid = opened
    engine, run = _run(s3, rid)
    _return(engine, run, s3, rid)
    _revise(engine, run, s3, rid, "참조 보강 재상신")
    assert _pending(run) == ["Revise_Report"] and len(s3.get(rid)["versions"]) == 1
    _revise(engine, run, s3, rid, "참조 보강 재상신", NOTE)
    assert _pending(run) == ["Approve_Report"]
    doc = s3.get(rid)
    v1, v2 = doc["versions"]
    assert (v1["state"], v2["state"], v2["report_id"]) == ("RETURNED", "WAITING", "REP-S3-01")
    assert v2["result_version"] == v1["result_version"]
    assert v2["attachment"] == v1["attachment"]
    assert (
        [i["request"] for i in v2["items"]] == [i["request"] for i in v1["items"]] == ["50", "30"]
    )
    [change] = v2["changes"]
    assert (change["item"], change["kind"], change["amount_same"]) == ("ALW", "reference", True)
    assert change["after"].endswith(NOTE) and change["before"] == v1["items"][1]["reason"]
    assert v2["previous"] == {
        "version": 1,
        "decision_id": "DEC-S3-01",
        "targets": ["ALW"],
        "reason": REASON,
    }
    rereview = [r for r in doc["reviews"] if r["state"] == "REREVIEWED"]
    assert [r["item"] for r in rereview] == ["ALW"]
    # 구버전(v1)으로 결정하면 처리된 상태를 안내하고, 현재 버전에서만 결정한다
    _decide(engine, run, s3, rid, version=1)
    assert _pending(run) == ["Approve_Report"]
    assert _decide(engine, run, s3, rid, version=2) is State.DONE
    doc = s3.get(rid)
    assert [d["report_version"] for d in doc["decisions"]] == [1, 2]
    assert doc["handoff"]["report_version"] == 2


def test_t06_amount_change_holds_resubmission_until_recalculated_and_rereviewed(
    procs, company, opened
) -> None:
    """
    06 — 회수예상액 60 → 50(영업 변경 회신·회계 재평가). 재계산 전 재상신은 보류되고, 장면 1
    재점검 → 재계산(새 결과·첨부 — 번호는 장면 2에 이어진다) → 영향 항목(충당금)만 재검토 → 재상신
    뒤 새 버전으로 결정한다. 상각비 검토는 승계된다.
    """
    s1, _, s3 = procs
    rid = opened
    engine, run = _run(s3, rid)
    _return(engine, run, s3, rid)
    new_input = _relink(procs, company, rid, "A-RECOVERY-50")
    assert s3.get(rid)["input_notice"]["input_version"] == new_input
    _revise(engine, run, s3, rid, "재상신")  # 재계산 전 — 보류
    assert _pending(run) == ["Revise_Report"]
    _revise(engine, run, s3, rid, "재계산")  # 장면 1 재점검 전 — 보류
    assert _pending(run) == ["Revise_Report"] and s3.get(rid)["results"] == []
    engine1, run1 = _start(s1, rid, "company1.s3.sc01")
    assert _pending(run1) == ["Check_Allowance"]
    _answer(engine1, run1, "Check_Allowance", {"충당점검버전": new_input, "충당점검": "점검 실행"})
    assert s1.get(rid)["handoff"]["valid"] is True
    _revise(
        engine, run, s3, rid, "참조 보강 재상신", NOTE
    )  # 입력이 바뀌었다 — 참조 보강으로 못 올린다
    assert _pending(run) == ["Revise_Report"]
    _revise(engine, run, s3, rid, "재계산")
    assert _pending(run) == ["Review_Revision"]
    doc = s3.get(rid)
    [res] = doc["results"]
    assert (res["result_version"], res["input_version"]) == ("RES-S3-v2", new_input)
    [att] = doc["attachments"]
    assert (att["file_id"], att["file_version"]) == ("WP-S3-v2", 2)
    assert [r["run_id"] for r in doc["runs"]] == ["RUN-S3-02"]
    summary = {s["item"]: s for s in res["calc"]["summary"]}
    assert (summary["ALW"]["current"], summary["ALW"]["request"]) == ("120", "40")
    assert summary["DEP"]["request"] == "50"
    carried = [r for r in doc["reviews"] if r["state"] == "CARRIED"]
    assert [(r["item"], r["carried_from"]) for r in carried] == [("DEP", "REV-DEP-1")]
    assert run.variables["검토대상"] == "ALW"
    _answer(engine, run, "Review_Revision", {"재검토결과버전": "RES-S3-v2", "재검토": "검토 완료"})
    assert _pending(run) == ["Revise_Report"]
    # 보완 처리 결재가 재검토 뒤의 안내를 보인다 — 재계산 때 안내가 남지 않는다(Center 실측)
    assert run.variables["처리안내"] == "재검토 끝 — 재상신"
    _revise(engine, run, s3, rid, "재상신")
    assert _pending(run) == ["Approve_Report"]
    # 팀장 결재의 첨부 이름이 새 첨부의 것이다 — 열 때 받은 v1 이름이 남지 않는다(Center 실측)
    assert (run.variables["첨부ID"], run.variables["파일명"]) == (
        "WP-S3-v2",
        "S3-CLOSE-01_결산조정_계산근거_v2.xlsx",
    )
    doc = s3.get(rid)
    v2 = current(doc)
    assert (v2["version"], v2["result_version"], v2["attachment"]["file_id"]) == (
        2,
        "RES-S3-v2",
        "WP-S3-v2",
    )
    assert [i["request"] for i in v2["items"]] == ["50", "40"]
    a26 = next(i for i in v2["evidence"]["individual"] if i["as_of"] == "2026-12-31")
    assert (a26["recovery"], a26["allowance"]) == ("50", "50")
    req = next(c for c in v2["changes"] if c["field"] == "request")
    assert (req["item"], req["before"], req["after"]) == ("ALW", "30", "40")
    stored = {a["file_id"]: a for a in company.close_attachments(rid)}
    assert stored["WP-S3-v2"]["scene"] == 3
    assert _decide(engine, run, s3, rid) is State.DONE
    posting = next(r for r in company.close_followups(rid) if r["path"] == "POSTING")
    assert (posting["report_version"], [t["request"] for t in posting["tasks"]]) == (
        2,
        ["50", "40"],
    )


def test_t07_unassigned_old_version_and_attachment_failure_hold_the_decision(
    procs, company, opened
) -> None:
    """
    07 — 미지정 사용자·구버전·첨부 접근 실패는 각각 사유(복구 담당)를 남기고 결정·후속 배정 0건으로
    같은 결재에 돌아간다. 복구 뒤 지정 팀장·유효 버전에서만 결정한다.
    """
    _, _, s3 = procs
    rid = opened
    engine, run = _run(s3, rid)
    _decide(engine, run, s3, rid, by=OWNER)
    doc = s3.get(rid)
    assert _pending(run) == ["Approve_Report"] and doc["decisions"] == []
    assert doc["hold"]["status"] == 403 and "지정 결재자" in doc["hold"]["reason"]
    _decide(engine, run, s3, rid, version=2)
    assert (
        s3.get(rid)["hold"]["status"] == 409 and "현재 상신 버전" in s3.get(rid)["hold"]["reason"]
    )
    company.set_close_fault(rid, "attachment_unavailable", 1)
    _decide(engine, run, s3, rid)
    doc = s3.get(rid)
    assert doc["decisions"] == [] and "첨부 WP-S3-v1를 열 수 없다" in doc["hold"]["reason"]
    assert doc["hold"]["recovery_owner"].startswith("회계담당")
    assert dashboard(doc)["hold"]["reason"] == doc["hold"]["reason"]
    assert company.close_followups(rid) == [] and len(doc["holds"]) == 3
    assert _decide(engine, run, s3, rid) is State.DONE
    doc = s3.get(rid)
    assert len(doc["decisions"]) == 1 and doc["hold"] is None and len(doc["holds"]) == 3


def test_t08_double_click_and_concurrent_decisions_keep_one_decision(
    procs, company, opened
) -> None:
    """
    08 — 승인 이중 클릭은 같은 결정 ID, 승인 뒤 보완 요청은 처리된 상태·현재 버전 안내(409). 두 행
    상태는 같고 후속 배정은 중복되지 않는다.
    """
    _, _, s3 = procs
    rid = opened
    engine, run = _run(s3, rid)
    assert _decide(engine, run, s3, rid) is State.DONE
    ext = s3.get(rid)["bpm"]["external_run_id"]
    body = {
        "demo_run_id": rid,
        "close_id": CLOSE,
        "report_version": "1",
        "decision": "승인",
        "answered_by": LEAD,
    }
    again = s3.operate(rid, "decide_close_report", body, external_run_id=ext, via="studio")
    assert (again["decision_id"], again["decision"]) == ("DEC-S3-01", "APPROVED")
    with pytest.raises(DomainError) as clash:
        s3.operate(
            rid,
            "decide_close_report",
            body | {"decision": "보완 요청", "targets": "대손충당금", "reason": REASON},
            external_run_id=ext,
            via="studio",
        )
    assert clash.value.status == 409 and "DEC-S3-01" in str(clash.value)
    assert "현재 버전 v1" in str(clash.value)
    doc = s3.get(rid)
    assert len(doc["decisions"]) == 1 and doc["hold"] is None
    assert {r["state"] for r in dashboard(doc)["rows"]} == {"APPROVED"}
    s3.operate(rid, "hand_off_close_approval", body, external_run_id=ext, via="studio")
    stored = company.close_followups(rid)
    assert len(stored) == 2 and sum(len(r["tasks"]) for r in stored) == 4


def test_t09_partial_handoff_keeps_the_approval_and_retries_only_the_failed_path(
    procs, company, opened
) -> None:
    """
    09 — 주석 경로만 실패: 승인은 그대로, 전표 경로는 등록(중복 0), 주석 경로는 인계 대기와 사유.
    재시도는 주석 경로만 — 등록 응답이 유실된 경우에는 기간계의 기존 업무를 먼저 찾아 그대로 쓴다.
    """
    _, _, s3 = procs
    rid = opened
    company.set_close_fault(rid, "notes_handoff_fail", 1)
    engine, run = _run(s3, rid)
    assert _decide(engine, run, s3, rid) is State.WAITING
    assert _pending(run) == ["Retry_Handoff"]
    doc = s3.get(rid)
    assert current(doc)["state"] == "APPROVED" and doc["handoff"] is None
    rows = _rows(doc)
    assert rows["ALW"]["state"] == "APPROVED"
    assert (rows["ALW"]["posting"]["state_label"], rows["ALW"]["notes"]["state_label"]) == (
        "반영 대기",
        "인계 대기",
    )
    assert "주석 취합 업무 등록 실패" in rows["ALW"]["notes"]["reason"]
    assert [r["path"] for r in company.close_followups(rid)] == ["POSTING"]
    company.set_close_fault(rid, "notes_handoff_lost", 1)
    _answer(engine, run, "Retry_Handoff", {"인계재시도": "인계 재시도"}, LEAD)
    assert _pending(run) == ["Retry_Handoff"]  # 등록은 됐는데 응답이 유실됐다
    assert [r["path"] for r in company.close_followups(rid)] == ["POSTING", "NOTES"]
    assert "응답이 유실" in s3.get(rid)["followups"]["NOTES"]["reason"]
    assert _answer(engine, run, "Retry_Handoff", {"인계재시도": "인계 재시도"}, LEAD) is State.DONE
    doc = s3.get(rid)
    stored = company.close_followups(rid)
    assert len(stored) == 2 and sum(len(r["tasks"]) for r in stored) == 4
    assert doc["followups"]["NOTES"]["recovered"] is True
    assert doc["followups"]["POSTING"]["attempts"] == 1
    assert doc["followups"]["NOTES"]["attempts"] == 3
    assert dashboard(doc)["handed"] == {"done": 2, "of": 2}
    assert "Retry_Handoff" in doc["bpm"]["visited"] and doc["handoff"] is not None


# ─────────────────────────── 기록 · 세계 따라가기 · 대시보드 · 확장 ───────────────────────────


def test_every_written_version_matches_the_record_schemas(procs, company, opened) -> None:
    """
    경영 기록(`docs/records/s3/sc03/`) — 보류·보완(참조 보강·재계산·재검토)·부분 인계 경로의 모든
    판이 봉투·종류별 스키마를 통과한다(다시 뽑기 `NOWVIEW_WRITE_RECORD_SCHEMAS=1`).
    """
    from records_contract import check, every_version

    from app.s3.sc03.records import KINDS

    s1, _, s3 = procs
    rid = opened
    engine, run = _run(s3, rid)
    _decide(engine, run, s3, rid, by=OWNER)
    _return(engine, run, s3, rid)
    _revise(engine, run, s3, rid, "참조 보강 재상신", NOTE)
    _decide(engine, run, s3, rid, "보완 요청", target="두 항목", reason=REASON)
    new_input = _relink(procs, company, rid, "A-RECOVERY-50")
    engine1, run1 = _start(s1, rid, "company1.s3.sc01")
    _answer(engine1, run1, "Check_Allowance", {"충당점검버전": new_input, "충당점검": "점검 실행"})
    _revise(engine, run, s3, rid, "재계산")
    _answer(engine, run, "Review_Revision", {"재검토결과버전": "RES-S3-v2", "재검토": "검토 완료"})
    _revise(engine, run, s3, rid, "재상신")
    company.set_close_fault(rid, "posting_handoff_fail", 1)
    _decide(engine, run, s3, rid)
    assert _answer(engine, run, "Retry_Handoff", {"인계재시도": "인계 재시도"}, LEAD) is State.DONE
    versions = every_version(company, rid, 3)
    assert len(versions) > 20
    assert check(3, KINDS, versions, "s3/sc03") == []


def test_base_demo_end_matches_the_site_example(procs, company, opened) -> None:
    """사이트 시험의 예시(`docs/records/s3/sc03/examples/base-end.json`) = 기본 시연 끝."""
    from records_contract import example

    _, _, s3 = procs
    engine, run = _run(s3, opened)
    assert _decide(engine, run, s3, opened) is State.DONE
    assert example(company, opened, 3, "s3/sc03") == []


def test_follower_opens_scene3_on_command_and_rewinds(monkeypatch, company, tmp_path) -> None:
    """
    사이트의 「장면 열기」(시나리오 3 장면 3) — 장면 2 상신이 있으면 연다(없으면 거절 사유). 「장면
    3부터 다시」는 장면 3 문서만, 「장면 2부터 다시」는 장면 2·3 문서를 거둔다.
    """
    from app.follower import Follower

    monkeypatch.delenv("NOWVIEW_TEST_INPUTS", raising=False)
    backend = build_sqlite_backend(str(tmp_path / "engine.sqlite"))
    p1 = S3Sc01Process(build_sc01_store(backend, "s3sc01"), company=company)
    p2 = S3Sc02Process(build_sc01_store(backend, "s3sc02"), company=company, sc01=p1)
    p3 = S3Sc03Process(build_sc01_store(backend, "s3sc03"), company=company, sc01=p1, sc02=p2)
    rid = f"demo-{uuid.uuid4().hex[:8]}"
    company._call("POST", "/worlds", {"world_id": rid, "origin": "site", "scenario_id": "s3"})
    f = Follower(company, {}, s3=p1, s3_scenes={2: p2, 3: p3})
    f._follow(company.world(rid))
    seq = iter(range(1, 100))

    def command(scene: int, kind: str, body: dict | None = None) -> dict:
        return company._call(
            "POST",
            f"/worlds/{rid}/commands",
            {
                "scene": scene,
                "kind": kind,
                "actor": "u-acct-lead",
                "body": body or {},
                "ref": f"{rid}:{kind}{scene}:{next(seq)}",
            },
        )

    _scene1(p1, rid, "run")
    command(2, "open")
    f._follow(company.world(rid))
    early = command(3, "open")
    f._follow(company.world(rid))
    [got] = [c for c in company.commands(rid, None) if c["command_id"] == early["command_id"]]
    assert (got["state"], got["status"]) == ("REJECTED", 409) and p3.store.load(rid) is None
    # 장면 2를 상신까지(Center 없이 — 서버 실행기 흉내)
    p2.discard(rid)
    p2.create(rid, executor="studio")
    _base(p1, p2, rid)
    command(3, "open")
    f._follow(company.world(rid))
    doc = p3.get(rid)
    assert current(doc)["version"] == 1 and "Center 연동이 설정되지 않았다" in doc["bpm"]["problem"]
    command(3, "rewind", {"scene": 3})
    f._follow(company.world(rid))
    assert p3.store.load(rid) is None and p2.store.load(rid) is not None
    command(3, "open")
    f._follow(company.world(rid))
    command(2, "rewind", {"scene": 2})
    f._follow(company.world(rid))
    assert p3.store.load(rid) is None and p2.store.load(rid) is None


def test_dashboard_shows_scene3_metrics(procs, company, opened, tmp_path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.companies import Settings, build_router
    from app.config import ConfigStore

    s1, s2, s3 = procs
    rid = opened
    engine, run = _run(s3, rid)
    _decide(engine, run, s3, rid)
    world = {**company.world(rid), "origin": "site"}

    class _System:
        def worlds(self):
            return [world]

        def worker_log_entries(self, world_id: str):
            return [{"scene": 3, "operation": "hand_off_close_approval", "ok": True, "at": "x"}]

    settings = Settings(ConfigStore(build_sqlite_backend(str(tmp_path / "config.sqlite"))))
    app = FastAPI()
    app.include_router(
        build_router(settings, None, None, None, {"company1": _System()}, {31: s1, 32: s2, 33: s3})
    )
    body = TestClient(app).get("/companies/company1/dashboard").json()
    work = {w["scene"]: w for w in body["works"]}[33]
    assert (work["work"], work["state"]) == ("팀장 보고 및 승인", "done")
    assert [m["value"] for m in work["metrics"]] == [
        "2/2항목",
        "1건",
        "0/2항목",
        "0/2항목",
        "REP-S3-01 v1 · 승인 완료",
        "2/2경로",
    ]


def test_extension_definition_matches_the_bpmn_service_calls() -> None:
    """
    확장 `external`(0.15.1 이상)이 계약 검사를 통과하고, 그림의 서비스 호출 다섯이 정의의
    입력·출력과 맞는다. 결정·인계 재시도는 회계팀장, 보완 처리·재검토는 회계담당자이고 기록
    작업마다 오류 경계가 있다. 그림에는 모든 노드·흐름의 좌표(DI)가 있다 — 없으면 Studio의 자동
    배치가 깨진다.
    """
    import re

    from chaeksas.contracts import extension as ext
    from chaeksas.contracts._semver import satisfies
    from chaeksas.contracts.bpmn_ext import read_process

    from app.s3.sc03.process import OPERATIONS, PROCESS_PATH

    raw = (
        Path(__file__).resolve().parents[2] / "chaeksas" / "external.extension.json"
    ).read_bytes()
    manifest = ext.ExtensionManifest.model_validate(json.loads(raw))
    assert ext.validate(manifest, from_center=True) == []
    assert satisfies(manifest.version, ">=0.15.1,<1")
    operations = {o["name"]: o for o in json.loads(raw)["service"]["adapter"]["operations"]}
    process = read_process(PROCESS_PATH.read_bytes())
    used = []
    for node in process.of_kind("serviceTask"):
        call = node.prop("serviceCall")
        op = operations[call.operation]
        assert set(op["input_schema"]["required"]) <= set(call.input), node.id
        assert set(call.input) <= set(op["input_schema"]["properties"]), node.id
        assert set(call.output.values()) <= set(op["output_schema"]["properties"]), node.id
        used.append(call.operation)
    assert sorted(set(used)) == sorted(OPERATIONS)
    owners = {n.id: n.prop("approval").assignees for n in process.of_kind("userTask")}
    assert owners == {
        "Approve_Report": [LEAD],
        "Retry_Handoff": [LEAD],
        "Revise_Report": [OWNER],
        "Review_Revision": [OWNER],
    }
    bounded = {n.attached_to for n in process.of_kind("boundaryEvent")}
    assert bounded == {"Record_Decision", "Record_Revision", "Record_Revision_Review"}
    text = PROCESS_PATH.read_text()
    ids = set(re.findall(r'<bpmn:\w+ id="([^"]+)"', text)) - {"company1.s3.sc03", "Err_record"}
    shapes = set(re.findall(r'<bpmndi:BPMN(?:Shape|Edge) id="[^"]+" bpmnElement="([^"]+)"', text))
    assert ids == shapes
