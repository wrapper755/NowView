"""
SC04 규칙 계산 — 통합가상데이터 v0.4의 파생 시트(SC04월효과·SC04월손익·SC04비교·SC04검증)와
대조한다.

값을 시험에 옮겨 적지 않는다 — 기대값은 엑셀에서 읽는다(장면 1~3과 같다). 시트에 없는
검수값(T403·E401·E402·
E403·E407)은 구현명세 17장의 숫자다.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.sc02.calc import Option
from app.sc02.seed import load_seed as load_sc02_seed
from app.sc03.seed import load_seed as load_sc03_seed
from app.sc04 import calc
from app.sc04.seed import SEED_PATH, load_seed

SEED = load_seed()
OPTION = Option(
    "PV-APP01", "APPROVED", "P-COM01", "SUP-01", Decimal(2000), Decimal(2120), date(2027, 7, 1)
)
BASE = calc.baseline(SEED.numbers, OPTION)


def _assumptions(**changes) -> list[dict]:
    out = [calc.assumption_from_row(r) for r in SEED.rows("SC04가정")]
    for alt, fields in changes.items():
        a = next(x for x in out if x["alt_id"] == alt)
        a.update(fields)
    return out


def report_run() -> dict:
    return calc.run(_assumptions(), BASE, SEED.numbers)


def decision_run(**extra) -> dict:
    return calc.run(
        _assumptions(ALT42={"start": "2027-09-01"}, **extra),
        BASE,
        SEED.numbers,
        conditional=["ALT42"],
    )


def _won(v) -> Decimal:
    return Decimal(str(v))


def test_numbers_sheets_are_the_same_as_v03() -> None:
    """v0.4는 v0.3 숫자 시트를 그대로 둔다(검토요약만 갈았다) — 장면 1~3 결과가 바뀌지 않는다."""
    v04 = load_sc02_seed(SEED_PATH)
    v03 = load_sc03_seed().numbers
    assert SEED_PATH.name == "SYN-SC04-v0.4.xlsx"
    assert v04.rows == v03.rows and v04.fixed == v03.fixed and v04.parts == v03.parts


def test_baseline_is_the_sc03_integrated_profit() -> None:
    """
    CK401 — 장면 3 기준 손익을 같은 원천·같은 계산으로 다시 낸다. 월별 Target·기준이 SC04월손익과
    같다.
    """
    rows = {r["기간"].date().isoformat(): r for r in SEED.rows("SC04월손익")[:12]}
    for b in BASE:
        r = rows[b["period"]]
        assert (_won(b["target"]), _won(b["base"])) == (_won(r["Target"]), _won(r["SC03기준손익"]))
    total = sum(_won(b["base"]) for b in BASE)
    check = SEED.by_id("SC04검증")["CK401"]
    assert total == _won(check["기대값"])


@pytest.mark.parametrize(
    ("version", "make"), [("REP41-v1", report_run), ("DEC41-v2", decision_run)]
)
def test_every_effect_line_matches_the_monthly_effect_sheet(version, make) -> None:
    """
    SC04월효과 36행 — 대상량·회피액·추가
    거래비·물류비·지원비·일회성비·초안할인·중복제거·순효과·고정비 절감.
    """
    lines = {(x["alt_id"], x["month"]): x for x in make()["lines"]}
    cols = {
        "qty": "대상량",
        "avoided": "회피액",
        "added": "추가거래비",
        "logistics": "추가물류비",
        "support": "운영지원비",
        "one_off": "일회성비",
        "draft_discount": "초안할인",
        "duplicate": "중복제거",
        "net": "최종순효과",
        "fixed_saving": "고정비절감",
    }
    rows = [r for r in SEED.rows("SC04월효과") if r["판단버전"] == version]
    assert len(rows) == 18
    for r in rows:
        x = lines[(r["대안ID"], r["월"].date().isoformat())]
        assert x["start"] == r["적용시작"].date().isoformat(), r["row_id"]
        assert x["applied"] == bool(r["적용여부"]), r["row_id"]
        for key, col in cols.items():
            assert _won(x[key]) == _won(r[col]), (r["row_id"], key)


def test_t402_report_and_decision_totals_and_periods() -> None:
    """
    T402 — 137,200,000 / 127,800,000원. 월·기간 합계가 SC04월손익과 원 단위로 같다. 두 버전을
    합산하지 않는다.
    """
    rep, dec = report_run(), decision_run()
    assert (rep["effect_total"], dec["effect_total"]) == ("137200000", "127800000")
    sheet = {str(r["기간"]): r for r in SEED.rows("SC04월손익")}
    for m_rep, m_dec in zip(rep["months"], dec["months"], strict=True):
        r = next(v for k, v in sheet.items() if k.startswith(m_rep["period"]))
        assert _won(m_rep["effect"]) == _won(r["보고순효과"])
        assert _won(m_dec["effect"]) == _won(r["판단순효과"])
    for kind, label in (
        ("year", "2027 연간"),
        ("q3", "2027 Q3"),
        ("q4", "2027 Q4"),
        ("remaining", "2027 잔여7~12월"),
    ):
        r = sheet[label]
        p_rep, p_dec = rep["periods"][kind], dec["periods"][kind]
        assert _won(p_rep["effect"]) == _won(r["보고순효과"]), kind
        assert _won(p_rep["forecast"]) == _won(r["보고후전망"]), kind
        assert _won(p_dec["effect"]) == _won(r["판단순효과"]), kind
        assert _won(p_dec["forecast"]) == _won(r["판단후전망"]), kind
        assert _won(p_dec["gap"]) == _won(r["잔여부족"]), kind
        assert _won(p_dec["forecast_excl_conditional"]) == _won(r["조건부제외전망"]), kind
        assert _won(p_dec["gap_excl_conditional"]) == _won(r["조건부제외부족"]), kind


def test_t416_q4_target_surplus_stays_negative() -> None:
    """T416 — Q4 부족 −34,278,880원은 목표 초과다. 0으로 자르지 않는다. 연간은 49,503,320원 미달."""
    dec = decision_run()["periods"]
    assert dec["q4"]["gap"] == "-34278880"
    assert dec["remaining"]["gap"] == "-3996680"
    assert dec["year"]["gap"] == "49503320"
    assert dec["year"]["gap_before"] == "177303320"


def test_comparison_sheet_and_normal_annual() -> None:
    """
    SC04비교·CK408 — 대안별 보고·판단 효과, 회의 조정 −9,400,000원, 정상 연간 357,600,000원(합산
    금지).
    """
    rep = {a["alt_id"]: a for a in report_run()["alts"]}
    dec = {a["alt_id"]: a for a in decision_run()["alts"]}
    for alt, row in SEED.by_id("SC04비교").items():
        if not alt.startswith("ALT"):
            continue
        assert _won(rep[alt]["net_2027"]) == _won(row["보고효과"]), alt
        assert _won(dec[alt]["net_2027"]) == _won(row["판단효과"]), alt
        assert _won(dec[alt]["normal_annual"]) == _won(row["정상연효과"]), alt
    assert decision_run()["normal_annual_total"] == "357600000"
    diff = calc.diff(report_run(), decision_run())
    assert [(d["alt_id"], d["diff"]) for d in diff] == [
        ("ALT41", "0"),
        ("ALT42", "-9400000"),
        ("ALT43", "0"),
    ]


def test_check_sheet_values() -> None:
    """SC04검증 — 판단 중복제거 1,800,000원, 고정비 절감 0, 잔여 부족·조건부 제외 부족."""
    dec = decision_run()
    checks = SEED.by_id("SC04검증")
    assert _won(dec["duplicate_total"]) == _won(checks["CK411"]["기대값"])
    assert dec["fixed_saving_total"] == "0" == str(checks["CK412"]["기대값"])
    assert _won(dec["periods"]["year"]["gap"]) == _won(checks["CK406"]["기대값"])
    assert _won(dec["periods"]["year"]["gap_excl_conditional"]) == _won(checks["CK407"]["기대값"])
    assert dec["fixed_cost_monthly"] == "370000000"


def test_t403_alt41_quantity_change_recalculates() -> None:
    """
    T403 — ALT41 월량 3,000 → 2,900이면 판단효과 124,800,000원·부족 52,503,320원(같은 계산 규칙).
    """
    dec = decision_run(ALT41={"monthly_qty": 2900})
    assert dec["effect_total"] == "124800000"
    assert dec["periods"]["year"]["gap"] == "52503320"


def test_t404_e401_depreciation_as_saving_is_blocked() -> None:
    """
    E401 — 기존 감가상각비 120백만원/월을 회피로 넣으면 검증 차단. 기준 고정비 370백만원은 그대로다.
    """
    run = calc.run(_assumptions(ALT41={"avoided_fixed": "120000000"}), BASE, SEED.numbers)
    assert not run["passed"]
    assert [e["code"] for e in run["errors"]] == ["FIXED_COST_NOT_AVOIDABLE"]
    assert run["errors"][0]["amount"] == "600000000"  # 8~12월
    assert run["fixed_cost_monthly"] == "370000000"
    assert sum(_won(b["base"]) for b in BASE) == sum(_won(b["base"]) for b in run["months"])


def test_t405_e402_duplicate_not_removed_is_blocked() -> None:
    """E402 — 10~12월 중복제거를 0으로 두면 1,800,000원 중복 검출, 보고 확정 차단."""
    zero = {m.isoformat(): "0" for m in calc.EFFECT_MONTHS[3:]}
    run = calc.run(_assumptions(ALT42={"duplicate_override": zero}), BASE, SEED.numbers)
    assert [e["code"] for e in run["errors"]] == ["DUPLICATE_NOT_REMOVED"]
    assert run["errors"][0]["amount"] == str(SEED.by_id("SC04예외")["E402"]["수치 기대값"])


def test_t406_e403_hold_alt43_changes_the_approved_scope() -> None:
    """E403 — ALT43 보류면 승인 범위 효과 121,600,000원, 부족 55,703,320원."""
    run = calc.run(
        _assumptions(ALT42={"start": "2027-09-01"}),
        BASE,
        SEED.numbers,
        include=["ALT41", "ALT42"],
        conditional=["ALT42"],
    )
    assert run["effect_total"] == str(SEED.by_id("SC04예외")["E403"]["수치 기대값"])
    assert run["periods"]["year"]["gap"] == "55703320"


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"ALT41": {"monthly_qty": 3500}}, "QTY_OVER_FORECAST"),  # 8월 A-a 전망 3,496
        ({"ALT41": {"avoid_price": "21000"}}, "AVOID_OVER_COST"),  # 변동가공비 20,000
        ({"ALT42": {"emergency_after": 13}}, "EMERGENCY_REVERSED"),
        ({"ALT43": {"one_off_cost": None}}, "ONE_OFF_MISSING"),
    ],
)
def test_ct402_input_limits_block(change, code) -> None:
    """
    CT402 — 적용량은 그 모델·월 전망 이하, 회피단가는 원 단위원가 이하, 긴급 after ≤ before,
    일회성비 필수.
    """
    run = calc.run(_assumptions(**change), BASE, SEED.numbers)
    assert code in [e["code"] for e in run["errors"]]


def test_start_must_be_the_first_of_a_month() -> None:
    """적용 시작은 월 첫날만 — Pilot은 일할 계산하지 않는다."""
    with pytest.raises(ValueError):
        calc.normalize("start", "2027-09-15")
    assert calc.normalize("start", "2027-09-01T00:00:00+09:00") == "2027-09-01"


def test_e407_budget_policy_lookups() -> None:
    """
    E407 — 1백만원 전용은 전체 책임 임원 승인(총괄 18백만원 유지), 총괄 19백만원은 대표 별도 승인.
    거래 없음.
    """
    total = Decimal(18_000_000)
    alloc = {"ACT41": Decimal(8_000_000), "ACT42": Decimal(6_000_000), "ACT43": Decimal(4_000_000)}
    a = calc.budget_policy(total, alloc, {"kind": "transfer", "from": "ACT41", "amount": "1000000"})
    assert a["allowed"] and a["approver"] == "경영관리임원" and a["total_after"] == "18000000"
    b = calc.budget_policy(total, alloc, {"kind": "total", "amount": "19000000"})
    assert not b["allowed"] and b["approver"] == "대표이사"
    assert sum(alloc.values()) == total  # CK409
