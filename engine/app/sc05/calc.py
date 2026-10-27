"""
SC05 규칙 계산 — 초기 실행 집계·예산 사용가능액·과제 효과·월간 Rolling 전망과 변경 대사(구현명세
8·9장,
M503~M512).

**숫자는 여기서만 만든다**(구현명세 8장 — Agent나 화면이 금액을 만들지 않는다). 기본 시연의
129,000,000원·
3,428,986,680원·48,303,320원도 이 계산이 원천(장면 4 승인 가정·예산 원장·구매 표본·운영계획)에서
낸다.

* **기초 손익은 과제 전 금액이다**(`basis_includes_action_effects=false`). 장면 2~4와 같은 월별 계산
  (`sc02.calc.monthly_rows` — F02 물량 × 승인 단가 반영 단위 공헌이익)으로 모델·월마다 다시 낸다.
  7~9월은 같은 값을
  시연용 가상 마감으로 쓴다 — 기존 전망 행에 ACTUAL 태그만 바꾼 것이 아니라, 마감
  묶음(`close_batch`)이 출처를
  따로 갖는다(구현명세 18장).
* **과제 효과는 모델에 한 번 더한다** — ACT41은 A-a, ACT42·43은 A-b. 공장 고정비는 a~e 합계에서 한
  번 뺀다(월
  370백만원). 모델별 고정비 배부는 없다.
* **월 순효과** = 적용량 × (회피단가 − 추가단가 − 물류단가) + 기준 긴급건 × 건당비용 − 실제(전망)
  긴급비용 −
  운영지원비 − 일회성비. 마감월의 긴급비용·지원비·일회성비는 **관측·집행된 값**이고(구매 표본·예산
  원장), 잔여월은
  담당 임원이 확정한 운영계획 가정이다. 고정비 절감은 0이다 — 넣으면 막는다(T522).
* **변경 대사**는 종전 공식본(FC50) 대비 변화만 원인별로 더한다. 장면 4 승인효과 전액을 이미 반영된
  공식본에 다시
  더하면 원인으로 설명되지 않는 차이가 남아 막힌다(X506·T521).
* 비율·평균은 반올림하지 않은 Decimal로 낸다 — 화면이 단위만 바꾼다. 시각 차는 초로 정규화한 뒤
  분으로 바꾼다.
  임계값과 같으면 정상, 넘으면 지연이다(구현명세 5장).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.sc02 import calc as sc02_calc
from app.sc02.calc import Option
from app.sc02.seed import Seed as NumbersSeed

YEAR_START, YEAR_END = date(2027, 1, 1), date(2028, 1, 1)
MONTHS = tuple(date(2027, m, 1) for m in range(1, 13))
#: 과제 효과가 생길 수 있는 달 — 장면 4 승인 이후(7~12월)
EFFECT_MONTHS = MONTHS[6:]
#: 과제 → 효과를 더하는 모델(구현명세 8장)
TASK_MODEL = {"ACT41": "A-a", "ACT42": "A-b", "ACT43": "A-b"}
TASKS = tuple(TASK_MODEL)
#: 장면 4 대안 → 장면 5 실행과제
ALT_OF = {"ACT41": "ALT41", "ACT42": "ALT42", "ACT43": "ALT43"}
PERIODS: tuple[tuple[str, str, date, date], ...] = (
    ("year", "2027 연간", YEAR_START, YEAR_END),
    ("closed", "2027 마감 1~9월", YEAR_START, date(2027, 10, 1)),
    ("forecast", "2027 전망 10~12월", date(2027, 10, 1), YEAR_END),
    ("q3", "2027 Q3", date(2027, 7, 1), date(2027, 10, 1)),
)


def _d(value: Any) -> Decimal:
    return Decimal(str(value))


def _month(value: Any) -> date:
    return date.fromisoformat(str(value)[:10])


def _sum(items: list[dict[str, Any]], key: str) -> Decimal:
    return sum((_d(x[key]) for x in items), Decimal(0))


# ─────────────────────────── 기초 손익(과제 전) ───────────────────────────


def basis(numbers: NumbersSeed, option: Option) -> list[dict[str, Any]]:
    """
    2027 월·모델별 과제 전 공헌이익 — 장면 2~4와 같은 월별 계산을 그대로 쓴다(새로 만들지 않는다).
    공헌이익은
    F02 물량 × 단위 공헌이익 + 승인 단가 효과다. Target 공헌이익은 같은 단위로 T01 물량에서 낸다.
    """
    out = []
    for m in sc02_calc.monthly_rows(list(numbers.rows), numbers, option):
        if not str(m["period"]).startswith("2027"):
            continue
        if m["f02_cm"] is None or m["target_cm"] is None:
            raise ValueError(f"{m['period'][:7]} {m['model_id']} 기초 손익을 계산할 수 없다")
        out.append(
            {
                "period": m["period"],
                "model_id": m["model_id"],
                "qty": m["f02"],
                "basis_cm": str(_d(m["f02_cm"]) + _d(m["cost"])),
                "target_cm": m["target_cm"],
                "revenue": m["revenue"],
            }
        )
    return out


# ─────────────────────────── 과제 효과 ───────────────────────────


def plan_inputs(assumption: dict[str, Any], month: date) -> dict[str, Any]:
    """
    장면 4 승인 가정(DEC41-v2) 한 달치 — 실적·운영계획이 덮기 전의 출발점이다. 적용 시작은 월
    첫날만이다.
    """
    applied = month >= _month(assumption["start"])
    one_off = assumption.get("one_off_cost")
    return {
        "month": month.isoformat(),
        "applied": applied,
        "qty": assumption["monthly_qty"] if applied else 0,
        "avoid": assumption["avoid_price"],
        "add": assumption["outsource_price"],
        "logistics": assumption["logistics_price"],
        "base_count": assumption["emergency_before"] if applied else 0,
        "count": assumption["emergency_after"] if applied else 0,
        "unit_cost": assumption["per_event_cost"],
        "extra_cost": None,
        "support": assumption["monthly_support"] if applied else "0",
        "one_off": one_off
        if one_off is not None and month == _month(assumption["one_off_month"])
        else "0",
        "fixed_saving": "0",
    }


def effect(task_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """
    과제 하나 · 달 하나(SC05월효과 한 행). 긴급비용은 관측값이 있으면 그것을, 없으면 건수 ×
    건당비용이다.
    """
    qty = int(inputs["qty"])
    unit = _d(inputs["unit_cost"])
    margin = qty * (_d(inputs["avoid"]) - _d(inputs["add"]) - _d(inputs["logistics"]))
    baseline_cost = int(inputs["base_count"]) * unit
    extra = (
        _d(inputs["extra_cost"])
        if inputs.get("extra_cost") is not None
        else int(inputs["count"]) * unit
    )
    support, one_off = _d(inputs["support"]), _d(inputs["one_off"])
    fixed = _d(inputs.get("fixed_saving") or 0)
    net = margin + baseline_cost - extra - support - one_off + fixed
    return {
        "task_id": task_id,
        "model_id": TASK_MODEL[task_id],
        **inputs,
        "margin": str(margin),
        "baseline_cost": str(baseline_cost),
        "extra": str(extra),
        "net": str(net),
    }


# ─────────────────────────── 월 손익 · 기간 ───────────────────────────


def months(
    base: list[dict[str, Any]],
    effects: list[dict[str, Any]],
    fixed: dict[str, Any],
    *,
    first_forecast: date,
) -> list[dict[str, Any]]:
    """월 손익 — 모델 공헌이익(과제 전 + 과제 순효과 한 번) 합계 − 공장 고정비(한 번)."""
    out = []
    for m in MONTHS:
        key = m.isoformat()
        rows = []
        for b in (x for x in base if x["period"] == key):
            eff = sum(
                (
                    _d(e["net"])
                    for e in effects
                    if e["month"] == key and e["model_id"] == b["model_id"]
                ),
                Decimal(0),
            )
            rows.append(
                {
                    **b,
                    "effect": str(eff),
                    "cm": str(_d(b["basis_cm"]) + eff),
                }
            )
        cost = _d(fixed[key])
        target = _sum(rows, "target_cm") - cost
        before = _sum(rows, "basis_cm") - cost
        eff_total = _sum(rows, "effect")
        profit = before + eff_total
        out.append(
            {
                "period": key,
                "kind": "ACTUAL" if m < first_forecast else "FORECAST",
                "models": rows,
                "fixed": str(cost),
                "target": str(target),
                "basis_profit": str(before),
                "effect": str(eff_total),
                "profit": str(profit),
                # 목표 부족 — 음수면 목표 초과다(0으로 자르지 않는다)
                "gap": str(target - profit),
                "revenue": str(_sum(rows, "revenue")),
            }
        )
    return out


def periods(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out = {}
    for kind, label, s, e in PERIODS:
        picked = [m for m in rows if s.isoformat() <= m["period"] < e.isoformat()]
        target, before, eff, profit = (
            _sum(picked, k) for k in ("target", "basis_profit", "effect", "profit")
        )
        out[kind] = {
            "kind": kind,
            "label": label,
            "target": str(target),
            "basis_profit": str(before),
            "effect": str(eff),
            "profit": str(profit),
            "gap": str(target - profit),
            "fixed": str(_sum(picked, "fixed")),
        }
    return out


# ─────────────────────────── 변경 대사 (M512 · CT511) ───────────────────────────

#: 원인 — 서로 배타적이다. 합계가 전망 변화와 원 단위로 같아야 한다.
CAUSES = (
    ("urgent", "긴급구매 건수·비용"),
    ("support", "운영지원비"),
    ("one_off", "일회성 준비·전환비"),
    ("volume", "과제 적용 물량"),
    ("basis", "그 외 기간·비과제 요인(물량·단가·기타원가)"),
)


def reconcile(
    new: list[dict[str, Any]],
    new_effects: list[dict[str, Any]],
    prior: list[dict[str, Any]],
    prior_effects: list[dict[str, Any]],
    *,
    reported_total: Decimal | None = None,
) -> dict[str, Any]:
    """
    종전 공식본 대비 변화 — 원인별로 나눠 더한다. `reported_total`은 산정 방식이 월 합계와 다른
    연간을 낼 때
    (X506 — 종전 공식본에 승인효과를 다시 더한 값)의 연간이다. 원인으로 설명되지 않는
    차이(`residual`)가 0이
    아니면 대사 실패다.
    """
    rows: list[dict[str, Any]] = []
    for m in EFFECT_MONTHS:
        key = m.isoformat()
        mine = [e for e in new_effects if e["month"] == key]
        theirs = [e for e in prior_effects if e["month"] == key]

        def total(xs: list[dict[str, Any]], field: str, task: str | None = None) -> Decimal:
            return sum(
                (_d(x[field]) for x in xs if task is None or x["task_id"] == task), Decimal(0)
            )

        amounts = {
            # 긴급비용이 줄면(−) 손익이 는다(+)
            "urgent": -(total(mine, "extra") - total(theirs, "extra"))
            + (total(mine, "baseline_cost") - total(theirs, "baseline_cost")),
            "support": -(total(mine, "support") - total(theirs, "support")),
            "one_off": -(total(mine, "one_off") - total(theirs, "one_off")),
            "volume": total(mine, "margin") - total(theirs, "margin"),
        }
        for cause, amount in amounts.items():
            if amount:
                rows.append({"cause": cause, "month": key, "amount": str(amount)})
    for m in MONTHS:
        key = m.isoformat()
        a = next(x for x in new if x["period"] == key)
        b = next(x for x in prior if x["period"] == key)
        diff = _d(a["basis_profit"]) - _d(b["basis_profit"])
        if diff:
            rows.append({"cause": "basis", "month": key, "amount": str(diff)})
    prior_total = _sum(prior, "profit")
    new_total = _sum(new, "profit") if reported_total is None else reported_total
    explained = _sum(rows, "amount")
    residual = new_total - prior_total - explained
    return {
        "prior_total": str(prior_total),
        "new_total": str(new_total),
        "rows": rows,
        "by_cause": [
            {
                "cause": c,
                "label": label,
                "amount": str(sum((_d(r["amount"]) for r in rows if r["cause"] == c), Decimal(0))),
            }
            for c, label in CAUSES
        ],
        "delta": str(new_total - prior_total),
        "residual": str(residual),
        "ok": residual == 0,
    }


# ─────────────────────────── 초기 실행 관측 (M503~M508) ───────────────────────────


def minutes(start: str | None, end: str | None) -> Decimal | None:
    """
    두 시각의 차 — 초로 정규화한 뒤 분. 어느 하나라도 없으면 미확인(None), 역전이면 None이 아니라
    음수다.
    """
    if not start or not end:
        return None
    seconds = round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())
    return Decimal(seconds) / Decimal(60)


def _timing(values: list[Decimal | None], limit: int) -> dict[str, Any]:
    done = [v for v in values if v is not None and v >= 0]
    return {
        "measured": len(done),
        "unconfirmed": sum(1 for v in values if v is None),
        "reversed": sum(1 for v in values if v is not None and v < 0),
        "average": None if not done else str(sum(done, Decimal(0)) / len(done)),
        "max": None if not done else str(max(done)),
        # 정확히 임계값이면 정상, 넘으면 지연
        "delayed": sum(1 for v in done if v > limit),
        "limit": limit,
    }


def observation(
    orders: list[dict[str, Any]],
    changes: list[dict[str, Any]],
    *,
    base_count: int,
    unit_cost: Decimal,
    support: Decimal | None,
    share_limit: int,
    ack_limit: int,
) -> dict[str, Any]:
    """
    9월 초기 결과 — 사업성과(구매 건·긴급·추가비·순개선·납기·품질)와 경영수행(공유·확인 소요)을
    나눈다. 구매
    60건과 변경 6건은 다른 모집단이다(분모를 섞지 않는다). 미확인은 0이 아니다 — 결과 확정을 막는다.
    """
    seen: dict[str, int] = {}
    for o in orders:
        seen[o["order_id"]] = seen.get(o["order_id"], 0) + 1
    duplicates = sorted(k for k, n in seen.items() if n > 1)
    unique = list({o["order_id"]: o for o in orders if not o.get("cancelled")}.values())
    count = len(unique)
    urgent = [o for o in unique if o["urgent"]]
    unknown_cost = sorted(o["order_id"] for o in urgent if o.get("extra") is None)
    extra = None if unknown_cost else sum((_d(o["extra"]) for o in urgent), Decimal(0))
    unconfirmed = sorted(o["order_id"] for o in unique if o.get("result_status") != "CONFIRMED")
    late = None if unconfirmed else sum(1 for o in unique if o.get("late"))
    quality = None if unconfirmed else sum(1 for o in unique if o.get("quality"))
    baseline = base_count * unit_cost
    net = None if extra is None or support is None else baseline - extra - support
    blocking = [f"주문 ID 중복 {', '.join(duplicates)}"] if duplicates else []
    if unknown_cost:
        blocking.append(f"긴급 추가비 미확인 {', '.join(unknown_cost)}")
    if unconfirmed:
        blocking.append(f"납기·품질 미확인 {len(unconfirmed)}건")
    if support is None:
        blocking.append("9월 운영지원비 집행 미확인")
    if count == 0:
        blocking.append("관측 대상 주문이 없다")
    return {
        "orders": count,
        "qty": sum(int(o["qty"]) for o in unique),
        "urgent": len(urgent),
        # 분모 0은 비해당 — 0%가 아니다
        "urgent_rate": None if count == 0 else str(Decimal(len(urgent)) / Decimal(count)),
        "extra_cost": None if extra is None else str(extra),
        "baseline_count": base_count,
        "baseline_cost": str(baseline),
        "support": None if support is None else str(support),
        "net": None if net is None else str(net),
        "late": late,
        "quality": quality,
        "unconfirmed_results": len(unconfirmed),
        "duplicates": duplicates,
        "unknown_cost": unknown_cost,
        "changes": len(changes),
        "share": _timing(
            [minutes(c.get("received_at"), c.get("shared_at")) for c in changes], share_limit
        ),
        "ack": _timing([minutes(c.get("shared_at"), c.get("ack_at")) for c in changes], ack_limit),
        "blocking": blocking,
        "complete": not blocking,
    }


# ─────────────────────────── 예산 (M509 · CT506) ───────────────────────────


def budget(
    limits: dict[str, Decimal], operating_limit: Decimal, ledger: list[dict[str, Any]]
) -> dict:
    """
    사용가능액 = 한도 − 집행 − 미집행 확정 약정. COMMIT는 약정을 늘리고 SETTLE은 같은 약정을 줄이며
    집행을 늘린다
    — 예정액과 약정·집행을 중복 차감하지 않는다. 운영지원(OPERATING)은 별도 원장 범위다.
    """

    def scope(txns: list[dict[str, Any]]) -> tuple[Decimal, Decimal, Decimal]:
        commit = sum((_d(t["commitment_delta"]) for t in txns), Decimal(0))
        paid = sum((_d(t["paid_delta"]) for t in txns), Decimal(0))
        pnl = sum((_d(t["pnl_cost"]) for t in txns), Decimal(0))
        return commit, paid, pnl

    tasks = []
    for task, limit in limits.items():
        commit, paid, pnl = scope(
            [t for t in ledger if t["task_id"] == task and t["scope"] == "ONEOFF"]
        )
        tasks.append(
            {
                "task_id": task,
                "limit": str(limit),
                "commitment": str(commit),
                "paid": str(paid),
                "pnl_cost": str(pnl),
                "available": str(limit - paid - commit),
            }
        )
    total_limit = sum(limits.values(), Decimal(0))
    commit, paid, pnl = scope([t for t in ledger if t["scope"] == "ONEOFF"])
    op_commit, op_paid, op_pnl = scope([t for t in ledger if t["scope"] == "OPERATING"])
    return {
        "tasks": tasks,
        "total": {
            "limit": str(total_limit),
            "commitment": str(commit),
            "paid": str(paid),
            "pnl_cost": str(pnl),
            "available": str(total_limit - paid - commit),
        },
        "operating": {
            "limit": str(operating_limit),
            "commitment": str(op_commit),
            "paid": str(op_paid),
            "available": str(operating_limit - op_paid - op_commit),
        },
    }


__all__ = [
    "ALT_OF",
    "EFFECT_MONTHS",
    "MONTHS",
    "TASKS",
    "TASK_MODEL",
    "basis",
    "budget",
    "effect",
    "months",
    "observation",
    "periods",
    "plan_inputs",
    "reconcile",
]
