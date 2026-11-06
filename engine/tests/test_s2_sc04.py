"""
시나리오 2 장면 4 — 실행 결과 확인과 관리기준 개선(`app/s2/sc04/`, `docs/s2/sc04.md`).

* 통합가상데이터 v0.4의 **파생 칸**(SC04실적의 여유·결과, SC04초기선별 전부, SC04회신재현의
  마감여유·도착 후보·처리 경로·채택 ETA·여유·비용 전망·회피액, SC04기준적용, SC04요약)을 규칙 계산과
  실행 결과로 다시 내서 대조한다 — 숫자를 시험에 옮겨 적지 않는다.
* 구현명세 §4 인수시험 01~09와 SC04기준적용의 표본(1·1·7).
* 진짜 BPM 엔진이 그림(`processes/s2-sc04.bpmn`)을 돌고 서비스 태스크는 C15 일꾼의 수행기를 지난다
  (Studio 흉내). 회사 시스템은 기간계 쌍둥이(`tests/company_twin/`)의 실행 증빙이다 — 증빙은 시연이
  보낸 세계 시각에 들어오고, 기다리는 실행은 메시지 「실행증빙」으로 깨운다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import openpyxl
import pytest
from chaeksas.core.engine import Engine, RunEnv, State, new_run_id
from chaeksas.core.run_log import RunLog
from conftest import C15Calls
from test_s2_sc01 import _scenario
from test_s2_sc02 import _base as _sc02_base
from test_s2_sc03 import _base as _sc03_base

from app import company as company_mod
from app.platform import catalog
from app.s2.sc01.process import S2Sc01Process
from app.s2.sc02.process import S2Sc02Process
from app.s2.sc03.process import S2Sc03Process
from app.s2.sc04 import calc
from app.s2.sc04 import process as sc04
from app.s2.sc04.process import S2Sc04Process
from app.s2.sc04.records import records_of
from app.sc01.center import CenterConfig, CenterError
from app.sc01.domain import DomainError, parse_at
from app.sc01.store import build_sc01_store
from app.store import build_sqlite_backend

SEED = Path(__file__).resolve().parents[1] / "seed" / "SYN-S2-SC04-v0.4.xlsx"
KST = calc.at("2026-11-05T00:00:00+09:00").tzinfo
#: 장면 4 각본 시각(구현용 보완 — 자료는 「11/5 납품 이후」만 말한다, `docs/s2/sc04.md` 「시각」)
OPEN_AT = "2026-11-06T09:00:00+09:00"
EVIDENCE_AT = {
    "BOOK-R": "2026-11-06T09:01:00+09:00",
    "POD-S": "2026-11-06T09:02:00+09:00",
    "POD-R": "2026-11-06T09:03:00+09:00",
    "SET-S": "2026-11-06T09:04:00+09:00",
    "SET-R": "2026-11-06T09:05:00+09:00",
}
START_AT = "2026-11-06T09:20:00+09:00"
REQUEST_AT = "2026-11-06T09:30:00+09:00"
IMPACT_AT = "2026-11-06T09:40:00+09:00"
TEST_AT = "2026-11-06T10:00:00+09:00"
APPLY_AT = "2026-11-06T10:30:00+09:00"
CONFIG_AT = "2026-11-06T11:00:00+09:00"
EFFECTIVE = "2026-11-09T00:00:00+09:00"


def _sheet(name: str) -> list[dict]:
    ws = openpyxl.load_workbook(SEED, data_only=True)[name]
    header = [c.value for c in ws[4]]
    rows = []
    for row in ws.iter_rows(min_row=5, values_only=True):
        if row[0] is None:
            break
        rows.append(dict(zip(header, row, strict=False)))
    return rows


def _kst(value: datetime | None) -> datetime | None:
    return None if value is None else value.replace(tzinfo=KST)


def _by(rows: list[dict], key: str) -> dict:
    return {r[key]: r for r in rows}


def _same_at(ours: str | None, sheet: datetime | None) -> bool:
    if sheet is None or sheet == "":
        return ours is None
    return ours is not None and parse_at(ours) == _kst(sheet)


# ─────────────────────────── 고정물 ───────────────────────────


@pytest.fixture()
def company():
    return company_mod.default_client()


@pytest.fixture()
def master(company) -> dict:
    return company.s2_master()


@pytest.fixture()
def backend(tmp_path):
    return build_sqlite_backend(str(tmp_path / "engine.sqlite"))


@pytest.fixture()
def sc01(backend, company) -> S2Sc01Process:
    return S2Sc01Process(build_sc01_store(backend, "s2sc01"), company=company)


@pytest.fixture()
def sc02(backend, company, sc01) -> S2Sc02Process:
    return S2Sc02Process(build_sc01_store(backend, "s2sc02"), company=company, sc01=sc01)


@pytest.fixture()
def sc03(backend, company, sc02) -> S2Sc03Process:
    return S2Sc03Process(build_sc01_store(backend, "s2sc03"), company=company, sc02=sc02)


@pytest.fixture()
def proc(backend, company, sc03) -> S2Sc04Process:
    return S2Sc04Process(build_sc01_store(backend, "s2sc04"), company=company, sc03=sc03)


@pytest.fixture()
def handed(sc01, sc02, sc03, company) -> str:
    """장면 1~3을 Studio 흉내로 HAND-03까지 — 장면 4의 출발점."""
    rid = f"s2-{uuid.uuid4().hex[:8]}"
    sc01.create(rid, executor="studio")
    _scenario(sc01, company, rid)
    assert _sc02_base(sc02, company, rid) is State.DONE
    assert _sc03_base(sc03, company, rid) is State.DONE
    assert sc03.get(rid)["handoff"]["handoff_id"] == "HAND-03"
    return rid


def _clock(company, proc: S2Sc04Process, rid: str, at: str) -> None:
    company._call("POST", f"/worlds/{rid}/clock", {"at": at})
    if proc.store.load(rid) is not None:
        proc.follow_clock(rid, at)


def _open(proc: S2Sc04Process, company, rid: str) -> dict:
    _clock(company, proc, rid, OPEN_AT)
    return proc.create(rid, executor="studio")


def _start(proc: S2Sc04Process, rid: str, calls: C15Calls | None = None) -> tuple[Engine, object]:
    run_id = new_run_id(test=True)
    engine = Engine()
    run = engine.start(
        proc.process,
        run_id=run_id,
        log=RunLog(run_id=run_id),
        env=RunEnv(services=calls or C15Calls(proc, origin="test"), processes=proc.processes),
        executor="studio",
        bpm_process_id="company1.s2.sc04",
        inputs={"데모실행ID": rid, "사건ID": "CASE-S2-01"},
        now=parse_at(proc.get(rid)["clock"]),
    )
    engine.run_until_blocked(run)
    return engine, run


def _send(company, proc, rid, fixture: str, at: str | None = None, **body) -> str:
    """실행 증빙 하나를 그 시각에 보낸다 — 세계 따라가기처럼 장면 4에 넘긴다."""
    _clock(company, proc, rid, at or EVIDENCE_AT[fixture])
    got = company._call(
        "POST", f"/worlds/{rid}/sim/execution-evidence", {"fixture_id": fixture, **body}
    )
    proc.receive_evidence(rid, got["doc_id"])
    return got["source_id"]


def _deliver(engine: Engine, run, source_id: str) -> State:
    engine.deliver(run, "실행증빙", payload={"증빙ID": source_id})
    return engine.run_until_blocked(run)


def _pending(run) -> list[str]:
    return [p.node_id for p in run.pendings.values()]


def _answer(engine: Engine, run, node: str, answer: dict, by: str) -> State:
    [pending] = [p for p in run.pendings.values() if p.node_id == node]
    engine.answer(run, pending.request_id, answer, answered_by=by)
    return engine.run_until_blocked(run)


def _to_start(proc, company, rid) -> tuple[Engine, object]:
    """D09 — 열고(증빙 대기), 증빙 다섯이 와서 결과 대조가 끝날 때까지."""
    _open(proc, company, rid)
    engine, run = _start(proc, rid)
    assert run.state is State.WAITING and _pending(run) == []
    for fixture in EVIDENCE_AT:
        _deliver(engine, run, _send(company, proc, rid, fixture))
    assert _pending(run) == ["Approve_Start"]
    return engine, run


def _to_test(proc, company, rid, impact: str = "차질 없음") -> tuple[Engine, object]:
    engine, run = _to_start(proc, company, rid)
    _clock(company, proc, rid, START_AT)
    start = {"개선착수": "착수", "착수사유": "정시였지만 R에 긴급차 120만원 — 조정 요청 시점 검토"}
    assert _answer(engine, run, "Approve_Start", start, "오세린") is State.WAITING
    _clock(company, proc, rid, REQUEST_AT)
    request = {"요청확인": "송신", "요청의견": "전량 적재·울산 경유 확인"}
    assert _answer(engine, run, "Approve_Request", request, "출하담당") is State.WAITING
    _clock(company, proc, rid, IMPACT_AT)
    answer = {"타고객영향": impact, "영향근거": "조정 노선 경유 고객의 11/5 약정 수량·시각 대조"}
    assert _answer(engine, run, "Approve_Impact", answer, "출하담당") is State.WAITING
    assert _pending(run) == ["Approve_Test"]
    return engine, run


def _base(proc, company, rid) -> State:
    """D09 → D11 — 기본 시연(구현용 각본 시각에 사람 여섯이 답한다)."""
    engine, run = _to_test(proc, company, rid)
    _clock(company, proc, rid, TEST_AT)
    verdict = {"시험판정": "통과", "검증의견": "표본 1·1·7 일치, 시험 01~09 통과"}
    assert _answer(engine, run, "Approve_Test", verdict, "운영담당") is State.WAITING
    _clock(company, proc, rid, APPLY_AT)
    apply = {
        "적용확인": "확인",
        "적용범위": "신규 사건 — 울산 A제품 주문별 운송납기 여유·조정 요청",
        "효력시점": EFFECTIVE,
        "확인의견": "기존 사건은 당시 버전 유지",
    }
    assert _answer(engine, run, "Approve_Apply", apply, "오세린") is State.WAITING
    _clock(company, proc, rid, CONFIG_AT)
    config = {"설정반영": "반영", "설정버전": "KRI-CTL-v2", "설정의견": "위임 범위 안"}
    return _answer(engine, run, "Approve_Config", config, "운영담당")


# ─────────────────────────── 통합가상데이터 대조 ───────────────────────────


def test_v04_keeps_scenes_1_to_3_and_adds_scene_4(master: dict) -> None:
    """v0.4의 앞 22개 시트는 v0.3과 셀 단위로 같다(`docs/s2/sc04.md`) — 장면 1~4가 같은 파일."""
    wb = openpyxl.load_workbook(SEED, data_only=True)
    assert wb.sheetnames[21] == "SC03인계" and wb.sheetnames[22] == "SC04요약"
    assert master["dataset_version"] == "SYN-S2-SC04-v0.4"
    assert [e["fixture_id"] for e in master["execution_evidence"]] == [
        "POD-S",
        "SET-S",
        "BOOK-R",
        "POD-R",
        "SET-R",
    ]
    assert master["route_contract"]["route_id"] == "RUN-REG"
    assert len(master["replay_branches"]) == 8


def test_outcome_matches_the_results_sheet(master: dict, proc, company, handed) -> None:
    """D09 · SC04실적 — 약정별 결정·운송·예약·수량·시각·여유·결과·정산·증빙. 판정 식을 다시 낸다."""
    engine, run = _to_start(proc, company, handed)
    o = proc.get(handed)["outcome"]
    rows = _by(o["rows"], "commitment_id")
    for row in _sheet("SC04실적"):
        r = rows[row["약정"]]
        assert r["decision"] == row["결정·과제"]
        assert r["transport"] == row["운송"]
        assert _same_at(r["reserved_at"], row["예약 확정"])
        assert (r["qty"], r["accepted_qty"]) == (row["약정수량"], row["인수수량"])
        assert _same_at(r["promised_at"], row["약정시각"])
        assert _same_at(r["accepted_at"], row["인수시각"])
        assert r["margin_min"] == row["여유(분)"]
        assert r["result"] == row["결과"]
        assert r["extra_cost"] == row["정산 추가비(원)"]
        assert " / ".join(r["evidence_ids"]) == row["증빙 ID"]
    assert o["on_time_full"] == 2 and o["duplicates"] == 0
    r = rows["COM-R"]
    assert {c["check"]: c["ok"] for c in r["checks"]} == {
        "reservation": True,
        "cost": True,
        "arrival": True,
    }


def test_screening_matches_the_initial_selection_sheet(master, proc, company, handed) -> None:
    """D10 · SC04초기선별 — 09:00 자료로 8건, S +60분·R −30분, R만 조정 후보, 배경 6건은 범위 밖."""
    doc = _open(proc, company, handed)
    found = calc.screen(master, doc["source"]["analysis"]["rows"], "2026-11-04T09:00:00+09:00")
    assert found["revision_id"] == "P-v2" and found["production_plan_version"] == "PROD-V1"
    rows = _by(found["rows"], "commitment_id")
    sheet = _sheet("SC04초기선별")
    assert [r["commitment_id"] for r in found["rows"]] == [r["약정"] for r in sheet]
    for row in sheet:
        r = rows[row["약정"]]
        assert _same_at(r["promised_at"], row["약정시각"])
        assert _same_at(r["available_at"], row["자재 가용"])
        assert _same_at(r["line_start"], row["라인 시작"])
        assert (r["assembly_min"], r["prep_min"]) == (row["조립(분)"], row["준비(분)"])
        assert _same_at(r["ready_at"], row["출하준비 전망"])
        assert _same_at(r["arrival"], row["미조정 도착"])
        assert r["margin_min"] == row["여유(분)"]
        assert r["verdict"] == row["조정 후보"]
    assert found["candidates"] == ["COM-R"]


def test_reply_branches_match_the_replay_sheet(master, proc, company, handed) -> None:
    """D10 · SC04회신재현 — 8개 분기의 마감여유·도착 후보·처리 경로·채택 ETA·여유·비용·회피액."""
    _to_test(proc, company, handed)
    doc = proc.get(handed)
    found = {b["branch"]: sc04._evaluate(doc, master, b) for b in master["replay_branches"]}
    for row in _sheet("SC04회신재현"):
        b = found[row["분기"]]
        assert b["deadline_margin_min"] == (
            row["마감여유(분)"] if row["마감여유(분)"] != "" else None
        )
        assert _same_at(b["arrival_candidate"], row["도착 후보"] or None)
        assert b["path"] == row["처리 경로"]
        assert _same_at(b["eta"], row["채택 ETA"] or None)
        assert b["margin_min"] == (row["여유(분)"] if row["여유(분)"] != "" else None)
        assert b["cost_forecast"] == (row["비용 전망(원)"] if row["비용 전망(원)"] != "" else None)
        cell = row["조건부 회피(원)"]
        assert b["conditional_avoidance"] == (cell if cell != "" else None)


# ─────────────────────────── 기본 시연 (진짜 엔진) ───────────────────────────


def test_base_flow_reconciles_replays_verifies_and_applies(
    proc, company, sc02, sc03, handed
) -> None:
    """
    기본 시연 — 증빙 대기 → 대조(정시 2·R 120만원) → H06 착수 → 재현(R만 후보, 마감 10분 전) → H04
    송신(09:03) → 모의 접수증(09:05, 5분)·수락 회신(09:08 — 생산 반영 확인 대기) → H04 차질 없음 →
    채택(18:15·+15분·0원·조건부 120만원) → 시험(1·1·7 표본 일치) → H07 통과 → H06 APP-04 → H07
    CFG-04. 끝 = SC04요청이력·기준적용·요약.
    """
    assert _base(proc, company, handed) is State.DONE
    doc = proc.get(handed)
    assert doc["bpm"]["visited"] == [
        "Task_Results",
        "Wait_Evidence",
        "Approve_Start",
        "Record_Start",
        "Task_Replay",
        "Approve_Request",
        "Record_Request",
        "Task_Reply",
        "Approve_Impact",
        "Record_Impact",
        "Task_Verify",
        "Approve_Test",
        "Record_Test",
        "Approve_Apply",
        "Record_Apply",
        "Approve_Config",
        "Record_Config",
        "End",
    ]
    rp = doc["replay"]
    events = _by(_sheet("SC04요청이력"), "기록 ID")
    assert _same_at(rp["data_as_of"], events["SNAP-0900"]["일시"])
    assert _same_at(rp["request"]["sent_at"], events["REQ-R-04"]["일시"])
    assert _same_at(rp["receipt"]["received_at"], events["ACK-R-04"]["일시"])
    assert _same_at(rp["reply"]["replied_at"], events["REP-R-04"]["일시"])
    assert _same_at(rp["cutoff"]["cutoff_at"], events["CUT-REG"]["일시"])
    assert _same_at(rp["existing"]["inquiry_started_at"], events["W-TRAN-R"]["일시"])
    assert rp["cutoff"]["minutes_left"] == 10 and rp["existing"]["past_cutoff"] is True
    # 09:00에는 W-TRAN-R(09:10 시작)이 없었다 — 재현 업무 한 건이 원업무 계보에 잇는다
    assert rp["request"]["work_mode"] == "replay_work" and rp["request"]["lineage"] == "W-TRAN-R"
    assert rp["external_sends"] == 0 and rp["request"]["mode"] == "mock"
    assert rp["adoption_at_reply"]["state"] == calc.AWAITING_PRODUCTION
    a = rp["adoption"]
    assert (a["state"], a["path"], a["margin_min"], a["cost_forecast"]) == (
        calc.ADOPTED,
        calc.ADOPT,
        15,
        0,
    )
    assert a["conditional_avoidance"] == 1_200_000
    v = doc["verification"]
    assert v["passed"] is True and [r["verdict"] for r in v["rows"]] == ["PASS"] * 9
    sheet = {r["시험·설정 ID"]: r for r in _sheet("SC04기준적용")}
    for key in ("T-04-01", "T-04-02", "T-04-03"):
        assert v["sample"][key] == sheet[key]["예시 결과"]
    assert v["sample_verdict"] == sheet["TEST-04"]["예시 결과"]
    assert v["state"] == "PASSED" and v["verdict_by"] == "운영담당"
    ap = doc["approval"]
    assert (ap["state"], ap["actor"], ap["version"]) == ("CONFIRMED", "오세린", "KRI-CTL-v2")
    assert sheet["APP-04"]["예시 결과"] == "확인" and ap["decision"] == "확인"
    cfg = doc["config"]
    assert cfg["state"] == sheet["CFG-04"]["예시 결과"] == sheet["CASE-NEXT-01"]["예시 결과"]
    cases = _by(cfg["cases"], "case_id")
    assert cases["CASE-NEXT-01"]["version"] == sheet["CASE-NEXT-01"]["검증본"]
    assert cases["CASE-S2-01"]["version"] == "기존 버전"
    assert sheet["CASE-S2-01"]["예시 결과"] == "기존 버전 유지"
    assert parse_at(cfg["effective_at"]) == parse_at(EFFECTIVE)
    # 장면 3의 결정 당시 공란은 소급 입력하지 않는다
    d3 = sc03.get(handed)["decisions"][-1]
    assert d3["actual"] == {"reserved_at": None, "accepted_at": None, "actual_cost": None}
    assert company.production_plan(handed)["version"] == "PROD-V2"
    board = next(r for r in records_of(doc, proc.master()) if r["kind"] == "dashboard")["body"]
    summary = {r["지표"]: r["값"] for r in _sheet("SC04요약")}
    s = board["summary"]
    assert s["on_time_full"] == summary["정시 전량 인수"]
    assert s["r_actual_extra_cost"] == summary["R 실제 추가 운송비"]
    assert s["r_unadjusted_margin_min"] == summary["R 미조정 납기 여유"]
    assert s["receipt_margin_min"] == summary["접수 시점 마감 여유"]
    assert s["adjusted_margin_min"] == summary["조정 후 납기 여유"]
    assert s["fare_forecast"] == summary["추가 운임 전망"]
    assert s["conditional_avoidance"] == summary["조건부 비용 회피 가능액"]
    assert float(s["october_otd"]) == summary["10월 OTD"]
    assert s["application"] == summary["적용 상태"]
    # 위험 식별 앞당김 — 기존 판정은 이 실행의 HAND-02 시각이다(장면 2가 반영·재평가를 확인 시각에
    # 적는다). 자료(09:15 − 09:00 = 15분)와 다르다 — `docs/s2/sc04.md` 「시각」
    judged = parse_at(sc02.get(handed)["handoff"]["handed_at"])
    assert s["detection_earlier_min"] == round(
        (judged - parse_at("2026-11-04T09:00:00+09:00")).total_seconds() / 60
    )


def test_01_resent_evidence_is_counted_once_and_missing_stays_unconfirmed(
    proc, company, handed
) -> None:
    """
    시험 01 — 같은 증빙을 다시 보내도 한 번, 정산이 없으면 비용 미확인(인수는 정시), 정정은 새 판.
    """
    _open(proc, company, handed)
    engine, run = _start(proc, handed)
    for fixture in ("BOOK-R", "POD-S", "POD-R", "SET-S"):
        _deliver(engine, run, _send(company, proc, handed, fixture))
    again = company._call(
        "POST", f"/worlds/{handed}/sim/execution-evidence", {"fixture_id": "POD-R"}
    )
    assert again["created"] is False
    o = proc.get(handed)["outcome"]
    r = _by(o["rows"], "commitment_id")["COM-R"]
    assert (r["result"], r["extra_cost"], r["cost_state"]) == ("정시 전량", None, "미확인")
    assert r["missing"] == ["settlement"] and o["ready"] is False and o["duplicates"] == 0
    assert _pending(run) == []  # 정산이 오기 전에는 개선 착수로 가지 않는다
    _deliver(engine, run, _send(company, proc, handed, "SET-R"))
    assert _pending(run) == ["Approve_Start"]
    before = proc.get(handed)["outcome"]["version"]
    _send(
        company,
        proc,
        handed,
        "POD-R",
        at="2026-11-06T09:10:00+09:00",
        source_id="POD-R-v2",
        overrides={"accepted_qty": 230},
    )
    o = proc.get(handed)["outcome"]
    r = _by(o["rows"], "commitment_id")["COM-R"]
    assert (
        o["version"] == before + 1 and r["result"] == "미준수" and "POD-R-v2" in r["evidence_ids"]
    )
    assert proc.get(handed)["outcome_history"][-1]["version"] == before


def test_h06_may_decide_no_improvement(proc, company, handed) -> None:
    """N12 — 모든 사건을 개선으로 잇지 않는다. 「개선 불필요」면 결과 기록만 남고 끝난다."""
    engine, run = _to_start(proc, company, handed)
    answer = {"개선착수": "개선 불필요", "착수사유": "단발 사례 — 유사 이력 확인 뒤 다시 본다"}
    assert _answer(engine, run, "Approve_Start", answer, "오세린") is State.DONE
    doc = proc.get(handed)
    assert doc["improvement"]["state"] == "NOT_NEEDED" and doc["replay"] is None
    assert doc["bpm"]["visited"][-1] == "End_NoImprovement"


def test_only_the_holder_answers_and_a_refusal_returns_to_the_same_approval(
    proc, company, handed
) -> None:
    """
    권한 — H06 결재에 다른 사람이 답하면 기록이 거절돼 같은 결재로 돌아간다(403, 남는 것 없음).
    """
    engine, run = _to_start(proc, company, handed)
    answer = {"개선착수": "착수", "착수사유": "검토"}
    assert _answer(engine, run, "Approve_Start", answer, "운영담당") is State.WAITING
    assert _pending(run) == ["Approve_Start"] and proc.get(handed)["improvement"] is None
    with pytest.raises(DomainError) as refused:
        sc04.start_improvement(proc.get(handed), {"answered_by": "권태윤", **answer})
    assert refused.value.status == 403


def test_06_other_customer_impact_keeps_the_reply_but_does_not_adopt(proc, company, handed) -> None:
    """시험 06 — 수락 회신은 그대로, 회사 채택은 보류: R 도착 후보만, ETA·비용·회피액은 공란."""
    _to_test(proc, company, handed, impact="차질 예상")
    a = proc.get(handed)["replay"]["adoption"]
    assert (a["reply"], a["path"], a["eta"], a["cost_forecast"]) == (
        "수락",
        calc.EXISTING,
        None,
        None,
    )
    assert a["arrival_candidate"] is not None and a["conditional_avoidance"] is None
    impact = proc.get(handed)["replay"]["impact"]
    assert (impact["value"], impact["confirmed_by"]) == (1, "출하담당")


def test_unknown_impact_holds_adoption(proc, company, handed) -> None:
    """구현명세 §3 — 공란(미확인)이면 근거 보완, 채택과 회피 가능액 산출을 보류한다."""
    _to_test(proc, company, handed, impact="미확인")
    a = proc.get(handed)["replay"]["adoption"]
    assert (a["state"], a["path"], a["conditional_avoidance"]) == (
        calc.ON_HOLD,
        calc.EXISTING,
        None,
    )


def test_04_05_07_branch_reasons_and_boundaries(master, proc, company, handed) -> None:
    """
    시험 04·05·07 — 실패 사유와 마감·생산 경계(09:10 기한 내, 09:11 경과, 반영 불일치, 준비 지연).
    """
    _to_test(proc, company, handed)
    doc = proc.get(handed)
    base = next(b for b in master["replay_branches"] if b["branch"] == "기본 수락")

    def ev(change: dict, reflect: object = "source") -> dict:
        return sc04._evaluate(doc, master, {**base, **change}, reflect=reflect)

    assert ev({"received_at": "2026-11-04T09:10:00+09:00"})["path"] == calc.ADOPT
    late = ev({"received_at": "2026-11-04T09:11:00+09:00"})
    assert late["path"] == calc.EXISTING and late["deadline_margin_min"] == -1
    assert any("기한 경과" in r for r in late["reasons"])
    mismatch = ev({}, reflect={"match": "MISMATCH", "ready_at": None})
    assert any("불일치" in r for r in mismatch["reasons"])
    assert ev({"departure": "2026-11-05T15:55:00+09:00"})["path"] == calc.EXISTING
    assert ev({}, reflect=None)["state"] == calc.AWAITING_PRODUCTION
    v = doc["verification"]
    assert {r["test_id"]: r["verdict"] for r in v["rows"]} == {
        f"{n:02d}": "PASS" for n in range(1, 10)
    }


def test_failing_tests_cannot_be_recorded_as_passed(proc, company, handed) -> None:
    """
    N14 — 미통과 시험이 있으면 「통과」 기록은 거절(422), 「보완·재시험」이면 적용 차단으로 끝.
    """
    engine, run = _to_test(proc, company, handed)
    doc = proc.get(handed)
    doc["verification"]["passed"] = False
    doc["verification"]["rows"][2]["verdict"] = "FAIL"
    with pytest.raises(DomainError) as refused:
        sc04.record_verdict(doc, {"answered_by": "운영담당", "verdict": "통과"})
    assert refused.value.status == 422 and "03" in str(refused.value)
    verdict = {"시험판정": "보완·재시험", "검증의견": "재시험"}
    assert _answer(engine, run, "Approve_Test", verdict, "운영담당") is State.DONE
    doc = proc.get(handed)
    assert doc["verification"]["state"] == "REWORK" and doc["approval"] is None
    assert doc["bpm"]["visited"][-1] == "End_TestFailed"


def test_09_application_needs_a_future_effective_time_and_the_confirmed_version(
    proc, company, handed
) -> None:
    """시험 09 — 효력시점이 지금보다 앞이면 거절(소급 금지), 다른 버전 설정은 거절, 보류면 끝."""
    engine, run = _to_test(proc, company, handed)
    verdict = {"시험판정": "통과", "검증의견": "통과"}
    assert _answer(engine, run, "Approve_Test", verdict, "운영담당") is State.WAITING
    past = {"적용확인": "확인", "적용범위": "신규 사건", "효력시점": "2026-11-04T00:00:00+09:00"}
    assert _answer(engine, run, "Approve_Apply", past, "오세린") is State.WAITING
    assert _pending(run) == ["Approve_Apply"] and proc.get(handed)["approval"] is None
    good = {"적용확인": "확인", "적용범위": "신규 사건", "효력시점": EFFECTIVE}
    assert _answer(engine, run, "Approve_Apply", good, "오세린") is State.WAITING
    wrong = {"설정반영": "반영", "설정버전": "KRI-CTL-v3"}
    assert _answer(engine, run, "Approve_Config", wrong, "운영담당") is State.WAITING
    assert _pending(run) == ["Approve_Config"] and proc.get(handed)["config"] is None
    assert calc.application_state(calc.SAMPLE_MATCH, False) == calc.HELD
    assert calc.version_for("2026-11-08T23:59:00+09:00", EFFECTIVE) == "기존 버전"
    assert calc.version_for("2026-11-09T00:00:00+09:00", EFFECTIVE) == "KRI-CTL-v2"


def test_h06_hold_ends_with_the_old_standard(proc, company, handed) -> None:
    engine, run = _to_test(proc, company, handed)
    assert _answer(engine, run, "Approve_Test", {"시험판정": "통과"}, "운영담당") is State.WAITING
    hold = {"적용확인": "보류", "확인의견": "효력시점 협의 뒤"}
    assert _answer(engine, run, "Approve_Apply", hold, "오세린") is State.DONE
    doc = proc.get(handed)
    assert doc["approval"]["state"] == "HELD" and doc["config"] is None
    assert doc["bpm"]["visited"][-1] == "End_ApplyHeld"


def test_scene_4_needs_the_scene_3_handoff(proc, sc01, sc02, sc03, company) -> None:
    rid = f"s2-{uuid.uuid4().hex[:8]}"
    sc01.create(rid, executor="studio")
    _scenario(sc01, company, rid)
    assert _sc02_base(sc02, company, rid) is State.DONE
    with pytest.raises(DomainError):
        proc.create(rid, executor="studio")


def test_other_run_and_other_place_are_refused(proc, company, handed) -> None:
    _to_start(proc, company, handed)
    args = {"demo_run_id": handed, "case_id": "CASE-S2-01"}
    with pytest.raises(DomainError) as other:
        proc.operate(handed, "link_execution_results", args, external_run_id="run_x")
    assert other.value.status == 409
    run_id = proc.get(handed)["bpm"]["external_run_id"]
    with pytest.raises(DomainError) as place:
        proc.operate(handed, "link_execution_results", args, external_run_id=run_id, via="center")
    assert place.value.status == 409


def test_extension_definition_matches_the_bpmn_service_calls() -> None:
    """
    확장 `external` 0.12.1 — 그림의 서비스 호출이 정의의 입력·출력과 맞고, 결재 담당자가 역할
    배정(H06·H04·H07)과 같고, 기록 작업마다 오류 경계가 있다. 호출 활동(공통 BPM)은 없다.
    """
    import json

    from chaeksas.contracts import extension as ext
    from chaeksas.contracts.bpmn_ext import read_process

    from app.s2.sc04.process import OPERATIONS, PROCESS_PATH

    raw = (
        Path(__file__).resolve().parents[2] / "chaeksas" / "external.extension.json"
    ).read_bytes()
    manifest = ext.ExtensionManifest.model_validate(json.loads(raw))
    assert ext.validate(manifest, from_center=True) == []
    assert manifest.version == "0.12.1"
    operations = {o["name"]: o for o in json.loads(raw)["service"]["adapter"]["operations"]}
    process = read_process(PROCESS_PATH.read_bytes())
    used = []
    for node in process.of_kind("serviceTask"):
        call = node.prop("serviceCall")
        op = operations[call.operation]
        assert set(op["input_schema"]["required"]) <= set(call.input), node.id
        assert set(call.output.values()) <= set(op["output_schema"]["properties"]), node.id
        used.append(call.operation)
    [need] = [n for n in process.info.extensions if n.id == manifest.id]
    assert need.version.startswith(">=0.12.0")
    assert used == list(OPERATIONS)
    holders = {
        "Approve_Start": catalog.HOLDERS["H06"],
        "Approve_Request": catalog.HOLDERS["H04"],
        "Approve_Impact": catalog.HOLDERS["H04"],
        "Approve_Test": catalog.HOLDERS["H07"],
        "Approve_Apply": catalog.HOLDERS["H06"],
        "Approve_Config": catalog.HOLDERS["H07"],
    }
    assert {n.id: n.prop("approval").assignees for n in process.of_kind("userTask")} == holders
    boundaries = [n.attached_to for n in process.all_nodes() if n.kind == "boundaryEvent"]
    assert boundaries == [
        f"Record_{x}" for x in ("Start", "Request", "Impact", "Test", "Apply", "Config")
    ]
    assert process.of_kind("callActivity") == []


def test_every_written_version_matches_the_common_record_schemas(proc, company, handed) -> None:
    """
    공통 기록 종류(`docs/records/s2/sc04/`) — 기본 시연의 모든 판이 봉투·종류별 스키마를 통과하고,
    사이트 예시가 최신이다(다시 뽑기 `NOWVIEW_WRITE_RECORD_SCHEMAS=1`·`…_EXAMPLES=1`).
    """
    from records_contract import check, every_version, example

    from app.s2.sc04.records import KINDS

    assert _base(proc, company, handed) is State.DONE
    versions = every_version(company, handed, 4)
    assert len(versions) > 10
    assert check(4, KINDS, versions, "s2/sc04") == []
    assert example(company, handed, 4, "s2/sc04") == []
    kinds = {r["kind"] for r in company.records(handed, scene=4)}
    assert kinds == set(KINDS)


# ─────────────────────────── 세계 따라가기 · Center · 대시보드 ───────────────────────────


class _Center:
    """Center 흉내 — 작업은 받고, 메시지는 처음 한 번 `no_receiver`(실행이 아직 대기 전)."""

    def __init__(self) -> None:
        self.config = CenterConfig(url="http://center.test", integration_key="k")
        self.messages: list[dict] = []
        self.refuse = 1

    def start_job(self, inputs, **kw) -> dict:
        return {"job_id": "job_1"}

    def job(self, job_id: str) -> dict:
        return {"job_id": job_id, "state": "running", "run_status": "running"}

    def send_message(self, name, *, correlation, payload, idempotency_key, on_behalf) -> dict:
        if self.refuse:
            self.refuse -= 1
            raise CenterError(422, "no_receiver", "기다리는 실행이 없다")
        self.messages.append({"name": name, "correlation": correlation, "payload": payload})
        return {"message_id": "m1", "delivered_to": "run"}

    def cancel_job(self, job_id: str) -> dict:
        return {}


def test_center_message_wakes_the_wait_and_the_poller_retries(
    company, backend, sc03, handed
) -> None:
    """
    Center 실행 — 증빙이 오면 「실행증빙」 메시지로 깨운다. `no_receiver`면 폴러가 다시 보낸다.
    """
    center = _Center()
    proc = S2Sc04Process(
        build_sc01_store(backend, "s2sc04"), company=company, sc03=sc03, center=center
    )
    _clock(company, proc, handed, OPEN_AT)
    doc = proc.create(handed)
    assert doc["bpm"]["job_id"] == "job_1" and doc["bpm"]["state"] == "running"
    args = {"demo_run_id": handed, "case_id": "CASE-S2-01"}
    out = proc.operate(
        handed, "link_execution_results", args, external_run_id="run_c", via="center"
    )
    assert out["ready"] is False
    _send(company, proc, handed, "BOOK-R")
    assert center.messages == [] and proc.get(handed)["wait"]["message_pending"] is True
    assert proc.poll_center() == 1
    assert center.messages == [
        {"name": "실행증빙", "correlation": handed, "payload": {"증빙ID": "BOOK-R"}}
    ]
    assert proc.poll_center() == 0


def test_follower_opens_scene_4_and_passes_new_evidence(
    monkeypatch, company, backend, sc01, sc02, sc03
) -> None:
    """
    사이트가 시나리오 2 회차에 「장면 열기」(장면 4)를 남기면 장면 4 문서를 연다. 기간계에 새 증빙이
    들어오면 장면 4에 넘긴다. 「장면 4부터 다시」면 장면 4 문서를 거둔다(장면 3은 그대로).
    """
    from app.follower import Follower

    monkeypatch.delenv("NOWVIEW_TEST_INPUTS", raising=False)
    s4 = S2Sc04Process(build_sc01_store(backend, "s2sc04"), company=company, sc03=sc03)
    rid = f"demo-{uuid.uuid4().hex[:8]}"
    company._call("POST", "/worlds", {"world_id": rid, "origin": "site", "scenario_id": "s2"})
    f = Follower(company, {}, s2=sc01, s2_scenes={2: sc02, 3: sc03, 4: s4})
    f._follow(company.world(rid))
    with sc01._lock(rid):
        d, v = sc01._load(rid)
        d["executor"] = "studio"
        sc01.store.save(rid, d, v, "studio")
    _scenario(sc01, company, rid)
    assert _sc02_base(sc02, company, rid) is State.DONE
    assert _sc03_base(sc03, company, rid) is State.DONE
    company._call("POST", f"/worlds/{rid}/clock", {"at": OPEN_AT})
    company._call(
        "POST",
        f"/worlds/{rid}/commands",
        {"scene": 4, "kind": "open", "actor": "u-fin-lead", "body": {}, "ref": f"{rid}:open4"},
    )
    f._follow(company.world(rid))
    [cmd] = [c for c in company.commands(rid, None) if c["scene"] == 4]
    assert cmd["state"] == "DONE", cmd
    doc = s4.get(rid)
    assert doc["source"]["handoff"]["handoff_id"] == "HAND-03"
    assert "Center 연동이 설정되지 않았다" in doc["bpm"]["problem"]
    got = company._call("POST", f"/worlds/{rid}/sim/execution-evidence", {"fixture_id": "BOOK-R"})
    f._follow(company.world(rid))
    assert s4.get(rid)["evidence_seen"] == [got["doc_id"]]
    company._call(
        "POST",
        f"/worlds/{rid}/commands",
        {"scene": 4, "kind": "rewind", "actor": "u-demo", "body": {"scene": 4}, "ref": f"{rid}:rw"},
    )
    f._follow(company.world(rid))
    assert s4.store.load(rid) is None and sc03.store.load(rid) is not None
    # 기간계가 증빙을 비운다(Company1 `legacy/tests`) — 수신 번호를 처음부터 다시 센다
    assert f._seen[rid]["evidence"] == 0


def test_dashboard_shows_scene_4_metrics_for_a_scenario_2_world(
    proc, sc01, sc02, sc03, company, handed, tmp_path
) -> None:
    """회사 대시보드 — 시나리오 2 회차의 업무 24 카드에 SC04요약의 숫자와 결재 진행."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.companies import Settings, build_router
    from app.config import ConfigStore

    assert _base(proc, company, handed) is State.DONE
    world = {**company.world(handed), "origin": "site"}

    class _System:
        def worlds(self):
            return [world]

        def worker_log_entries(self, world_id: str):
            return []

    settings = Settings(ConfigStore(build_sqlite_backend(str(tmp_path / "config.sqlite"))))
    app = FastAPI()
    app.include_router(
        build_router(
            settings,
            None,
            None,
            None,
            {"company1": _System()},
            {21: sc01, 22: sc02, 23: sc03, 24: proc},
        )
    )
    body = TestClient(app).get("/companies/company1/dashboard").json()
    w = {x["scene"]: x for x in body["works"]}[24]
    assert (w["work"], w["state"]) == ("실행 결과 확인과 관리기준 개선", "done")
    assert w["progress"] == {"approvals": 6, "passed": 6}
    values = {m["label"]: m["value"] for m in w["metrics"]}
    assert values["정시 전량 인수"] == "2건"
    assert values["R 실제 추가 운송비"] == "1200000"
    assert values["R 미조정 납기 여유(재현)"] == "-30분"
    assert values["접수 시점 마감 여유"] == "5분"
    assert values["조정 후 납기 여유(전망)"] == "+15분"
    assert values["추가 운임 전망"] == "0"
    assert values["조건부 비용 회피 가능액"] == "1200000"
    assert values["10월 OTD"] == "99%"
    assert values["적용 상태"] == "신규 사건 적용"
