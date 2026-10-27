"""
SC03 규칙 계산 — 물량(장면 1)·승인 단가(장면 2)의 통합 손익영향과 목표 부족 분리(구현명세 8장,
M31~M37).

**숫자는 여기서만 만든다**(P39). Agent는 이 결과를 인용만 하고, BPM은 순서만 쥔다.

* **장면 2 계산을 다시 쓴다** — 월·모델별 F01·F02 공헌이익과 승인 단가의 원가 효과는
  `app.sc02.calc.monthly_rows`가 낸다(F02 물량에 승인 단가를 적용 — 교차효과를 따로 더하지 않는다,
  S33).
  요청안·협상안은 합산하지 않는다 — 입력이 승인안 하나다(P35).
* 관리손익 = 모델 CM 합계 − 공장 고정비. **고정비는 공장·월에 한 번만** 차감하고 모델에 배부하지
  않는다
  (P36). 본사비·금융비·세금은 없다.
* 변동 영향은 손익 감소를 음수로, 목표 부족은 양수로 낸다. **기존 부족 − 신규 영향 = 전체
  부족**(CT33).
* 2028 Target은 미설정이다 — 향후 12개월의 Target·부족은 `None`이다(0이 아니다, NEXT37).
* **정합 검증이 계산의 일부다**(CT33). 검증이 하나라도 어긋나면 결과는 `CALCULATION_BLOCKED`이고
  부서
  확인 요청·보고 확정이 막힌다. E33(고정비 중복 계수 2)은 `fixed_multiplier`로 주입한다 — 모델
  합계에서
  따로 잰 값과 어긋나서 드러난다.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from app.sc02 import calc as sc02_calc
from app.sc02.calc import Option, add_months
from app.sc02.seed import MonthRow
from app.sc02.seed import Seed as NumbersSeed

QTY_VERSION = "F02+EXT28-v1"
COST_VERSION = "C02-APP01"
FIXED_VERSION = "FC01/FC28-v1"
PRICE_VERSION = "PV-APP01"

YEAR = (date(2027, 1, 1), date(2028, 1, 1))
#: 화면이 고르는 기간(UI35) — 연간 · Q3 · 잔여 7~12월 · 향후 12개월(2027.7~2028.6)
PERIODS: tuple[tuple[str, str, date, date], ...] = (
    ("year", "2027 연간", *YEAR),
    ("q3", "2027 Q3", date(2027, 7, 1), date(2027, 10, 1)),
    ("remaining", "2027 잔여 7~12월", date(2027, 7, 1), date(2028, 1, 1)),
    ("next12", "향후 12개월 2027.7~2028.6", date(2027, 7, 1), date(2028, 7, 1)),
)


def _months(start: date, end: date) -> list[date]:
    out, m = [], start
    while m < end:
        out.append(m)
        m = add_months(m, 1)
    return out


def _sum(rows: list[dict[str, Any]], key: str) -> Decimal:
    return sum((Decimal(r[key]) for r in rows), Decimal(0))


def models(monthly: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    """모델별 공헌이익 — c~e도 표시한다(UI35). 고정비는 여기에 없다(공장 합계에서만 차감)."""
    out = []
    for model in sorted({m["model_id"] for m in monthly}):
        picked = [
            m
            for m in monthly
            if m["model_id"] == model and start.isoformat() <= m["period"] < end.isoformat()
        ]
        if not picked or any(m["f02_cm"] is None for m in picked):
            out.append({"model_id": model, "computable": False})
            continue
        f01 = _sum(picked, "f01_cm")
        vol = _sum(picked, "volume")
        cost = _sum(picked, "cost")
        out.append(
            {
                "model_id": model,
                "computable": True,
                "f01_qty": sum(m["f01"] for m in picked),
                "f02_qty": sum(m["f02"] for m in picked),
                "cm_f01": str(f01),
                "volume_effect": str(vol),
                "cost_effect": str(cost),
                "cm_combined": str(f01 + vol + cost),
            }
        )
    return out


def period(
    monthly: list[dict[str, Any]],
    seed: NumbersSeed,
    kind: str,
    label: str,
    start: date,
    end: date,
    *,
    fixed_multiplier: int = 1,
) -> dict[str, Any]:
    """
    기간 하나 — Target → F01 → 물량 → 승인 단가 → 통합. 기간 안의 원천을 그대로 집계한다(연간 값을
    나누지 않는다). 정합 검증 세 줄을 같이 낸다.
    """
    picked = [m for m in monthly if start.isoformat() <= m["period"] < end.isoformat()]
    months = _months(start, end)
    base = {"kind": kind, "label": label, "from": start.isoformat(), "to": end.isoformat()}
    complete = (
        len(picked) == len(months) * len(seed.models)
        and all(m["f02_cm"] is not None for m in picked)
        and all(p in seed.fixed for p in months)
    )
    if not complete:
        return {**base, "computable": False, "reason": "기간 안의 물량·원가·고정비가 완전하지 않다"}
    fixed = sum((seed.fixed[p] for p in months), Decimal(0))
    applied = fixed * fixed_multiplier  # E33 — 고정비 중복 입력
    f01 = _sum(picked, "f01_cm") - applied
    volume = _sum(picked, "volume")
    cost = _sum(picked, "cost")
    combined = _sum(picked, "f02_cm") - applied + cost
    has_target = all(m["target_cm"] is not None for m in picked)
    target = _sum(picked, "target_cm") - applied if has_target else None
    event = volume + cost
    by_model = models(monthly, start, end)
    model_sum = sum((Decimal(m["cm_combined"]) for m in by_model), Decimal(0))
    existing_gap = None if target is None else target - f01
    total_gap = None if target is None else target - combined
    checks = [
        {
            "check_id": "CT33-1",
            "label": "모델 CM 합계 − 공장 고정비(한 번) = 관리손익",
            "diff": str(model_sum - fixed - combined),
        },
        {
            "check_id": "CT33-2",
            "label": "F01 + 물량 영향 + 단가 영향 = 통합 관리손익",
            "diff": str(f01 + volume + cost - combined),
        },
    ]
    if target is not None:
        checks.append(
            {
                "check_id": "CT33-3",
                "label": "기존 부족 − 신규 사건 영향 = 전체 부족",
                "diff": str(existing_gap - event - total_gap),  # type: ignore[operator]
            }
        )
    for c in checks:
        c["ok"] = Decimal(c["diff"]) == 0
    return {
        **base,
        "computable": True,
        "fixed": str(fixed),
        "fixed_applied": str(applied),
        "target": None if target is None else str(target),
        "f01": str(f01),
        "volume_profit": str(f01 + volume),
        "volume_effect": str(volume),
        "cost_effect": str(cost),
        "event_effect": str(event),
        "combined": str(combined),
        # 목표 부족은 양수 — 기존 부족(사건 이전)과 전체 부족을 따로 둔다(M31·M32)
        "existing_gap": None if existing_gap is None else str(existing_gap),
        "total_gap": None if total_gap is None else str(total_gap),
        "models": by_model,
        "checks": checks,
    }


def integrated(
    seed: NumbersSeed,
    option: Option,
    *,
    rows: list[MonthRow] | None = None,
    fixed_multiplier: int = 1,
) -> dict[str, Any]:
    """
    통합 분석 한 번(RUN-SC03-xx). `option`은 장면 2의 **승인안**이다 — 단가·적용일은 승인 기록에서
    읽는다
    (구현명세 3장). `rows`는 새 전망 버전(E34)처럼 물량을 바꾼 표다 — 주지 않으면 기본 F02다.
    """
    rows = list(seed.rows if rows is None else rows)
    monthly = sc02_calc.monthly_rows(rows, seed, option)
    periods = {
        kind: period(monthly, seed, kind, label, s, e, fixed_multiplier=fixed_multiplier)
        for kind, label, s, e in PERIODS
    }
    months = [
        period(
            monthly,
            seed,
            "month",
            f"{m.year}-{m.month:02d}",
            m,
            add_months(m, 1),
            fixed_multiplier=fixed_multiplier,
        )
        for m in _months(date(2027, 7, 1), date(2028, 1, 1))
    ]
    # 구매 증가(M36)는 손익과 다른 지표다 — 장면 2 분석이 낸 값을 그대로 싣는다(혼용 금지).
    price = sc02_calc.analyze(seed, option, rows=rows)
    checks = [c for p in periods.values() if p["computable"] for c in p["checks"]]
    computable = all(p["computable"] for p in periods.values())
    passed = computable and all(c["ok"] for c in checks)
    b7 = next((m for m in monthly if m["period"] == "2027-07-01" and m["model_id"] == "A-b"), None)
    return {
        "basis": {
            "quantity": QTY_VERSION,
            "cost": COST_VERSION,
            "fixed": FIXED_VERSION,
            "price_version": option.version_id,
            "old_price": str(option.old_price),
            "approved_price": None if option.new_price is None else str(option.new_price),
            "effective_date": option.effective.isoformat(),
        },
        "fixed_multiplier": fixed_multiplier,
        "status": "CALCULATED" if passed else "CALCULATION_BLOCKED",
        "computable": computable,
        "passed": passed,
        "failed_checks": [
            f"{c['check_id']} {c['label']} (차이 {c['diff']}원)" for c in checks if not c["ok"]
        ],
        "periods": periods,
        "months": months,
        "purchase": {
            "remaining_increase": price["remaining"]["increase"],
            "remaining_qty": price["remaining"]["purchase_qty"],
            "next12_increase": price["next12"]["increase"],
            "next12_qty": price["next12"]["purchase_qty"],
        },
        "b_july": None
        if b7 is None
        else {"f01": b7["f01"], "f02": b7["f02"], "unit_cm": b7["unit_cm"]},
        "assumptions": [
            "Target은 이번 사건으로 바꾸지 않는다(UNCHANGED)",
            "2028 물량은 2027 동일월 F01 × 97% 정수 반올림 — 내부가정, 고객 확정 계획이 아니다",
            "b모델 7월 추가 700대분 감소를 2028에 복제하지 않는다",
            "재고·기발주·구매·생산·납품 시차 없음 — 구매 증가와 CM 감소의 대응은 이 가정에 한한다",
            "향후 12개월 Target은 미설정 — 부족액은 미산정이다",
            "공장관리손익은 전사 영업이익이 아니다(본사비·금융비·세금 제외)",
        ],
    }


def compare(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    """두 분석의 기간별 통합 관리손익 차이 — 새 전망 버전(E34)의 변경 요약."""
    out = []
    for kind, label, _s, _e in PERIODS:
        a, b = old["periods"][kind], new["periods"][kind]
        if not (a["computable"] and b["computable"]):
            continue
        out.append(
            {
                "kind": kind,
                "label": label,
                "before": a["combined"],
                "after": b["combined"],
                "diff": str(Decimal(b["combined"]) - Decimal(a["combined"])),
            }
        )
    return out
