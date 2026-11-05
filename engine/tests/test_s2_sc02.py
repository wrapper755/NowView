"""
시나리오 2 장면 2 — 정형통제 실행과 주문별 분기(`app/s2/sc02/`, `docs/s2/sc02.md`).

* 통합가상데이터 v0.2의 **파생 칸**(SC02생산안의 제안 착수·종료, SC02반영본의 대조, SC02납기판정의
출하
  준비·이용 정기차·예상 도착·여유·후속 경로, SC02요약, SC02수행계획·SC02확인·SC02인계의 키)을 규칙
  계산과
  실행 결과로 다시 내서 대조한다 — 숫자를 시험에 옮겨 적지 않는다.
* 구현명세 §5 인수시험 T01~T09.
* 진짜 BPM 엔진이 그림(`processes/s2-sc02.bpmn` + 공통 BPM `case-plan.bpmn`)을 돌고 서비스 태스크는
C15
  일꾼의 수행기를 지난다(Studio 흉내). 회사 시스템은 기간계 쌍둥이(`tests/company_twin/`)의 생산계획
  저장소다 — 반영은 거기 적히고 대조는 거기서 다시 읽는다.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime
from pathlib import Path

import openpyxl
import pytest
from chaeksas.core.engine import Engine, RunEnv, State, new_run_id
from chaeksas.core.run_log import RunLog
from conftest import C15Calls
from test_s2_sc01 import _scenario

from app import company as company_mod
from app.platform import catalog
from app.s2.sc01.process import S2Sc01Process
from app.s2.sc02 import calc
from app.s2.sc02.process import S2Sc02Process
from app.s2.sc02.records import records_of
from app.sc01.domain import DomainError, parse_at
from app.sc01.store import build_sc01_store
from app.store import build_sqlite_backend

SEED = Path(__file__).resolve().parents[1] / "seed" / "SYN-S2-SC03-v0.3.xlsx"
KST = calc.at("2026-11-05T00:00:00+09:00").tzinfo
CONFIRM_AT = None  # SC02확인의 확인시각 — 시트에서 읽는다(`_sheet`)


def _sheet(name: str) -> list[dict]:
    ws = openpyxl.load_workbook(SEED, data_only=True)[name]
    header = [c.value for c in ws[4]]
    rows = []
    for row in ws.iter_rows(min_row=5, values_only=True):
        if row[0] is None:
            break
        rows.append(dict(zip(header, row, strict=False)))
    return rows


def _kst(value: datetime) -> datetime:
    return value.replace(tzinfo=KST)


def _by(rows: list[dict], key: str) -> dict:
    return {r[key]: r for r in rows}


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
def proc(backend, company, sc01) -> S2Sc02Process:
    return S2Sc02Process(build_sc01_store(backend, "s2sc02"), company=company, sc01=sc01)


@pytest.fixture()
def handed(sc01, company) -> str:
    """장면 1을 Studio 흉내로 인계(HAND-01)까지 — 장면 2의 출발점."""
    rid = f"s2-{uuid.uuid4().hex[:8]}"
    sc01.create(rid, executor="studio")
    _scenario(sc01, company, rid)
    assert sc01.get(rid)["handoff"]["next_node"] == "N03A"
    return rid


def _confirm_at() -> str:
    return _kst(_sheet("SC02확인")[0]["확인시각 KST"]).isoformat()


def _open(proc: S2Sc02Process, rid: str, case_id: str = "BASE") -> dict:
    return proc.create(rid, case_id=case_id, executor="studio")


def _start(proc: S2Sc02Process, rid: str, calls: C15Calls | None = None) -> tuple[Engine, object]:
    run_id = new_run_id(test=True)
    engine = Engine()
    run = engine.start(
        proc.process,
        run_id=run_id,
        log=RunLog(run_id=run_id),
        env=RunEnv(services=calls or C15Calls(proc, origin="test"), processes=proc.processes),
        executor="studio",
        bpm_process_id="company1.s2.sc02",
        inputs={"데모실행ID": rid, "사건ID": "CASE-S2-01"},
        now=parse_at(proc.get(rid)["clock"]),
    )
    engine.run_until_blocked(run)
    return engine, run


def _answer_values(proc: S2Sc02Process, rid: str, decision: str = "확정") -> dict:
    d = proc.get(rid)["drafts"][-1]
    return {"확인결정": decision, "확인버전": d["draft_id"], "확인의견": "생산 가능시간 확인"}


def _answer(engine: Engine, run, answer: dict, by: str = "배정훈") -> State:
    [pending] = [p for p in run.pendings.values() if p.node_id == "Approve_Change"]
    engine.answer(run, pending.request_id, answer, answered_by=by)
    return engine.run_until_blocked(run)


def _clock(company, proc: S2Sc02Process, rid: str, at: str) -> None:
    company._call("POST", f"/worlds/{rid}/clock", {"at": at})
    proc.follow_clock(rid, at)


def _base(proc, company, rid, case_id: str = "BASE") -> State:
    """D03 → D04 → D05 — 열고, H03이 확인시각(SC02확인)에 한 번 확정한다."""
    _open(proc, rid, case_id)
    engine, run = _start(proc, rid)
    assert [p.node_id for p in run.pendings.values()] == ["Approve_Change"]
    _clock(company, proc, rid, _confirm_at())
    return _answer(engine, run, _answer_values(proc, rid))


# ─────────────────────────── 통합가상데이터 대조 ───────────────────────────


def test_v02_keeps_the_scene_1_sheets_and_adds_scene_2(master: dict) -> None:
    """v0.3의 앞 7개 시트는 장면 1(v0.1)과 값이 같다 — 장면 1·2 시험이 같은 파일로 돈다."""
    wb = openpyxl.load_workbook(SEED, data_only=True)
    assert wb.sheetnames[:7] == [
        "상황판",
        "납기약정",
        "입고개정",
        "입고분",
        "주문영향",
        "모델별 집계",
        "사건근거",
    ]
    assert master["dataset_version"] == "SYN-S2-SC03-v0.3"
    assert [p["commitment_id"] for p in master["production"]] == ["COM-S", "COM-R"]


def test_draft_matches_the_production_proposal_sheet(proc, company, handed, master) -> None:
    """T02 · SC02생산안 — 착수 = max(자재 사용, 빈 시간 시작), 종료 = 착수 + 조립. 80·240세트."""
    _open(proc, handed)
    sheet = _by(_sheet("SC02생산안"), "약정")
    found = calc.draft(
        proc.get(handed)["source"]["analysis"]["rows"], master, company.production_plan(handed)
    )
    rows = _by(found["rows"], "commitment_id")
    for cid, row in sheet.items():
        r = rows[cid]
        assert (r["lot_id"], r["allocated_qty"]) == (row["입고분"], row["확보수량"])
        assert parse_at(r["original_start"]) == _kst(row["기존 착수"])
        assert parse_at(r["available_at"]) == _kst(row["자재 사용"])
        assert parse_at(r["start"]) == _kst(row["제안 착수"])
        assert parse_at(r["end"]) == _kst(row["제안 종료"])
        assert r["ok"] and r["conflicts"] == []
    assert found["confirmable"] and found["base_version"] == "PROD-V1"
    assert len(found["background"]) == 6 and all(b["kept"] for b in found["background"])


def test_reassessment_matches_the_delivery_judgment_sheet(master: dict) -> None:
    """SC02납기판정 — 준비 = 저장 종료 + 준비, 마감 ≥ 준비인 첫 차, 여유 = 약정 − 도착, 경로."""
    stored = _by(_sheet("SC02반영본"), "약정")
    plan = _by(_sheet("SC02생산안"), "약정")
    targets = [
        {"commitment_id": cid, "qty": stored[cid]["반영 수량"], "prep_min": plan[cid]["준비(분)"]}
        for cid in stored
    ]
    readback = {
        cid: {"match": calc.MATCHED, "stored": {"end": _kst(r["반영 종료"]).isoformat()}}
        for cid, r in stored.items()
    }
    found = _by(calc.reassess(targets, readback, master), "commitment_id")
    route = {"인수 관찰": calc.OBSERVE, "운송 확인": calc.TRANSPORT, "판정 보류": calc.HOLD}
    for row in _sheet("SC02납기판정"):
        r = found[row["약정"]]
        assert parse_at(r["ready_at"]) == _kst(row["출하 준비"])
        assert r["truck_id"] == row["이용 정기차"]
        assert parse_at(r["arrival"]) == _kst(row["예상 도착"])
        assert parse_at(r["promised_at"]) == _kst(row["고객 약정"])
        assert r["margin_min"] == row["여유(분)"]
        assert r["route"] == route[row["후속 경로"]]
    assert [m["truck_id"] for m in found["COM-R"]["missed"]] == ["R-1"]
    assert found["COM-R"]["missed"][0]["late_min"] == 150  # 첫 차 마감 초과 150분 ≠ 납기 부족 30분


def test_plan_items_match_the_execution_plan_sheet() -> None:
    """SC02수행계획 — U01 → U05, 선행 HAND-01 → 앞 항목, 담당 역할."""
    items = calc.propose({"handoff_id": "HAND-01"})
    sheet = _sheet("SC02수행계획")
    assert [i["unit"] for i in items] == [r["업무 단위"].split(" ")[0] for r in sheet]
    assert [i["predecessor"] for i in items] == [r["선행"] for r in sheet]
    for i, r in zip(items, sheet, strict=True):
        assert set(i["owner"]) == {x.strip() for x in r["담당"].replace("시스템", "Y01").split("/")}
    assert calc.check(items, "HAND-01")["result"] == calc.PASS


# ─────────────────────────── 기본 시연 (진짜 엔진) ───────────────────────────


def test_base_flow_confirms_once_applies_requeries_and_splits_s_and_r(
    proc, company, handed
) -> None:
    """
    T06 · 기본 시연 — 수행계획 적용(원계획 그대로) → 변경안 → H03 확인 한 번 → 반영 → 재조회 두 행
    일치(SC02반영본) → S +60분 관찰 · R −30분 운송 확인 → HAND-02(SC02인계). 끝 = SC02요약.
    """
    assert _base(proc, company, handed) is State.DONE
    doc = proc.get(handed)
    assert doc["bpm"]["visited"] == [
        "Task_Propose",
        "Task_Check",
        "Task_ApplyPlan",
        "Task_Draft",
        "Approve_Change",
        "Record_Approve_Change",
        "Task_Apply",
        "Task_Requery",
        "Task_Reassess",
        "Task_Handoff",
        "End",
    ]
    [conf] = doc["confirmations"]
    sheet = _sheet("SC02확인")[0]
    assert (conf["approval_id"], conf["draft_id"], conf["base_version"]) == (
        sheet["확인 ID"],
        sheet["제안 버전"],
        sheet["기준 원계획"],
    )
    assert conf["target_version"] == sheet["반영 버전"] and conf["actor_role"] == sheet["담당자"]
    assert conf["targets"] == [c.strip() for c in sheet["대상"].split("/")]
    assert parse_at(conf["confirmed_at"]) == _kst(sheet["확인시각 KST"])
    stored = company.production_plan(handed)
    assert stored["version"] == "PROD-V2"
    rows = _by(stored["rows"], "commitment_id")
    for row in _sheet("SC02반영본"):
        s = rows[row["약정"]]
        assert (s["approval_id"], s["version"], s["qty"]) == (
            row["확인 ID"],
            row["저장 버전"],
            row["반영 수량"],
        )
        assert parse_at(s["start"]) == _kst(row["반영 착수"])
        assert parse_at(s["end"]) == _kst(row["반영 종료"])
        assert doc["readback"]["rows"][row["약정"]]["match_label"] == row["대조 결과"]
    # 반영·재조회는 확인 뒤 자동 — 조회시각은 확인시각 이후다(자료의 09:14는 시연 시간표의 예시다)
    assert parse_at(doc["readback"]["read_at"]) >= parse_at(conf["confirmed_at"])
    background = [r for r in stored["rows"] if r["commitment_id"] not in ("COM-S", "COM-R")]
    assert len(background) == 6 and {r["version"] for r in background} == {"PROD-V1"}
    h = doc["handoff"]
    sheet = _sheet("SC02인계")[0]
    assert (h["handoff_id"], h["case_id"]) == (sheet["인계 ID"], sheet["사건"])
    assert [i["commitment_id"] for i in h["items"]] == [sheet["약정"]]
    assert f"{h['draft_id']} / {h['approval_id']}" == sheet["변경 / 확인"]
    assert f"{h['production_plan_version']} · {h['items'][0]['truck_id']}" == sheet["반영 근거"]
    assert h["items"][0]["shortfall_min"] == 30 and h["items"][0]["qty"] == 240
    assert h["observed"] == ["COM-S"] and h["held"] == []
    board = next(r for r in records_of(doc, proc.master()) if r["kind"] == "dashboard")["body"]
    summary = {r["화면 지표"]: r["현재값"] for r in _sheet("SC02요약")}
    s = board["summary"]
    assert (s["initial_impact"], s["matched"], s["observe"], s["residual"], s["hold"]) == (
        summary["최초 영향"],
        summary["반영 대조 일치"],
        summary["통제 종료·관찰"],
        summary["잔여 위험"],
        summary["판정 보류"],
    )
    assert s["confirmations"] == summary["담당자 확인"]
    assert float(board["kpi"]["otd"]) == summary["마감 OTD"]  # 미래 전망은 OTD에 합산하지 않는다


def test_t01_plan_applies_without_changing_the_production_plan(proc, company, handed) -> None:
    """T01 — 수행계획 적용 뒤에도 생산계획은 PROD-V1. 구성 승인이 없다(결재는 H03 하나)."""
    _open(proc, handed)
    engine, run = _start(proc, handed)
    doc = proc.get(handed)
    assert doc["plan"]["state"] == "APPLIED" and doc["plan"]["check"]["needs_approval"] is False
    assert [i["unit"] for i in doc["plan"]["items"]] == ["U01", "U02", "U03", "U04", "U05"]
    assert company.production_plan(handed)["version"] == "PROD-V1"
    assert [n.id for n in proc.process.of_kind("userTask")] == ["Approve_Change"]
    assert [n.id for p in proc.processes.values() for n in p.of_kind("userTask")] == []


def test_t01_plan_without_u03_is_blocked_and_touches_nothing(proc, company, handed) -> None:
    """T01 — 필수 U03을 뺀 조합은 차단. 변경안·결재 없이 끝나고 생산계획은 원본."""
    _open(proc, handed, "PLAN-NO-U03")
    engine, run = _start(proc, handed)
    assert run.state is State.DONE
    doc = proc.get(handed)
    assert doc["plan"]["state"] == "BLOCKED"
    rules = {i["rule"] for i in doc["plan"]["check"]["issues"]}
    assert {"required_if_change", "delegation"} <= rules
    assert doc["drafts"] == [] and doc["bpm"]["visited"][-1] == "End_PlanBlocked"
    assert company.production_plan(handed)["version"] == "PROD-V1"


def test_t03_only_h03_confirms_and_a_repeat_returns_the_same_record(proc, company, handed) -> None:
    """T03 — 비권한 확인은 서버가 거절해 같은 결재로 돌아간다. H03 정상 확인은 APP-01 한 건."""
    _open(proc, handed)
    engine, run = _start(proc, handed)
    state = _answer(engine, run, _answer_values(proc, handed), by="김태오")
    assert state is State.WAITING
    assert [p.node_id for p in run.pendings.values()] == ["Approve_Change"]
    assert proc.get(handed)["confirmations"] == []
    assert _answer(engine, run, _answer_values(proc, handed)) is State.DONE
    doc = proc.get(handed)
    assert [c["approval_id"] for c in doc["confirmations"]] == ["APP-01"]
    args = {
        "demo_run_id": handed,
        "version": doc["drafts"][-1]["draft_id"],
        "content_hash": doc["drafts"][-1]["content_hash"],
        "decision": "확정",
        "comment": "다시 누름",
        "answered_by": "배정훈",
    }
    again = proc.operate(
        handed,
        "confirm_production_change",
        args,
        external_run_id=doc["bpm"]["external_run_id"],
        via="studio",
    )
    assert again["approval_id"] == "APP-01" and len(proc.get(handed)["confirmations"]) == 1
    assert catalog.HOLDERS["H03"] == ["배정훈"]


def test_t04_plan_changed_after_confirmation_blocks_apply_and_asks_again(
    proc, company, handed
) -> None:
    """T04 — 확인 뒤 원계획 버전이 바뀌면 그 확인으로 반영하지 않는다. 새 판·재확인, 이력 보존."""
    _open(proc, handed)
    engine, run = _start(proc, handed)
    real = company.apply_plan_row

    def revised_first(world_id, body):  # 확인과 반영 사이에 다른 담당자가 원계획을 고쳤다
        company._call("POST", f"/worlds/{world_id}/sim/production-plan/revise", {})
        company.apply_plan_row = real
        return real(world_id, body)

    company.apply_plan_row = revised_first
    state = _answer(engine, run, _answer_values(proc, handed))
    company.apply_plan_row = real
    assert state is State.WAITING  # 새 판의 확인을 기다린다
    doc = proc.get(handed)
    assert [d["draft_id"] for d in doc["drafts"]] == ["PP-DRAFT-V1", "PP-DRAFT-V2"]
    assert doc["drafts"][0]["state"] == "STALE"
    assert doc["confirmations"][0]["state"] == "EXPIRED"
    assert doc["drafts"][1]["base_version"] == "PROD-V1.1"
    assert all(r.get("approval_id") is None for r in company.production_plan(handed)["rows"])
    assert _answer(engine, run, _answer_values(proc, handed)) is State.DONE
    doc = proc.get(handed)
    assert [c["approval_id"] for c in doc["confirmations"]] == ["APP-01", "APP-02"]
    assert doc["handoff"]["approval_id"] == "APP-02"


def test_t05_rework_request_keeps_the_original_plan(proc, company, handed) -> None:
    """T05 — H03 보완 요청이면 반영 0건, 원계획 유지."""
    _open(proc, handed)
    engine, run = _start(proc, handed)
    assert _answer(engine, run, _answer_values(proc, handed, "보완요청")) is State.DONE
    doc = proc.get(handed)
    assert doc["bpm"]["visited"][-1] == "End_Rework" and doc["apply"] is None
    assert company.production_plan(handed)["version"] == "PROD-V1"


def test_t05_line_conflict_cannot_be_confirmed_and_shows_its_evidence(
    proc, company, handed
) -> None:
    """T05 — 배경 주문과 라인이 겹치는 변경안은 확정할 수 없다(같은 결재로). 충돌 근거 표시."""
    _open(proc, handed, "LINE-CONFLICT")
    engine, run = _start(proc, handed)
    d = proc.get(handed)["drafts"][-1]
    r = _by(d["rows"], "commitment_id")["COM-R"]
    assert not d["confirmable"] and r["conflicts"][0]["commitment_id"] == "COM-D2"
    assert _answer(engine, run, _answer_values(proc, handed)) is State.WAITING
    assert proc.get(handed)["confirmations"] == []
    assert _answer(engine, run, _answer_values(proc, handed, "보완요청")) is State.DONE
    assert company.production_plan(handed)["version"] == "PROD-V1"


def test_t07_lost_response_is_unknown_until_requery_then_reapplied_once(
    proc, company, handed
) -> None:
    """T07 — R 응답 유실은 결과 미확인. 미반영이 확인된 R만 같은 실행키로 다시, S는 한 번."""
    sent: list[str] = []
    real = company.apply_plan_row

    def counting(world_id, body):
        sent.append(body["row"]["commitment_id"])
        return real(world_id, body)

    company.apply_plan_row = counting
    try:
        assert _base(proc, company, handed, "R-LOST") is State.DONE
    finally:
        company.apply_plan_row = real
    doc = proc.get(handed)
    assert sent == ["COM-S", "COM-R"]  # S 중복 반영 없음
    r = doc["apply"]["rows"]["COM-R"]
    assert [a["outcome"] for a in r["attempts"]] == ["LOST", "ACK"]
    assert r["execution_key"].endswith(":APP-01:COM-R")
    assert doc["bpm"]["visited"].count("Task_Apply") == 1  # 노드는 한 번 기록(재방문은 이력)
    assert doc["handoff"]["items"][0]["commitment_id"] == "COM-R"


def test_t07_stored_quantity_mismatch_holds_r_and_hands_nothing_off(proc, company, handed) -> None:
    """T07 — 저장 수량 불일치면 R 보류(재조회 필요), S는 관찰. 대조 전 R 인계 금지."""
    company._call(
        "POST",
        f"/worlds/{handed}/sim/production-plan/faults",
        {"commitment_id": "COM-R", "qty": 230},
    )
    assert _base(proc, company, handed) is State.DONE
    doc = proc.get(handed)
    assert doc["readback"]["rows"]["COM-R"]["match"] == calc.MISMATCH
    assert doc["readback"]["rows"]["COM-R"]["diffs"] == ["qty"]
    rows = _by(doc["assessments"][-1]["rows"], "commitment_id")
    assert rows["COM-R"]["route"] == calc.HOLD and rows["COM-R"]["margin_min"] is None
    assert rows["COM-S"]["route"] == calc.OBSERVE
    assert doc["handoff"] is None and doc["bpm"]["visited"][-1] == "End_Observe"


def test_t08_boundary_boards_and_missing_trucks_hold_without_zero(master: dict) -> None:
    """T08 — 준비시각 = 마감이면 탑승 가능. 차량 자료 누락은 보류이고 0분으로 메우지 않는다."""
    m = copy.deepcopy(master)
    for t in m["trucks"]:
        if t["truck_id"] == "R-1":
            t["cutoff"] = "2026-11-05T16:00:00+09:00"
    targets = [{"commitment_id": "COM-R", "qty": 240, "prep_min": 30}]
    rb = {"COM-R": {"match": calc.MATCHED, "stored": {"end": "2026-11-05T15:30:00+09:00"}}}
    [r] = calc.reassess(targets, rb, m)
    assert r["truck_id"] == "R-1" and r["margin_min"] == 150
    m["trucks"] = [t for t in m["trucks"] if t["commitment_id"] != "COM-R"]
    [r] = calc.reassess(targets, rb, m)
    assert r["route"] == calc.HOLD and r["margin_min"] is None and "trucks" in r["missing"]


def test_t08_no_truck_case_holds_r_in_the_flow(proc, company, handed) -> None:
    assert _base(proc, company, handed, "NO-TRUCK") is State.DONE
    doc = proc.get(handed)
    rows = _by(doc["assessments"][-1]["rows"], "commitment_id")
    assert rows["COM-R"]["route"] == calc.HOLD and rows["COM-S"]["margin_min"] == 60
    assert doc["handoff"] is None


def test_t09_same_result_requery_makes_no_new_handoff(proc, company, handed) -> None:
    """T09 — 같은 결과로 다시 판정·인계해도 HAND-02 한 건·판정 판 하나. OTD 99% 그대로."""
    assert _base(proc, company, handed) is State.DONE
    doc = proc.get(handed)
    run_id = doc["bpm"]["external_run_id"]
    for op in ("reassess_delivery_risk", "hand_off_residual_risk"):
        proc.operate(handed, op, {"demo_run_id": handed}, external_run_id=run_id, via="studio")
    doc = proc.get(handed)
    assert len(doc["assessments"]) == 1 and doc["handoff"]["handoff_id"] == "HAND-02"
    board = next(r for r in records_of(doc, proc.master()) if r["kind"] == "dashboard")["body"]
    assert board["kpi"]["otd"] == "0.9900"
    assert "경영검토 상신" in doc["handoff"]["not_done"]


# ─────────────────────────── 경계 ───────────────────────────


def test_scene_2_needs_the_scene_1_handoff(proc, sc01) -> None:
    rid = f"s2-{uuid.uuid4().hex[:8]}"
    sc01.create(rid, executor="studio")
    with pytest.raises(DomainError) as no:
        _open(proc, rid)
    assert no.value.status == 409


def test_apply_before_confirmation_is_refused(proc, company, handed) -> None:
    """확인 전 반영 금지 — 일감이 와도 409."""
    _open(proc, handed)
    _start(proc, handed)
    doc = proc.get(handed)
    with pytest.raises(DomainError) as early:
        proc.operate(
            handed,
            "apply_production_change",
            {"demo_run_id": handed},
            external_run_id=doc["bpm"]["external_run_id"],
            via="studio",
        )
    assert early.value.status == 409
    assert company.production_plan(handed)["version"] == "PROD-V1"


def test_other_run_and_other_place_are_refused(proc, company, handed) -> None:
    _open(proc, handed)
    args = {"demo_run_id": handed, "case_id": "CASE-S2-01"}
    proc.operate(handed, "propose_case_plan", args, external_run_id="run-a", via="studio")
    with pytest.raises(DomainError) as other:
        proc.operate(handed, "check_case_plan", args, external_run_id="run-b", via="studio")
    assert other.value.status == 409
    with pytest.raises(DomainError) as place:
        proc.operate(handed, "check_case_plan", args, external_run_id="run-a", via="center")
    assert place.value.status == 409


def test_center_not_configured_leaves_a_reason(company, backend, sc01, handed) -> None:
    proc = S2Sc02Process(build_sc01_store(backend, "s2sc02"), company=company, sc01=sc01)
    doc = proc.create(handed)  # 실행 위치 center — 설정 없음
    assert doc["bpm"]["job_id"] is None and "Center 연동이 설정되지 않았다" in doc["bpm"]["problem"]
    assert proc.create(handed)["created_at"] == doc["created_at"]  # 다시 열어도 그대로


def test_extension_definition_matches_the_bpmn_service_calls() -> None:
    """
    확장 `external` 0.10.0 — 업무 그림과 공통 BPM `platform.case-plan`의 서비스 호출이 정의의
    입력·출력과
    맞고, 결재 담당자가 H03 배정과 같고, 기록 작업에 오류 경계가 있다. 호출 활동이 내보내는 값은
    공통
    BPM이 만든다.
    """
    import json

    from chaeksas.contracts import extension as ext
    from chaeksas.contracts.bpmn_ext import read_process

    from app.s2.sc02.process import CALLED_PATHS, OPERATIONS, PROCESS_PATH

    raw = (
        Path(__file__).resolve().parents[2] / "chaeksas" / "external.extension.json"
    ).read_bytes()
    manifest = ext.ExtensionManifest.model_validate(json.loads(raw))
    assert ext.validate(manifest, from_center=True) == []
    operations = {o["name"]: o for o in json.loads(raw)["service"]["adapter"]["operations"]}
    process = read_process(PROCESS_PATH.read_bytes())
    called = {p.id: p for p in (read_process(path.read_bytes()) for path in CALLED_PATHS)}
    assert set(called) == {"platform.case-plan"}
    used = []
    for drawing in (*called.values(), process):
        for node in drawing.of_kind("serviceTask"):
            call = node.prop("serviceCall")
            op = operations[call.operation]
            assert set(op["input_schema"]["required"]) <= set(call.input), node.id
            assert set(call.output.values()) <= set(op["output_schema"]["properties"]), node.id
            used.append(call.operation)
        [need] = [n for n in drawing.info.extensions if n.id == manifest.id]
        assert need.version.startswith(">=0.10.0")
    assert used == list(OPERATIONS)
    [approval] = process.of_kind("userTask")
    spec = approval.prop("approval")
    assert spec.assignees == catalog.HOLDERS["H03"] and spec.answered_by_as == "확인자"
    boundaries = [n for n in process.all_nodes() if n.kind == "boundaryEvent"]
    assert [b.attached_to for b in boundaries] == ["Record_Approve_Change"]
    [node] = process.of_kind("callActivity")
    target = called[node.called_element]
    produced = {
        name for n in target.of_kind("serviceTask") for name in n.prop("serviceCall").output
    }
    assert set(node.prop("call").output.values()) <= produced


def test_common_bpm_jobs_carry_the_calling_package(proc, company, handed) -> None:
    """공통 BPM `platform.case-plan` 안의 일감도 실행 신원이 바깥 패키지(`company1.s2.sc02`)다."""
    seen: list[tuple[str, str | None]] = []

    class _Recorded(C15Calls):
        def call(self, request):
            seen.append((request.operation, request.bpm_process_id))
            return super().call(request)

    _open(proc, handed)
    _start(proc, handed, _Recorded(proc, origin="test"))
    assert {pid for _, pid in seen} == {"company1.s2.sc02"}
    assert [op for op, _ in seen] == [
        "propose_case_plan",
        "check_case_plan",
        "apply_case_plan",
        "draft_production_change",
    ]


def test_every_written_version_matches_the_common_record_schemas(proc, company, handed) -> None:
    """
    공통 기록 종류(`docs/records/s2/sc02/`) — 기본 시연의 모든 판이 봉투·종류별 스키마를 통과하고,
    사이트 예시가 최신이다(다시 뽑기 `NOWVIEW_WRITE_RECORD_SCHEMAS=1`·`…_EXAMPLES=1`).
    """
    from records_contract import check, every_version, example

    from app.s2.sc02.records import KINDS

    assert _base(proc, company, handed) is State.DONE
    versions = every_version(company, handed, 2)
    assert len(versions) > 8
    assert check(2, KINDS, versions, "s2/sc02") == []
    assert example(company, handed, 2, "s2/sc02") == []
    kinds = {r["kind"] for r in company.records(handed, scene=2)}
    assert "case" not in kinds  # Case 기록은 장면 1 문서의 것이다


# ─────────────────────────── 세계 따라가기 · 대시보드 ───────────────────────────


def test_follower_opens_scene_2_on_the_site_command_and_sweeps(
    monkeypatch, company, backend, sc01
) -> None:
    """
    사이트가 시나리오 2 회차에 「장면 열기」(장면 2)를 남기면 장면 2 문서를 연다(Center 설정이
    없으면
    사유). 초기화 회차가 오르면 장면 2 문서를 지우고, 세계가 지워지면 거둔다.
    """
    from app.follower import Follower

    monkeypatch.delenv("NOWVIEW_TEST_INPUTS", raising=False)
    s2 = S2Sc02Process(build_sc01_store(backend, "s2sc02"), company=company, sc01=sc01)
    rid = f"demo-{uuid.uuid4().hex[:8]}"
    company._call("POST", "/worlds", {"world_id": rid, "origin": "site", "scenario_id": "s2"})
    f = Follower(company, {}, s2=sc01, s2_scenes={2: s2})
    f._follow(company.world(rid))
    with sc01._lock(rid):  # 장면 1을 인계까지(엔진 시험 — Studio로 바꿔 진행)
        d, v = sc01._load(rid)
        d["executor"] = "studio"
        sc01.store.save(rid, d, v, "studio")
    _scenario(sc01, company, rid)
    company._call(
        "POST",
        f"/worlds/{rid}/commands",
        {"scene": 2, "kind": "open", "actor": "u-prod-lead", "body": {}, "ref": f"{rid}:open2"},
    )
    f._follow(company.world(rid))
    [cmd] = company.commands(rid, None)
    assert cmd["state"] == "DONE", cmd
    doc = s2.get(rid)
    assert doc["source"]["handoff"]["handoff_id"] == "HAND-01"
    assert "Center 연동이 설정되지 않았다" in doc["bpm"]["problem"]
    company._call("POST", f"/worlds/{rid}/reset")
    f._follow(company.world(rid))
    assert s2.store.load(rid) is None
    company._call("DELETE", f"/worlds/{rid}")
    f._sweep({w["world_id"] for w in company.worlds()})
    assert sc01.store.load(rid) is None


def test_dashboard_shows_scene_2_metrics_for_a_scenario_2_world(
    proc, sc01, company, handed, tmp_path
) -> None:
    """회사 대시보드 — 시나리오 2 회차의 업무 22 카드에 SC02요약의 숫자와 열린 결재 진행."""
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
        build_router(settings, None, None, None, {"company1": _System()}, {21: sc01, 22: proc})
    )
    body = TestClient(app).get("/companies/company1/dashboard").json()
    works = {w["scene"]: w for w in body["works"]}
    assert set(works) == {21, 22, 23}  # 장면 3 카드는 문서가 없어 시작 전이다
    w = works[22]
    assert (w["work"], w["state"]) == ("정형통제 실행과 주문별 분기", "done")
    assert w["progress"] == {"approvals": 1, "passed": 1}
    assert [m["value"] for m in w["metrics"]] == ["2건", "2건", "1건", "1건", "0건", "1회"]


def test_center_run_failing_before_any_job_is_recorded_with_its_reason(
    company, backend, sc01, handed
) -> None:
    """
    일감 전에 실패한 Center 실행 — 폴러가 작업 상태로 실패와 사유를 남기고 장면은 「실행 실패」다
    (2026-11-05 로컬 실측: 공통 BPM `platform.case-plan` 대신 `case-intake`를 설치한 패키지).
    """
    from test_s2_sc01 import _EndedCenter

    center = _EndedCenter()
    proc = S2Sc02Process(
        build_sc01_store(backend, "s2sc02"), company=company, sc01=sc01, center=center
    )
    doc = proc.create(handed)
    assert (doc["bpm"]["state"], doc["bpm"]["job_id"]) == ("running", "job_1")
    assert proc.poll_center() == 1
    doc = proc.get(handed)
    assert doc["bpm"]["state"] == "failed" and "call_target_missing" in doc["bpm"]["problem"]
    scene = next(r for r in records_of(doc, proc.master()) if r["kind"] == "scene")
    assert scene["state"] == "RUN_FAILED"
    assert proc.poll_center() == 0
