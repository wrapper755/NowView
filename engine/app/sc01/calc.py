"""
SC01 규칙 계산 — 지표·위험 판정(CALC-01~03), 손익 집계(CALC-04~05), 전망 생성(UI03-03).

**규칙 계산과 Agent 설명을 가른다**(G12·AG-01). 지표는 여기서 정해진 산식으로 재현되고,
Agent는 이 결과를 인용할 뿐 숫자를 만들지 않는다.

정밀도 규칙(CALC-02): 금액은 원 단위 `Decimal`로 계산하고, 비율은 **소수점 8자리로
반올림한 뒤** 임계값과 비교한다 — 엑셀 기준값과 경계에서 같은 판정이 나와야 한다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.sc01.seed import Key, Seed, SourceRow

RATIO_PLACES = Decimal("0.00000001")


class Risk(StrEnum):
    NORMAL = "NORMAL"  # 기준 이내
    ATTENTION = "ATTENTION"  # 관심
    CRITICAL = "CRITICAL"  # 중요


RISK_LABEL = {Risk.NORMAL: "기준 이내", Risk.ATTENTION: "관심", Risk.CRITICAL: "중요"}
_ORDER = [Risk.NORMAL, Risk.ATTENTION, Risk.CRITICAL]


def _ratio(num: Decimal, den: Decimal) -> Decimal:
    return (num / den).quantize(RATIO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Metric:
    """지표 하나(API-02 모양). `value`가 None이면 미산출이고 `reason`이 그 이유다."""

    metric_id: str
    value: Decimal | None
    unit: str
    risk: Risk | None = None  # 임계값이 걸린 KRI만
    reason: str | None = None

    @property
    def computable(self) -> bool:
        return self.value is not None


@dataclass(frozen=True)
class Assessment:
    """한 모델·월의 비교 결과. `risk`가 None이면 판정 보류(필수 입력 누락, CALC-03)."""

    key: Key
    target: int | None
    prior: int | None
    latest: int | None
    unit_cm: Decimal
    metrics: dict[str, Metric]
    risk: Risk | None
    partial: bool  # 일부 지표 미산출

    @property
    def model_id(self) -> str:
        return self.key[2]

    @property
    def period(self) -> date:
        return self.key[3]


def _level(value: Decimal, attention: Decimal, critical: Decimal) -> Risk:
    # 임계값 이상(≥)이면 그 수준이다(CALC-02).
    if value >= critical:
        return Risk.CRITICAL
    if value >= attention:
        return Risk.ATTENTION
    return Risk.NORMAL


def assess(
    key: Key,
    target: int | None,
    prior: int | None,
    latest: int | None,
    unit_cm: Decimal,
    rules: Mapping[str, Decimal],
) -> Assessment:
    """KPI01·M01·KRI01·M03·KRI02·M02·KRI03과 R01 통합 판정(구현명세 7장 표)."""
    m: dict[str, Metric] = {}
    T, P, L = target, prior, latest

    def missing(metric_id: str, unit: str, why: str) -> None:
        m[metric_id] = Metric(metric_id, None, unit, reason=why)

    # KPI01 달성률 = L ÷ T
    if T is None or L is None:
        missing("KPI01", "ratio", "입력 누락")
    elif T == 0:
        missing("KPI01", "ratio", "목표 0 — 미산출")
    else:
        m["KPI01"] = Metric("KPI01", _ratio(Decimal(L), Decimal(T)), "ratio")

    # M01 추가 감소 물량 = P − L (증가면 음수 유지)
    if P is None or L is None:
        missing("M01", "qty", "입력 누락")
    else:
        m["M01"] = Metric("M01", Decimal(P - L), "qty")

    # KRI01 감소율 = (P − L) ÷ P
    if P is None or L is None:
        missing("KRI01", "ratio", "입력 누락")
    elif P == 0:
        missing("KRI01", "ratio", "직전 전망 0 — 미산출")
    else:
        v = _ratio(Decimal(P - L), Decimal(P))
        risk = _level(v, rules["감소율_관심"], rules["감소율_중요"])
        m["KRI01"] = Metric("KRI01", v, "ratio", risk)

    # M03 순손익 영향 = (L − P) × CM, KRI02 감소액 = MAX(−M03, 0)
    if P is None or L is None:
        missing("M03", "krw", "입력 누락")
        missing("KRI02", "krw", "입력 누락")
    else:
        net = Decimal(L - P) * unit_cm
        m["M03"] = Metric("M03", net, "krw")
        loss = max(-net, Decimal(0))
        m["KRI02"] = Metric(
            "KRI02", loss, "krw", _level(loss, rules["감소액_관심"], rules["감소액_중요"])
        )

    # M02 목표 대비 부족물량 = T − L, KRI03 부족률 = MAX(1 − L ÷ T, 0)
    if T is None or L is None:
        missing("M02", "qty", "입력 누락")
        missing("KRI03", "ratio", "입력 누락")
    else:
        m["M02"] = Metric("M02", Decimal(T - L), "qty")
        if T == 0:
            missing("KRI03", "ratio", "목표 0 — 미산출")
        else:
            short = max(Decimal(1) - _ratio(Decimal(L), Decimal(T)), Decimal(0))
            m["KRI03"] = Metric(
                "KRI03", short, "ratio", _level(short, rules["부족률_관심"], rules["부족률_중요"])
            )

    kri = [m[k] for k in ("KRI01", "KRI02", "KRI03")]
    levels = [x.risk for x in kri if x.risk is not None]
    # 최신 물량이 없으면 판정을 보류한다 — 누락을 0이나 "정상"으로 읽으면 안 된다(CALC-03).
    # 모든 지표가 미산출인 것도 정상으로 처리하지 않는다.
    risk = None if latest is None or not levels else max(levels, key=_ORDER.index)
    return Assessment(
        key=key,
        target=T,
        prior=P,
        latest=L,
        unit_cm=unit_cm,
        metrics=m,
        risk=risk,
        partial=any(not x.computable for x in kri),
    )


def assess_all(
    keys: Iterable[Key],
    target: Mapping[Key, int],
    prior: Mapping[Key, int],
    latest: Mapping[Key, int | None],
    seed: Seed,
) -> list[Assessment]:
    return [
        assess(k, target.get(k), prior.get(k), latest.get(k), seed.costs[k].cm, seed.rules)
        for k in keys
    ]


# ─────────────────────────── 전망 생성 (UI03-03) ───────────────────────────


def build_forecast(
    prior: Mapping[Key, int], verified: Iterable[SourceRow]
) -> dict[Key, int | None]:
    """
    직전 승인 전망을 복제하고 **확인된 원천의 대상 월만** 덮어쓴다.

    원천에 없는 월(1~6월, 10~12월)은 직전 전망을 그대로 둔다 — 7월 감소를 이후 월로
    자동 전파하지 않는다(D09). 원천은 당사 배정·월 전체 물량이므로 그대로 쓴다(D05·G10).
    누락은 None으로 남겨 계산이 보류되게 한다(0으로 메우지 않는다).
    """
    out: dict[Key, int | None] = dict(prior)
    for row in verified:
        if row.quantity_scope != "FULL_MONTH" or row.allocation_scope != "ASSIGNED_SUPPLY":
            # 잔여물량·고객 전체 물량은 변환 규칙이 필요하다 — 조용히 그대로 쓰지 않는다.
            raise ValueError(f"{row.source_id} {row.model_id}: 변환 규칙 없는 물량 범위")
        out[row.key] = row.quantity
    return out


# ─────────────────────────── 손익 집계 (CALC-04·05) ───────────────────────────


@dataclass(frozen=True)
class Pnl:
    revenue: Decimal
    cm: Decimal
    fixed: Decimal

    @property
    def mgmt_profit(self) -> Decimal:
        """공장관리손익 = 공헌이익 합계 − 공장고정비(공장·월에 한 번만 차감)."""
        return self.cm - self.fixed

    def __add__(self, other: Pnl) -> Pnl:
        return Pnl(self.revenue + other.revenue, self.cm + other.cm, self.fixed + other.fixed)


ZERO = Pnl(Decimal(0), Decimal(0), Decimal(0))


def monthly_pnl(
    plan: Mapping[Key, int | None], seed: Seed, plant_id: str = "ULS"
) -> dict[date, Pnl]:
    """월별 손익. 모델별 고정비 배부는 만들지 않는다(D11)."""
    months: dict[date, Pnl] = {}
    for key, qty in plan.items():
        if key[1] != plant_id:
            continue
        if qty is None:
            raise ValueError(f"{key}: 수량 누락 — 손익을 집계할 수 없다")
        c = seed.costs[key]
        p = months.get(key[3], ZERO)
        months[key[3]] = Pnl(p.revenue + c.price * qty, p.cm + c.cm * qty, p.fixed)
    return {
        m: Pnl(p.revenue, p.cm, seed.fixed_costs[(plant_id, m)]) for m, p in sorted(months.items())
    }


def period_pnl(months: Mapping[date, Pnl], start: int, end: int) -> Pnl:
    """분기·연간은 월 금액을 더한다 — 비율을 평균하지 않는다(CALC-04)."""
    total = ZERO
    for m, p in months.items():
        if start <= m.month <= end:
            total = total + p
    return total


PERIODS: dict[str, tuple[int, int]] = {
    **{f"{i}월": (i, i) for i in range(1, 13)},
    "Q1": (1, 3),
    "Q2": (4, 6),
    "Q3": (7, 9),
    "Q4": (10, 12),
    "연간": (1, 12),
}
