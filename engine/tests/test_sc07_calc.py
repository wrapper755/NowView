"""
SC07 규칙 계산 — **통합가상데이터 v0.7 기대값 시트와 대조**한다. 숫자·상태를 시험에 옮겨 적지 않고
시트를 읽는다
(장면 1~6과 같다).

* 앞선 92개 시트 = v0.6(값·수식) — 구현명세 2장 「앞선 92개 시트는 수정하지 않는다」.
* `SC07판단` 5행 — 유효 확인·소요 분·120분·마감·적시 공급·원인 후보(AT701·AT702).
* `SC07검증결과` 8행 — 규칙으로 다시 계산한 관측값이 기대값과 같다. 데이터의 PASS를 옮기지 않는다.
* `SC07요약`·`SC07적용` 판정 — 운영 설정 반영 확인 · 운영 실행 미확인.
* 개발 인수 시험 AT703~AT711의 변형(무효 대행·대행 지정만·누락 사유·경계·마감·정답 차단·확인
  조건·적용 증적).
* 적재 검사 — 고유 키 중복·참조 누락·필수 버전 공란은 DATA_INVALID.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.sc07 import calc, domain
from app.sc07.seed import SEED_PATH, kst, load_seed

V06 = Path(__file__).resolve().parents[1] / "seed" / "SYN-SC06-v0.6.xlsx"
WORDS = {"OVER": "초과", "WITHIN": "기준 내", "UNKNOWN": "미확인"}


@pytest.fixture(scope="module")
def batch() -> dict:
    return domain.load_batch(load_seed())


def test_the_92_earlier_sheets_are_v06_unchanged() -> None:
    """v0.7은 SC07 시트 11개만 더했다 — 앞 시트는 값과 수식까지 v0.6과 같다(EV78 · TC707의 데이터
    쪽)."""
    for data_only in (False, True):
        old = load_workbook(V06, read_only=True, data_only=data_only)
        new = load_workbook(SEED_PATH, read_only=True, data_only=data_only)
        assert new.sheetnames[: len(old.sheetnames)] == old.sheetnames
        assert len(old.sheetnames) == 92
        assert [s for s in new.sheetnames if s not in old.sheetnames] == [
            "SC07요약", "SC07개선", "SC07기준", "SC07버전", "SC07검증입력", "SC07근거",
            "SC07판단", "SC07검증결과", "SC07확인이력", "SC07적용", "SC07화면계약",
        ]  # fmt: skip
        for name in old.sheetnames:
            assert list(old[name].iter_rows(values_only=True)) == list(
                new[name].iter_rows(values_only=True)
            ), name


def test_assessments_match_the_sc07_judgment_sheet(batch: dict) -> None:
    """`SC07판단` 5행 — 규칙 계산이 같은 값을 낸다(AT701 대표 사례 40분·SUPPLY, AT702 내부·복합)."""
    expected = {r["입력 ID"]: r for r in load_seed().rows("SC07판단")}
    assert sorted(expected) == sorted(batch["inputs"])
    for iid, case in batch["inputs"].items():
        a = calc.assess(case, threshold_min=batch["threshold_min"])
        e = expected[iid]
        assert a["confirmed_at"] == kst(e["유효 확인 시각"]), iid
        assert a["elapsed_minutes"] == (e["확인 소요 분"] or None), iid
        assert WORDS[a["deadline_status"]] == e["120분 초과"], iid
        assert WORDS[a["cutoff_status"]] == e["마감 초과"], iid
        assert WORDS[a["supply_status"]] == e["적시 주문도 납기 초과"], iid
        assert a["candidate_cause"] == e["원인 후보"], iid


def test_at701_representative_case(batch: dict) -> None:
    """IN71 — 주담당 공란, 유효 대행 10:00 확인 → 40분, 요구 11/14·적시 공급 11/16 → 조달 제약
    후보."""
    a = calc.assess(batch["inputs"]["IN71"])
    assert (a["confirmed_by"], a["elapsed_minutes"], a["deadline_status"]) == (
        "DEPUTY",
        40,
        "WITHIN",
    )
    assert a["supply_gap_minutes"] == 2 * 24 * 60 and a["candidate_cause"] == "SUPPLY"
    assert batch["inputs"]["IN71"]["evidence_refs"] == ["EV71", "EV72"]


def test_verification_recomputed_matches_the_expected_values(batch: dict) -> None:
    """
    TS71-v1 — 관측값은 규칙으로 다시 계산한다. 8건 모두 기대값과 같고, 데이터의 가상 결과·PASS도
    같다(판정에는
    쓰지 않는다). TC706 정답 차단 · TC707 원본 보존 · TC708 버전 일치는 각각 별도 검사다.
    """
    rows = {r["검증 ID"]: r for r in load_seed().rows("SC07검증결과")}
    results = calc.verify(
        batch["cases"],
        batch["inputs"],
        agent_version="AGT71-v2",
        projection="PR71-v2",
        target_version="AGT71-v2",
        preserved=True,
        threshold_min=120,
        bundle="AGT71-v2/MB71-v2/PR71-v2",
    )
    assert [r["check"] for r in results] == [f"TC70{i}" for i in range(1, 9)]
    for r in results:
        assert r["observed"] == rows[r["check"]]["기대값 (Agent 제외)"], r["check"]
        assert r["observed"] == rows[r["check"]]["가상 결과 / 비교값"], r["check"]
        assert r["status"] == rows[r["check"]]["일치 여부"] == "PASS", r["check"]
    # 검증용 합성 사례는 표시된다(성과 집계에 넣지 않는다)
    assert {c["check"] for c in batch["cases"] if c["fixture"]} == {"TC703", "TC704"}


def test_tc707_and_tc708_fail_when_their_conditions_break(batch: dict) -> None:
    """보존이 깨지거나 적용 대상 버전이 다르면 그 검사만 FAIL — 일부 통과를 전체 통과로 보지
    않는다."""
    results = calc.verify(
        batch["cases"], batch["inputs"], agent_version="AGT71-v2", projection="PR71-v2",
        target_version="AGT71-v3", preserved=False, threshold_min=120, bundle="b",
    )  # fmt: skip
    failed = {r["check"]: r["observed"] for r in results if r["status"] == "FAIL"}
    assert failed == {"TC707": "CHANGED", "TC708": "MISMATCH"}


def test_application_from_the_data_is_setting_reflected_not_executed(batch: dict) -> None:
    """
    `SC07요약`·`SC07적용` 판정 — 검증·두 임원 확인·설정 근거가 맞아 운영 설정 반영 확인(ST707). 운영
    실행은
    미확인이고 실행 id는 없다(AT711).
    """
    doc = {**batch, "clock": None}
    state = domain.planned_state(doc)
    summary = {r["항목"]: r["값 / 상태"] for r in load_seed().rows("SC07요약")}
    assert state["state"] == "ST707" and state["label"] == summary["적용 판단"]
    assert state["label"] == batch["plan"]["verdict"] == "운영 설정 반영 확인"
    assert state["execution_status"] == "NOT_CONFIRMED" and summary["운영 실행"] == "미확인"
    assert state["operation_run_id"] is None and batch["plan"]["operation_run_id"] is None
    assert all(c["ok"] for c in state["checks"]) and len(state["checks"]) == 5
    assert summary["검증 사례 수"] == len(batch["cases"]) == summary["가상 검증 통과 수"]
    assert batch["plan"]["follow_up_by"] == "USR-FIN"
    assert batch["plan"]["follow_up_at"] == "2028-02-11T10:00:00+09:00"


# ─────────────────────────── 개발 인수 시험 변형 ───────────────────────────


def _case(batch: dict, iid: str = "IN71", **change) -> dict:
    return {**copy.deepcopy(batch["inputs"][iid]), **change}


def test_at703_invalid_or_designation_only_deputy_is_not_a_confirmation(batch: dict) -> None:
    """무효 대행(IN73)·대행 지정만 있고 실제 확인 로그가 없는 변형 — 확인 완료로 보지 않는다."""
    a = calc.assess(batch["inputs"]["IN73"])
    assert a["candidate_cause"] == "NEED_EVIDENCE" and a["elapsed_minutes"] is None
    assert [m["reason"] for m in a["missing_fields"]] == ["INVALID_DELEGATION"]
    only = calc.assess(_case(batch, deputy_confirmed_at=None))
    assert only["candidate_cause"] == "NEED_EVIDENCE"
    assert [m["reason"] for m in only["missing_fields"]] == ["NOT_CONFIRMED"]


def test_at704_missing_reasons_are_distinguished_never_zero(batch: dict) -> None:
    """누락·권한 없음·미결합은 사유가 다르고, 0분·정상으로 바꾸지 않는다."""
    a = calc.assess(batch["inputs"]["IN74"])
    assert a["candidate_cause"] == "NEED_EVIDENCE" and a["supply_status"] == "UNKNOWN"
    assert [(m["field"], m["reason"]) for m in a["missing_fields"]] == [
        ("timely_supply_at", "MISSING")
    ]
    for reason in ("ACCESS_DENIED", "NOT_JOINED"):
        b = calc.assess(
            _case(batch, timely_supply_at=None, field_status={"timely_supply_at": reason})
        )
        assert (
            b["missing_fields"][0]["reason"] == reason and b["candidate_cause"] == "NEED_EVIDENCE"
        )
    c = calc.assess(_case(batch, primary_confirmed_at=None, deputy_confirmed_at=None))
    assert c["elapsed_minutes"] is None and c["deadline_status"] == "UNKNOWN"


@pytest.mark.parametrize(
    ("confirmed", "status"),
    [
        ("2027-11-12T11:20:00+09:00", "WITHIN"),  # 120분 — 기준 내
        ("2027-11-12T11:21:00+09:00", "OVER"),  # 121분
        ("2027-11-12T11:20:01+09:00", "OVER"),  # 120분 1초 — 초 단위로 비교한다
    ],
)
def test_at705_threshold_boundary(batch: dict, confirmed: str, status: str) -> None:
    a = calc.assess(_case(batch, deputy_confirmed_at=confirmed))
    assert a["deadline_status"] == status


def test_at705_reshare_does_not_restart_the_clock(batch: dict) -> None:
    """대행자에게 다시 공유한 시각이 있어도 측정은 최초 공유부터다(BR702)."""
    a = calc.assess(_case(batch, reshared_at="2027-11-12T09:50:00+09:00"))
    assert a["elapsed_minutes"] == 40


def test_at706_within_threshold_but_past_cutoff_flags_internal_review(batch: dict) -> None:
    """120분 안이어도 발주 마감을 넘기면 함께 표시하고 내부 영향의 추가 검토를 요청한다."""
    a = calc.assess(
        _case(
            batch,
            deputy_confirmed_at="2027-11-12T10:40:00+09:00",
            order_cutoff_at="2027-11-12T10:30:00+09:00",
        )
    )
    assert (a["deadline_status"], a["cutoff_status"], a["internal_review"]) == (
        "WITHIN",
        "OVER",
        True,
    )


def test_time_reversal_is_data_invalid(batch: dict) -> None:
    """확인이 공유보다 앞이면 오류로 분리하고 원인 판단을 멈춘다."""
    a = calc.assess(_case(batch, deputy_confirmed_at="2027-11-12T09:00:00+09:00"))
    assert a["data_status"] == "DATA_INVALID" and a["candidate_cause"] is None


def test_at707_agent_payload_excludes_answers(batch: dict) -> None:
    """
    실제 페이로드 검사 — 허용 칸만 있고 최종 원인·원인 해설·인적 수정·기대값·사례 이름이 없다.
    정답을 넣은
    변형은 잡힌다(TC706).
    """
    codes = {"SUPPLY", "INTERNAL", "MIXED", "NEED_EVIDENCE"}
    for iid, case in batch["inputs"].items():
        payload = calc.project(case, "PR71-v2", bundle="AGT71-v2")
        assert set(payload) == set(calc.PROJECTIONS["PR71-v2"]), iid
        assert calc.leaks(payload, codes) == [], iid
        assert "합성" not in str(payload), iid
    assert calc.project(batch["inputs"]["IN73"], "PR71-v2")["change_id"] is None
    dirty = {**calc.project(batch["inputs"]["IN71"], "PR71-v2"), "final_cause": "SUPPLY"}
    assert calc.leaks(dirty, codes) == ["금지 칸 final_cause", "기대 원인 SUPPLY"]


def _setting(batch: dict, **change) -> dict:
    plan = batch["plan"]
    return {
        "active_version": plan["target_version"],
        "scope": plan["scope"],
        "evidence_type": "SETTINGS_SNAPSHOT",
        "applied_at": plan["applied_at"],
        "checked_at": plan["checked_at"],
        "check_result": "MATCH",
        **change,
    }


def _state(batch: dict, *, confirmations=None, setting=None, as_of=None, verified=True) -> dict:
    plan = batch["plan"]
    confirmations = (
        confirmations
        if confirmations is not None
        else {
            "EX-BUY": {"state": "CONFIRMED", "version": "AGT71-v2"},
            "USR-CFO": {"state": "CONFIRMED", "version": "AGT71-v2"},
        }
    )
    verification = [{"check": "TC701", "status": "PASS" if verified else "FAIL"}]
    return calc.application_state(
        verification=verification,
        confirmations=confirmations,
        setting=setting if setting is not None else _setting(batch),
        target_version=plan["target_version"],
        scope=plan["scope"],
        as_of=as_of or plan["checked_at"],
    )


def test_at709_confirmation_conditions(batch: dict) -> None:
    """CFO 미확인·역할 중복(같은 역할 두 건)·구버전 확인은 설정 반영 확인이 아니다."""
    buy = {"state": "CONFIRMED", "version": "AGT71-v2"}
    assert _state(batch, confirmations={"EX-BUY": buy})["state"] == "ST704"
    assert _state(batch, confirmations={"EX-BUY": buy, "USR-BUY": buy})["state"] == "ST704"
    old = _state(
        batch,
        confirmations={"EX-BUY": buy, "USR-CFO": {"state": "CONFIRMED", "version": "AGT71-v1"}},
    )
    assert old["state"] == "ST704" and old["attention"] == ["VERSION_MISMATCH"]
    assert _state(batch, verified=False)["state"] == "ST703"


def test_at710_application_evidence(batch: dict) -> None:
    """예약만 · 버전/범위 불일치 · 미래 시각은 예정 또는 확인 필요다 — 실행 완료 표시는 없다."""
    reserved = _state(batch, setting=_setting(batch, evidence_type="RESERVED"))
    assert reserved["state"] == "ST705" and reserved["reserved_only"]
    other = _state(batch, setting=_setting(batch, active_version="AGT71-v1"))
    assert other["state"] == "ST706" and "VERSION_MISMATCH" in other["attention"]
    scope = _state(batch, setting=_setting(batch, scope="전체 Agent"))
    assert scope["state"] == "ST706" and scope["attention"] == ["SCOPE_MISMATCH"]
    future = _state(batch, as_of="2028-01-25T09:30:00+09:00")
    assert future["state"] == "ST706"
    unchecked = _state(batch, setting=_setting(batch, checked_at=None, check_result=None))
    assert unchecked["state"] == "ST706"
    for s in (reserved, other, scope, future, unchecked):
        assert s["execution_status"] == "NOT_CONFIRMED" and not s["setting_reflected"]


# ─────────────────────────── 적재 검사 ───────────────────────────


def _rows(sheet: str) -> list[dict]:
    return copy.deepcopy(load_seed().rows(sheet))


def test_duplicate_key_missing_reference_and_blank_version_are_data_invalid() -> None:
    seed = load_seed()
    dup = _rows("SC07검증입력")
    dup.append(dict(dup[0]))
    with pytest.raises(domain.ReadError) as a:
        domain.load_batch(seed, {"SC07검증입력": dup})
    assert a.value.code == "DATA_INVALID" and "중복" in str(a.value)
    cases = _rows("SC07검증결과")
    cases[0]["입력 / 증적"] = "IN79"
    with pytest.raises(domain.ReadError) as b:
        domain.load_batch(seed, {"SC07검증결과": cases})
    assert "참조 누락" in str(b.value)
    versions = _rows("SC07버전")
    next(v for v in versions if v["식별자"] == "AGT71")["버전 / 값"] = None
    with pytest.raises(domain.ReadError) as c:
        domain.load_batch(seed, {"SC07버전": versions})
    assert "AGT71" in str(c.value)
    confirmations = _rows("SC07확인이력")
    confirmations[1]["대상 버전"] = ""
    with pytest.raises(domain.ReadError):
        domain.load_batch(seed, {"SC07확인이력": confirmations})


def test_times_are_kst_wall_clock_and_blanks_stay_null(batch: dict) -> None:
    """엑셀 시각은 KST 현지 시각으로 읽는다(UTC로 읽고 9시간을 더하지 않는다). 공란은 null이다."""
    assert batch["inputs"]["IN71"]["shared_at"] == "2027-11-12T09:20:00+09:00"
    assert batch["inputs"]["IN71"]["primary_confirmed_at"] is None
    assert batch["schedule"]["CF71"]["at"] == "2028-01-24T10:00:00+09:00"
    assert batch["schedule"]["CF72"]["at"] == "2028-01-24T15:00:00+09:00"
    assert batch["plan"]["applied_at"] == "2028-01-25T09:00:00+09:00"
    assert (
        batch["bundle"]["agent"] == "AGT71-v2" and batch["bundle"]["agent_previous"] == "AGT71-v1"
    )
    assert batch["threshold_min"] == 120
