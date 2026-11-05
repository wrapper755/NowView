"""
시나리오 2 장면 3 — 잔여 납기 위험의 경영검토와 대응 합의(`app/s2/sc03/`, `docs/s2/sc03.md`).

* 통합가상데이터 v0.3의 **파생 칸**(SC03대안비교의 필요량·대수·운송 가능량·추가비·출발·도착·여유·
  초과액·판정, SC03요약, SC03업무연결·결정인계·인계의 키와 시각)을 규칙 계산과 실행 결과로 다시 내서
  대조한다 — 숫자를 시험에 옮겨 적지 않는다.
* 구현명세 §4 인수시험 T01~T09.
* 진짜 BPM 엔진이 그림(`processes/s2-sc03.bpmn` + 공통 BPM `case-plan.bpmn`)을 돌고 서비스 태스크는
  C15 일꾼의 수행기를 지난다(Studio 흉내). 회사 시스템은 기간계 쌍둥이(`tests/company_twin/`)의
  운송 문의·근거 원천이다 — 근거는 시연이 보낸 세계 시각에 들어오고, 실행은 메시지 「사건근거」로
  깨운다.
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

from app import company as company_mod
from app.platform import catalog
from app.s2.sc01.process import S2Sc01Process
from app.s2.sc02.process import S2Sc02Process
from app.s2.sc03 import calc
from app.s2.sc03.process import S2Sc03Process
from app.s2.sc03.records import records_of
from app.sc01.center import CenterConfig, CenterError
from app.sc01.domain import DomainError, parse_at
from app.sc01.store import build_sc01_store
from app.store import build_sqlite_backend

SEED = Path(__file__).resolve().parents[1] / "seed" / "SYN-S2-SC03-v0.3.xlsx"
KST = calc.at("2026-11-05T00:00:00+09:00").tzinfo


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


def _at(object_id: str) -> str:
    """SC03업무연결의 그 객체 시각(KST ISO)."""
    return _kst(_by(_sheet("SC03업무연결"), "객체 ID")[object_id]["시각 KST"]).isoformat()


#: 각본 시각(SC03고객권한·SC03운송회신의 확인·수신 시각) — 시험이 근거를 그 시각에 보낸다
def _source_at(fixture: str) -> str:
    rows = {r["회신 ID"]: r["수신시각"] for r in _sheet("SC03운송회신")} | {
        r["근거 ID"]: r["확인 시각"] for r in _sheet("SC03고객권한")
    }
    return _kst(rows[fixture]).isoformat()


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
def proc(backend, company, sc02) -> S2Sc03Process:
    return S2Sc03Process(build_sc01_store(backend, "s2sc03"), company=company, sc02=sc02)


@pytest.fixture()
def handed(sc01, sc02, company) -> str:
    """장면 1·2를 Studio 흉내로 HAND-02까지 — 장면 3의 출발점."""
    rid = f"s2-{uuid.uuid4().hex[:8]}"
    sc01.create(rid, executor="studio")
    _scenario(sc01, company, rid)
    assert _sc02_base(sc02, company, rid) is State.DONE
    assert sc02.get(rid)["handoff"]["handoff_id"] == "HAND-02"
    return rid


def _clock(company, proc: S2Sc03Process, rid: str, at: str) -> None:
    company._call("POST", f"/worlds/{rid}/clock", {"at": at})
    proc.follow_clock(rid, at)


def _open(proc: S2Sc03Process, company, rid: str, case_id: str = "BASE") -> dict:
    _clock(company, proc.sc02, rid, _at("CP-S2-V2"))
    return proc.create(rid, case_id=case_id, executor="studio")


def _start(proc: S2Sc03Process, rid: str, calls: C15Calls | None = None) -> tuple[Engine, object]:
    run_id = new_run_id(test=True)
    engine = Engine()
    run = engine.start(
        proc.process,
        run_id=run_id,
        log=RunLog(run_id=run_id),
        env=RunEnv(services=calls or C15Calls(proc, origin="test"), processes=proc.processes),
        executor="studio",
        bpm_process_id="company1.s2.sc03",
        inputs={"데모실행ID": rid, "사건ID": "CASE-S2-01"},
        now=parse_at(proc.get(rid)["clock"]),
    )
    engine.run_until_blocked(run)
    return engine, run


def _send(company, proc, rid, fixture: str, at: str | None = None, **body) -> str:
    """근거 원천 하나를 그 시각에 보낸다 — 세계 따라가기처럼 장면 3에 넘긴다."""
    _clock(company, proc, rid, at or _source_at(fixture))
    got = company._call("POST", f"/worlds/{rid}/sim/case-sources", {"fixture_id": fixture, **body})
    proc.receive_source(rid, got["doc_id"])
    return got["source_id"]


def _deliver(engine: Engine, run, source_id: str) -> State:
    """Center가 기다리는 실행에 메시지를 넣는다(Studio 흉내)."""
    engine.deliver(run, "사건근거", payload={"근거ID": source_id})
    return engine.run_until_blocked(run)


def _pending(run) -> list[str]:
    return [p.node_id for p in run.pendings.values()]


def _answer(engine: Engine, run, node: str, answer: dict, by: str) -> State:
    [pending] = [p for p in run.pendings.values() if p.node_id == node]
    engine.answer(run, pending.request_id, answer, answered_by=by)
    return engine.run_until_blocked(run)


def _version(proc, rid) -> str:
    return proc.get(rid)["comparisons"][-1]["label"]


def _recommend(engine, run, proc, rid, choice: str = "ALT-EXP", by: str = "배정훈") -> State:
    answer = {"권고안": choice, "비교버전": _version(proc, rid), "권고사유": "고객 납기 우선 권고"}
    return _answer(engine, run, "Approve_Recommend", answer, by)


def _decide(
    engine, run, proc, rid, limit: str = "1200000", by: str = "권태윤", version: str | None = None
) -> State:
    answer = {
        "결정": "ALT-EXP",
        "결정비교버전": version or _version(proc, rid),
        "결정사유": "고객 약정을 비용 절감보다 우선",
        "결정한도": limit,
    }
    return _answer(engine, run, "Approve_Decision", answer, by)


def _accept(engine, run, by: str = "출하담당") -> State:
    answer = {"인수결정": "인수", "인수의견": "예약 유효시각 전 3대 확보"}
    return _answer(engine, run, "Approve_Accept", answer, by)


def _to_recommend(proc, company, rid, case_id: str = "BASE", **reply) -> tuple[Engine, object]:
    """D06 → D07 — 열고(대기), 고객 확인 09:22·운송 회신 09:23이 와서 비교까지."""
    _open(proc, company, rid, case_id)
    engine, run = _start(proc, rid)
    assert run.state is State.WAITING and _pending(run) == []
    for fixture in ("CUST-R-v1", "Q-R-v1"):
        sid = _send(
            company,
            proc,
            rid,
            fixture,
            **({"overrides": reply} if reply and fixture == "Q-R-v1" else {}),
        )
        _deliver(engine, run, sid)
    return engine, run


def _base(proc, company, rid) -> State:
    """D06 → D08 — 기본 시연(SC03업무연결의 시각에 사람 셋이 답한다)."""
    engine, run = _to_recommend(proc, company, rid)
    assert _pending(run) == ["Approve_Recommend"]
    _clock(company, proc, rid, _at("ESC-03"))
    assert _recommend(engine, run, proc, rid) is State.WAITING
    _clock(company, proc, rid, _at("DEC-03"))
    assert _decide(engine, run, proc, rid) is State.WAITING
    _clock(company, proc, rid, _at("ACT-03"))
    return _accept(engine, run)


# ─────────────────────────── 통합가상데이터 대조 ───────────────────────────


def test_v03_keeps_scenes_1_and_2_and_adds_scene_3(master: dict) -> None:
    """v0.3의 앞 15개 시트는 v0.2와 값이 같다(셀 대조, `docs/s2/sc03.md`) — 장면 1·2가 같은 파일."""
    wb = openpyxl.load_workbook(SEED, data_only=True)
    assert wb.sheetnames[14] == "SC02인계" and wb.sheetnames[15] == "SC03요약"
    assert master["dataset_version"] == "SYN-S2-SC03-v0.3"
    [reply] = [s for s in master["case_sources"] if s["kind"] == "transport_reply"]
    assert (reply["fixture_id"], reply["work_id"], reply["owner_role"]) == (
        "Q-R-v1",
        "W-TRAN-R",
        "H04",
    )
    [auth] = master["authority"]
    assert (auth["rule_id"], auth["limit"]) == ("AUTH-T1", 1_000_000)


def test_comparison_matches_the_alternatives_sheet(master: dict, proc, company, handed) -> None:
    """
    T04 · SC03대안비교 — 정기차 −30분·0원, 긴급 3대 +15분·120만원·20만원 초과, 분할 대안 없음. 판단
    시각은 결정 시각(DEC-03)이다(시트의 판정 식이 예약 유효시각을 그 시각과 견준다).
    """
    sources = {s["fixture_id"]: s for s in master["case_sources"]}
    reply = {**sources["Q-R-v1"], "source_id": "Q-R-v1", "received_at": _source_at("Q-R-v1")}
    customer = {**sources["CUST-R-v1"], "source_id": "CUST-R-v1"}
    regular = _open(proc, company, handed)["source"]["regular"]
    found = calc.compare(
        reply=reply,
        customer=customer,
        authority=master["authority"][0],
        regular=regular,
        judged_at=_at("DEC-03"),
    )
    verdict = {v: k for k, v in calc.VERDICT_LABEL.items()}
    rows = _by(found["alternatives"], "alternative_id")
    for row in _sheet("SC03대안비교"):
        a = rows[row["대안 ID"]]
        assert a["name"] == row["대안"]
        assert (a["need_qty"], a["trucks"], a["capacity"]) == (
            row["필요량"],
            row["긴급차 대수"],
            row["운송 가능량"],
        )
        assert a["extra_cost"] == row["추가비(원)"] and a["excess"] == row["초과액(원)"]
        assert parse_at(a["departure"]) == _kst(row["출발 예정"])
        assert parse_at(a["arrival"]) == _kst(row["도착 예정"])
        assert parse_at(a["promised_at"]) == _kst(row["약정"])
        assert a["margin_min"] == row["여유(분)"]
        assert a["verdict"] == verdict[row["판정"]]
    assert [a["alternative_id"] for a in found["alternatives"]] == ["ALT-REG", "ALT-EXP"]
    assert found["excluded"][0]["alternative"] == "분할 납품"
    assert found["faster_min"] == 45


def test_escalation_boundary_is_strictly_above_the_limit() -> None:
    """T05 — 한도와 같으면 금액만으로 재보고하지 않는다. 120만원이면 재보고."""
    assert calc.needs_escalation(1_000_000, 1_000_000) is False
    assert calc.needs_escalation(1_200_000, 1_000_000) is True
    assert calc.needs_escalation(None, 1_000_000) is None


# ─────────────────────────── 기본 시연 (진짜 엔진) ───────────────────────────


def test_base_flow_links_compares_escalates_decides_and_hands_off(
    proc, company, sc02, handed
) -> None:
    """
    T02·T08 · 기본 시연 — v2 적용(S·PROD-V2·APP-01 유지) → 원업무 연결(대기 → 09:23 회신 유효, 새
    문의 0건) → CMP-03 → 팀장 재보고 ESC-03(20만원 초과) → H05 전량 긴급 → H04 인수 → HAND-03. 끝 =
    SC03 결정인계·인계·요약.
    """
    assert _base(proc, company, handed) is State.DONE
    doc = proc.get(handed)
    assert doc["bpm"]["visited"] == [
        "Task_Propose",
        "Task_Check",
        "Task_ApplyPlan",
        "Task_Link",
        "Wait_Sources",
        "Task_Compare",
        "Approve_Recommend",
        "Record_Recommend",
        "Approve_Decision",
        "Record_Decision",
        "Approve_Accept",
        "Record_Accept",
        "End",
    ]
    plan = doc["plan"]
    assert [i["unit"] for i in plan["items"]] == ["U01", "U02", "U03", "U04", "U05", "U06", "U07"]
    u06, u07 = plan["items"][5:]
    assert (u06["link_mode"], u06["ref_work_id"], u06["ref_owner_role"]) == (
        "reference",
        "W-TRAN-R",
        "H04",
    )
    assert u07["activation"] == "conditional" and plan["u07_active"] is True
    assert parse_at(plan["applied_at"]) == parse_at(_at("CP-S2-V2"))
    link = doc["link"]
    assert link["new_inquiries"] == 0 and link["owner_role"] == "H04"
    assert [o["reply_state"] for o in link["observations"]] == ["WAITING", "WAITING", "VALID"]
    assert link["reserved"] is False  # 「가능」 회신은 예약 확정이 아니다
    # 연결·비교는 근거가 들어온 순간 자동이다 — 자료 09:18·09:25보다 앞설 수 있다(문서 「시각」)
    assert parse_at(link["linked_at"]) <= parse_at(_at("LINK-03"))
    [cmp] = doc["comparisons"]
    assert parse_at(cmp["compared_at"]) <= parse_at(_at("CMP-03"))
    assert cmp["basis"]["reply_id"] == "Q-R-v1" and cmp["basis"]["customer_id"] == "CUST-R-v1"
    [esc] = doc["recommendations"]
    assert (esc["result"], esc["excess"], esc["to_role"]) == ("ESCALATED", 200_000, "H05")
    assert parse_at(esc["recommended_at"]) == parse_at(_at("ESC-03"))
    [d] = doc["decisions"]
    sheet = _sheet("SC03결정인계")[0]
    assert d["decision_id"] == sheet["결정 ID"]
    basis = d["evidence"]["basis"]
    choice = (
        f"{d['selected']} / {calc.COMPARISON_ID} / {basis['reply_id']} / {basis['customer_id']}"
    )
    assert choice == sheet["선택 / 근거 버전"]
    assert d["decided_role"] == "H05" and parse_at(d["decided_at"]) == parse_at(_at("DEC-03"))
    assert d["limit"] == sheet["결정 한도(원)"]
    assert f"{d['executor_role']} / {doc['action']['action_id']}" == sheet["책임 / 과제"]
    assert parse_at(doc["action"]["accepted_at"]) == _kst(sheet["인수 시각"])
    assert parse_at(d["reservation_due"]) == _kst(sheet["예약 기한"])
    assert len(d["re_report_conditions"]) == 3 and d["re_report_to"] == "H05"
    assert d["actual"] == {"reserved_at": None, "accepted_at": None, "actual_cost": None}
    assert all(sheet[k] is None for k in ("예약확정시각", "실제 인수시각", "실제 비용(원)"))
    h = doc["handoff"]
    sheet = _sheet("SC03인계")[0]
    assert h["handoff_id"] == sheet["인계 ID"]
    assert f"{h['case_id']} / {h['commitment_id']}" == sheet["사건 / 약정"]
    assert f"{h['decision_id']} / {h['action_id']}" == sheet["결정·과제"]
    assert " · ".join(h["evidence"]) == sheet["당시 근거"]
    assert h["actual"] == {"reserved_at": None, "accepted_at": None, "actual_cost": None}
    assert h["observed"] == ["COM-S"]
    # 장면 2의 결과는 그대로다 — 생산계획 재승인 없음
    assert company.production_plan(handed)["version"] == "PROD-V2"
    assert [c["approval_id"] for c in sc02.get(handed)["confirmations"]] == ["APP-01"]
    board = next(r for r in records_of(doc, proc.master()) if r["kind"] == "dashboard")["body"]
    summary = {r["항목"]: r["값"] for r in _sheet("SC03요약")}
    s = board["summary"]
    assert s["regular_margin_min"] == summary["정기차 납기 여유"]
    assert s["express_margin_min"] == summary["긴급차 납기 여유"]
    assert s["express_extra_cost"] == summary["긴급차 추가비"]
    assert s["express_excess"] == summary["팀장 한도 초과"]
    assert s["decision"] == summary["H05 결정"] and s["action"] == summary["H04 과제"]
    assert float(board["kpi"]["otd"]) == summary["마감 OTD"]  # 견적·전망은 OTD에 합산하지 않는다


def test_t01_reentry_and_repeat_link_keep_one_reference(proc, company, handed) -> None:
    """T01 — 같은 HAND-02로 다시 열어도 같은 문서, 같은 문의를 두 번 이어도 링크 하나·새 문의 0."""
    doc = _open(proc, company, handed)
    assert proc.create(handed)["created_at"] == doc["created_at"]
    engine, run = _start(proc, handed)
    rid_run = proc.get(handed)["bpm"]["external_run_id"]
    proc.operate(
        handed,
        "link_transport_work",
        {"demo_run_id": handed},
        external_run_id=rid_run,
        via="studio",
    )
    link = proc.get(handed)["link"]
    assert link["link_id"] == "LINK-03" and link["new_inquiries"] == 0
    assert len(link["observations"]) == 1  # 같은 상태는 한 번만 관측으로 남긴다
    inquiry = company.shipping_inquiry(handed, "W-TRAN-R")
    assert inquiry["owner_role"] == "H04" and inquiry["state"] == "IN_PROGRESS"


def test_t01_new_inquiry_beside_the_open_one_is_blocked(proc, company, handed) -> None:
    """Y01 — 진행 중인 원업무가 있는데 새 문의를 제안하면 차단, v1 유지·연결 없음."""
    _open(proc, company, handed, "PLAN-DUP-INQUIRY")
    engine, run = _start(proc, handed)
    assert run.state is State.DONE
    doc = proc.get(handed)
    assert doc["plan"]["state"] == "BLOCKED"
    assert {i["rule"] for i in doc["plan"]["check"]["issues"]} == {"duplicate"}
    assert doc["link"] is None and doc["bpm"]["visited"][-1] == "End_PlanBlocked"


def test_t03_two_trucks_cannot_be_recommended_and_a_refresh_waits_for_a_new_reply(
    proc, company, handed
) -> None:
    """
    T03 — 가용 2대면 전량 불가(조건 재확인): 권고하면 서버가 거절해 같은 결재로. 갱신 요청하면 같은
    근거로는 다시 비교하지 않고 새 회신(3대)을 기다린다.
    """
    engine, run = _to_recommend(proc, company, handed, vehicles=2)
    [cmp] = proc.get(handed)["comparisons"]
    exp = calc.alternative(cmp, "ALT-EXP")
    assert (exp["verdict"], exp["capacity"]) == (calc.RECHECK, 160)
    assert _recommend(engine, run, proc, handed) is State.WAITING
    assert _pending(run) == ["Approve_Recommend"] and proc.get(handed)["recommendations"] == []
    assert _recommend(engine, run, proc, handed, "갱신요청") is State.WAITING
    doc = proc.get(handed)
    assert _pending(run) == [] and doc["bpm"]["waiting"][0]["node_id"] == "Wait_Sources"
    sid = _send(company, proc, handed, "Q-R-v1", source_id="Q-R-v2")
    _deliver(engine, run, sid)
    doc = proc.get(handed)
    assert [c["label"] for c in doc["comparisons"]] == ["CMP-03 v1", "CMP-03 v2"]
    assert doc["comparisons"][0]["state"] == "REFRESH_REQUESTED"  # 과거 판은 남는다
    assert calc.alternative(doc["comparisons"][1], "ALT-EXP")["verdict"] == calc.ESCALATE


def test_t03_expired_reply_is_not_used_to_decide(proc, company, handed) -> None:
    """T03 — 예약 유효시각(12:00)에 닿으면 기존 견적으로 권고·확정하지 않는다."""
    engine, run = _to_recommend(proc, company, handed)
    _clock(company, proc, handed, "2026-11-04T12:00:00+09:00")
    assert _recommend(engine, run, proc, handed) is State.WAITING
    assert proc.get(handed)["recommendations"] == []
    assert (
        calc.reply_state({"valid_until": "2026-11-04T12:00:00+09:00"}, "2026-11-04T12:00:00+09:00")
        == calc.EXPIRED
    )


def test_t05_exactly_the_limit_stays_with_the_team_lead(proc, company, handed) -> None:
    """T05 — 4대 × 60세트 × 25만원 = 정확히 100만원 → 재보고 없이 팀장 전결 범위로 끝."""
    engine, run = _to_recommend(
        proc, company, handed, vehicles=4, sets_per_vehicle=60, extra_cost_per_vehicle=250_000
    )
    exp = calc.alternative(proc.get(handed)["comparisons"][-1], "ALT-EXP")
    assert (exp["extra_cost"], exp["excess"], exp["verdict"]) == (1_000_000, 0, calc.WITHIN)
    assert _recommend(engine, run, proc, handed) is State.DONE
    doc = proc.get(handed)
    assert doc["recommendations"][0]["result"] == "WITHIN_AUTHORITY"
    assert doc["decisions"] == [] and doc["action"] is None and doc["plan"]["u07_active"] is False
    assert doc["bpm"]["visited"][-1] == "End_WithinAuthority"


def test_t06_new_quote_after_escalation_blocks_the_old_comparison(proc, company, handed) -> None:
    """
    T06 — 재보고 뒤 운임이 바뀐 새 회신이 오면 이전 비교로는 결정하지 않는다. 다시 연결·비교(v2) →
    재보고(v2) → 결정. 과거 근거는 보존한다.
    """
    engine, run = _to_recommend(proc, company, handed)
    assert _recommend(engine, run, proc, handed) is State.WAITING
    old = _version(proc, handed)
    _send(
        company,
        proc,
        handed,
        "Q-R-v1",
        "2026-11-04T09:30:00+09:00",
        source_id="Q-R-v2",
        overrides={"extra_cost_per_vehicle": 450_000},
    )
    assert _decide(engine, run, proc, handed, version=old) is State.WAITING
    doc = proc.get(handed)
    assert doc["decisions"] == [] and doc["recommendations"][0]["state"] == "STALE"
    assert _pending(run) == ["Approve_Recommend"]
    assert [c["label"] for c in doc["comparisons"]] == ["CMP-03 v1", "CMP-03 v2"]
    assert _recommend(engine, run, proc, handed) is State.WAITING
    esc = proc.get(handed)["recommendations"][-1]
    assert (esc["extra_cost"], esc["excess"]) == (1_350_000, 350_000)
    assert _decide(engine, run, proc, handed, limit="1350000") is State.WAITING
    d = proc.get(handed)["decisions"][-1]
    assert d["comparison"] == "CMP-03 v2" and d["evidence"]["basis"]["reply_id"] == "Q-R-v2"


def test_t07_only_h05_decides_and_a_resend_returns_the_same_decision(proc, company, handed) -> None:
    """T07 — 비권한 결정은 서버가 거절(같은 결재로). 정상 결정·과제 1건, 재전송은 같은 DEC-03."""
    engine, run = _to_recommend(proc, company, handed)
    _recommend(engine, run, proc, handed)
    assert _decide(engine, run, proc, handed, by="배정훈") is State.WAITING
    assert _pending(run) == ["Approve_Decision"] and proc.get(handed)["decisions"] == []
    assert _decide(engine, run, proc, handed, limit="1,000,000") is State.WAITING  # 한도 < 추가비
    assert proc.get(handed)["decisions"] == []
    assert _decide(engine, run, proc, handed) is State.WAITING
    doc = proc.get(handed)
    args = {
        "demo_run_id": handed,
        "version": doc["comparisons"][-1]["label"],
        "decision": "ALT-EXP",
        "reason": "다시 누름",
        "limit": "1200000",
        "answered_by": "권태윤",
    }
    run_id = doc["bpm"]["external_run_id"]
    again = proc.operate(
        handed, "record_transport_decision", args, external_run_id=run_id, via="studio"
    )
    doc = proc.get(handed)
    assert again["decision_id"] == "DEC-03" and len(doc["decisions"]) == 1
    assert doc["action"]["action_id"] == "ACT-03"


def test_t08_requery_after_acceptance_keeps_one_handoff(proc, company, handed) -> None:
    """T08 — 인수 뒤 다시 와도 HAND-03 한 건. 예약·실제 인수·집행비 null, S 관찰·OTD 그대로."""
    assert _base(proc, company, handed) is State.DONE
    doc = proc.get(handed)
    args = {"demo_run_id": handed, "decision": "인수", "answered_by": "출하담당"}
    again = proc.operate(
        handed,
        "accept_transport_action",
        args,
        external_run_id=doc["bpm"]["external_run_id"],
        via="studio",
    )
    assert again["handoff_id"] == "HAND-03"
    after = proc.get(handed)
    assert after["handoff"] == doc["handoff"]
    board = next(r for r in records_of(after, proc.master()) if r["kind"] == "dashboard")["body"]
    assert board["kpi"]["otd"] == "0.9900"


@pytest.mark.parametrize(
    ("overrides", "rule"),
    [
        ({"vehicles": 2}, "vehicles"),
        ({"extra_cost_per_vehicle": 450_000}, "cost"),
        ({"arrival": "2026-11-05T18:45:00+09:00"}, "arrival"),
    ],
)
def test_t09_changes_after_acceptance_ask_for_a_re_report(
    proc, company, handed, overrides, rule
) -> None:
    """T09 — 인수 뒤 3대 미확보·한도 초과·약정 이후 도착 전망이면 H05 재보고(집행·종료 없음)."""
    assert _base(proc, company, handed) is State.DONE
    before = proc.get(handed)
    _send(
        company,
        proc,
        handed,
        "Q-R-v1",
        "2026-11-04T10:30:00+09:00",
        source_id="Q-R-v2",
        overrides=overrides,
    )
    doc = proc.get(handed)
    [rr] = doc["re_reports"]
    assert [t["rule"] for t in rr["triggers"]] == [rule]
    assert (rr["to_role"], rr["state"]) == ("H05", "REPORT_REQUIRED")
    assert doc["action"]["state"] == "ACCEPTED" and doc["action"]["re_report_required"] is True
    assert doc["handoff"] == before["handoff"] and doc["decisions"] == before["decisions"]


# ─────────────────────────── 경계 ───────────────────────────


def test_scene_3_needs_the_scene_2_handoff(proc, sc01, sc02, company) -> None:
    rid = f"s2-{uuid.uuid4().hex[:8]}"
    sc01.create(rid, executor="studio")
    _scenario(sc01, company, rid)
    sc02.create(rid, executor="studio")
    with pytest.raises(DomainError) as no:
        proc.create(rid, executor="studio")
    assert no.value.status == 409


def test_compare_before_the_reply_is_refused(proc, company, handed) -> None:
    _open(proc, company, handed)
    _start(proc, handed)
    doc = proc.get(handed)
    with pytest.raises(DomainError) as early:
        proc.operate(
            handed,
            "compare_transport_options",
            {"demo_run_id": handed},
            external_run_id=doc["bpm"]["external_run_id"],
            via="studio",
        )
    assert early.value.status == 409


def test_other_run_and_other_place_are_refused(proc, company, handed) -> None:
    _open(proc, company, handed)
    args = {"demo_run_id": handed, "case_id": "CASE-S2-01"}
    proc.operate(handed, "propose_case_plan", args, external_run_id="run-a", via="studio")
    with pytest.raises(DomainError) as other:
        proc.operate(handed, "check_case_plan", args, external_run_id="run-b", via="studio")
    assert other.value.status == 409
    with pytest.raises(DomainError) as place:
        proc.operate(handed, "check_case_plan", args, external_run_id="run-a", via="center")
    assert place.value.status == 409


def test_extension_definition_matches_the_bpmn_service_calls() -> None:
    """
    확장 `external` 0.11.0 — 업무 그림과 공통 BPM `platform.case-plan`의 서비스 호출이 정의의
    입력·출력과 맞고, 결재 담당자가 역할 배정(H03·H05·H04)과 같고, 기록 작업마다 오류 경계가 있다.
    """
    import json

    from chaeksas.contracts import extension as ext
    from chaeksas.contracts.bpmn_ext import read_process

    from app.s2.sc03.process import CALLED_PATHS, OPERATIONS, PROCESS_PATH

    raw = (
        Path(__file__).resolve().parents[2] / "chaeksas" / "external.extension.json"
    ).read_bytes()
    manifest = ext.ExtensionManifest.model_validate(json.loads(raw))
    assert ext.validate(manifest, from_center=True) == []
    assert manifest.version == "0.11.0"
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
    [need] = [n for n in process.info.extensions if n.id == manifest.id]
    assert need.version.startswith(">=0.11.0")
    assert used == list(OPERATIONS)
    holders = {
        "Approve_Recommend": catalog.HOLDERS["H03"],
        "Approve_Decision": catalog.HOLDERS["H05"],
        "Approve_Accept": catalog.HOLDERS["H04"],
    }
    assert {n.id: n.prop("approval").assignees for n in process.of_kind("userTask")} == holders
    boundaries = [n for n in process.all_nodes() if n.kind == "boundaryEvent"]
    assert [b.attached_to for b in boundaries] == [
        "Record_Recommend",
        "Record_Decision",
        "Record_Accept",
    ]
    # 공통 BPM 안에는 결재가 없다 — 서버 실행기는 호출 활동 안의 결재를 올리지 않는다
    assert [n.id for p in called.values() for n in p.of_kind("userTask")] == []


def test_common_bpm_jobs_carry_the_calling_package(proc, company, handed) -> None:
    """공통 BPM `platform.case-plan` 안의 일감도 실행 신원이 바깥 패키지(`company1.s2.sc03`)다."""
    seen: list[tuple[str, str | None]] = []

    class _Recorded(C15Calls):
        def call(self, request):
            seen.append((request.operation, request.bpm_process_id))
            return super().call(request)

    _open(proc, company, handed)
    _start(proc, handed, _Recorded(proc, origin="test"))
    assert {pid for _, pid in seen} == {"company1.s2.sc03"}
    assert [op for op, _ in seen] == [
        "propose_case_plan",
        "check_case_plan",
        "apply_case_plan",
        "link_transport_work",
    ]


def test_every_written_version_matches_the_common_record_schemas(proc, company, handed) -> None:
    """
    공통 기록 종류(`docs/records/s2/sc03/`) — 기본 시연의 모든 판이 봉투·종류별 스키마를 통과하고,
    사이트 예시가 최신이다(다시 뽑기 `NOWVIEW_WRITE_RECORD_SCHEMAS=1`·`…_EXAMPLES=1`).
    """
    from records_contract import check, every_version, example

    from app.s2.sc03.records import KINDS

    assert _base(proc, company, handed) is State.DONE
    versions = every_version(company, handed, 3)
    assert len(versions) > 10
    assert check(3, KINDS, versions, "s2/sc03") == []
    assert example(company, handed, 3, "s2/sc03") == []
    kinds = {r["kind"] for r in company.records(handed, scene=3)}
    assert "case" not in kinds  # Case 기록은 장면 1 문서의 것이다


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
    company, backend, sc02, handed
) -> None:
    """
    Center 실행 — 근거가 오면 「사건근거」 메시지로 기다리는 실행을 깨운다. 실행이 아직 대기에 닿지
    않아 Center가 거절하면(`no_receiver`) 폴러가 다시 보낸다.
    """
    center = _Center()
    proc = S2Sc03Process(
        build_sc01_store(backend, "s2sc03"), company=company, sc02=sc02, center=center
    )
    _clock(company, sc02, handed, _at("CP-S2-V2"))
    doc = proc.create(handed)
    assert doc["bpm"]["job_id"] == "job_1" and doc["bpm"]["state"] == "running"
    args = {"demo_run_id": handed, "case_id": "CASE-S2-01"}
    for op in ("propose_case_plan", "check_case_plan", "apply_case_plan", "link_transport_work"):
        out = proc.operate(handed, op, args, external_run_id="run_c", via="center")
    assert out["ready"] is False
    _send(company, proc, handed, "CUST-R-v1")
    assert center.messages == [] and proc.get(handed)["wait"]["message_pending"] is True
    assert proc.poll_center() == 1
    assert center.messages == [
        {"name": "사건근거", "correlation": handed, "payload": {"근거ID": "CUST-R-v1"}}
    ]
    assert proc.get(handed)["wait"]["message_pending"] is False
    assert proc.poll_center() == 0


def test_follower_opens_scene_3_and_passes_new_sources(
    monkeypatch, company, backend, sc01, sc02
) -> None:
    """
    사이트가 시나리오 2 회차에 「장면 열기」(장면 3)를 남기면 장면 3 문서를 연다. 기간계에 새 근거가
    들어오면 장면 3에 넘긴다. 「장면 3부터 다시」면 장면 3 문서를 거둔다.
    """
    from app.follower import Follower

    monkeypatch.delenv("NOWVIEW_TEST_INPUTS", raising=False)
    s3 = S2Sc03Process(build_sc01_store(backend, "s2sc03"), company=company, sc02=sc02)
    rid = f"demo-{uuid.uuid4().hex[:8]}"
    company._call("POST", "/worlds", {"world_id": rid, "origin": "site", "scenario_id": "s2"})
    f = Follower(company, {}, s2=sc01, s2_scenes={2: sc02, 3: s3})
    f._follow(company.world(rid))
    with sc01._lock(rid):  # 장면 1을 인계까지(엔진 시험 — Studio로 바꿔 진행)
        d, v = sc01._load(rid)
        d["executor"] = "studio"
        sc01.store.save(rid, d, v, "studio")
    _scenario(sc01, company, rid)
    assert _sc02_base(sc02, company, rid) is State.DONE
    company._call(
        "POST",
        f"/worlds/{rid}/commands",
        {"scene": 3, "kind": "open", "actor": "u-prod-lead", "body": {}, "ref": f"{rid}:open3"},
    )
    f._follow(company.world(rid))
    [cmd] = company.commands(rid, None)
    assert cmd["state"] == "DONE", cmd
    doc = s3.get(rid)
    assert doc["source"]["handoff"]["handoff_id"] == "HAND-02"
    assert "Center 연동이 설정되지 않았다" in doc["bpm"]["problem"]
    got = company._call("POST", f"/worlds/{rid}/sim/case-sources", {"fixture_id": "CUST-R-v1"})
    f._follow(company.world(rid))
    assert s3.get(rid)["sources_seen"] == [got["doc_id"]]
    company._call(
        "POST",
        f"/worlds/{rid}/commands",
        {"scene": 3, "kind": "rewind", "actor": "u-demo", "body": {"scene": 3}, "ref": f"{rid}:rw"},
    )
    f._follow(company.world(rid))
    assert s3.store.load(rid) is None and sc02.store.load(rid) is not None


def test_dashboard_shows_scene_3_metrics_for_a_scenario_2_world(
    proc, sc01, sc02, company, handed, tmp_path
) -> None:
    """회사 대시보드 — 시나리오 2 회차의 업무 23 카드에 SC03요약의 숫자와 결재 진행."""
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
            settings, None, None, None, {"company1": _System()}, {21: sc01, 22: sc02, 23: proc}
        )
    )
    body = TestClient(app).get("/companies/company1/dashboard").json()
    works = {w["scene"]: w for w in body["works"]}
    w = works[23]
    assert (w["work"], w["state"]) == ("잔여 납기 위험의 경영검토와 대응 합의", "done")
    assert w["progress"] == {"approvals": 3, "passed": 3}
    assert [m["value"] for m in w["metrics"]] == [
        "-30분",
        "+15분",
        "1200000",
        "200000",
        "전량 긴급 운송",
        "인수",
    ]
