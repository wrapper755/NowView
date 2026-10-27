"""
SC04 규칙 계산 — 대응안 효과·중복 제거·검증과 대응 후 전망·잔여 부족(구현명세 8·9장, M401~M405).

**숫자는 여기서만 만든다**(P413). Agent는 결과를 인용만 하고, BPM은 순서만 쥔다. 화면에 고정 숫자를
넣지 않는다 — 기본 시연의 137,200,000원·127,800,000원도 가정(`SC04가정`)에서 이 계산이 낸다.

* **효과는 기존 기준 손익에 더하는 순증분이다.** 기준 비용을 손익에 다시 더하거나 기존 고정비를
  지우지
  않는다(CT403). 월 반복효과 = 회피액 − 추가 거래비 − 추가 물류비 − 운영지원비, 일회성비는 그
  달에만 뺀다.
* **적용 시작은 월 첫날만** — 일할 계산하지 않는다. 일회성비 월은 시작월과 따로 입력이다(시작을
  옮겨도
  준비비는 따라 움직이지 않는다 — DEC41-v2의 8월 2,000,000원).
* **중복 제거(EVDC44)** — ALT42 초안의 P-MAT02 할인(100원/개)은 ALT43 가격차에 포함된다. 두 안이
  함께
  적용되는 달의 ALT43 물량만큼 「초안 할인」과 「중복 제거」를 같은 값으로 둔다 — 순효과에 중복이
  남지 않는다.
* **고정비 절감은 0이다**(EVDC45·DEC406). 기존 감가상각비는 대안 사이에 변하지 않는 잔존 고정비다 —
  초안에
  넣으면(E401) 검증이 막는다. 기준 손익의 공장 고정비 370백만원/월은 그대로다.
* **기준은 장면 3 통합 손익이다** — 장면 3 계산(`app.sc03.calc.period`)으로 월마다 다시 낸다.
  보고본과
  판단본은 같은 기준에 각자의 효과를 더한다 — **두 버전을 합산하지 않는다.**
* 목표 부족 = Target − 전망. 음수는 목표 초과다 — 0으로 자르지 않는다(Q4 −34,278,880원).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from app.sc02 import calc as sc02_calc
from app.sc02.calc import Option, add_months
from app.sc02.seed import Seed as NumbersSeed
from app.sc03 import calc as sc03_calc

YEAR_START, YEAR_END = date(2027, 1, 1), date(2028, 1, 1)
#: 대안이 적용될 수 있는 달 — 장면 4 결정 이후(7~12월). 1~6월은 미적용(0)이다.
EFFECT_MONTHS = tuple(date(2027, m, 1) for m in range(7, 13))
#: 화면이 고르는 기간 — 연간 · Q3 · Q4 · 잔여 7~12월(구현명세 9장). 기간을 바꿔도 버전을 섞지
#: 않는다.
PERIODS: tuple[tuple[str, str, date, date], ...] = (
    ("year", "2027 연간", YEAR_START, YEAR_END),
    ("q3", "2027 Q3", date(2027, 7, 1), date(2027, 10, 1)),
    ("q4", "2027 Q4", date(2027, 10, 1), YEAR_END),
    ("remaining", "2027 잔여 7~12월", date(2027, 7, 1), YEAR_END),
)
#: 초안 할인이 다른 안의 가격차에 이미 들어 있는 관계(EVDC44) — 할인한 안 → 그 가격차를 가진 안
DUPLICATE_OF = {"ALT42": "ALT43"}
#: 비용 대상 → 회피단가가 넘으면 안 되는 원 단위원가 항목(EVDC41~43). 하위 내역이 원가보다 클 수
#: 없다.
COST_CEILING = {"PR-": "process_var", "URG-": "process_var", "P-MAT": "material"}
#: 가정 칸 — 판단 초안이 바꿀 수 있는 것(T403의 월 대상량, 질의 뒤의 효과 시작 …)
FIELDS = {
    "start": "효과 시작",
    "monthly_qty": "월 대상량",
    "avoid_price": "회피단가",
    "outsource_price": "추가단가",
    "logistics_price": "물류단가",
    "emergency_before": "긴급 전",
    "emergency_after": "긴급 후",
    "per_event_cost": "건당비용",
    "monthly_support": "월지원비",
    "one_off_cost": "일회성비",
    "one_off_month": "일회성월",
    "avoided_fixed": "회피 고정비",
}
DATE_FIELDS = ("start", "one_off_month")


def _d(value: Any) -> Decimal:
    return Decimal(str(value))


def _month(value: Any) -> date:
    return date.fromisoformat(str(value)[:10])


def assumption_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """
    `SC04가정` 한 행 → 가정(JSON). 시작은 **보고 시작**이다 — 판단 시작은 회의 뒤에 생기는 값이다.
    """
    dup = row.get("초안중복할인단가")
    return {
        "alt_id": str(row["대안ID"]),
        "name": str(row["대안명"]),
        "task_id": str(row["분석과제"]),
        "model_id": str(row["모델"]),
        "cost_item": str(row["비용대상"]),
        "start": row["보고 시작"].date().isoformat(),
        "monthly_qty": int(row["월 대상량"]),
        "avoid_price": str(row["회피단가"]),
        "outsource_price": str(row["추가단가"]),
        "logistics_price": str(row["물류단가"]),
        "emergency_before": int(row["긴급 전"]),
        "emergency_after": int(row["긴급 후"]),
        "per_event_cost": str(row["건당비용"]),
        "monthly_support": str(row["월지원비"]),
        "one_off_cost": None if row["일회성비"] is None else str(row["일회성비"]),
        "one_off_month": row["일회성월"].date().isoformat(),
        "budget": str(row["전용예산"]),
        "draft_dup_price": None if dup in (None, "") else str(dup),
        # E401 — 기존 감가상각비를 회피 비용으로 넣은 초안. 기본은 0(회피 고정비 없음, EVDC45).
        "avoided_fixed": "0",
        # E402 — 중복 제거를 비운 달(YYYY-MM-01 → 제거액). 비어 있으면 초안 할인과 같은 값이다.
        "duplicate_override": {},
    }


def normalize(field: str, value: Any) -> Any:
    """판단 초안의 바꾼 값 → 가정 칸의 형식. 시작·일회성월은 월 첫날만이다(일할 계산 없음)."""
    if field not in FIELDS:
        raise ValueError(f"바꿀 수 없는 가정: {field}")
    if field in DATE_FIELDS:
        d = _month(value)
        if d.day != 1:
            raise ValueError(f"{FIELDS[field]}은 월 첫날만이다 — {value}")
        return d.isoformat()
    if field in ("monthly_qty", "emergency_before", "emergency_after"):
        n = int(str(value).replace(",", ""))
        if n < 0:
            raise ValueError(f"{FIELDS[field]}은 0 이상이다")
        return n
    d = _d(str(value).replace(",", ""))
    if d < 0:
        raise ValueError(f"{FIELDS[field]}은 0 이상이다")
    return str(d)


# ─────────────────────────── 기준(장면 3 통합 손익) ───────────────────────────


def baseline(numbers: NumbersSeed, option: Option) -> list[dict[str, Any]]:
    """2027 월별 Target·장면 3 기준 관리손익 — 장면 3 계산을 그대로 쓴다(새로 만들지 않는다)."""
    monthly = sc02_calc.monthly_rows(list(numbers.rows), numbers, option)
    out = []
    m = YEAR_START
    while m < YEAR_END:
        p = sc03_calc.period(monthly, numbers, "month", m.isoformat()[:7], m, add_months(m, 1))
        if not p["computable"] or p["target"] is None:
            raise ValueError(f"{m:%Y-%m} 기준 손익을 계산할 수 없다")
        out.append({"period": m.isoformat(), "target": p["target"], "base": p["combined"]})
        m = add_months(m, 1)
    return out


# ─────────────────────────── 대안 효과 ───────────────────────────


def _row_for(numbers: NumbersSeed, model: str, month: date):
    return next((r for r in numbers.rows if r.model_id == model and r.period == month), None)


def line(a: dict[str, Any], month: date, others: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """대안 하나 · 달 하나(SC04월효과 한 행). 금액은 원 단위 정수다."""
    applied = month >= _month(a["start"])
    qty = a["monthly_qty"] if applied else 0
    events = (a["emergency_before"] - a["emergency_after"]) if applied else 0
    avoided = qty * _d(a["avoid_price"]) + events * _d(a["per_event_cost"])
    added = qty * _d(a["outsource_price"])
    logistics = qty * _d(a["logistics_price"])
    support = _d(a["monthly_support"]) if applied else Decimal(0)
    one_off = (
        _d(a["one_off_cost"])
        if a["one_off_cost"] is not None and month == _month(a["one_off_month"])
        else Decimal(0)
    )
    discount = Decimal(0)
    target = others.get(DUPLICATE_OF.get(a["alt_id"], ""))
    if applied and a.get("draft_dup_price") and target and month >= _month(target["start"]):
        discount = _d(a["draft_dup_price"]) * target["monthly_qty"]
    override = (a.get("duplicate_override") or {}).get(month.isoformat())
    duplicate = discount if override is None else _d(override)
    fixed_saving = _d(a.get("avoided_fixed") or 0) if applied else Decimal(0)
    net = avoided - added - logistics - support - one_off + discount - duplicate + fixed_saving
    return {
        "alt_id": a["alt_id"],
        "month": month.isoformat(),
        "start": a["start"],
        "applied": applied,
        "qty": qty,
        "avoided": str(avoided),
        "added": str(added),
        "logistics": str(logistics),
        "support": str(support),
        "one_off": str(one_off),
        "draft_discount": str(discount),
        "duplicate": str(duplicate),
        "net": str(net),
        "fixed_saving": str(fixed_saving),
    }


def normal_monthly(a: dict[str, Any]) -> Decimal:
    """정상 가동 월 반복효과(M403) — 일회성비·중복 조정·고정비 제외. ×12가 정상 연간 참고값이다."""
    q = a["monthly_qty"]
    return (
        q * (_d(a["avoid_price"]) - _d(a["outsource_price"]) - _d(a["logistics_price"]))
        + (a["emergency_before"] - a["emergency_after"]) * _d(a["per_event_cost"])
        - _d(a["monthly_support"])
    )


def validate(
    assumptions: list[dict[str, Any]], lines: list[dict[str, Any]], numbers: NumbersSeed
) -> list[dict[str, Any]]:
    """
    CT402·CT403 검증 — 차단만 낸다(조건부 승인으로 우회할 수 없다). 근거 없는 회피 비용 · 중복
    미조정 ·
    적용량 초과 · 원가 초과 회피단가 · 긴급건수 역전 · 일회성비 누락.
    """
    errors: list[dict[str, Any]] = []

    def err(alt: str, code: str, message: str, amount: Decimal | None = None) -> None:
        errors.append(
            {
                "alt_id": alt,
                "code": code,
                "message": message,
                "amount": None if amount is None else str(amount),
            }
        )

    for a in assumptions:
        alt = a["alt_id"]
        mine = [x for x in lines if x["alt_id"] == alt]
        fixed = sum((_d(x["fixed_saving"]) for x in mine), Decimal(0))
        if fixed:
            err(
                alt,
                "FIXED_COST_NOT_AVOIDABLE",
                f"기존 고정비(감가상각비 등) {int(fixed):,}원을 회피 비용으로 넣었다 — 잔존 "
                "고정비는 "
                "대안 사이에 변하지 않는다(EVDC45). 기준 고정비는 그대로 둔다",
                fixed,
            )
        gap = sum((_d(x["draft_discount"]) - _d(x["duplicate"]) for x in mine), Decimal(0))
        if gap:
            err(
                alt,
                "DUPLICATE_NOT_REMOVED",
                f"다른 안 가격차에 포함된 할인 {int(gap):,}원이 제거되지 않았다(EVDC44) — "
                "같은 품목·물량·기간의 절감을 두 번 더하지 않는다",
                gap,
            )
        if a["emergency_after"] > a["emergency_before"]:
            err(alt, "EMERGENCY_REVERSED", "긴급구매 목표 건수가 현재보다 많다(after ≤ before)")
        if a["one_off_cost"] is None:
            err(alt, "ONE_OFF_MISSING", "일회성 전환·준비비가 비어 있다 — 0이면 0을 적는다")
        for key in ("avoid_price", "outsource_price", "logistics_price", "per_event_cost"):
            if _d(a[key]) < 0:
                err(alt, "NEGATIVE_COST", f"{FIELDS[key]}가 음수다")
        ceiling = next((v for k, v in COST_CEILING.items() if a["cost_item"].startswith(k)), None)
        for x in mine:
            if not x["applied"] or not a["monthly_qty"]:
                continue
            row = _row_for(numbers, a["model_id"], _month(x["month"]))
            if row is None or row.f02 is None:
                err(alt, "FORECAST_MISSING", f"{x['month'][:7]} {a['model_id']} 전망이 없다")
                continue
            if a["monthly_qty"] > row.f02:
                err(
                    alt,
                    "QTY_OVER_FORECAST",
                    f"{x['month'][:7]} 대상량 {a['monthly_qty']:,}이 {a['model_id']} 전망 "
                    f"{row.f02:,}을 넘는다",
                )
            unit = getattr(row, ceiling) if ceiling else None
            if unit is not None and _d(a["avoid_price"]) > unit:
                err(
                    alt,
                    "AVOID_OVER_COST",
                    f"회피단가 {int(_d(a['avoid_price'])):,}원이 원 단위원가 {int(unit):,}원보다 "
                    "크다",
                )
                break
    return errors


def _sum(items: list[dict[str, Any]], key: str) -> Decimal:
    return sum((_d(x[key]) for x in items), Decimal(0))


def _periods(months: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out = {}
    for kind, label, s, e in PERIODS:
        picked = [m for m in months if s.isoformat() <= m["period"] < e.isoformat()]
        target, base, effect = (_sum(picked, k) for k in ("target", "base", "effect"))
        excl = _sum(picked, "effect_excl")
        out[kind] = {
            "kind": kind,
            "label": label,
            "target": str(target),
            "base": str(base),
            "effect": str(effect),
            "forecast": str(base + effect),
            # 목표 부족 — 음수면 목표 초과다(0으로 자르지 않는다)
            "gap_before": str(target - base),
            "gap": str(target - base - effect),
            "forecast_excl_conditional": str(base + excl),
            "gap_excl_conditional": str(target - base - excl),
        }
    return out


def run(
    assumptions: list[dict[str, Any]],
    base: list[dict[str, Any]],
    numbers: NumbersSeed,
    *,
    include: list[str] | None = None,
    conditional: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """
    효과 계산 한 번(effect_run). `include`가 있으면 그 안만 합산한다(승인 범위 — HOLD·REJECTED
    제외).
    `conditional`은 조건부 제외 비교에서 뺄 안이다 — 승인된 다른 시나리오가 아니다(구현명세 8장).
    """
    by_alt = {a["alt_id"]: a for a in assumptions}
    lines = [line(a, m, by_alt) for a in assumptions for m in EFFECT_MONTHS]
    errors = validate(assumptions, lines, numbers)
    counted = set(by_alt if include is None else include)
    months = []
    for b in base:
        picked = [x for x in lines if x["month"] == b["period"] and x["alt_id"] in counted]
        effect = _sum(picked, "net")
        excl = _sum([x for x in picked if x["alt_id"] not in conditional], "net")
        months.append({**b, "effect": str(effect), "effect_excl": str(excl)})
    alts = []
    for a in assumptions:
        mine = [x for x in lines if x["alt_id"] == a["alt_id"]]
        nm = normal_monthly(a)
        alts.append(
            {
                "alt_id": a["alt_id"],
                "name": a["name"],
                "start": a["start"],
                "counted": a["alt_id"] in counted,
                "net_2027": str(_sum(mine, "net")),
                "one_off": str(_sum(mine, "one_off")),
                "duplicate": str(_sum(mine, "duplicate")),
                "fixed_saving": str(_sum(mine, "fixed_saving")),
                "normal_monthly": str(nm),
                "normal_annual": str(nm * 12),
            }
        )
    counted_alts = [x for x in alts if x["counted"]]
    return {
        "lines": lines,
        "alts": alts,
        "months": months,
        "periods": _periods(months),
        "effect_total": str(_sum(counted_alts, "net_2027")),
        "normal_annual_total": str(_sum(counted_alts, "normal_annual")),
        "duplicate_total": str(_sum(lines, "duplicate")),
        "fixed_saving_total": str(_sum(lines, "fixed_saving")),
        "fixed_cost_monthly": str(numbers.fixed[YEAR_START]),
        "errors": errors,
        "passed": not errors,
        "status": "VERIFIED" if not errors else "VALIDATION_FAILED",
    }


def diff(report: dict[str, Any], decision: dict[str, Any]) -> list[dict[str, Any]]:
    """보고본 → 판단본 대안별 차이(U405 전후 비교). 두 버전을 합산하지 않는다 — 나란히 둘 뿐이다."""
    before = {a["alt_id"]: a for a in report["alts"]}
    out = []
    for a in decision["alts"]:
        b = before.get(a["alt_id"])
        if b is None:
            continue
        out.append(
            {
                "alt_id": a["alt_id"],
                "start_before": b["start"],
                "start_after": a["start"],
                "before": b["net_2027"],
                "after": a["net_2027"],
                "diff": str(_d(a["net_2027"]) - _d(b["net_2027"])),
            }
        )
    return out


def budget_policy(total: Decimal, allocations: dict[str, Decimal], request: dict[str, Any]) -> dict:
    """
    예산 위임 조항 조회(POL41·E407) — 규칙을 보여 줄 뿐 거래를 만들지 않는다. 무보고 전용 불허,
    총괄 한도 안
    전용은 변경 보고 후 전체 책임 임원 승인, 총괄 한도 초과는 대표 별도 승인 전 신규 약정 제한.
    """
    kind = request.get("kind")
    if kind == "transfer":
        amount = _d(request["amount"])
        src = str(request["from"])
        if amount > allocations.get(src, Decimal(0)):
            return {
                "allowed": False,
                "approver": None,
                "rule": f"{src} 배분액보다 큰 전용은 할 수 없다",
                "total_after": str(total),
            }
        return {
            "allowed": True,
            "approver": "경영관리임원",
            "rule": "총괄 한도 안의 과제 간 전용 — 변경 보고 후 전체 책임 임원(경영관리 임원) "
            "승인. "
            "무보고 전용은 허용하지 않는다",
            "total_after": str(total),
        }
    if kind == "total":
        need = _d(request["amount"])
        over = need > total
        return {
            "allowed": not over,
            "approver": "대표이사" if over else "현업임원·경영관리예산임원",
            "rule": (
                f"총괄 한도 {int(total):,}원 초과 — 대표 별도 보고·승인 전 신규 약정 제한"
                if over
                else "한도 안의 실행 품의 — 담당 현업 임원과 경영관리 예산 임원이 처리한다"
            ),
            "total_after": str(total),
        }
    raise ValueError(f"모르는 조회: {kind}")
