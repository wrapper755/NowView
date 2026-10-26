"""
SC02 규칙 계산 — 구매 증가·위험·승인선(CALC-21·M21~M25), 장면 1·2 손익 연결(CALC-22~24·M27).

**숫자는 여기서만 만든다**(AG-21). BPM은 순서만, Agent는 이 결과를 인용만 한다.

* 금액은 원 단위 `Decimal`, 수량은 정수다. 계산값을 맞추려고 반올림하지 않는다(DATA-23).
* **경계는 나눗셈 없이 비교한다**(CALC-25) — `단가차이 ≥ 기존단가 × 임계값`. 장면 1의 비율 8자리
  반올림(CALC-02)을 그대로 가져오지 않는다.
* **기간은 시작 포함·종료 제외**다(PERIOD-01). 잔여기간은 [적용일, 다음 해 1/1), 향후 12개월은
  [적용일, 적용일 + 12개월). 월중 적용일은 일별 자료가 없어 확정 분석을 막는다.
* **누락은 0이 아니다**(DATA-21 표). 12개월 창에 5모델 × 12개월이 다 있어야 12개월 금액이 나온다 —
  없으면 미산출이고, 미산출 금액으로 대표 비대상을 판정하지 않는다(X09).
* 위험 규칙 R02-v1과 승인권한 AUTH02-v1은 **같은 12개월 구매 증가액을 쓰지만 서로 다른 판단**이다
  (NEXT02·AUTH-02). 위험이 중요라고 대표를 더하지 않고, 대표 비대상이라고 경영검토를 빼지 않는다.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.sc01.calc import Risk
from app.sc02.seed import MonthRow, PartLink, Seed

RULE_VERSION = "R02-v1"
AUTHORITY_VERSION = "AUTH02-v1"
QTY_VERSION = "F02+EXT28-v1"
COST_VERSION = "C01"
FIXED_VERSION = "FC01+FC28-v1"
_ORDER = [Risk.NORMAL, Risk.ATTENTION, Risk.CRITICAL]


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, 1)


def _months(start: date, end: date) -> list[date]:
    out, m = [], date(start.year, start.month, 1)
    while m < end:
        out.append(m)
        m = add_months(m, 1)
    return out


@dataclass(frozen=True)
class Option:
    """단가안 하나 — 요청안·내부제시안·협상안·기안안·승인안(SC02-07). 서로 합산하지 않는다."""

    version_id: str
    kind: str
    part_id: str
    supplier_id: str
    old_price: Decimal
    new_price: Decimal | None  # None = 협상 미합의(X06) — 0원이 아니다
    effective: date


# ─────────────────────────── 판정 규칙 (R02-v1 · AUTH02-v1) ───────────────────────────


def _level(value: Decimal, attention: Decimal, critical: Decimal) -> Risk:
    # 임계값 이상(≥)이면 그 수준이다 — 경계 포함(설정 「정확히 경계값 포함」).
    if value >= critical:
        return Risk.CRITICAL
    if value >= attention:
        return Risk.ATTENTION
    return Risk.NORMAL


def rate_level(old: Decimal, new: Decimal, settings: Mapping[str, Any]) -> Risk | None:
    """M21 품목 인상률 위험. 기존 단가 0이면 미산출(None) — 신규 거래로 따로 본다."""
    if old == 0:
        return None
    diff = new - old
    # 나눗셈 없이 비교한다(CALC-25): diff/old ≥ t  ⇔  diff ≥ old × t (old > 0)
    if diff >= old * Decimal(str(settings["rate_critical"])):
        return Risk.CRITICAL
    if diff >= old * Decimal(str(settings["rate_attention"])):
        return Risk.ATTENTION
    return Risk.NORMAL


def amount_level(increase12: Decimal | None, settings: Mapping[str, Any]) -> Risk | None:
    """요청건 향후 12개월 구매 증가액 위험(DEC28). 미산출이면 판정 보류."""
    if increase12 is None:
        return None
    return _level(
        increase12,
        Decimal(str(settings["amount_attention"])),
        Decimal(str(settings["amount_critical"])),
    )


def combined_level(levels: Iterable[Risk | None]) -> Risk | None:
    """비율과 금액 중 **높은 수준**(X08). 하나라도 미산출이면 종합 판정 보류(DATA-21)."""
    found = list(levels)
    if not found or any(x is None for x in found):
        return None
    return max(found, key=_ORDER.index)  # type: ignore[arg-type]


def ceo_required(increase12: Decimal | None, settings: Mapping[str, Any]) -> bool | None:
    """
    AUTH02-v1 — 최종 기안의 향후 12개월 구매 증가액(VAT 제외·공급사 요청건 부품 합계) ≥ 기준이면
    대표 승인 대상. **원 단위로 정확히 비교한다**(X03: 9,999,999 비대상 · 10,000,000 대상).
    미산출이면 None — 판정 보류다. 미확정 금액으로 비대상 처리하지 않는다.
    """
    if increase12 is None:
        return None
    return increase12 >= Decimal(str(settings["ceo_threshold"]))


def ratio(old: Decimal, new: Decimal) -> Decimal | None:
    """표시용 인상률(정밀값). 판정은 `rate_level`이 나눗셈 없이 한다."""
    if old == 0:
        return None
    return (new - old) / old


# ─────────────────────────── 자료 검사 (DATA-21 · ERR-23) ───────────────────────────


@dataclass(frozen=True)
class Problem:
    """계산을 막는 자료 문제 — 필드와 조치 방법을 함께 낸다(ERR-23). 서버 오류로 뭉치지 않는다."""

    code: str
    field: str
    message: str
    action: str

    def json(self) -> dict[str, str]:
        return {
            "code": self.code,
            "field": self.field,
            "message": self.message,
            "action": self.action,
        }


def check_option(option: Option, seed: Seed) -> list[Problem]:
    out: list[Problem] = []
    if option.new_price is None:
        out.append(
            Problem(
                "NEGOTIATION_UNRESOLVED",
                "new_price",
                "협상 미합의 — 잠정 단가가 없다",
                "팀장과 협의해 단가를 정한다. 0원으로 대신하지 않는다",
            )
        )
    if option.effective.day != 1:
        out.append(
            Problem(
                "MID_MONTH_EFFECTIVE",
                "effective_date",
                f"월중 적용일({option.effective.isoformat()}) — 일별 자료·배분 규칙이 없다",
                "월초 적용일로 바꾸거나 배분 규칙을 합의한다",
            )
        )
    if option.old_price == 0:
        out.append(
            Problem(
                "OLD_PRICE_ZERO",
                "old_price",
                "기존 단가 0 — 인상률 미산출",
                "신규 거래로 별도 검토한다. 기본 단가 인상 상신은 보류한다",
            )
        )
    links = [p for p in seed.parts if p.part_id == option.part_id]
    if not links:
        out.append(
            Problem(
                "UNMAPPED_PART",
                "part_id",
                f"{option.part_id}의 모델 매핑이 없다",
                "부품-모델 매핑(BOM)을 등록한다",
            )
        )
    if any(p.supplier_id != option.supplier_id for p in links):
        out.append(
            Problem(
                "SUPPLIER_MISMATCH",
                "supplier_id",
                f"{option.part_id}의 공급사가 요청 공급사({option.supplier_id})와 다르다",
                "다른 공급사 품목을 같은 요청건에 섞지 않는다",
            )
        )
    return out


def check_window(
    rows: list[MonthRow], seed: Seed, start: date, end: date, part_id: str
) -> list[Problem]:
    """창 안의 월·모델 행 완전성. 중복 키(X10)·누락 행·수량 NULL(X09)·원가 누락·고정비 누락."""
    out: list[Problem] = []
    window = [r for r in rows if start <= r.period < end]
    counts = Counter((r.period, r.model_id) for r in window)
    for (period, model), n in sorted(counts.items()):
        if n > 1:
            out.append(
                Problem(
                    "DUPLICATE_KEY",
                    f"{period.isoformat()[:7]}|{model}",
                    f"{period.isoformat()[:7]} {model} 행이 {n}개다",
                    "중복 행을 정리한다. 합산해 정상값으로 쓰지 않는다",
                )
            )
    for period in _months(start, end):
        for model in seed.models:
            if (period, model) not in counts:
                out.append(
                    Problem(
                        "MISSING_ROW",
                        f"{period.isoformat()[:7]}|{model}",
                        f"{period.isoformat()[:7]} {model} 물량·원가 행이 없다",
                        "해당 월 물량·원가를 보완한다",
                    )
                )
        if period not in seed.fixed:
            out.append(
                Problem(
                    "MISSING_FIXED",
                    period.isoformat()[:7],
                    f"{period.isoformat()[:7]} 월고정비가 없다",
                    "월고정비를 보완한다",
                )
            )
    for r in window:
        key = f"{r.period.isoformat()[:7]}|{r.model_id}"
        if r.f02 is None:
            out.append(
                Problem(
                    "MISSING_QTY",
                    key,
                    f"{key} 물량 누락(NULL)",
                    "물량을 보완한다. 0으로 가정하지 않는다",
                )
            )
        elif r.f02 < 0:
            out.append(Problem("INVALID_QTY", key, f"{key} 음수 물량", "비음수 정수만 허용한다"))
        if r.unit_cm is None:
            out.append(
                Problem("MISSING_COST", key, f"{key} 판매단가·원가 누락", "C01 원가를 보완한다")
            )
        qty_per = seed.qty_per(r.model_id, part_id)
        if qty_per is None:
            out.append(
                Problem(
                    "UNMAPPED_PART", key, f"{key} {part_id} 매핑 없음", "부품-모델 매핑을 등록한다"
                )
            )
        elif r.outsource is not None and qty_per * seed.setting_decimal("old_price") > r.outsource:
            out.append(
                Problem(
                    "PART_EXCEEDS_OUTSOURCE",
                    key,
                    f"{key} 기존 부품원가가 기존 외주비를 넘는다",
                    "원가 구성을 확인한다",
                )
            )
    return out


# ─────────────────────────── 구매 증가 (M22·M23·M25) ───────────────────────────


def _purchase(rows: list[MonthRow], seed: Seed, part_id: str, start: date, end: date) -> int | None:
    """기간 부품 구매수량 = Σ 공급수량 × 소요량. 재고·기발주·시차 0(DEC26)이라 공급수량과 같다."""
    total = Decimal(0)
    for r in rows:
        if not start <= r.period < end:
            continue
        qty_per = seed.qty_per(r.model_id, part_id)
        if r.f02 is None or qty_per is None:
            return None
        total += Decimal(r.f02) * qty_per
    return int(total)


def _period(
    rows: list[MonthRow],
    seed: Seed,
    option: Option,
    start: date,
    end: date,
    problems: list[Problem],
) -> dict[str, Any]:
    blocked = [p for p in problems if p.code in _BLOCKING]
    qty = None if blocked else _purchase(rows, seed, option.part_id, start, end)
    increase = (
        None
        if qty is None or option.new_price is None
        else Decimal(qty) * (option.new_price - option.old_price)
    )
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "purchase_qty": qty,
        "increase": None if increase is None else str(increase),
        "computable": increase is not None,
        "reasons": [p.message for p in blocked],
    }


#: 금액을 미산출로 만드는 문제 — 기존 단가 0은 금액이 아니라 비율만 막는다.
_BLOCKING = {
    "NEGOTIATION_UNRESOLVED",
    "MID_MONTH_EFFECTIVE",
    "UNMAPPED_PART",
    "SUPPLIER_MISMATCH",
    "DUPLICATE_KEY",
    "MISSING_ROW",
    "MISSING_FIXED",
    "MISSING_QTY",
    "INVALID_QTY",
    "MISSING_COST",
    "PART_EXCEEDS_OUTSOURCE",
}


def comparison(
    rows: list[MonthRow], seed: Seed, base: Option, option: Option
) -> dict[str, Any] | None:
    """
    M25 요청 대비 부담 감소 — **같은 비교기간**(기본: 요청안의 12개월)에서 요청안 부담 − 이 안 부담.
    적용일이 다른 안이면 가격 효과와 적용일 연기 효과를 나눠 낸다(PERIOD-03). 서로 다른 12개월의
    증가액을 직접 빼지 않는다. 기존 대비로는 여전히 원가가 오른다 — 절감·이익으로 부르지 않는다.
    """
    if option.new_price is None or base.new_price is None:
        return None
    start, end = base.effective, add_months(base.effective, 12)
    if check_window(rows, seed, start, end, base.part_id):
        return None
    base_inc = Decimal(0)
    opt_inc = Decimal(0)
    price_effect = Decimal(0)
    deferral = Decimal(0)
    for r in rows:
        if not start <= r.period < end:
            continue
        units = Decimal(r.f02 or 0) * (seed.qty_per(r.model_id, base.part_id) or Decimal(0))
        base_d = base.new_price - base.old_price if r.period >= base.effective else Decimal(0)
        opt_d = option.new_price - option.old_price if r.period >= option.effective else Decimal(0)
        base_inc += units * base_d
        opt_inc += units * opt_d
        if r.period >= option.effective:
            price_effect += units * (base_d - opt_d)
        else:
            deferral += units * base_d
    return {
        "base_version": base.version_id,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "base_increase": str(base_inc),
        "increase": str(opt_inc),
        "reduction": str(base_inc - opt_inc),
        "price_effect": str(price_effect),
        "deferral_effect": str(deferral),
    }


# ─────────────────────────── 손익 연결 (M27 · CALC-22·23) ───────────────────────────


def _monthly(rows: list[MonthRow], seed: Seed, option: Option) -> list[dict[str, Any]]:
    """
    월·모델별 — F01+C01(기준) · F02+C01(물량 후) · F02+선택 원가안(단가 후).
    물량 효과 = (F02 − F01) × C01 단위 CM, 단가 효과 = −F02 × 소요량 × 단가 차이(적용일 이전 0).
    교차효과는 변경 물량에 적용한 원가 효과에 들어간다(M27).
    """
    diff = (option.new_price or Decimal(0)) - option.old_price
    out = []
    for r in sorted(rows, key=lambda r: (r.period, r.model_id)):
        cm = r.unit_cm
        qty_per = seed.qty_per(r.model_id, option.part_id) or Decimal(0)
        ok = cm is not None and r.f01 is not None and r.f02 is not None
        cost = (
            -Decimal(r.f02) * qty_per * diff
            if ok and r.period >= option.effective and option.new_price is not None
            else Decimal(0)
        )
        out.append(
            {
                "period": r.period.isoformat(),
                "model_id": r.model_id,
                "f01": r.f01,
                "f02": r.f02,
                "assumed": r.assumed,
                "unit_cm": None if cm is None else str(cm),
                "part_qty": None if r.f02 is None else int(Decimal(r.f02) * qty_per),
                "f01_cm": None if not ok else str(Decimal(r.f01) * cm),  # type: ignore[arg-type]
                "f02_cm": None if not ok else str(Decimal(r.f02) * cm),  # type: ignore[arg-type]
                "volume": None if not ok else str(Decimal(r.f02 - r.f01) * cm),  # type: ignore[operator,arg-type]
                "cost": str(cost) if ok else None,
                "target_cm": None if r.t01 is None or cm is None else str(Decimal(r.t01) * cm),
                "revenue": None
                if r.f02 is None or r.price is None
                else str(Decimal(r.f02) * r.price),
            }
        )
    return out


def period_pnl(
    monthly: list[dict[str, Any]], seed: Seed, label: str, kind: str, start: date, end: date
) -> dict[str, Any]:
    """기간 손익 — 고정비는 **공장 월 1회** 차감한다(D11). 모델별 배부 손익은 만들지 않는다."""
    picked = [m for m in monthly if start.isoformat() <= m["period"] < end.isoformat()]
    months = _months(start, end)
    base = {"label": label, "kind": kind, "from": start.isoformat(), "to": end.isoformat()}
    complete = (
        len(picked) == len(months) * len(seed.models)
        and all(m["f02_cm"] is not None for m in picked)
        and all(p in seed.fixed for p in months)
    )
    if not complete:
        return {**base, "computable": False, "reason": "기간 안의 물량·원가·고정비가 완전하지 않다"}

    def total(key: str) -> Decimal:
        return sum((Decimal(m[key]) for m in picked), Decimal(0))

    fixed = sum((seed.fixed[p] for p in months), Decimal(0))
    f01 = total("f01_cm") - fixed
    f02 = total("f02_cm") - fixed
    volume = f02 - f01
    cost = total("cost")
    combined = f02 + cost
    has_target = all(m["target_cm"] is not None for m in picked)
    target = total("target_cm") - fixed if has_target else None
    return {
        **base,
        "computable": True,
        "revenue_f02": str(total("revenue")),
        "fixed": str(fixed),
        "profit_f01": str(f01),
        "profit_volume": str(f02),
        "volume_effect": str(volume),
        "cost_effect": str(cost),
        "profit_combined": str(combined),
        "total_change": str(combined - f01),
        # 2028 Target은 미설정 — 12개월 Target 차이는 미산출(CALC-23). 당해연도 것을 섞지 않는다.
        "target_profit": None if target is None else str(target),
        "target_gap": None if target is None else str(target - combined),
        "bridge_diff": str(combined - (f01 + volume + cost)),
    }


def pnl_periods(monthly: list[dict[str, Any]], seed: Seed, effective: date) -> list[dict[str, Any]]:
    """통합손익 표 — 2027 월별 · Q3 · Q4 · 2027 잔여 · 2027 연간 · 향후 12개월."""
    y = date(2027, 1, 1)
    out = [
        period_pnl(
            monthly,
            seed,
            f"2027-{m:02d}",
            "month",
            date(2027, m, 1),
            add_months(date(2027, m, 1), 1),
        )
        for m in range(1, 13)
    ]
    out += [
        period_pnl(monthly, seed, "2027 Q3", "quarter", date(2027, 7, 1), date(2027, 10, 1)),
        period_pnl(monthly, seed, "2027 Q4", "quarter", date(2027, 10, 1), date(2028, 1, 1)),
        period_pnl(
            monthly, seed, "2027 잔여", "remaining", effective, date(effective.year + 1, 1, 1)
        ),
        period_pnl(monthly, seed, "2027 연간", "year", y, date(2028, 1, 1)),
        period_pnl(monthly, seed, "향후12개월", "next12", effective, add_months(effective, 12)),
    ]
    return out


def model_pnl(monthly: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    """모델별 공헌이익 — 고정비는 공장 합계에서만 차감한다(배부 없음). c~e도 0으로 표시한다."""
    out = []
    for model in sorted({m["model_id"] for m in monthly}):
        picked = [
            m
            for m in monthly
            if m["model_id"] == model and start.isoformat() <= m["period"] < end.isoformat()
        ]
        if any(m["f02_cm"] is None for m in picked):
            out.append({"model_id": model, "computable": False})
            continue
        f01 = sum((Decimal(m["f01_cm"]) for m in picked), Decimal(0))
        vol = sum((Decimal(m["volume"]) for m in picked), Decimal(0))
        cost = sum((Decimal(m["cost"]) for m in picked), Decimal(0))
        out.append(
            {
                "model_id": model,
                "computable": True,
                "cm_f01": str(f01),
                "volume_effect": str(vol),
                "cost_effect": str(cost),
                "cm_combined": str(f01 + vol + cost),
            }
        )
    return out


# ─────────────────────────── 분석 한 번 (CALC-21) ───────────────────────────


def analyze(
    seed: Seed, option: Option, *, rows: list[MonthRow] | None = None, base: Option | None = None
) -> dict[str, Any]:
    """
    단가안 하나의 분석. 입력 버전(물량·원가·고정비·위험·권한)을 결과에 고정한다(CALC-21).
    `rows`는 시연 사례가 바꾼 물량 표다(X09·X10) — 주지 않으면 시드 그대로.
    `base`가 있으면 그 안(요청안) 대비 부담 감소를 같은 비교기간으로 낸다(M25).
    """
    rows = list(seed.rows if rows is None else rows)
    start = option.effective
    next12_end = add_months(start, 12)
    remaining_end = date(start.year + 1, 1, 1)
    problems = check_option(option, seed) + check_window(
        rows, seed, start, next12_end, option.part_id
    )
    remaining = _period(rows, seed, option, start, remaining_end, problems)
    next12 = _period(rows, seed, option, start, next12_end, problems)
    inc12 = None if next12["increase"] is None else Decimal(next12["increase"])

    new = option.new_price
    rate_risk = None if new is None else rate_level(option.old_price, new, seed.settings)
    amt_risk = amount_level(inc12, seed.settings)
    rate = None if new is None else ratio(option.old_price, new)
    monthly = _monthly(rows, seed, option) if new is not None else []
    window_monthly = [
        m for m in monthly if start.isoformat() <= m["period"] < next12_end.isoformat()
    ]
    return {
        "version_id": option.version_id,
        "kind": option.kind,
        "part_id": option.part_id,
        "supplier_id": option.supplier_id,
        "old_price": str(option.old_price),
        "new_price": None if new is None else str(new),
        "effective_date": option.effective.isoformat(),
        "versions": {
            "quantity": QTY_VERSION,
            "cost": COST_VERSION,
            "fixed": FIXED_VERSION,
            "rule": RULE_VERSION,
            "authority": AUTHORITY_VERSION,
        },
        "rate": None if rate is None else str(rate),
        "rate_risk": None if rate_risk is None else rate_risk.value,
        "remaining": remaining,
        "next12": next12,
        "amount_risk": None if amt_risk is None else amt_risk.value,
        "risk": _value(combined_level([rate_risk, amt_risk])),
        "ceo_required": ceo_required(inc12, seed.settings),
        "comparison": None if base is None else comparison(rows, seed, base, option),
        "problems": [p.json() for p in problems],
        "computable": not [p for p in problems if p.code in _BLOCKING],
        "periods": pnl_periods(monthly, seed, start) if monthly else [],
        "q3_models": model_pnl(monthly, date(2027, 7, 1), date(2027, 10, 1)) if monthly else [],
        "next12_models": model_pnl(monthly, start, next12_end) if monthly else [],
        "monthly": window_monthly,
        "assumptions": {
            # 화면이 따로 적지 않는다 — 분석에 고정된 가정이 그대로 간다(U22-02 「근거 및 가정」).
            "inventory": "기발주·재고 없음(DEC26)",
            "lag": f"구매·생산·납품 시차 {seed.settings['purchase_lag']}개월",
            "next_year": f"2028 물량은 동일월 F01 × {seed.settings['next_year_factor']} 내부가정",
            "forecast": "F02 검토 중 — 공식 승인 전망이 아니다",
            "cost": "C01 외주비에 공통부품 기존 단가가 들어 있다 — 그 부분만 대체한다",
        },
    }


def _value(r: Risk | None) -> str | None:
    return None if r is None else r.value


def new_outsource(seed: Seed, part_id: str, old: Decimal, new: Decimal) -> list[dict[str, Any]]:
    """
    COST-01 — 기존 외주비의 **대상 부품 부분만** 대체한다. a 75,000 → 75,120, b 95,000 → 95,120,
    c~e 그대로. 전체 외주비에 새 부품값을 통째로 더하지 않는다.
    """
    out = []
    base = {r.model_id: r.outsource for r in seed.rows if r.period == date(2027, 7, 1)}
    for link in sorted(seed.parts, key=lambda p: p.model_id):
        if link.part_id != part_id:
            continue
        before = base[link.model_id] or Decimal(0)
        part_old = link.qty_per * old
        part_new = link.qty_per * new
        out.append(
            {
                "model_id": link.model_id,
                "qty_per": str(link.qty_per),
                "outsource_before": str(before),
                "part_before": str(part_old),
                "rest": str(before - part_old),
                "part_after": str(part_new),
                "outsource_after": str(before - part_old + part_new),
            }
        )
    return out


def integrity(seed: Seed) -> dict[str, int]:
    """V05·V06·V09·V16·V17 — 원천 자체의 정합성(분석과 무관하게 볼 것)."""
    eff = seed.setting_date("effective_date")
    end = add_months(eff, 12)
    counts = Counter((r.period, r.model_id) for r in seed.rows)
    valid = [
        r
        for r in seed.rows
        if r.f02 is not None and r.unit_cm is not None and counts[(r.period, r.model_id)] == 1
    ]
    window = [r for r in seed.rows if eff <= r.period < end]
    old = seed.setting_decimal("old_price")
    outsource = {r.model_id: r.outsource for r in seed.rows if r.period == date(2027, 1, 1)}
    return {
        "V05": sum(1 for r in window if r in valid),
        "V06": len(window),
        "V09": sum(1 for p in seed.parts if (outsource[p.model_id] or 0) - p.qty_per * old < 0),
        "V16": sum(r.actual or 0 for r in seed.rows if r.period.year == 2027),
        "V17": len(valid),
    }


__all__ = [
    "Option",
    "PartLink",
    "add_months",
    "amount_level",
    "analyze",
    "ceo_required",
    "combined_level",
    "integrity",
    "new_outsource",
    "rate_level",
]
