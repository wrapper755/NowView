"""
시나리오 2 장면 1 — 납기 위험 조기 감지(`app/s2/sc01/`, `docs/s2/sc01.md`).

* 통합가상데이터 v0.1의 **파생 칸**(입고개정의 변경수·최소 여유·부족·판정, 주문영향의 배정
  입고분·사용 가능·
  착수차질, 상황판·모델별 집계)을 규칙 계산으로 다시 내서 대조한다 — 숫자를 시험에 옮겨 적지 않는다.
* 구현명세 §5 인수시험 T01~T09.
* 진짜 Chaeksas 엔진이 그림(`processes/s2-sc01.bpmn`)을 돌고 서비스 태스크는 C15 일꾼의 수행기를
  지난다
  (Studio 흉내 — `conftest.C15Calls`). 회사 시스템은 기간계 쌍둥이(`tests/company_twin/`)다.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl
import pytest
from chaeksas.core.engine import Engine, RunEnv, State, new_run_id
from chaeksas.core.run_log import RunLog
from conftest import C15Calls

from app import company as company_mod
from app.s2.sc01 import calc
from app.s2.sc01.process import S2Sc01Process
from app.s2.sc01.records import records_of
from app.sc01.domain import DomainError, parse_at
from app.sc01.store import build_sc01_store
from app.store import build_sqlite_backend

SEED = Path(__file__).resolve().parents[1] / "seed" / "SYN-S2-SC01-v0.1.xlsx"
KST = calc.KST
AT = {
    "P-v0": "2026-11-02T09:00:00+09:00",
    "P-v1": "2026-11-03T09:00:00+09:00",
    "P-v2": "2026-11-04T09:00:00+09:00",
}


def _sheet(name: str) -> list[dict]:
    """파생 칸의 엑셀 계산값(data_only) — 기대값이다."""
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


@pytest.fixture()
def company():
    return company_mod.default_client()


@pytest.fixture()
def master(company) -> dict:
    return company.s2_master()


def _revision(master: dict, rid: str, **override) -> dict:
    found = copy.deepcopy(next(r for r in master["revisions"] if r["revision_id"] == rid))
    return {**found, "registered_at": AT[rid], **override}


def _evaluate_all(master: dict) -> list[dict]:
    done: list[dict] = []
    for rid in ("P-v0", "P-v1", "P-v2"):
        done.append(calc.evaluate(_revision(master, rid), done, master))
    return done


# ─────────────────────────── 통합가상데이터 대조 ───────────────────────────


def test_revisions_match_the_receipt_revision_sheet(master: dict) -> None:
    """입고개정 — 최근 3영업일 변경수·최소 착수 여유·필요시각 부족·판정(최초·기록·경보)."""
    found = {e["revision_id"]: e for e in _evaluate_all(master)}
    label = {"최초": calc.FIRST, "기록": calc.RECORD, "경보": calc.ALERT}
    for row in _sheet("입고개정"):
        e = found[row["원천 개정"]]
        assert e["change_count"] == row["최근 3영업일 변경수"]
        assert e["min_slack_min"] == row["최소 착수 여유(분)"]
        assert e["shortage"] == row["필요시각 부족(개)"]
        assert e["judgment"] == label[row["판정"]]


def test_allocation_matches_the_order_impact_sheet(master: dict) -> None:
    """주문영향 — 배정 입고분·배정수량·사용 가능 예정·착수차질(대표 S·R + 배경 c·d·e 각 2건)."""
    latest = _evaluate_all(master)[-1]
    rows = {
        r["commitment_id"]: r for r in calc.open_commitments(master, latest["lots"], AT["P-v2"])
    }
    allocated = calc.allocate(
        [*master["background_lots"], *latest["lots"]],
        master["demand"],
        {c["commitment_id"]: c["qty"] for c in master["commitments"]},
    )
    for row in _sheet("주문영향"):
        cid = row["약정 ID"]
        a = allocated[cid]
        assert [p["lot_id"] for p in a["lots"]] == [row["배정 입고분"]]
        assert a["allocated_qty"] == row["배정수량"]
        assert parse_at(a["available_at"]) == _kst(row["사용가능 예정"])
        assert rows[cid]["start_delay_min"] == row["착수차질(분)"]


def test_dashboard_matches_the_board_and_model_sheets(master: dict) -> None:
    """T01 · 상황판 — 99/100 = 99%, 목표 98%. 모델별 — 모델당 20건, d만 19/20."""
    o = calc.otd(master, AT["P-v2"])
    board = {r["지표"]: r["값"] for r in _sheet("상황판")}
    assert (o["numerator"], o["denominator"]) == (board["정시 전량 인수"], board["마감 약정"])
    assert float(o["otd"]) == board["OTD"] and float(o["target"]) == board["목표"]
    assert o["meets_target"] is True
    by_model = {r["model"]: r for r in o["by_model"]}
    for row in _sheet("모델별 집계"):
        m = by_model[row["모델"]]
        assert (m["due"], m["on_time"]) == (row["10월 약정"], row["정시"])
        assert float(m["otd"]) == row["OTD"]
    upcoming = calc.open_commitments(master, _evaluate_all(master)[-1]["lots"], AT["P-v2"])
    assert len([r for r in upcoming if r["demo_role"] == "background"]) == board["현재 배경 약정"]


def test_otd_does_not_count_promises_not_yet_due(master: dict) -> None:
    """G03 — 아직 납기가 오지 않은 약정은 분모·지연에 넣지 않는다. 분모 0은 「대상 없음」(None)."""
    early = calc.otd(master, "2026-10-01T09:00:00+09:00")
    assert early["denominator"] == 0 and early["otd"] is None
    assert calc.otd(master, "2026-10-20T14:59:00+09:00")["late"] == []  # H199 약정 15:00 전
    assert calc.otd(master, "2026-11-04T09:00:00+09:00")["late"] == ["H199"]


# ─────────────────────────── T02~T04 경보 규칙 ───────────────────────────


def _shift_lots(rev: dict, minutes: int) -> dict:
    for lot in rev["lots"]:
        lot["planned_at"] = (parse_at(lot["planned_at"]) + timedelta(minutes=minutes)).isoformat()
    return rev


def test_t02_first_change_at_exactly_15_minutes_is_record_only_and_14_alerts(master: dict) -> None:
    v0 = calc.evaluate(_revision(master, "P-v0"), [], master)
    v1 = calc.evaluate(_revision(master, "P-v1"), [v0], master)
    assert (v1["judgment"], v1["min_slack_min"]) == (calc.RECORD, 15)
    later = calc.evaluate(_shift_lots(_revision(master, "P-v1"), 1), [v0], master)
    assert (later["judgment"], later["min_slack_min"]) == (calc.ALERT, 14)
    assert any("15분 미만" in r for r in later["reasons"])


def test_t03_first_change_one_part_short_alerts_regardless_of_time(master: dict) -> None:
    v0 = calc.evaluate(_revision(master, "P-v0"), [], master)
    short = _revision(master, "P-v1")
    short["lots"] = [{**short["lots"][0], "qty": 319, "planned_at": "2026-11-05T05:00:00+09:00"}]
    # S 80개 중 79개만 07:00 전에 — 나머지 1개는 R 몫까지 내려가지 않는다(배정은 S부터)
    m = copy.deepcopy(master)
    for d in m["demand"]:
        if d["commitment_id"] == "COM-R":
            d["assembly_start"] = "2026-11-05T05:00:00+09:00"
    found = calc.evaluate(short, [v0], m)
    assert found["judgment"] == calc.ALERT
    assert found["shortage"] >= 1
    assert any("부족" in r for r in found["reasons"])


def test_t04_window_counts_only_changes_in_three_business_days(master: dict) -> None:
    """창 밖의 이전 변경은 횟수에서 뺀다 — 이력은 보존한다. 주말은 영업일이 아니다."""
    v0 = calc.evaluate(
        _revision(master, "P-v0", registered_at="2026-10-26T09:00:00+09:00"), [], master
    )
    v1 = calc.evaluate(
        _revision(master, "P-v1", registered_at="2026-10-27T09:00:00+09:00"), [v0], master
    )
    v2 = calc.evaluate(_revision(master, "P-v2"), [v0, v1], master)
    assert v2["window"] == ["2026-11-02", "2026-11-03", "2026-11-04"]
    assert v2["change_count"] == 1  # 창 안의 유효 변경은 이번 하나
    assert calc.business_window(datetime(2026, 11, 2).date()) == [
        datetime(2026, 10, 29).date(),
        datetime(2026, 10, 30).date(),
        datetime(2026, 11, 2).date(),
    ]


def test_hold_when_first_change_lacks_required_data(master: dict) -> None:
    """
    첫 변경의 판정에 필요한 자료가 없고 다른 조건으로 경보를 확정할 수 없으면 「평가 보류」 —
    정상이 아니다.
    """
    m = copy.deepcopy(master)
    for d in m["demand"]:
        if d["part_id"] == "P":
            d["assembly_start"] = None
    v0 = calc.evaluate(_revision(master, "P-v0"), [], m)
    found = calc.evaluate(_revision(master, "P-v1"), [v0], m)
    assert found["judgment"] == calc.HOLD
    assert "COM-S:assembly_start" in found["missing"]


# ─────────────────────────── 프로세스 (기간계 쌍둥이 + 진짜 엔진) ───────────────────────────


@pytest.fixture()
def proc(tmp_path, company) -> S2Sc01Process:
    backend = build_sqlite_backend(str(tmp_path / "engine.sqlite"))
    return S2Sc01Process(build_sc01_store(backend, "s2sc01"), company=company)


class _Recorded(C15Calls):
    """일감마다 (작업, 실행 신원)을 적는다 — 호출된 공통 BPM 안의 일감도 바깥 패키지 id인지 본다."""

    def __init__(self, proc, **kw) -> None:
        super().__init__(proc, **kw)
        self.seen: list[tuple[str, str | None]] = []

    def call(self, request):
        self.seen.append((request.operation, request.bpm_process_id))
        return super().call(request)


def _run(proc: S2Sc01Process, rid: str, doc_id: str, calls: C15Calls | None = None) -> State:
    """
    Studio 흉내 — 진짜 엔진이 그림을 돌고(호출 활동은 공통 BPM을 같은 실행 안에서 돈다) 서비스
    태스크는 C15 수행기를 지난다(실행 하나 = 개정 하나).
    """
    run_id = new_run_id(test=True)
    engine = Engine()
    run = engine.start(
        proc.process,
        run_id=run_id,
        log=RunLog(run_id=run_id),
        env=RunEnv(services=calls or C15Calls(proc, origin="test"), processes=proc.processes),
        executor="studio",
        bpm_process_id="company1.s2.sc01",
        inputs={"데모실행ID": rid, "원천개정": doc_id},
        now=parse_at(proc.get(rid)["clock"]),
    )
    return engine.run_until_blocked(run)


def _send(proc: S2Sc01Process, company, rid: str, fixture: str) -> str:
    company._call("POST", f"/worlds/{rid}/clock", {"at": AT[fixture]})
    proc.follow_clock(rid, AT[fixture])
    sent = company.purchase_registers(rid, fixture)
    proc.receive_inbox(rid, sent["doc_id"])
    return sent["doc_id"]


@pytest.fixture()
def rid(proc: S2Sc01Process) -> str:
    rid = f"s2-{uuid.uuid4().hex[:8]}"
    proc.create(rid, executor="studio")
    return rid


def _scenario(proc, company, rid) -> dict[str, str]:
    docs = {}
    for fixture in ("P-v0", "P-v1", "P-v2"):
        docs[fixture] = _send(proc, company, rid, fixture)
        assert _run(proc, rid, docs[fixture]) is State.DONE
    return docs


def test_base_flow_opens_one_case_with_two_commitments_and_hands_off(proc, company, rid) -> None:
    """
    D01·D02 — 최초·기록은 이력만, 2차 변경에서 경보 1·Case 1·약정 2, 분석 S 90분·R 150분, N03A 인계.
    """
    s0 = proc.get(rid)
    assert s0["clock"] == "2026-11-02T08:00:00+09:00"  # 시나리오 2 회차의 처음 시각(기간계)
    _scenario(proc, company, rid)
    doc = proc.get(rid)
    runs = {r["revision_id"]: r["run"] for r in doc["receipts"].values()}
    assert runs["P-v0"]["visited"] == ["Task_Evaluate", "End_Recorded"]
    assert runs["P-v1"]["visited"] == ["Task_Evaluate", "End_Recorded"]
    assert runs["P-v2"]["visited"] == [
        "Task_Evaluate",
        "Task_Link",
        "Task_Analyze",
        "Task_Handoff",
        "End",
    ]
    assert all(r["state"] == "done" for r in runs.values())
    assert doc["case"]["commitments"] == ["COM-S", "COM-R"]
    assert doc["case"]["state"] == "ANALYZED"
    rows = {r["commitment_id"]: r for r in doc["analyses"][-1]["rows"]}
    assert (rows["COM-S"]["start_delay_min"], rows["COM-R"]["start_delay_min"]) == (90, 150)
    assert rows["COM-S"]["truck_cutoff"] == "2026-11-05T11:30:00+09:00"
    assert rows["COM-R"]["promised_at"] == "2026-11-05T18:30:00+09:00"
    assert doc["analyses"][-1]["total_qty"] == {"first": 320, "latest": 320}
    assert (
        doc["analyses"][-1]["execution_mode"] == "rule"
    )  # 가상자료 재현을 실제 AI 호출로 표시하지 않는다
    assert doc["handoff"]["next_node"] == "N03A" and doc["handoff"]["revision_id"] == "P-v2"


def test_t05_redelivery_counts_once_and_creates_nothing_new(proc, company, rid) -> None:
    """같은 개정(P-v2)의 재수신 — 유효 변경 2회, 경보·Case·분석 각 1. 그림은 이력 끝으로 간다."""
    _scenario(proc, company, rid)
    doc = proc.get(rid)
    source = next(r for r in doc["receipts"].values() if r["revision_id"] == "P-v2")
    with proc._lock(rid):  # 기간계가 같은 개정을 다른 문서로 다시 전달한 상황
        d, v = proc._load(rid)
        d["receipts"]["RCV-9999"] = {**copy.deepcopy(source), "doc_id": "RCV-9999"}
        d["receipts"]["RCV-9999"]["run"] = {
            "job_id": None,
            "external_run_id": None,
            "state": "waiting",
            "visited": [],
            "problem": None,
        }
        proc.store.save(rid, d, v, "redelivery")
    assert _run(proc, rid, "RCV-9999") is State.DONE
    doc = proc.get(rid)
    assert doc["receipts"]["RCV-9999"]["run"]["visited"] == ["Task_Evaluate", "End_Recorded"]
    assert doc["receipts"]["RCV-9999"]["outcome"] == "DUPLICATE"
    assert doc["events"]["P-v2"]["change_count"] == 2
    assert len(doc["analyses"]) == 1 and doc["alert"]["events"] == ["EV-S2-01-R2"]


def test_t06_board_lists_background_commitments_without_delay(proc, company, rid) -> None:
    """상황판 — c·d·e 각 2건 착수 차질 0분, 과거 d 지연 1건(H199)은 마감 실적에 따로."""
    _scenario(proc, company, rid)
    board = next(r for r in records_of(proc.get(rid), proc.master()) if r["kind"] == "dashboard")[
        "body"
    ]
    background = [r for r in board["open_commitments"] if r["demo_role"] == "background"]
    assert len(background) == 6 and {r["start_delay_min"] for r in background} == {0}
    assert board["kpi"]["late"] == ["H199"]
    assert (board["kri"]["alerts"], board["kri"]["affected_commitments"]) == (1, 2)
    assert [r["judgment"] for r in board["revisions"]] == ["FIRST", "RECORD", "ALERT"]


def test_t07_missing_truck_cutoff_keeps_alert_and_marks_shipment_unconfirmed(master: dict) -> None:
    """
    R 차량 마감 누락 — 경보·S 분석은 그대로, R 출하 영향만 미확인(빈 값을 정상·0으로 보이지 않는다).
    """
    m = copy.deepcopy(master)
    for d in m["demand"]:
        if d["commitment_id"] == "COM-R":
            d["truck_cutoff"] = None
    latest = _evaluate_all(m)[-1]
    assert latest["judgment"] == calc.ALERT
    rows = {r["commitment_id"]: r for r in calc.analyze(latest, ["COM-S", "COM-R"], m)}
    assert rows["COM-R"]["truck_cutoff"] is None and rows["COM-R"]["shipment"] == "미확인"
    assert "truck_cutoff" in rows["COM-R"]["missing"]
    assert rows["COM-S"]["missing"] == [] and rows["COM-S"]["start_delay_min"] == 90


def test_t08_failed_analysis_is_not_complete_and_retry_succeeds(proc, company) -> None:
    """
    A01 실패 — 완료로 보이지 않는다(503 → 일꾼 dependency_down, 다시 내준다). 다시 하면 같은 Case에
    이어진다.
    """
    rid = f"s2-{uuid.uuid4().hex[:8]}"
    proc.create(rid, case_id="A01-FAIL", executor="studio")
    for fixture in ("P-v0", "P-v1"):
        doc_id = _send(proc, company, rid, fixture)
        assert _run(proc, rid, doc_id) is State.DONE
    doc_id = _send(proc, company, rid, "P-v2")
    args = {"demo_run_id": rid, "doc_id": doc_id}
    run_id = "test_t08"
    proc.operate(rid, "evaluate_receipt_change", args, external_run_id=run_id, via="studio")
    proc.operate(rid, "link_case", args, external_run_id=run_id, via="studio")
    with pytest.raises(DomainError) as failed:
        proc.operate(rid, "analyze_case_impact", args, external_run_id=run_id, via="studio")
    assert failed.value.status == 503
    doc = proc.get(rid)
    assert doc["analyses"] == [] and doc["case"]["state"] == "ANALYZING"
    assert [a["state"] for a in doc["attempts"]] == ["FAILED"]
    flow = {
        f["node"]: f["state"]
        for f in next(r for r in records_of(doc, proc.master()) if r["kind"] == "case")["body"][
            "flow"
        ]
    }
    assert flow["N03"] == "failed"
    proc.operate(rid, "analyze_case_impact", args, external_run_id=run_id, via="studio")
    doc = proc.get(rid)
    assert [a["state"] for a in doc["attempts"]] == ["FAILED", "SUCCEEDED"]
    assert doc["case"]["case_id"] == "CASE-S2-01" and doc["case"]["state"] == "ANALYZED"


def test_t09_handoff_keeps_the_plan_and_has_no_approvals(proc, company, rid) -> None:
    """N03 종료 — 원계획 불변, 생산계획 승인 0건, 같은 Case·분석 판이 N03A 입력이다."""
    _scenario(proc, company, rid)
    h = proc.get(rid)["handoff"]
    assert (h["case_id"], h["alert_id"], h["revision_id"]) == ("CASE-S2-01", "AL-S2-01", "P-v2")
    assert h["commitments"] == ["COM-S", "COM-R"] and h["analysis"] == {
        "analysis_id": "ANA-01",
        "version": 1,
    }
    assert h["approvals"] == 0 and h["production_plan"].startswith("원본 유지")
    assert h["data_as_of"] == AT["P-v2"] and h["missing"] == []


def test_records_reach_the_company_and_reruns_add_no_versions(proc, company, rid) -> None:
    """
    경영 기록 — 사이트가 그릴 종류가 다 있고, 같은 일감을 다시 해도 새 판이 생기지 않는다(멱등).
    """
    docs = _scenario(proc, company, rid)
    kinds = {r["kind"] for r in company.records(rid)}
    assert {"scene", "event", "alert", "case", "analysis", "handoff", "dashboard"} <= kinds
    case = company.record(rid, "case", "CASE-S2-01")
    roles = [r["role_id"] for r in case["body"]["roles"]]
    assert roles[:2] == ["Y01", "A01"] and case["body"]["roles"][0]["kind"] == "system"
    before = {(r["kind"], r["record_id"]): r["version"] for r in company.records(rid)}
    run_id = proc.get(rid)["receipts"][docs["P-v2"]]["run"]["external_run_id"]
    proc.operate(
        rid,
        "analyze_case_impact",
        {"demo_run_id": rid, "doc_id": docs["P-v2"]},
        external_run_id=run_id,
        via="studio",
    )
    after = {(r["kind"], r["record_id"]): r["version"] for r in company.records(rid)}
    assert after == before


def test_other_run_on_the_same_revision_is_refused(proc, company, rid) -> None:
    doc_id = _send(proc, company, rid, "P-v0")
    args = {"demo_run_id": rid, "doc_id": doc_id}
    proc.operate(rid, "evaluate_receipt_change", args, external_run_id="run-a", via="studio")
    with pytest.raises(DomainError) as other:
        proc.operate(rid, "evaluate_receipt_change", args, external_run_id="run-b", via="studio")
    assert other.value.status == 409
    with pytest.raises(DomainError) as place:
        proc.operate(rid, "evaluate_receipt_change", args, external_run_id="run-a", via="center")
    assert place.value.status == 409


def test_center_not_configured_leaves_a_reason_instead_of_running_silently(
    company, tmp_path
) -> None:
    backend = build_sqlite_backend(str(tmp_path / "engine.sqlite"))
    proc = S2Sc01Process(build_sc01_store(backend, "s2sc01"), company=company)
    rid = f"s2-{uuid.uuid4().hex[:8]}"
    proc.create(rid)  # 실행 위치 center — 설정 없음
    doc_id = _send(proc, company, rid, "P-v0")
    run = proc.get(rid)["receipts"][doc_id]["run"]
    assert run["job_id"] is None and "Center 연동이 설정되지 않았다" in run["problem"]


# ─────────────────────────── 세계 따라가기 · 대시보드 ───────────────────────────


def test_follower_creates_and_receives_for_a_scenario_2_world(
    monkeypatch, company, tmp_path
) -> None:
    """
    사이트가 만든 시나리오 2 회차 — 같은 id로 장면 1 문서, 시각을 따라가고, 수신함의 새 개정마다
    실행을
    기동한다(Center 설정이 없으면 사유). 초기화 회차가 오르면 처음으로, 세계가 지워지면 거둔다.
    """
    from app.follower import Follower

    monkeypatch.delenv("NOWVIEW_TEST_INPUTS", raising=False)
    backend = build_sqlite_backend(str(tmp_path / "engine.sqlite"))
    s2 = S2Sc01Process(build_sc01_store(backend, "s2sc01"), company=company)
    rid = f"demo-{uuid.uuid4().hex[:8]}"
    company._call("POST", "/worlds", {"world_id": rid, "origin": "site", "scenario_id": "s2"})
    f = Follower(company, {}, s2=s2)
    f._follow(company.world(rid))
    assert s2.get(rid)["clock"] == "2026-11-02T08:00:00+09:00"
    company._call("POST", f"/worlds/{rid}/clock", {"at": AT["P-v0"]})
    company.purchase_registers(rid, "P-v0")
    f._follow(company.world(rid))
    doc = s2.get(rid)
    assert doc["clock"] == AT["P-v0"] and list(doc["receipts"]) == ["RCV-0001"]
    assert "Center 연동이 설정되지 않았다" in doc["receipts"]["RCV-0001"]["run"]["problem"]
    f._follow(company.world(rid))  # 다시 돌아도 한 번만 들인다
    assert len(s2.get(rid)["receipts"]) == 1
    company._call("POST", f"/worlds/{rid}/reset")
    f._follow(company.world(rid))
    doc = s2.get(rid)
    assert doc["receipts"] == {} and doc["world_generation"] == 2
    assert doc["clock"] == "2026-11-02T08:00:00+09:00"
    company._call("DELETE", f"/worlds/{rid}")
    f._sweep({w["world_id"] for w in company.worlds()})
    assert s2.store.load(rid) is None


def test_dashboard_shows_the_scenario_2_board_for_a_scenario_2_world(
    proc, company, rid, tmp_path
) -> None:
    """회사 대시보드 — 시나리오 2 회차는 시나리오 2 업무만, 상황판 본문(UI-D01)과 지표를 싣는다."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.companies import Settings, build_router
    from app.config import ConfigStore

    _scenario(proc, company, rid)
    world = {**company.world(rid), "origin": "site"}

    class _System:
        def worlds(self):
            return [world]

        def worker_log_entries(self, world_id: str):
            return [{"scene": 1, "operation": "evaluate_receipt_change", "ok": True, "at": "x"}]

    settings = Settings(ConfigStore(build_sqlite_backend(str(tmp_path / "config.sqlite"))))
    app = FastAPI()
    app.include_router(
        build_router(settings, None, None, None, {"company1": _System()}, {21: proc})
    )
    body = TestClient(app).get("/companies/company1/dashboard").json()
    assert body["worlds"][0]["scenarioId"] == "s2"
    [work] = body["works"]
    assert (work["scene"], work["work"], work["state"]) == (21, "납기 위험 조기 감지", "done")
    assert work["worker"]["count"] == 1
    assert [m["value"] for m in work["metrics"]] == ["99%", "98%", "1건", "2건"]
    assert work["board"]["cases"][0]["case_id"] == "CASE-S2-01"


def test_every_written_version_matches_the_common_record_schemas(proc, company, rid) -> None:
    """
    공통 기록 종류(`docs/records/s2/sc01/`) — 기본 시연의 모든 판이 봉투·종류별 스키마를 통과하고,
    사이트 예시가 최신이다(다시 뽑기 `NOWVIEW_WRITE_RECORD_SCHEMAS=1`·`…_EXAMPLES=1`).
    """
    from records_contract import check, every_version, example

    from app.s2.sc01.records import KINDS

    _scenario(proc, company, rid)
    versions = every_version(company, rid, 1)
    assert len(versions) > 10
    assert check(1, KINDS, versions, "s2/sc01") == []
    assert example(company, rid, 1, "s2/sc01") == []


def test_extension_definition_matches_the_bpmn_service_calls() -> None:
    """
    확장 `external` 0.9.0이 최신 계약 검사를 통과하고, 업무 그림과 그것이 호출하는 공통 BPM
    (`platform.case-intake`)의 서비스 호출 넷이 정의의 입력·출력과 맞는다. 호출 활동의 대상은
    받아 둔 정의에 있고, 내보내는 값은 공통 BPM이 만드는 변수다.
    """
    import json

    from chaeksas.contracts import extension as ext
    from chaeksas.contracts._semver import satisfies
    from chaeksas.contracts.bpmn_ext import read_process

    from app.s2.sc01.process import CALLED_PATHS, PROCESS_PATH

    raw = (
        Path(__file__).resolve().parents[2] / "chaeksas" / "external.extension.json"
    ).read_bytes()
    manifest = ext.ExtensionManifest.model_validate(json.loads(raw))
    assert ext.validate(manifest, from_center=True) == []
    assert manifest.version == "0.9.0"
    operations = {o["name"]: o for o in json.loads(raw)["service"]["adapter"]["operations"]}
    process = read_process(PROCESS_PATH.read_bytes())
    called = {p.id: p for p in (read_process(path.read_bytes()) for path in CALLED_PATHS)}
    assert set(called) == {"platform.case-intake"}
    used = []
    for drawing in (process, *called.values()):
        assert [n.id for n in drawing.of_kind("userTask")] == []  # 결재가 없다 — 조회만
        for node in drawing.of_kind("serviceTask"):
            call = node.prop("serviceCall")
            op = operations[call.operation]
            assert set(op["input_schema"]["required"]) <= set(call.input), node.id
            assert set(call.output.values()) <= set(op["output_schema"]["properties"]), node.id
            used.append(call.operation)
        [need] = [n for n in drawing.info.extensions if n.id == manifest.id]
        assert satisfies(manifest.version, need.version) and need.version.startswith(">=0.9.0")
    assert used == [
        "evaluate_receipt_change",
        "link_case",
        "analyze_case_impact",
        "hand_off_case_analysis",
    ]
    [node] = process.of_kind("callActivity")
    target = called[node.called_element]
    spec = node.prop("call")
    produced = {
        name for n in target.of_kind("serviceTask") for name in n.prop("serviceCall").output
    }
    assert set(spec.output.values()) <= produced
    assert set(spec.input) == {i.name for i in target.info.inputs}


def test_common_bpm_jobs_carry_the_calling_package(proc, company, rid) -> None:
    """
    호출된 공통 BPM 안의 일감도 실행 신원이 바깥 패키지(`company1.s2.sc01`)다 — 일꾼은 그것으로
    업무(21)를 찾는다. 공통 작업 셋이 Case·분석·인계를 이 업무 규칙으로 해낸다.
    """
    calls = _Recorded(proc, origin="test")
    for fixture in ("P-v0", "P-v1", "P-v2"):
        doc_id = _send(proc, company, rid, fixture)
        assert _run(proc, rid, doc_id, calls) is State.DONE
    assert {pid for _, pid in calls.seen} == {"company1.s2.sc01"}
    assert [op for op, _ in calls.seen][-3:] == [
        "link_case",
        "analyze_case_impact",
        "hand_off_case_analysis",
    ]
    assert proc.get(rid)["handoff"]["next_node"] == "N03A"


class _EndedCenter:
    """
    Center 흉내 — 작업은 받지만 실행이 일감 전에 실패한다(2026-11-05 로컬 실측: 배포된 패키지에
    공통 BPM 사본이 없어 `call_target_missing`).
    """

    def __init__(self) -> None:
        from app.sc01.center import CenterConfig

        self.config = CenterConfig(url="http://center.test", integration_key="k")
        self.jobs: list[str] = []

    def start_job(self, inputs, **kw) -> dict:
        self.jobs.append(f"job_{len(self.jobs) + 1}")
        return {"job_id": self.jobs[-1]}

    def job(self, job_id: str) -> dict:
        return {"job_id": job_id, "state": "done", "run_status": "failed", "run_id": "run_x"}

    def run_events(self, run_id: str) -> list[dict]:
        message = "[Call_CaseIntake] 호출 대상이 패키지에 없다: platform.case-intake"
        return [
            {"kind": "run_started", "data": {}},
            {
                "kind": "node_state",
                "node_id": "Call_CaseIntake",
                "data": {
                    "state": "failed",
                    "error_code": "call_target_missing",
                    "message": message,
                },
            },
            {"kind": "run_finished", "data": {"status": "failed"}},
        ]

    def cancel_job(self, job_id: str) -> dict:
        return {}


def test_center_run_that_fails_before_any_job_is_recorded_with_its_reason(
    tmp_path, company
) -> None:
    """
    일감이 오기 전에 실패한 Center 실행 — 폴러가 작업 상태를 읽어 그 개정을 「실패」와 사유로
    남긴다.
    예전에는 알려 줄 일감이 없어 영영 「실행 중」이었다.
    """
    backend = build_sqlite_backend(str(tmp_path / "engine.sqlite"))
    center = _EndedCenter()
    proc = S2Sc01Process(build_sc01_store(backend, "s2sc01"), company=company, center=center)
    rid = f"s2-{uuid.uuid4().hex[:8]}"
    proc.create(rid, executor="center")
    doc_id = _send(proc, company, rid, "P-v0")
    run = proc.get(rid)["receipts"][doc_id]["run"]
    assert (run["state"], run["job_id"]) == ("running", "job_1")
    assert proc.get(rid)["bpm"]["state"] == "running"
    assert proc.poll_center() == 1
    doc = proc.get(rid)
    run = doc["receipts"][doc_id]["run"]
    assert run["state"] == "failed" and "call_target_missing" in run["problem"]
    assert doc["bpm"]["state"] == "idle" and doc["audit"][-1]["action"] == "center_run_failed"
    assert proc.poll_center() == 0  # 도는 실행이 없다
