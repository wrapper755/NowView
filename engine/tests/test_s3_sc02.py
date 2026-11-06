"""
시나리오 3 장면 2 — 결산조정 계산 및 담당자 검토(`app/s3/sc02/`, `docs/s3/sc02.md`).

* 계산은 입력 7개 시트만 읽고, **결산조정 계산근거 견본 v0.1**(`seed/S3-WORKPAPERS-v0.1.xlsx` — 장면
  2의 기대값)의 승인요약·상각비비교·유형자산주석·충당금비교·충당금주석·채권별계산·손실률·원장대사와
  같은 숫자를 낸다(견본을 옮겨 적지 않는다 — 시험만 읽는다).
* 구현명세 §4 인수시험 01~09. 장면 1(`company1.s3.sc01`)을 진짜 BPM 엔진으로 인계(HAND-S3-01)까지
  돌린 뒤 장면 2 그림(`processes/s3-sc02.bpmn`)을 돌린다. 서비스 태스크는 C15 일꾼의 수행기를
  지난다(Studio 흉내). 회계담당자의 실행·검토·상신은 결재 답이다. 회사 시스템은 기간계
  쌍둥이다(첨부·연계 PC 장애 스위치).
* 연계 PC는 **모의**다 — 실행 기록이 그것을 드러내는지도 본다.
"""

from __future__ import annotations

import base64
import io
import json
import shutil
import subprocess
import uuid
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest
from chaeksas.core.engine import Engine, RunEnv, State, new_run_id
from chaeksas.core.run_log import RunLog
from conftest import C15Calls

from app import company as company_mod
from app.s3.sc01.process import S3Sc01Process
from app.s3.sc02 import calc, workpaper
from app.s3.sc02.process import S3Sc02Process
from app.s3.sc02.records import dashboard
from app.sc01.domain import DomainError, parse_at
from app.sc01.store import build_sc01_store
from app.store import build_sqlite_backend

WORKPAPERS = Path(__file__).resolve().parents[1] / "seed" / "S3-WORKPAPERS-v0.1.xlsx"
OWNER = "회계담당"
CLOSE = "S3-CLOSE-01"


@pytest.fixture()
def company():
    return company_mod.default_client()


@pytest.fixture()
def master(company) -> dict:
    return company.s3_master()


@pytest.fixture()
def procs(tmp_path, company) -> tuple[S3Sc01Process, S3Sc02Process]:
    backend = build_sqlite_backend(str(tmp_path / "engine.sqlite"))
    s1 = S3Sc01Process(build_sc01_store(backend, "s3sc01"), company=company)
    s2 = S3Sc02Process(build_sc01_store(backend, "s3sc02"), company=company, sc01=s1)
    return s1, s2


@pytest.fixture()
def s1(procs):
    return procs[0]


@pytest.fixture()
def s2(procs):
    return procs[1]


def _start(proc, rid: str, process_id: str, origin: str = "test") -> tuple[Engine, object]:
    """진짜 엔진 — `test`는 Studio 시험 실행, `run`은 서버 실행기 흉내(Center 데모 실행)."""
    run_id = new_run_id(test=origin == "test")
    engine = Engine()
    run = engine.start(
        proc.process,
        run_id=run_id,
        log=RunLog(run_id=run_id),
        env=RunEnv(services=C15Calls(proc, origin=origin), processes=proc.processes),
        executor="studio" if origin == "test" else "server",
        bpm_process_id=process_id,
        inputs={"데모실행ID": rid, "결산건ID": CLOSE},
        now=parse_at(proc.get(rid)["clock"]),
    )
    engine.run_until_blocked(run)
    return engine, run


def _pending(run) -> list[str]:
    return [p.node_id for p in run.pendings.values()]


def _answer(engine, run, node: str, answer: dict, by: str = OWNER) -> State:
    [pending] = [p for p in run.pendings.values() if p.node_id == node]
    engine.answer(run, pending.request_id, answer, answered_by=by)
    return engine.run_until_blocked(run)


def _scene1(s1: S3Sc01Process, rid: str, origin: str = "test") -> None:
    """장면 1을 인계(HAND-S3-01)까지 — 감가상각비·충당금 점검."""
    engine, run = _start(s1, rid, "company1.s3.sc01", origin)
    for node, (ver, dec_) in (
        ("Check_Depreciation", ("상각점검버전", "상각점검")),
        ("Check_Allowance", ("충당점검버전", "충당점검")),
    ):
        if node in _pending(run):
            _answer(engine, run, node, {ver: s1.get(rid)["current_version"], dec_: "점검 실행"})
    assert s1.get(rid)["handoff"]["valid"] is True


@pytest.fixture()
def rid(s1, company) -> str:
    rid = f"s3-{uuid.uuid4().hex[:8]}"
    s1.create(rid, executor="studio")
    _scene1(s1, rid)
    return rid


@pytest.fixture()
def opened(s2, rid) -> str:
    s2.create(rid, executor="studio")
    return rid


def _request(engine, run, s1, rid, by: str = OWNER, version: str | None = None) -> State:
    ver = version or s1.get(rid)["current_version"]
    return _answer(
        engine, run, "Request_Analysis", {"실행입력버전": ver, "분석실행": "분석 실행"}, by
    )


REVIEW = {
    "Review_Allowance": ("충당검토버전", "충당검토"),
    "Review_Depreciation": ("상각검토버전", "상각검토"),
}


def _review(engine, run, s2, rid, node: str, version: str | None = None, by: str = OWNER) -> State:
    ver, dec_ = REVIEW[node]
    res = version or s2.get(rid)["results"][-1]["result_version"]
    return _answer(engine, run, node, {ver: res, dec_: "검토 완료"}, by)


def _submit(engine, run, s2, rid, version: str | None = None) -> State:
    res = version or s2.get(rid)["results"][-1]["result_version"]
    return _answer(engine, run, "Submit_Report", {"상신결과버전": res, "상신": "상신"})


def _to_review(s1, s2, rid) -> tuple[Engine, object]:
    engine, run = _start(s2, rid, "company1.s3.sc02")
    assert _pending(run) == ["Request_Analysis"]
    assert _request(engine, run, s1, rid) is State.WAITING
    assert _pending(run) == ["Review_Allowance"]
    return engine, run


def _base(s1, s2, rid) -> tuple[Engine, object]:
    engine, run = _to_review(s1, s2, rid)
    _review(engine, run, s2, rid, "Review_Allowance")
    assert _pending(run) == ["Review_Depreciation"]
    _review(engine, run, s2, rid, "Review_Depreciation")
    assert _pending(run) == ["Submit_Report"]
    assert _submit(engine, run, s2, rid) is State.DONE
    return engine, run


def _relink(s1, s2, company, rid, *variants: str) -> str:
    """자료 담당자가 입력을 다시 연결했다 — 세계 따라가기처럼 장면 1·2에 넘긴다."""
    got = company.link_close_inputs(rid, list(variants))
    s1.receive_inputs(rid)
    s2.receive_inputs(rid)
    return got["version"]


def _wp(name: str) -> list[tuple]:
    wb = openpyxl.load_workbook(WORKPAPERS, data_only=True)
    return [r for r in wb[name].iter_rows(min_row=4, values_only=True) if r[0] is not None]


def _d(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"))


# ─────────────────────────── 계산 = 견본 v0.1 ───────────────────────────


def test_calculation_matches_the_workpaper_sample(company, master, rid) -> None:
    """
    견본 v0.1 대조 — 감가상각비 1,120 → 1,200(+80, 장부 1,150 → 추가 50), 대손충당금 100 → 110
    (+10, 조정 전 80 → 추가 설정 30), 집합 75 → 70 · 개별 25 → 40, 유형자산 기말 8,700, 원장 대사 0,
    2024년말 원본 재현 302,527,880원. 전기 대비 증감과 승인 요청액을 섞지 않는다.
    """
    v = company.close_input(rid, "IN-26-01")
    got = calc.calculate(v, master)
    assert got["state"] == calc.OK and got["max_diff_won"] == 0 and got["findings"] == []
    summary = {s["name"]: s for s in got["summary"]}
    for name, prior, cur, change, book, req, *_ in _wp("승인요약")[1:]:
        s = summary[name]
        assert [_d(s[k]) for k in ("prior", "current", "change", "book", "request")] == [
            _d(x) for x in (prior, cur, change, book, req)
        ], name
    assert summary["감가상각비"]["request_label"] == "추가 계상"
    assert summary["대손충당금"]["request_label"] == "추가 설정"
    dep = got["depreciation"]
    groups = {g["group"]: g for g in dep["by_kind"] + dep["by_allocation"]}
    for name, prior, cur, *_ in _wp("상각비비교")[1:]:
        assert (_d(groups[name]["prior"]), _d(groups[name]["current"])) == (_d(prior), _d(cur)), (
            name
        )
    note = {r["kind"]: r for r in [*dep["note"]["rows"], dep["note"]["total"]]}
    for kind, *vals in _wp("유형자산주석")[1:]:
        keys = ("opening", "acquired", "disposed", "impairment", "depreciation", "closing")
        assert [_d(note[kind][k]) for k in keys] == [_d(x) for x in vals], kind
    assets = {a["asset_id"]: a for a in dep["assets"]}
    for row in _wp("자산별계산")[1:]:
        assert (_d(assets[row[0]]["current"]), _d(assets[row[0]]["prior"])) == (
            _d(row[10]),
            _d(row[11]),
        ), row[0]
    alw = got["allowance"]
    methods = {m["method"]: m for m in alw["methods"]}
    customers = {c["customer"]: c for c in alw["customers"]}
    for name, prior, cur, *_ in _wp("충당금비교")[1:]:
        found = methods.get(name) or customers[name]
        assert (_d(found["prior"]), _d(found["current"])) == (_d(prior), _d(cur)), name
    assert alw["top3"] == ["A사", "G사", "F사"]
    for row in _wp("채권별계산")[1:]:
        c = customers[row[0]]
        assert (_d(c["prior"]), _d(c["current"]), c["rank"]) == (_d(row[6]), _d(row[7]), row[9])
    [(_, opening, prov, rev, used, ending, diff)] = _wp("충당금주석")[1:]
    n = alw["note"]
    assert [_d(n[k]) for k in ("opening", "provision", "reversal", "written_off", "ending")] == [
        _d(x) for x in (opening, prov, rev, used, ending)
    ]
    assert n["diff_won"] == diff == 0
    seg = {s["aging"]: s for s in alw["model"]["segments"]}
    for row in _wp("손실률")[1:-1]:
        s = seg[row[0]]
        if row[2] is not None:
            assert abs(Decimal(s["weighted_rate"]) - Decimal(str(row[2]))) < Decimal("1e-12")
        assert abs(Decimal(s["rate"]) - Decimal(str(row[5]))) < Decimal("1e-12"), row[0]
    assert alw["model"]["reproduced_won"] == 302_527_880 == round(_wp("손실률")[-1][7])
    ind = {(i["customer"], i["as_of"]): i for i in alw["individual"]}
    for name, year, balance, recovery, allowance, _basis in _wp("개별평가")[1:]:
        i = ind[(name, f"{year}-12-31")]
        assert [_d(i[k]) for k in ("balance", "recovery", "allowance")] == [
            _d(x) for x in (balance, recovery, allowance)
        ]
    assert ind[("A사", "2026-12-31")]["accounting_confirmation"] == "CONF-26-F"
    assert ind[("A사", "2026-12-31")]["sales_confirmation"] == "CONF-26-S"


def test_agent_draft_cites_result_fields_and_has_no_directive(company, master, rid) -> None:
    """Agent 문안 — 수치마다 결과 칸을 잇고, 팀장 판단을 지시하는 문구가 없다(규칙 문안 표시)."""
    got = calc.calculate(company.close_input(rid, "IN-26-01"), master)
    d = calc.draft(got)
    assert d["mode"] == "rule-template" and "LLM 호출 없음" in d["note"]
    for section in d["sections"]:
        assert section["refs"] and all(
            r["field"] and r["value"] is not None for r in section["refs"]
        )
        assert "승인하" not in section["text"] and "승인해" not in section["text"]
    text = {s["item"]: s["text"] for s in d["sections"]}
    assert "E2(설비) 6개월 상각으로 100 증가" in text["DEP"] and "추가 계상 50" in text["DEP"]
    assert "75 → 60(CONF-26-F 확인)" in text["ALW"] and "추가 설정 30" in text["ALW"]


# ─────────────────────────── 인수시험 01~09 ───────────────────────────


def test_t01_entry_permissions_and_latest_input(s1, s2, company, rid) -> None:
    """
    01 — 준비 2/2면 연다. 지시 열람은 실행 0건. 미배정 사용자의 실행은 거절되어 같은 실행 요청으로
    돌아가고, 변경된 입력(본 버전이 최신이 아님)으로도 실행되지 않는다.
    """
    s2.create(rid, executor="studio")
    engine, run = _start(s2, rid, "company1.s3.sc02")
    doc = s2.get(rid)
    assert doc["entry"]["input_version"] == "IN-26-01" and doc["entry"]["opened_at"] is not None
    assert doc["runs"] == [] and _pending(run) == ["Request_Analysis"]
    assert _request(engine, run, s1, rid, by="회계팀장") is State.WAITING
    assert _pending(run) == ["Request_Analysis"] and s2.get(rid)["runs"] == []
    assert _request(engine, run, s1, rid, version="IN-26-00") is State.WAITING
    assert _pending(run) == ["Request_Analysis"] and s2.get(rid)["runs"] == []
    assert _request(engine, run, s1, rid) is State.WAITING
    [r] = s2.get(rid)["runs"]
    assert (r["run_id"], r["requested_by"], r["input_version"]) == ("RUN-S3-01", OWNER, "IN-26-01")
    assert r["versions"]["prompt"] == "PRM-S3-SC02-v0.1"
    assert r["versions"]["format"] == workpaper.FORMAT_VERSION


def test_t01_scene_cannot_open_before_scene1_hands_off(s1, s2, company) -> None:
    rid = f"s3-{uuid.uuid4().hex[:8]}"
    s1.create(rid, executor="studio")
    with pytest.raises(DomainError) as early:
        s2.create(rid, executor="studio")
    assert early.value.status == 409 and "분석 준비" in str(early.value)
    assert s2.store.load(rid) is None


def test_t02_double_click_is_one_run_and_pc_delay_shows_last_response(
    s1, s2, company, opened
) -> None:
    """
    02 — 실행 연속 클릭은 같은 실행 1건. 연계 PC가 계산 중에 응답하지 않으면 실제 단계(PC 수신 완료
    · 계산 중)와 마지막 응답 시각을 보이고, 같은 실행 ID로 상태를 조회한다(자동 재생하지 않는다).
    """
    rid = opened
    company.set_close_fault(rid, "pc_delay", 1)
    engine, run = _start(s2, rid, "company1.s3.sc02")
    assert _request(engine, run, s1, rid) is State.WAITING
    assert _pending(run) == ["Check_Run"]
    doc = s2.get(rid)
    [r] = doc["runs"]
    steps = {s["step"]: s["state"] for s in r["steps"]}
    assert (steps["ACCEPTED"], steps["PC_RECEIVED"], steps["CALCULATING"]) == (
        "done",
        "done",
        "running",
    )
    assert steps["FILE_CREATED"] == "waiting" and r["last_success"] == "PC_RECEIVED"
    assert r["last_response_at"] == doc["clock"] and r["state"] == "PENDING"
    again = s2.operate(
        rid,
        "request_close_analysis",
        {
            "demo_run_id": rid,
            "close_id": CLOSE,
            "version": "IN-26-01",
            "decision": "분석 실행",
            "answered_by": OWNER,
        },
        external_run_id=doc["bpm"]["external_run_id"],
        via="studio",
    )
    assert again["run_id"] == r["run_id"] and len(s2.get(rid)["runs"]) == 1
    assert _answer(engine, run, "Check_Run", {"상태조회": "상태 조회"}) is State.WAITING
    assert _pending(run) == ["Review_Allowance"]
    [r] = s2.get(rid)["runs"]
    assert (
        r["pc_queries"] == 2
        and r["state"] == "REVIEW_READY"
        and r["last_success"] == "REVIEW_READY"
    )
    assert r["execution_mode"] == "simulated" and "연동이 없다" in r["execution_note"]


def test_t03_allowance_collective_individual_and_request(s1, s2, opened) -> None:
    """
    03 — 집합 70 · 개별 40 · 기말 110. 전기 대비 +10과 요청 +30을 구분. 집합 6개사·개별 1개사,
    차이 0.
    """
    _to_review(s1, s2, opened)
    doc = s2.get(opened)
    [r] = doc["runs"]
    assert r["reconciliation"] == {
        "receivable_diff_won": 0,
        "max_diff_won": 0,
        "collective": 6,
        "individual": 1,
        "prior_collective": 6,
        "prior_individual": 1,
        "a_plan_match": True,
    }
    alw = doc["results"][-1]["calc"]["allowance"]
    assert [(m["method"], m["current"]) for m in alw["methods"]] == [
        ("집합", "70"),
        ("개별", "40"),
        ("합계", "110"),
    ]
    s = alw["summary"]
    assert (s["change"], s["request"], s["book"]) == ("10", "30", "80")


def test_t04_depreciation_allocation_and_note_match(s1, s2, opened) -> None:
    """04 — E2·E3를 포함한 자산대장: 당기 1,200, 귀속·주석 대사 차이 0, 요청 +50."""
    _to_review(s1, s2, opened)
    dep = s2.get(opened)["results"][-1]["calc"]["depreciation"]
    assert dep["summary"]["current"] == "1200" and dep["summary"]["request"] == "50"
    assert dep["diffs"] == {"allocation_won": 0, "note_won": 0, "closing_won": 0}
    alloc = {g["group"]: g["current"] for g in dep["by_allocation"]}
    assert (alloc["제조원가"], alloc["판매관리비"]) == ("1020", "180")
    changes = {c["asset_id"]: (c["change"], c["months"]) for c in dep["changes"]}
    assert changes == {"E2": ("100", 6), "E3": ("-20", 0)}


@pytest.mark.parametrize(
    ("variant", "owner", "check"),
    [("CONF-AMOUNT-MISMATCH", "회계담당", "ALW-08"), ("LEDGER-1WON", "채권담당", "ALW-03")],
)
def test_t05_input_exceptions_show_item_reason_owner_and_hold_submission(
    s1, s2, company, master, opened, variant, owner, check
) -> None:
    """
    05 — A사 확인액 불일치·원장 1원 차이: 영향 항목·근거·보완 담당을 보이고 통합 상신을 보류한다.
    누락·불일치를 0이나 추정액으로 채우지 않는다(계산 기능도 스스로 보류한다).
    """
    rid = opened
    engine, run = _to_review(s1, s2, rid)
    _relink(s1, s2, company, rid, variant)
    assert s2.get(rid)["stale"] is not None
    assert _review(engine, run, s2, rid, "Review_Allowance") is State.WAITING
    assert _pending(run) == ["Request_Analysis"]  # 기록 거절 → 다시 고르기 → 다시 실행
    with pytest.raises(DomainError) as held:
        s2.operate(
            rid,
            "request_close_analysis",
            {
                "demo_run_id": rid,
                "close_id": CLOSE,
                "version": s1.get(rid)["current_version"],
                "decision": "분석 실행",
                "answered_by": OWNER,
            },
            external_run_id=s2.get(rid)["bpm"]["external_run_id"],
            via="studio",
        )
    assert held.value.status == 409
    assert "통합 상신은 보류" in str(held.value)
    # 장면 1 재점검이 내는 보완 근거가 사유로 실린다
    engine1, run1 = _start(s1, rid, "company1.s3.sc01")
    for node, f in (("Check_Allowance", ("충당점검버전", "충당점검")),):
        _answer(engine1, run1, node, {f[0]: s1.get(rid)["current_version"], f[1]: "점검 실행"})
    with pytest.raises(DomainError) as why:
        s2.operate(
            rid,
            "request_close_analysis",
            {
                "demo_run_id": rid,
                "close_id": CLOSE,
                "version": s1.get(rid)["current_version"],
                "decision": "분석 실행",
                "answered_by": OWNER,
            },
            external_run_id=s2.get(rid)["bpm"]["external_run_id"],
            via="studio",
        )
    assert check in str(why.value) and owner in str(why.value)
    assert s2.get(rid)["report"] is None and len(s2.get(rid)["runs"]) == 1
    v = company.close_input(rid, s1.get(rid)["current_version"])
    got = calc.calculate(v, master)
    assert got["state"] == calc.NEEDS_FIX
    assert {f["owner_role"] for f in got["findings"]} == {owner}


def test_t06_transfer_failure_waits_and_retries_the_same_file(s1, s2, company, opened) -> None:
    """
    06 — 계산 성공 뒤 전송 실패: 첨부 대기 → [첨부 재시도] → 같은 실행의 파일 1개 복구 → 검토 대기.
    """
    rid = opened
    company.set_close_fault(rid, "transfer_fail", 1)
    engine, run = _start(s2, rid, "company1.s3.sc02")
    assert _request(engine, run, s1, rid) is State.WAITING
    assert _pending(run) == ["Retry_Attach"]
    doc = s2.get(rid)
    [att] = doc["attachments"]
    assert att["state"] == "TRANSFER_FAILED" and doc["runs"][0]["state"] == "ATTACH_WAIT"
    assert company.close_attachments(rid) == []
    assert dashboard(doc)["rows"][0]["state"] == "ATTACH_WAIT"
    assert _answer(engine, run, "Retry_Attach", {"첨부재시도": "첨부 재시도"}) is State.WAITING
    assert _pending(run) == ["Review_Allowance"]
    doc = s2.get(rid)
    [att] = doc["attachments"]
    assert att["state"] == "REGISTERED" and [a["ok"] for a in att["attempts"]] == [False, True]
    [stored] = company.close_attachments(rid)
    assert (stored["file_id"], stored["run_id"], stored["sha256"]) == (
        att["file_id"],
        doc["runs"][0]["run_id"],
        att["sha256"],
    )
    assert att["open_check"]["ok"] is True and doc["runs"][0]["state"] == "REVIEW_READY"


def test_t07_registered_xlsx_opens_and_its_summary_matches_the_screen(
    s1, s2, company, opened
) -> None:
    """
    07 — 등록된 .xlsx를 열면 견본의 시트 구성이고, 승인요약의 두 요청액은 상세 시트 수식에 이어진다.
    실행 ID·결과 버전이 파일과 화면에 같다.
    """
    rid = opened
    _to_review(s1, s2, rid)
    doc = s2.get(rid)
    [att] = doc["attachments"]
    raw = base64.b64decode(company.close_attachment(rid, att["file_id"])["content_b64"])
    wb = openpyxl.load_workbook(io.BytesIO(raw))
    assert wb.sheetnames == list(workpaper.SHEETS)
    sample = openpyxl.load_workbook(WORKPAPERS).sheetnames
    assert set(sample) <= set(wb.sheetnames)
    summary = wb["승인요약"]
    assert summary["F5"].value == "=C5-E5" and summary["F6"].value == "=C6-E6"
    assert summary["C6"].value == "=충당금비교!C7" and summary["E6"].value == "=원장대사!B8"
    info = {r[0]: r[1] for r in wb["실행정보"].iter_rows(min_row=5, values_only=True)}
    assert info["실행 ID"] == doc["runs"][0]["run_id"]
    assert info["결과 버전"] == doc["results"][-1]["result_version"] == att["result_version"]
    assert info["실행 방식"] == "simulated"
    formulas = [c.value for ws in wb for row in ws.iter_rows() for c in row]
    assert sum(1 for f in formulas if isinstance(f, str) and f.startswith("=")) > 150


@pytest.mark.skipif(
    shutil.which("soffice") is None, reason="LibreOffice가 없다 — 재계산 시험은 로컬"
)
def test_t07_recalculated_workbook_has_no_errors_and_same_requests(
    s1, s2, company, opened, tmp_path
) -> None:
    """
    07 — LibreOffice로 다시 계산하면 수식 오류 0, 대사 차이 0, 두 요청액·전기·당기가 화면과 같다.
    """
    rid = opened
    _to_review(s1, s2, rid)
    doc = s2.get(rid)
    [att] = doc["attachments"]
    src = tmp_path / "wp.xlsx"
    src.write_bytes(base64.b64decode(company.close_attachment(rid, att["file_id"])["content_b64"]))
    out = tmp_path / "out"
    out.mkdir()
    subprocess.run(
        ["soffice", "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(out), str(src)],
        check=True,
        capture_output=True,
        timeout=180,
    )
    wb = openpyxl.load_workbook(out / "wp.xlsx", data_only=True)
    errors = [
        (ws.title, c.coordinate)
        for ws in wb
        for row in ws.iter_rows()
        for c in row
        if isinstance(c.value, str) and c.value.startswith("#")
    ]
    assert errors == []
    rows = {r[0]: r for r in wb["승인요약"].iter_rows(min_row=5, values_only=True)}
    summary = {s["name"]: s for s in doc["results"][-1]["calc"]["summary"]}
    for name in ("감가상각비", "대손충당금"):
        assert [_d(x) for x in rows[name][1:6]] == [
            _d(summary[name][k]) for k in ("prior", "current", "change", "book", "request")
        ]
    diffs = [
        r[3] for r in wb["원장대사"].iter_rows(min_row=5, values_only=True) if r[3] is not None
    ]
    assert diffs and all(d == 0 for d in diffs)
    assert round(wb["손실률"]["H11"].value) == 302_527_880


def test_t08_amount_change_rechecks_recalculates_and_rereviews_only_the_affected_item(
    s1, s2, company, opened
) -> None:
    """
    08 — 검토 뒤 금액 근거 변경(E2 가동 8월): 상각비 재점검(장면 1) → 재계산(새 실행·결과·파일 버전)
    → 상각비만 재검토(충당금 검토는 승계). 옛 결과의 검토·상신 응답은 409로 막힌다.
    """
    rid = opened
    engine, run = _to_review(s1, s2, rid)
    _review(engine, run, s2, rid, "Review_Allowance")
    _review(engine, run, s2, rid, "Review_Depreciation")
    assert _pending(run) == ["Submit_Report"]
    old = s2.get(rid)["results"][-1]["result_version"]
    new_input = _relink(s1, s2, company, rid, "E2-START-AUG")
    doc = s2.get(rid)
    assert doc["stale"]["result_version"] == old
    assert dashboard(doc)["rows"][0]["state"] == "STALE"
    # 옛 결과의 상신 → 기록 거절 → 다시 고르기 → 다시 실행
    assert _submit(engine, run, s2, rid, version=old) is State.WAITING
    assert _pending(run) == ["Request_Analysis"] and s2.get(rid)["report"] is None
    # 장면 1 재점검(상각비만) → 인계 → 다시 실행
    engine1, run1 = _start(s1, rid, "company1.s3.sc01")
    assert _pending(run1) == ["Check_Depreciation"]
    _answer(
        engine1, run1, "Check_Depreciation", {"상각점검버전": new_input, "상각점검": "점검 실행"}
    )
    assert s1.get(rid)["handoff"]["valid"] is True
    assert _request(engine, run, s1, rid) is State.WAITING
    doc = s2.get(rid)
    assert [r["state"] for r in doc["runs"]] == ["SUPERSEDED", "REVIEW_READY"]
    new = doc["results"][-1]
    assert new["input_version"] == new_input and new["result_version"] != old
    dep = new["calc"]["depreciation"]["summary"]
    assert (dep["current"], dep["request"]) == ("1183.333333", "33.333333")
    assert [a["file_version"] for a in doc["attachments"]] == [1, 2]
    assert _pending(run) == ["Review_Depreciation"]  # 충당금은 입력·금액이 같아 승계
    carried = [r for r in doc["reviews"] if r["result_version"] == new["result_version"]]
    assert [(r["item"], r["state"], r["carried_from"]) for r in carried] == [
        ("ALW", "CARRIED", "REV-ALW-1")
    ]
    with pytest.raises(DomainError) as stale_answer:
        s2.operate(
            rid,
            "review_close_item",
            {
                "demo_run_id": rid,
                "close_id": CLOSE,
                "item": "DEP",
                "result_version": old,
                "decision": "검토 완료",
                "answered_by": OWNER,
            },
            external_run_id=doc["bpm"]["external_run_id"],
            via="studio",
        )
    assert stale_answer.value.status == 409
    _review(engine, run, s2, rid, "Review_Depreciation")
    assert _submit(engine, run, s2, rid) is State.DONE
    report = s2.get(rid)["report"]
    assert report["result_version"] == new["result_version"]
    assert report["attachment"]["file_version"] == 2
    assert [i["request"] for i in report["items"]] == ["33.333333", "30"]


def test_t09_one_report_two_rows_waiting_zero_approved(s1, s2, company, opened) -> None:
    """
    09 — 두 항목 검토 후 상신, 재클릭: 보고 ID 1개, 승인 대기 2행, 승인 완료 0건. 팀장에게 같은
    버전의 요약과 첨부가 넘어간다(HAND-S3-02).
    """
    rid = opened
    _base(s1, s2, rid)
    doc = s2.get(rid)
    rep = doc["report"]
    assert (rep["report_id"], rep["version"], rep["state"]) == ("REP-S3-01", 1, "SUBMITTED")
    assert rep["approvals"] == {"done": 0, "of": 2}
    assert [(i["name"], i["request"], i["request_label"], i["approval"]) for i in rep["items"]] == [
        ("감가상각비", "50", "추가 계상", "WAITING"),
        ("대손충당금", "30", "추가 설정", "WAITING"),
    ]
    assert [(i["prior"], i["current"], i["change"], i["book"]) for i in rep["items"]] == [
        ("1120", "1200", "80", "1150"),
        ("100", "110", "10", "80"),
    ]
    assert rep["recipient"]["name"] == "회계팀장" and rep["attachment"]["file_id"] == "WP-S3-v1"
    assert rep["result_version"] == doc["attachments"][0]["result_version"]
    again = s2.operate(
        rid,
        "submit_close_report",
        {
            "demo_run_id": rid,
            "close_id": CLOSE,
            "result_version": rep["result_version"],
            "decision": "상신",
            "answered_by": OWNER,
        },
        external_run_id=doc["bpm"]["external_run_id"],
        via="studio",
    )
    assert again["report_id"] == "REP-S3-01"
    assert [r for r in company.records(rid) if r["kind"] == "close_report"][0]["version"] == 1
    board = dashboard(s2.get(rid))
    assert (board["reports"], board["waiting_approval"], board["approved"]) == (
        1,
        2,
        {"done": 0, "of": 2},
    )
    assert [r["state"] for r in board["rows"]] == ["SUBMITTED", "SUBMITTED"]
    h = s2.get(rid)["handoff"]
    assert (h["handoff_id"], h["report_id"], h["attachment_ref"]) == (
        "HAND-S3-02",
        "REP-S3-01",
        "WP-S3-v1",
    )
    assert s2.get(rid)["bpm"]["state"] == "done" and s2.get(rid)["bpm"]["visited"][-1] == "End"
    from records_contract import example

    assert example(company, rid, 2, "s3/sc02") == []  # 사이트 시험의 예시 = 기본 시연 끝


def test_old_run_responses_cannot_overwrite_the_latest(s1, s2, company, opened) -> None:
    """이전 실행의 PC 응답은 최신 결과를 덮지 않는다(구현명세 §4)."""
    rid = opened
    engine, run = _to_review(s1, s2, rid)
    _relink(s1, s2, company, rid, "ASSET-REPLACED")
    engine1, run1 = _start(s1, rid, "company1.s3.sc01")
    _answer(
        engine1,
        run1,
        "Check_Depreciation",
        {"상각점검버전": s1.get(rid)["current_version"], "상각점검": "점검 실행"},
    )
    _review(engine, run, s2, rid, "Review_Allowance")  # 낡음 → 다시 실행
    _request(engine, run, s1, rid)
    with pytest.raises(DomainError) as late:
        s2.operate(
            rid,
            "process_close_analysis",
            {"demo_run_id": rid, "close_id": CLOSE, "run_id": "RUN-S3-01"},
            external_run_id=s2.get(rid)["bpm"]["external_run_id"],
            via="studio",
        )
    assert late.value.status == 409
    assert s2.get(rid)["runs"][-1]["run_id"] == "RUN-S3-02"


# ─────────────────────────── 기록 · 세계 따라가기 · 대시보드 · 확장 ───────────────────────────


def test_every_written_version_matches_the_record_schemas(s1, s2, company, opened) -> None:
    """
    경영 기록(`docs/records/s3/sc02/`) — 기본 시연과 장애·재실행 경로의 모든 판이 봉투·종류별
    스키마를 통과한다(다시 뽑기 `NOWVIEW_WRITE_RECORD_SCHEMAS=1`). 사이트 예시는 기본 시연
    끝(인수시험 09)이다.
    """
    from records_contract import check, every_version

    from app.s3.sc02.records import KINDS

    rid = opened
    company.set_close_fault(rid, "pc_delay", 1)
    company.set_close_fault(rid, "transfer_fail", 1)
    engine, run = _start(s2, rid, "company1.s3.sc02")
    _request(engine, run, s1, rid)
    _answer(engine, run, "Check_Run", {"상태조회": "상태 조회"})
    _answer(engine, run, "Retry_Attach", {"첨부재시도": "첨부 재시도"})
    _review(engine, run, s2, rid, "Review_Allowance")
    _review(engine, run, s2, rid, "Review_Depreciation")
    new_input = _relink(s1, s2, company, rid, "E2-START-AUG")
    _submit(engine, run, s2, rid)
    engine1, run1 = _start(s1, rid, "company1.s3.sc01")
    _answer(
        engine1, run1, "Check_Depreciation", {"상각점검버전": new_input, "상각점검": "점검 실행"}
    )
    _request(engine, run, s1, rid)
    _review(engine, run, s2, rid, "Review_Depreciation")
    assert _submit(engine, run, s2, rid) is State.DONE
    versions = every_version(company, rid, 2)
    assert len(versions) > 20
    assert check(2, KINDS, versions, "s3/sc02") == []


def test_follower_opens_scene2_on_command_and_rewinds(monkeypatch, company, tmp_path) -> None:
    """
    사이트의 「장면 열기」(시나리오 3 장면 2) — 장면 1 인계가 있으면 연다(없으면 거절 사유). 「장면
    2부터 다시」는 장면 2 문서만 거두고, 입력이 다시 연결되면 장면 2의 결과를 다시 본다.
    """
    from app.follower import Follower

    monkeypatch.delenv("NOWVIEW_TEST_INPUTS", raising=False)
    backend = build_sqlite_backend(str(tmp_path / "engine.sqlite"))
    p1 = S3Sc01Process(build_sc01_store(backend, "s3sc01"), company=company)
    p2 = S3Sc02Process(build_sc01_store(backend, "s3sc02"), company=company, sc01=p1)
    rid = f"demo-{uuid.uuid4().hex[:8]}"
    company._call("POST", "/worlds", {"world_id": rid, "origin": "site", "scenario_id": "s3"})
    f = Follower(company, {}, s3=p1, s3_scenes={2: p2})
    f._follow(company.world(rid))

    seq = iter(range(1, 100))

    def command(scene: int, kind: str, body: dict | None = None) -> dict:
        return company._call(
            "POST",
            f"/worlds/{rid}/commands",
            {
                "scene": scene,
                "kind": kind,
                "actor": "u-acct",
                "body": body or {},
                "ref": f"{rid}:{kind}{scene}:{next(seq)}",
            },
        )

    early = command(2, "open")
    f._follow(company.world(rid))
    [got] = [c for c in company.commands(rid, None) if c["command_id"] == early["command_id"]]
    assert (got["state"], got["status"]) == ("REJECTED", 409) and p2.store.load(rid) is None
    _scene1(p1, rid, "run")  # 장면 1을 인계까지(Center 없이 — 서버 실행기 흉내)
    command(2, "open")
    f._follow(company.world(rid))
    doc = p2.get(rid)
    assert doc["entry"]["input_version"] == "IN-26-01" and doc["world_generation"] == 1
    assert "Center 연동이 설정되지 않았다" in doc["bpm"]["problem"]
    command(2, "rewind", {"scene": 2})
    f._follow(company.world(rid))
    assert p2.store.load(rid) is None and p1.store.load(rid) is not None


def test_dashboard_shows_scene2_metrics(s1, s2, company, opened, tmp_path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.companies import Settings, build_router
    from app.config import ConfigStore

    rid = opened
    _base(s1, s2, rid)
    world = {**company.world(rid), "origin": "site"}

    class _System:
        def worlds(self):
            return [world]

        def worker_log_entries(self, world_id: str):
            return [{"scene": 2, "operation": "submit_close_report", "ok": True, "at": "x"}]

    settings = Settings(ConfigStore(build_sqlite_backend(str(tmp_path / "config.sqlite"))))
    app = FastAPI()
    app.include_router(
        build_router(settings, None, None, None, {"company1": _System()}, {31: s1, 32: s2})
    )
    body = TestClient(app).get("/companies/company1/dashboard").json()
    works = {w["scene"]: w for w in body["works"]}
    work = works[32]
    assert (work["work"], work["state"]) == ("결산조정 계산 및 담당자 검토", "done")
    assert [m["value"] for m in work["metrics"]] == [
        "2/2항목",
        "2항목",
        "1건",
        "0/2항목",
        "추가 계상 50백만원",
        "추가 설정 30백만원",
    ]


def test_extension_definition_matches_the_bpmn_service_calls() -> None:
    """
    확장 `external`(0.14.0 이상)이 계약 검사를 통과하고, 그림의 서비스 호출 일곱이 정의의
    입력·출력과 맞는다. 결재 여섯의 담당은 배정된 회계담당자이고 기록 작업마다 오류 경계가 있다.
    """
    from chaeksas.contracts import extension as ext
    from chaeksas.contracts._semver import satisfies
    from chaeksas.contracts.bpmn_ext import read_process

    from app.s3.sc02.process import OPERATIONS, PROCESS_PATH

    raw = (
        Path(__file__).resolve().parents[2] / "chaeksas" / "external.extension.json"
    ).read_bytes()
    manifest = ext.ExtensionManifest.model_validate(json.loads(raw))
    assert ext.validate(manifest, from_center=True) == []
    assert satisfies(manifest.version, ">=0.14.0,<1")
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
    tasks = process.of_kind("userTask")
    assert sorted(n.id for n in tasks) == sorted(
        [
            "Request_Analysis",
            "Check_Run",
            "Retry_Attach",
            "Review_Allowance",
            "Review_Depreciation",
            "Submit_Report",
        ]
    )
    for n in tasks:
        assert n.prop("approval").assignees == [OWNER]
    bounded = {n.attached_to for n in process.of_kind("boundaryEvent")}
    assert bounded == {
        "Record_Request",
        "Record_Review_Allowance",
        "Record_Review_Depreciation",
        "Record_Submit",
    }
    shapes = (PROCESS_PATH.read_text()).count("<bpmndi:BPMNShape")
    assert shapes == len(process.nodes) if hasattr(process, "nodes") else shapes > 20
