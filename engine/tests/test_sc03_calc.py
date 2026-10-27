"""
SC03 규칙 계산 — 통합가상데이터 v0.3의 **파생 시트와 대조**한다(구현명세 8장 · 14장 T32·T40).

시드는 원천 시트만 읽는다(`app/sc03/seed.py` → 장면 2와 같은 원천). 여기서는 파생 시트(통합손익 ·
통합모델손익 · SC03검증 · SC03영업시간)를 따로 읽어 계산이 같은 값을 내는지 본다 — 숫자를 시험에
옮겨
적지 않는다(장면 1·2와 같은 원칙). 시트에 없는 검수용 변형(E33·E34)만 명세의 값을 쓴다.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.sc02.calc import Option
from app.sc02.seed import load_seed as load_sc02_seed
from app.sc03 import calc
from app.sc03.domain import business_hours
from app.sc03.seed import kst, load_seed

#: 화면 기간 → 통합손익 시트의 기간 이름
SHEET_PERIOD = {
    "year": "2027 연간",
    "q3": "2027 Q3",
    "remaining": "2027 잔여",
    "next12": "향후12개월",
}


def approved() -> Option:
    s = load_seed().numbers
    return Option(
        "PV-APP01",
        "APPROVED",
        "P-COM01",
        "SUP-01",
        s.setting_decimal("old_price"),
        s.setting_decimal("approved_price"),
        s.setting_date("effective_date"),
    )


def result(**kwargs) -> dict:
    return calc.integrated(load_seed().numbers, approved(), **kwargs)


def sheet_row(period: str) -> dict:
    return next(r for r in load_seed().rows("통합손익") if r["기간"] == period)


def test_numbers_come_from_the_same_source_sheets_as_scene_2() -> None:
    """v0.3은 장면 2의 원천 시트를 그대로 둔다 — 물량·고정비·설정·매핑이 v0.2와 같다(NEXT35)."""
    v3, v2 = load_seed().numbers, load_sc02_seed()
    assert v3.rows == v2.rows
    assert v3.fixed == v2.fixed
    assert v3.parts == v2.parts
    assert v3.settings == v2.settings


@pytest.mark.parametrize("kind", list(SHEET_PERIOD))
def test_period_bridge_matches_the_combined_sheet(kind: str) -> None:
    """T32 — 연간·Q3·잔여·12개월이 통합손익 시트와 원 단위로 같다. 12개월 Target은 NULL이다."""
    p = result()["periods"][kind]
    row = sheet_row(SHEET_PERIOD[kind])
    assert p["computable"]
    for key, col in [
        ("fixed", "공장고정비"),
        ("f01", "F01기준손익"),
        ("volume_profit", "물량반영손익"),
        ("volume_effect", "장면1물량영향"),
        ("cost_effect", "장면2원가영향"),
        ("combined", "통합손익"),
        ("event_effect", "전체변동"),
    ]:
        assert Decimal(p[key]) == row[col], (kind, key)
    if row["Target손익"] is None:
        assert p["target"] is None and p["total_gap"] is None and p["existing_gap"] is None
    else:
        assert Decimal(p["target"]) == row["Target손익"]
        assert Decimal(p["total_gap"]) == row["Target부족"]
        # 기존 부족 = Target − F01 (M32)
        assert Decimal(p["existing_gap"]) == row["Target손익"] - row["F01기준손익"]
    assert all(c["ok"] for c in p["checks"])


def test_existing_gap_and_new_event_impact_are_separate() -> None:
    """
    M31·M32·M35 · V39 — 기존 부족 153,939,000 − 신규 영향 −23,364,320 = 전체 부족 177,303,320.
    두 사건을 해소해도 목표를 다 메우지 못한다(QA31·QA32).
    """
    year = result()["periods"]["year"]
    checks = load_seed().by_id("SC03검증")
    assert Decimal(year["combined"]) == checks["V31"]["actual"]
    assert Decimal(year["total_gap"]) == checks["V32"]["actual"]
    assert (
        Decimal(year["existing_gap"]) - Decimal(year["event_effect"]) - Decimal(year["total_gap"])
        == checks["V39"]["actual"]
        == 0
    )
    assert Decimal(year["event_effect"]) == Decimal(year["volume_effect"]) + Decimal(
        year["cost_effect"]
    )


def test_q3_models_match_and_fixed_cost_is_not_allocated() -> None:
    """통합모델손익 — a~e 모델 CM. c~e도 표시하고, 고정비는 공장 합계에서만 차감한다(P36)."""
    got = {m["model_id"]: m for m in result()["periods"]["q3"]["models"]}
    for row in load_seed().rows("통합모델손익"):
        m = got[row["2027 Q3 모델"]]
        assert Decimal(m["cm_f01"]) == row["F01 공헌이익"]
        assert Decimal(m["volume_effect"]) == row["물량영향"]
        assert Decimal(m["cost_effect"]) == row["원가영향"]
        assert Decimal(m["cm_combined"]) == row["통합 공헌이익"]
        assert "fixed" not in m
    q3 = result()["periods"]["q3"]
    model_sum = sum(Decimal(m["cm_combined"]) for m in q3["models"])
    assert model_sum - Decimal(q3["fixed"]) == Decimal(q3["combined"])


def test_purchase_increase_is_a_different_metric_from_profit() -> None:
    """M36 — 향후 12개월 구매 증가 156,812개 × 120원 = 18,817,440원(잔여연도 손익 영향과 따로)."""
    r = result()
    assert r["purchase"]["next12_qty"] == 156812
    assert r["purchase"]["next12_increase"] == "18817440"
    assert r["purchase"]["remaining_increase"] == "9364320"
    assert r["b_july"] == {"f01": 9500, "f02": 8800, "unit_cm": "20000"}
    assert r["basis"]["approved_price"] == "2120" and r["basis"]["effective_date"] == "2027-07-01"


def test_e33_double_fixed_cost_blocks_the_calculation() -> None:
    """E33 — 고정비 중복 계수 2. 모델 합계에서 따로 잰 값과 어긋나 정합
    실패(CALCULATION_BLOCKED)."""
    r = result(fixed_multiplier=2)
    assert r["status"] == "CALCULATION_BLOCKED" and not r["passed"]
    assert any(f.startswith("CT33-1") for f in r["failed_checks"])
    assert result()["status"] == "CALCULATED"


def test_e34_new_forecast_is_a_separate_version() -> None:
    """E34 — b 7월 8,800 → 8,700. 승인 후 단위 CM 19,880원 × 100 = 1,988,000원 추가 감소."""
    seed = load_seed().numbers
    rows = [
        replace(r, f02=8700) if (r.period, r.model_id) == (date(2027, 7, 1), "A-b") else r
        for r in seed.rows
    ]
    new = calc.integrated(seed, approved(), rows=rows)
    assert new["periods"]["year"]["combined"] == "3297998680"
    [year] = [c for c in calc.compare(result(), new) if c["kind"] == "year"]
    assert year["diff"] == "-1988000"
    # 기본 F02는 그대로다
    assert result()["periods"]["year"]["combined"] == "3299986680"


def test_business_hours_follow_the_demo_calendar() -> None:
    """V40·V41 · CAL-DEMO01 — 착수 6/24 10:05 ~ 완료 6/30 11:30, 경과 145h25m · 영업 37h25m."""
    checks = load_seed().by_id("SC03검증")
    start, end = "2027-06-24T10:05:00+09:00", "2027-06-30T11:30:00+09:00"
    assert round(float(business_hours(start, end)), 6) == round(checks["V40"]["expected"], 6)
    days = load_seed().rows("SC03영업시간")
    by_day = {kst(r["date_KST"])[:10]: r["elapsed_business_hours"] for r in days}  # type: ignore[index]
    assert round(by_day["2027-06-24"], 4) == round(
        float(business_hours(start, "2027-06-24T18:00:00+09:00")), 4
    )


def test_excel_times_are_kst_wall_clock_rounded_to_the_second() -> None:
    """구현명세 9장 — 10:21:59.999는 10:22:00이다. UTC로 오인해 9시간 옮기지 않는다."""
    qa33 = load_seed().by_id("SC03회의")["QA33"]
    assert kst(qa33["event_at"]) == "2027-06-29T10:22:00+09:00"
    assert kst(None) is None
