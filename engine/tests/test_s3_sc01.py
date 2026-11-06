"""
시나리오 3 장면 1 — 결산조정 업무 착수(`app/s3/sc01/`, `docs/s3/sc01.md`).

* 입력자료 명세 및 대표 사건 v0.1의 **입력 7개 시트**만 읽고(설계안내·입력명세·대표사건·검수기준은
  읽지 않는다), 구현명세 §1의 정상 표본 수치(E2 개시일·기계상 1,150·채권 6,458.799691 = 원장·
  100 − 20 = 80·16분기·PLAN-A-26 3회 × 20 = 60 = CONF-26-F)를 점검 결과로 다시 낸다.
* 구현명세 §3 인수시험 01~08. 예외 표본은 기간계의 입력 변형(`s3.VARIANTS`)으로 낸다 — 자료 담당자가
  입력을 다시 연결한 새 버전이다.
* 진짜 BPM 엔진이 그림(`processes/s3-sc01.bpmn`)을 돌고 서비스 태스크는 C15 일꾼의 수행기를 지난다
  (Studio 흉내). 회계담당자의 「점검 실행」 둘은 결재 답이다. 회사 시스템은 기간계 쌍둥이다.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import openpyxl
import pytest
from chaeksas.core.engine import Engine, RunEnv, State, new_run_id
from chaeksas.core.run_log import RunLog
from conftest import C15Calls

from app import company as company_mod
from app.s3.sc01 import calc
from app.s3.sc01.process import S3Sc01Process
from app.s3.sc01.records import dashboard
from app.sc01.domain import DomainError, parse_at
from app.sc01.store import build_sc01_store
from app.store import build_sqlite_backend

SEED = Path(__file__).resolve().parents[1] / "seed" / "S3-INPUT-v0.1.xlsx"
OWNER = "회계담당"
S0 = "2027-01-04T09:00:00+09:00"


@pytest.fixture()
def company():
    return company_mod.default_client()


@pytest.fixture()
def master(company) -> dict:
    return company.s3_master()


@pytest.fixture()
def backend(tmp_path):
    return build_sqlite_backend(str(tmp_path / "engine.sqlite"))


@pytest.fixture()
def proc(backend, company) -> S3Sc01Process:
    return S3Sc01Process(build_sc01_store(backend, "s3sc01"), company=company)


@pytest.fixture()
def rid(proc) -> str:
    rid = f"s3-{uuid.uuid4().hex[:8]}"
    proc.create(rid, executor="studio")
    return rid


def _start(proc: S3Sc01Process, rid: str) -> tuple[Engine, object]:
    run_id = new_run_id(test=True)
    engine = Engine()
    run = engine.start(
        proc.process,
        run_id=run_id,
        log=RunLog(run_id=run_id),
        env=RunEnv(services=C15Calls(proc, origin="test"), processes=proc.processes),
        executor="studio",
        bpm_process_id="company1.s3.sc01",
        inputs={"데모실행ID": rid, "결산건ID": "S3-CLOSE-01"},
        now=parse_at(proc.get(rid)["clock"]),
    )
    engine.run_until_blocked(run)
    return engine, run


def _pending(run) -> list[str]:
    return [p.node_id for p in run.pendings.values()]


FIELDS = {
    "Check_Depreciation": ("상각점검버전", "상각점검"),
    "Check_Allowance": ("충당점검버전", "충당점검"),
}


def _check(engine, run, proc, rid, node: str, by: str = OWNER, version: str | None = None):
    """회계담당자의 「점검 실행」 — 본 입력 버전은 화면이 보인 지금 버전이다."""
    [pending] = [p for p in run.pendings.values() if p.node_id == node]
    ver, decision = FIELDS[node]
    answer = {ver: version or proc.get(rid)["current_version"], decision: "점검 실행"}
    engine.answer(run, pending.request_id, answer, answered_by=by)
    return engine.run_until_blocked(run)


def _relink(proc, company, rid, *variants: str) -> str:
    """자료 담당자가 입력을 다시 연결했다 — 세계 따라가기처럼 장면에 넘긴다. 새 버전 id."""
    got = company.link_close_inputs(rid, list(variants))
    proc.receive_inputs(rid)
    return got["version"]


def _deliver(engine, run, version: str) -> State:
    engine.deliver(run, "결산자료보완", payload={"입력버전": version})
    return engine.run_until_blocked(run)


def _states(proc, rid) -> dict[str, str]:
    return {k: v["state"] for k, v in proc.get(rid)["items"].items()}


def _board(proc, rid) -> dict:
    return dashboard(proc.get(rid))


def _base(proc, rid) -> tuple[Engine, object]:
    engine, run = _start(proc, rid)
    assert _pending(run) == ["Check_Depreciation"]
    assert _check(engine, run, proc, rid, "Check_Depreciation") is State.WAITING
    assert _check(engine, run, proc, rid, "Check_Allowance") is State.DONE
    return engine, run


# ─────────────────────────── 입력자료 ───────────────────────────


def test_master_reads_only_the_seven_input_sheets(master: dict) -> None:
    """구현명세 §1 — 입력 허용목록 7개. 설계·기대값 시트는 회사 자료에 싣지 않는다."""
    wb = openpyxl.load_workbook(SEED, data_only=True)
    assert wb.sheetnames[:4] == ["설계안내", "입력명세", "대표사건", "검수기준"]
    assert master["allowed_sheets"] == wb.sheetnames[4:]
    assert set(master["sheets"]) == set(master["allowed_sheets"])
    assert master["excluded_sheets"] == wb.sheetnames[:4]
    assert [i["item_id"] for i in master["close"]["items"]] == ["DEP", "ALW"]
    assert master["units"]["전이율원천"] == "원" and master["units"]["채권명세"] == "백만원"


def test_normal_sample_values_come_out_of_the_checks(company, master, rid) -> None:
    """정상 표본(IN-26-01) — 구현명세 §1의 수치를 점검·근거가 다시 낸다(옮겨 적지 않는다)."""
    [summary] = company.close_inputs(rid)
    assert summary["version"] == "IN-26-01" and summary["registered_at"] == S0
    v = company.close_input(rid, "IN-26-01")
    dep = calc.evidence(v, "DEP")
    assert dep["new_assets"] == [
        {"asset_id": "E2", "kind": "설비", "acquired": 2000, "in_service": "2026-07-01"}
    ]
    assert dep["booked_depreciation"] == 1150
    alw = calc.evidence(v, "ALW")
    assert alw["receivables"]["current_total"] == "6458.799691"
    assert alw["ledger"]["2026-12-31 외상매출금"] == 6458.799691
    assert (alw["rates"]["quarters"], alw["rates"]["unit"]) == (16, "원")
    assert alw["plan"]["current"] == "PLAN-A-26"
    assert [r["amount"] for r in alw["plan"]["rounds"]] == [20, 20, 20]
    found = {c["check_id"]: c for c in calc.check_item(v, master, "ALW")}
    assert found["ALW-03"]["actual"].endswith("차이 0원")
    assert found["ALW-04"]["actual"] == "100 − 20 → 조정 전 80"
    assert found["ALW-08"]["actual"] == "CONF-26-F 근거 PLAN-A-26 · 확인액 60백만원"
    for item in calc.ITEMS:
        assert calc.verdict(calc.check_item(v, master, item)) == calc.READY


# ─────────────────────────── 인수시험 01~08 ───────────────────────────


def test_t01_reentry_opens_the_same_two_works_and_no_approval(proc, company, rid) -> None:
    """01 — 같은 결산 건을 다시 열어도 같은 두 원업무다. 중복 업무·결재 생성 0건."""
    first = proc.get(rid)
    again = proc.create(rid, executor="studio")
    assert again["center_epoch"] == first["center_epoch"]
    assert [i["work_id"] for i in again["items"].values()] == ["W-S3-DEP", "W-S3-ALW"]
    assert {i["owner_name"] for i in again["items"].values()} == {OWNER}
    board = _board(proc, rid)
    assert (board["ready"], board["approved"], board["reports"]) == (
        {"done": 0, "of": 2},
        {"done": 0, "of": 2},
        0,
    )
    assert {r["kind"] for r in company.records(rid)} >= {"scene", "close_case", "close_item"}
    assert not [r for r in company.records(rid) if r["kind"] in ("input_check", "fix_request")]


def test_t02_normal_flow_goes_0_1_2_of_2_and_hands_off(proc, company, rid) -> None:
    """02 — 감가상각비 점검 후 충당금 점검. 준비 0/2 → 1/2 → 2/2, 승인 0/2·상신 0건, 장면 2 인계."""
    engine, run = _start(proc, rid)
    assert _board(proc, rid)["ready"]["done"] == 0
    assert _check(engine, run, proc, rid, "Check_Depreciation") is State.WAITING
    assert _board(proc, rid)["ready"]["done"] == 1 and _pending(run) == ["Check_Allowance"]
    assert _check(engine, run, proc, rid, "Check_Allowance") is State.DONE
    doc = proc.get(rid)
    board = dashboard(doc)
    assert board["ready"] == {"done": 2, "of": 2} and board["needs_fix"] == 0
    assert (board["approved"]["done"], board["reports"]) == (0, 0)
    assert [r["next_action"] for r in board["rows"]] == [
        "자산대장 점검 결과 보기",
        "분석 지시 보기",
    ]
    h = doc["handoff"]
    assert (h["handoff_id"], h["input_version"], h["approvals"], h["reports"]) == (
        "HAND-S3-01",
        "IN-26-01",
        0,
        0,
    )
    assert h["allowed_sheets"] == company.s3_master()["allowed_sheets"]
    [alw] = [i for i in h["items"] if i["item_id"] == "ALW"]
    assert {"PLAN-A-26", "CONF-26-S", "CONF-26-F"} <= set(alw["evidence_refs"])
    assert doc["bpm"]["state"] == "done" and doc["bpm"]["visited"][-1] == "End"
    assert all(i["started_at"] == S0 for i in doc["items"].values())


def test_t03_missing_e2_start_blocks_only_depreciation(proc, company, rid) -> None:
    """03 — E2 개시일 누락: 감가상각비에 E2·사용개시일·자산담당. 충당금은 정상 점검 가능."""
    v2 = _relink(proc, company, rid, "E2-START-MISSING")
    engine, run = _start(proc, rid)
    assert _check(engine, run, proc, rid, "Check_Depreciation") is State.WAITING
    assert _states(proc, rid)["DEP"] == "NEEDS_FIX" and _pending(run) == ["Check_Allowance"]
    [fix] = proc.get(rid)["fixes"]
    assert (fix["version"], fix["owners"], fix["state"]) == (v2, ["자산담당"], "OPEN")
    assert {(f["ref"], f["sheet"]) for f in fix["findings"]} == {("E2", "자산대장")}
    assert any("사용개시일" in f["actual"] for f in fix["findings"])
    assert fix["due"] == "2027-01-05T18:00:00+09:00"
    assert _check(engine, run, proc, rid, "Check_Allowance") is State.WAITING
    assert _states(proc, rid) == {"DEP": "NEEDS_FIX", "ALW": "READY"}
    assert _pending(run) == [] and proc.get(rid)["bpm"]["waiting"][0]["node_id"] == "Wait_Fix"
    v3 = _relink(proc, company, rid)  # 자산담당이 보완 — 정상 원천으로 다시 연결
    assert proc.get(rid)["wait"]["message_pending"] is False  # Studio는 시험이 넣는다
    assert _deliver(engine, run, v3) is State.WAITING and _pending(run) == ["Check_Depreciation"]
    assert _check(engine, run, proc, rid, "Check_Depreciation") is State.DONE
    doc = proc.get(rid)
    assert doc["fixes"][0]["state"] == "RESOLVED" and doc["fixes"][0]["closed_by_version"] == v3
    assert doc["handoff"]["input_version"] == v3


def test_t04_missing_accounting_record_blocks_only_the_allowance(proc, company, rid) -> None:
    """04 — 영업 확인은 있고 CONF-26-F 없음: 충당금만 보완(회계), 준비 1/2. 보완 후 재점검 2/2."""
    _relink(proc, company, rid, "CONF-F-MISSING")
    engine, run = _start(proc, rid)
    _check(engine, run, proc, rid, "Check_Depreciation")
    _check(engine, run, proc, rid, "Check_Allowance")
    board = _board(proc, rid)
    assert board["ready"]["done"] == 1 and board["needs_fix"] == 1
    [fix] = proc.get(rid)["fixes"]
    assert fix["owners"] == ["회계담당"]
    [finding] = fix["findings"]
    assert (finding["check_id"], finding["actual"]) == ("ALW-08", "회계 평가 기록 없음")
    check = proc.get(rid)["checks"][-1]
    assert next(c for c in check["checks"] if c["check_id"] == "ALW-07")["verdict"] == "PASS"
    fixed = _relink(proc, company, rid)
    assert _states(proc, rid)["DEP"] == "READY"  # 감가상각비 자료는 그대로 — 재점검 아님
    assert _deliver(engine, run, fixed) is State.WAITING and _pending(run) == ["Check_Allowance"]
    assert _check(engine, run, proc, rid, "Check_Allowance") is State.DONE
    assert _board(proc, rid)["ready"]["done"] == 2


@pytest.mark.parametrize(
    ("variant", "failed"),
    [("CONF-PRIOR-PLAN", {"ALW-08"}), ("PLAN-DUP-ROUND", {"ALW-06", "ALW-08"})],
)
def test_t05_version_or_round_mix_holds_the_allowance(proc, company, rid, variant, failed) -> None:
    """05 — 당기 확인을 전기 계획에 연결·회차 중복: 문제 버전·회차를 보이고 충당금 준비 보류."""
    _relink(proc, company, rid, variant)
    engine, run = _start(proc, rid)
    _check(engine, run, proc, rid, "Check_Depreciation")
    _check(engine, run, proc, rid, "Check_Allowance")
    assert _states(proc, rid) == {"DEP": "READY", "ALW": "NEEDS_FIX"}
    check = proc.get(rid)["checks"][-1]
    assert {c["check_id"] for c in check["checks"] if c["verdict"] == "FAIL"} == failed
    plan = next(c for c in check["checks"] if c["check_id"] == "ALW-06")
    if variant == "PLAN-DUP-ROUND":
        assert "회차 2 중복" in plan["actual"]  # 중복 회차를 합산하지 않는다(80이 아니다)
    else:
        f = next(c for c in check["checks"] if c["check_id"] == "ALW-08")
        assert "PLAN-A-25" in f["actual"]


@pytest.mark.parametrize(
    ("variant", "failed", "dep"),
    [
        ("LEDGER-1WON", {"ALW-03"}, "READY"),
        ("RATE-UNIT-MILLION", {"C-03", "ALW-05"}, "READY"),
    ],
)
def test_t06_one_won_and_unit_errors_are_caught_before_rounding(
    proc, company, rid, variant, failed, dep
) -> None:
    """06 — 1원 차이·전이율원천 백만원 단위: 표시 반올림 전 차이를 탐지, 그 항목만 보완."""
    _relink(proc, company, rid, variant)
    engine, run = _start(proc, rid)
    _check(engine, run, proc, rid, "Check_Depreciation")
    _check(engine, run, proc, rid, "Check_Allowance")
    assert _states(proc, rid) == {"DEP": dep, "ALW": "NEEDS_FIX"}
    check = proc.get(rid)["checks"][-1]
    bad = {c["check_id"]: c for c in check["checks"] if c["verdict"] == "FAIL"}
    assert set(bad) == failed
    if variant == "LEDGER-1WON":
        assert bad["ALW-03"]["actual"].endswith("차이 -1원")
        assert bad["ALW-03"]["owner_role"] == "채권담당"
    else:
        assert bad["ALW-05"]["sheet"] == "전이율원천"


def test_t07_replaced_assets_recheck_depreciation_and_old_answers_cannot_overwrite(
    proc, company, rid
) -> None:
    """
    07 — 준비 뒤 자산자료만 교체: 상각비 재점검. 이전 버전의 점검 응답을 다시 보내도 새 자료 상태를
    덮지 않고(409 → 같은 점검으로), 충당금 상태는 그대로다.
    """
    engine, run = _start(proc, rid)
    _check(engine, run, proc, rid, "Check_Depreciation")
    assert _pending(run) == ["Check_Allowance"]
    v2 = _relink(proc, company, rid, "ASSET-REPLACED")
    doc = proc.get(rid)
    assert doc["items"]["DEP"]["state"] == "RECHECK" and doc["inputs"][-1]["affected"] == ["DEP"]
    run_id = doc["bpm"]["external_run_id"]
    old = {
        "demo_run_id": rid,
        "close_id": "S3-CLOSE-01",
        "item": "DEP",
        "version": "IN-26-01",
        "decision": "점검 실행",
        "answered_by": OWNER,
    }
    with pytest.raises(DomainError) as stale:
        proc.operate(rid, "check_close_item", old, external_run_id=run_id, via="studio")
    assert stale.value.status == 409
    assert proc.get(rid)["items"]["DEP"]["state"] == "RECHECK"
    assert _check(engine, run, proc, rid, "Check_Allowance") is State.WAITING
    assert _states(proc, rid) == {"DEP": "RECHECK", "ALW": "READY"}
    assert _pending(run) == ["Check_Depreciation"]
    assert _check(engine, run, proc, rid, "Check_Depreciation") is State.DONE
    doc = proc.get(rid)
    assert [c["version"] for c in doc["checks"] if c["item"] == "DEP"] == ["IN-26-01", v2]
    assert doc["handoff"]["input_version"] == v2


def test_t07_change_after_handoff_invalidates_it_and_starts_a_recheck_run(
    proc, company, rid
) -> None:
    """인계 뒤 자료 교체 — 인계는 무효(장면 2 진입 차단), 재점검 실행이 새로 선다(앞은 이력)."""
    _base(proc, rid)
    _relink(proc, company, rid, "ASSET-REPLACED")
    doc = proc.get(rid)
    assert doc["handoff"]["valid"] is False
    assert [b["state"] for b in doc["bpm_history"]] == ["done"]
    assert doc["bpm"]["reason"].endswith("재점검") and doc["bpm"]["state"] == "idle"
    engine, run = _start(proc, rid)
    assert _pending(run) == ["Check_Depreciation"]  # 충당금은 지금 입력으로 이미 준비 완료
    assert _check(engine, run, proc, rid, "Check_Depreciation") is State.DONE
    assert proc.get(rid)["handoff"]["valid"] is True


def test_t08_unassigned_user_is_refused_back_to_the_same_check(proc, company, rid) -> None:
    """08 — 미배정 사용자의 점검은 기록이 거절되고 같은 점검으로 돌아간다. 분석·파일 생성 0건."""
    engine, run = _start(proc, rid)
    assert _check(engine, run, proc, rid, "Check_Depreciation", by="회계팀장") is State.WAITING
    assert _pending(run) == ["Check_Depreciation"]
    assert _states(proc, rid)["DEP"] == "ASSIGNED" and proc.get(rid)["checks"] == []
    _check(engine, run, proc, rid, "Check_Depreciation")
    _check(engine, run, proc, rid, "Check_Allowance")
    kinds = {r["kind"] for r in company.records(rid)}
    assert not kinds & {"analysis", "attachment", "report", "approval"}


def test_handoff_refuses_items_not_ready(proc, rid) -> None:
    doc = proc.get(rid)
    proc.operate(
        rid,
        "link_close_inputs",
        {"demo_run_id": rid, "close_id": "S3-CLOSE-01"},
        external_run_id="run-a",
        via="studio",
    )
    with pytest.raises(DomainError) as blocked:
        proc.operate(
            rid,
            "hand_off_close_items",
            {"demo_run_id": rid, "close_id": "S3-CLOSE-01"},
            external_run_id="run-a",
            via="studio",
        )
    assert blocked.value.status == 409 and doc["handoff"] is None


def test_other_run_or_place_is_refused(proc, rid) -> None:
    args = {"demo_run_id": rid, "close_id": "S3-CLOSE-01"}
    proc.operate(rid, "link_close_inputs", args, external_run_id="run-a", via="studio")
    with pytest.raises(DomainError) as other:
        proc.operate(rid, "link_close_inputs", args, external_run_id="run-b", via="studio")
    assert other.value.status == 409
    with pytest.raises(DomainError) as place:
        proc.operate(rid, "link_close_inputs", args, external_run_id="run-a", via="center")
    assert place.value.status == 409


def test_center_not_configured_leaves_a_reason(company, tmp_path) -> None:
    backend = build_sqlite_backend(str(tmp_path / "engine.sqlite"))
    proc = S3Sc01Process(build_sc01_store(backend, "s3sc01"), company=company)
    rid = f"s3-{uuid.uuid4().hex[:8]}"
    doc = proc.create(rid)  # 실행 위치 center — 설정 없음
    assert doc["bpm"]["job_id"] is None and "Center 연동이 설정되지 않았다" in doc["bpm"]["problem"]


class _Center:
    """기동·메시지를 받는 가짜 Center — 메시지는 처음 한 번 `no_receiver`로 거절한다."""

    def __init__(self) -> None:
        from app.sc01.center import CenterConfig

        self.config = CenterConfig(url="http://center", integration_key="k", relay_key="r")
        self.jobs: list[dict] = []
        self.messages: list[dict] = []
        self.refuse = 1

    def start_job(self, inputs, **kw) -> dict:
        self.jobs.append({"inputs": inputs, **kw})
        return {"job_id": f"job_{len(self.jobs)}"}

    def send_message(self, name, **kw) -> dict:
        from app.sc01.center import CenterError

        if self.refuse:
            self.refuse -= 1
            raise CenterError(409, "no_receiver", "기다리는 실행이 없다")
        self.messages.append({"name": name, **kw})
        return {"message_id": "m1"}

    def job(self, job_id: str) -> dict:
        return {"state": "running", "run_status": "running"}

    def cancel_job(self, job_id: str) -> dict:
        return {}


def test_center_start_and_fix_message_is_resent_until_received(company, tmp_path) -> None:
    """
    Center 실행 — 열면 결산 건을 기동하고, 보완을 기다릴 때 입력이 다시 연결되면 「결산자료보완」을
    보낸다. 받는 실행이 아직 없으면(`no_receiver`) 폴러가 다시 보낸다.
    """
    backend = build_sqlite_backend(str(tmp_path / "engine.sqlite"))
    center = _Center()
    proc = S3Sc01Process(build_sc01_store(backend, "s3sc01"), company=company, center=center)
    rid = f"s3-{uuid.uuid4().hex[:8]}"
    proc.create(rid, executor="center")
    [job] = center.jobs
    assert job["inputs"] == {"데모실행ID": rid, "결산건ID": "S3-CLOSE-01"}
    assert job["package"] == "company1.s3.sc01"
    _relink(proc, company, rid, "CONF-F-MISSING")
    args = {"demo_run_id": rid, "close_id": "S3-CLOSE-01"}
    run = {"external_run_id": "run-c", "via": "center"}
    proc.operate(rid, "link_close_inputs", args, **run)
    for item in ("DEP", "ALW"):
        proc.operate(rid, "route_close_items", args, **run)
        check = {**args, "item": item, "decision": "점검 실행", "answered_by": OWNER}
        proc.operate(rid, "check_close_item", {**check, "version": "IN-26-02"}, **run)
    assert proc.operate(rid, "route_close_items", args, **run)["next"] == "WAIT"
    _relink(proc, company, rid)
    assert proc.get(rid)["wait"]["message_pending"] is True and center.messages == []
    assert proc.poll_center() == 1
    [msg] = center.messages
    assert msg["name"] == "결산자료보완" and msg["correlation"] == rid
    assert msg["payload"] == {"입력버전": "IN-26-03"}
    assert proc.get(rid)["wait"]["message_pending"] is False


# ─────────────────────────── 기록 · 세계 따라가기 · 대시보드 ───────────────────────────


def test_every_written_version_matches_the_record_schemas(proc, company, rid) -> None:
    """
    경영 기록(`docs/records/s3/sc01/`) — 기본 시연과 보완 경로의 모든 판이 봉투·종류별 스키마를
    통과하고, 사이트 예시가 최신이다(다시 뽑기 `NOWVIEW_WRITE_RECORD_SCHEMAS=1`·`…_EXAMPLES=1`).
    """
    from records_contract import check, every_version, example

    from app.s3.sc01.records import KINDS

    _relink(proc, company, rid, "CONF-F-MISSING")
    engine, run = _start(proc, rid)
    _check(engine, run, proc, rid, "Check_Depreciation")
    _check(engine, run, proc, rid, "Check_Allowance")
    fixed = _relink(proc, company, rid)
    _deliver(engine, run, fixed)
    assert _check(engine, run, proc, rid, "Check_Allowance") is State.DONE
    versions = every_version(company, rid, 1)
    assert len(versions) > 10
    assert check(1, KINDS, versions, "s3/sc01") == []
    assert example(company, rid, 1, "s3/sc01") == []


def test_records_reruns_add_no_versions(proc, company, rid) -> None:
    _base(proc, rid)
    before = {(r["kind"], r["record_id"]): r["version"] for r in company.records(rid)}
    run_id = proc.get(rid)["bpm"]["external_run_id"]
    proc.operate(
        rid,
        "hand_off_close_items",
        {"demo_run_id": rid, "close_id": "S3-CLOSE-01"},
        external_run_id=run_id,
        via="studio",
    )
    after = {(r["kind"], r["record_id"]): r["version"] for r in company.records(rid)}
    assert after == before


def test_follower_creates_follows_and_relinks_a_scenario_3_world(
    monkeypatch, company, tmp_path
) -> None:
    """
    사이트가 만든 시나리오 3 회차 — 같은 id로 결산 건 문서(입력 IN-26-01·두 원업무), 시각을
    따라가고, 입력이 다시 연결되면 들인다. 초기화 회차가 오르면 처음으로, 세계가 지워지면 거둔다.
    """
    from app.follower import Follower

    monkeypatch.delenv("NOWVIEW_TEST_INPUTS", raising=False)
    backend = build_sqlite_backend(str(tmp_path / "engine.sqlite"))
    s3 = S3Sc01Process(build_sc01_store(backend, "s3sc01"), company=company)
    rid = f"demo-{uuid.uuid4().hex[:8]}"
    company._call("POST", "/worlds", {"world_id": rid, "origin": "site", "scenario_id": "s3"})
    f = Follower(company, {}, s3=s3)
    f._follow(company.world(rid))
    doc = s3.get(rid)
    assert doc["clock"] == S0 and doc["current_version"] == "IN-26-01"
    assert "Center 연동이 설정되지 않았다" in doc["bpm"]["problem"]
    company._call("POST", f"/worlds/{rid}/clock", {"at": "2027-01-04T10:00:00+09:00"})
    company.link_close_inputs(rid, ["CONF-F-MISSING"])
    f._follow(company.world(rid))
    doc = s3.get(rid)
    assert doc["clock"] == "2027-01-04T10:00:00+09:00" and doc["current_version"] == "IN-26-02"
    f._follow(company.world(rid))  # 다시 돌아도 한 번만 들인다
    assert len(s3.get(rid)["inputs"]) == 2
    company._call("POST", f"/worlds/{rid}/reset")
    f._follow(company.world(rid))
    doc = s3.get(rid)
    assert doc["current_version"] == "IN-26-01" and doc["world_generation"] == 2
    assert len(doc["inputs"]) == 1 and doc["clock"] == S0
    company._call("DELETE", f"/worlds/{rid}")
    f._sweep({w["world_id"] for w in company.worlds()})
    assert s3.store.load(rid) is None


def test_dashboard_shows_the_checklist_metrics_for_a_scenario_3_world(
    proc, company, rid, tmp_path
) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.companies import Settings, build_router
    from app.config import ConfigStore

    _base(proc, rid)
    world = {**company.world(rid), "origin": "site"}

    class _System:
        def worlds(self):
            return [world]

        def worker_log_entries(self, world_id: str):
            return [{"scene": 1, "operation": "check_close_item", "ok": True, "at": "x"}]

    settings = Settings(ConfigStore(build_sqlite_backend(str(tmp_path / "config.sqlite"))))
    app = FastAPI()
    app.include_router(
        build_router(settings, None, None, None, {"company1": _System()}, {31: proc})
    )
    body = TestClient(app).get("/companies/company1/dashboard").json()
    assert body["worlds"][0]["scenarioId"] == "s3"
    work = next(w for w in body["works"] if w["scene"] == 31)  # 장면 2(32)는 열기 전이다
    assert (work["scene"], work["work"], work["state"]) == (31, "결산조정 업무 착수", "done")
    assert work["progress"] == {"approvals": 2, "passed": 2}
    assert [m["value"] for m in work["metrics"]] == [
        "2/2항목",
        "0항목",
        "0/2항목",
        "0건",
        "IN-26-01",
    ]


def test_extension_definition_matches_the_bpmn_service_calls() -> None:
    """
    확장 `external`(0.13.0 이상)이 계약 검사를 통과하고, 그림의 서비스 호출 넷이 정의의 입력·출력과
    맞는다. 결재 둘의 담당은 배정된 회계담당자이고 기록 작업마다 오류 경계가 같은 점검으로 돌린다.
    """
    from chaeksas.contracts import extension as ext
    from chaeksas.contracts._semver import satisfies
    from chaeksas.contracts.bpmn_ext import read_process

    from app.s3.sc01.process import PROCESS_PATH

    raw = (
        Path(__file__).resolve().parents[2] / "chaeksas" / "external.extension.json"
    ).read_bytes()
    manifest = ext.ExtensionManifest.model_validate(json.loads(raw))
    assert ext.validate(manifest, from_center=True) == []
    assert satisfies(manifest.version, ">=0.13.0,<1")
    operations = {o["name"]: o for o in json.loads(raw)["service"]["adapter"]["operations"]}
    process = read_process(PROCESS_PATH.read_bytes())
    used = []
    for node in process.of_kind("serviceTask"):
        call = node.prop("serviceCall")
        op = operations[call.operation]
        assert set(op["input_schema"]["required"]) <= set(call.input), node.id
        assert set(call.output.values()) <= set(op["output_schema"]["properties"]), node.id
        used.append(call.operation)
    assert sorted(set(used)) == sorted(
        ["link_close_inputs", "route_close_items", "check_close_item", "hand_off_close_items"]
    )
    tasks = process.of_kind("userTask")
    assert sorted(n.id for n in tasks) == ["Check_Allowance", "Check_Depreciation"]
    for n in tasks:
        assert n.prop("approval").assignees == [OWNER]
    bounded = {n.attached_to for n in process.of_kind("boundaryEvent")}
    assert bounded == {"Record_Depreciation", "Record_Allowance"}
