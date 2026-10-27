"""
SC06 계산 — 과제 완료 후 차 분기(2027 Q4)의 기대 대비 실현 효과. 원 단위 정수, 결정적 순서(구현명세
6·8장).

    거래 비용 → 월 효과 → 과제 효과 → 합계

* **기대는 고정된 FC51 스냅샷(BASE61-*)이다.** 실적에 맞춰 기준을 고치지 않는다(CT601). 장면 5 FC51
  산정본의 Q4
  과제 효과와 원 단위로 같아야 한다(CK61-14) — 다르면 적재를 막는다(`domain`).
* **ACT42 = 기준 긴급비 − 실제 긴급비 − 운영지원비.** 기준은 「월 12건 × 120만원」 — FC51 물량으로
  정규화한 비교
  가정이지 과거 관측이 아니다. 기존 일회성 2백만원은 8월 반영분이라 Q4에 다시 빼지 않는다(중복
  방지).
* **ACT41·43 = 수량 × (회피 단가 − 추가 단가 − 물류 단가).** 고정비 절감은 0이어야 한다 — 외주
  확대로 남는 고정비를
  절감으로 만들지 않는다(CT605). 0이 아니면 계산 오류다.
* **미확인은 0이 아니다.** 긴급 주문의 비용이 하나라도 null이면 그 달·그 과제 효과는 산정
  보류(None)다. 확인된 다른
  과제는 따로 소계로 낸다 — 「전체 확정 합계」라고 부르지 않는다(구현명세 8장 「불완전 자료의
  집계」).
* **원인별 비용과 기대 미달은 다른 지표다.** 원인별 합계는 긴급 14건 전체 비용(16.8백만원)과
  대사한다. 기대 미달
  (−4.8백만원)을 원인 비용에 더하거나 14건에 배분하지 않는다(X61-07).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

#: 검토 기간(포함) — 2027 Q4
QUARTER = (date(2027, 10, 1), date(2027, 11, 1), date(2027, 12, 1))
MONTHS = tuple(m.isoformat() for m in QUARTER)
TASKS = ("ACT41", "ACT42", "ACT43")
#: 원인 코드 — 서로 배타적이다. 복합은 단독 분류로 중복 합산을 막는다(CT607). 원인 미확정은
# UNKNOWN에 남긴다.
CAUSES = (
    ("INTERNAL", "내부 확인 지연"),
    ("SUPPLY", "적시 공유 후 조달 제약"),
    ("MIXED", "내부 지연·조달 제약 복합"),
    ("UNKNOWN", "원인 미확정"),
)
CAUSE_LABEL = dict(CAUSES)


class CalcError(ValueError):
    """계산 입력이 규칙을 어긴다 — 조용히 넘기지 않는다."""


def _i(value: Any) -> int | None:
    return None if value is None else int(value)


def _minutes(start: str | None, end: str | None) -> int | None:
    if start is None or end is None:
        return None
    return int((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() // 60)


# ─────────────────────────── 기대(고정 기준) ───────────────────────────


def expected_net(b: dict[str, Any]) -> int:
    """BASE61 한 행의 기대 순효과 — FC51을 만든 장면 5 산식 그대로(SC05월효과)."""
    if b["task_id"] == "ACT42":
        return (
            (b["base_count"] - b["forecast_count"]) * b["unit_cost"] - b["support"] - b["one_off"]
        )
    return b["qty"] * (b["avoid"] - b["add"] - b["logistics"]) - b["one_off"]


# ─────────────────────────── 거래 · 월 효과 ───────────────────────────


def urgent_cost(order: dict[str, Any]) -> int | None:
    """
    긴급 주문 한 건의 추가비 = 운송 + 할증. 정상 주문은 확인된 0이다. 둘 중 하나라도 미확인이면
    None.
    """
    if not order["urgent"]:
        return 0
    if order["freight"] is None or order["surcharge"] is None:
        return None
    return order["freight"] + order["surcharge"]


def month_effects(
    baselines: list[dict[str, Any]],
    actuals: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    opcosts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """과제 × 월 효과(SC06월효과 9행). 기준 행 순서(월 → 과제)를 따른다."""
    out = []
    for b in sorted(baselines, key=lambda r: (r["month"], TASKS.index(r["task_id"]))):
        task, month = b["task_id"], b["month"]
        expected = expected_net(b)
        if task == "ACT42":
            picked = [o for o in orders if o["month"] == month and o["task_id"] == task]
            costs = [urgent_cost(o) for o in picked]
            actual_cost = None if any(c is None for c in costs) else sum(c for c in costs if c)
            support = sum(
                c["amount"] for c in opcosts if c["month"] == month and c["task_id"] == task
            )
            base = b["base_count"] * b["unit_cost"]
            row = {
                "qty": sum(o["qty"] for o in picked),
                "baseline_or_avoided": base,
                "actual_cost": actual_cost,
                "operating_cost": support,
                "fixed_saving": 0,
                "net": None if actual_cost is None else base - actual_cost - support,
                "urgent_count": sum(1 for o in picked if o["urgent"]),
                "unconfirmed_orders": [
                    o["order_id"] for o, c in zip(picked, costs, strict=True) if c is None
                ],
                "sources": ["SC06구매거래", "SC06운영비"],
            }
        else:
            found = [a for a in actuals if a["task_id"] == task and a["month"] == month]
            if len(found) > 1:
                raise CalcError(f"{task} {month} 실행실적이 둘 이상이다 — 효과 이중 귀속")
            a = found[0] if found else None
            if a is not None and a["fixed_saving"] != 0:
                raise CalcError(
                    f"{a['actual_id']}: 고정비 절감은 0이어야 한다(CT605 — 잔존 고정비 절감 금지)"
                )
            avoided = None if a is None else a["qty"] * a["avoid"]
            cost = None if a is None else a["qty"] * (a["add"] + a["logistics"]) + a["other"]
            row = {
                "qty": None if a is None else a["qty"],
                "baseline_or_avoided": avoided,
                "actual_cost": cost,
                "operating_cost": 0,
                "fixed_saving": 0,
                "net": None if a is None else avoided - cost,  # type: ignore[operator]
                "urgent_count": None,
                "unconfirmed_orders": [],
                "sources": ["SC06실행실적"],
            }
        out.append(
            {
                "effect_id": f"EF61-{task}-{month[5:7]}",
                "task_id": task,
                "month": month,
                "baseline_id": b["baseline_id"],
                "expected": expected,
                **row,
                "variance": None if row["net"] is None else row["net"] - expected,
                "status": "CONFIRMED" if row["net"] is not None else "PENDING",
            }
        )
    return out


def task_effects(months: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """과제별 Q4 — 한 달이라도 산정 보류면 그 과제 실현·차이는 None(0으로 메우지 않는다)."""
    out = []
    for task in TASKS:
        rows = [m for m in months if m["task_id"] == task]
        pending = any(m["net"] is None for m in rows)
        actual = None if pending else sum(m["net"] for m in rows)
        expected = sum(m["expected"] for m in rows)
        out.append(
            {
                "task_id": task,
                "expected_krw": expected,
                "actual_krw": actual,
                "variance_krw": None if actual is None else actual - expected,
                "calculation_status": "PENDING" if pending else "CONFIRMED",
                "months": len(rows),
            }
        )
    return out


def totals(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """
    3과제 합계 — 과제 계산에서 낸다(TOTAL 행을 다시 합산하지 않는다). 보류 과제가 있으면 합계는
    None이고, 확인된
    과제만의 소계를 따로 낸다(그것을 확정 합계라 부르지 않는다).
    """
    confirmed = [t for t in tasks if t["actual_krw"] is not None]
    complete = len(confirmed) == len(tasks)
    return {
        "expected_krw": sum(t["expected_krw"] for t in tasks),
        "actual_krw": sum(t["actual_krw"] for t in tasks) if complete else None,
        "variance_krw": (
            sum(t["actual_krw"] for t in tasks) - sum(t["expected_krw"] for t in tasks)
            if complete
            else None
        ),
        "calculation_status": "CONFIRMED" if complete else "PENDING",
        "confirmed_subtotal": {
            "tasks": [t["task_id"] for t in confirmed],
            "expected_krw": sum(t["expected_krw"] for t in confirmed),
            "actual_krw": sum(t["actual_krw"] for t in confirmed),
        },
    }


def performance_word(task: dict[str, Any]) -> str:
    """효과 판단 — 같은 기간·대상의 실현 − 기대. 활동 완료와 별개다(J609)."""
    v = task["variance_krw"]
    if v is None:
        return "산정 보류"
    if v == 0:
        return "기대 달성"
    return "일부 기대 미달" if v < 0 else "기대 초과"


# ─────────────────────────── 원인 · 운영지표 ───────────────────────────


def causes(orders: list[dict[str, Any]]) -> dict[str, Any]:
    """
    긴급 주문의 최종 원인별 건수·비용(M607). 대표 한 건으로 추정하지 않고 거래마다의 최종원인을
    센다. 원인별
    합계는 긴급 전체와 맞아야 한다(CK61-08·15) — 이 표는 기대 미달의 배분표가 아니다.
    """
    urgent = [o for o in orders if o["urgent"]]
    groups = []
    for code, label in CAUSES:
        picked = [
            o for o in urgent if (o["cause"] if o["cause"] in CAUSE_LABEL else "UNKNOWN") == code
        ]
        if code == "UNKNOWN" and not picked:
            continue
        costs = [urgent_cost(o) for o in picked]
        groups.append(
            {
                "cause": code,
                "label": label,
                "count": len(picked),
                "actual_urgent_cost_krw": None if any(c is None for c in costs) else sum(costs),  # type: ignore[arg-type]
                "orders": [o["order_id"] for o in picked],
            }
        )
    total_costs = [urgent_cost(o) for o in urgent]
    total_cost = None if any(c is None for c in total_costs) else sum(total_costs)  # type: ignore[arg-type]
    return {
        "metric": "actual_urgent_cost",
        "groups": groups,
        "total": {"count": len(urgent), "actual_urgent_cost_krw": total_cost},
        **reconcile_causes(groups, len(urgent), total_cost),
    }


def reconcile_causes(
    groups: list[dict[str, Any]],
    urgent_count: int,
    urgent_cost_total: int | None,
    *,
    variance: int | None = None,
) -> dict[str, Any]:
    """
    원인별 합계 ↔ 긴급 전체. 원인 비용에 기대 미달을 섞은 표(X61-07)는 잔차가 미달액만큼 생긴다 —
    그것을 따로
    짚는다. 잔차는 0이어야 한다.
    """
    count_residual = sum(g["count"] for g in groups) - urgent_count
    known = [g["actual_urgent_cost_krw"] for g in groups]
    cost_residual = (
        None
        if urgent_cost_total is None or any(k is None for k in known)
        else sum(known) - urgent_cost_total  # type: ignore[arg-type]
    )
    problems = []
    if count_residual != 0:
        problems.append(
            f"원인별 건수 합계가 긴급 {urgent_count}건과 {count_residual:+d}건 어긋난다"
        )
    if cost_residual:
        if variance is not None and cost_residual == -variance:
            problems.append(
                "원인별 비용에 기대 미달액을 더했다 — "
                "실제 긴급비와 기대 대비 차이는 서로 다른 지표다(X61-07)"
            )
        else:
            problems.append(f"원인별 비용 합계가 긴급비 전체와 {cost_residual:+,d}원 어긋난다")
    return {"count_residual": count_residual, "cost_residual": cost_residual, "problems": problems}


def metrics(
    orders: list[dict[str, Any]],
    changes: list[dict[str, Any]],
    opcosts: list[dict[str, Any]],
    baselines: list[dict[str, Any]],
    *,
    share_limit: int,
    confirm_limit: int,
) -> list[dict[str, Any]]:
    """
    운영지표(SC06운영지표) — Q4 주문 180건과 긴급 원인 관측 14건은 서로 다른 모집단이다. 지연은
    달력 경과분이고
    같으면 정상, 넘으면 지연이다(SC05 규칙 계승). 미확인 시각은 지연 0이 아니라 따로 센다.
    """
    urgent = [o for o in orders if o["urgent"]]
    costs = [urgent_cost(o) for o in urgent]
    shares = [_minutes(c["received_at"], c["shared_at"]) for c in changes]
    acks = [_minutes(c["shared_at"], c["confirmed_at"]) for c in changes]
    act42 = [b for b in baselines if b["task_id"] == "ACT42"]
    base_count = sum(b["base_count"] for b in act42)
    forecast_count = sum(b["forecast_count"] for b in act42)
    rate = None if not orders else f"{len(urgent) / len(orders):.8f}"
    return [
        {"metric_id": "M61-01", "label": "구매 주문", "value": len(orders), "unit": "건"},
        {"metric_id": "M61-02", "label": "긴급구매", "value": len(urgent), "unit": "건"},
        {"metric_id": "M61-03", "label": "긴급구매율", "value": rate, "unit": "비율"},
        {
            "metric_id": "M61-04",
            "label": "긴급 추가비",
            "value": None if any(c is None for c in costs) else sum(costs),  # type: ignore[arg-type]
            "unit": "원",
        },
        {
            "metric_id": "M61-05",
            "label": "분기 지원비",
            "value": sum(c["amount"] for c in opcosts),
            "unit": "원",
        },
        {
            "metric_id": "M61-06",
            "label": "공유 지연",
            "value": sum(1 for m in shares if m is not None and m > share_limit),
            "unit": "건",
            "unconfirmed": sum(1 for m in shares if m is None),
        },
        {
            "metric_id": "M61-07",
            "label": "구매 확인 지연",
            "value": sum(1 for m in acks if m is not None and m > confirm_limit),
            "unit": "건",
            "unconfirmed": sum(1 for m in acks if m is None),
        },
        {"metric_id": "M61-08", "label": "기준 긴급건", "value": base_count, "unit": "건"},
        {"metric_id": "M61-09", "label": "FC51 전망 긴급건", "value": forecast_count, "unit": "건"},
        {
            "metric_id": "M61-10",
            "label": "전망 대비 추가 긴급건",
            "value": len(urgent) - forecast_count,
            "unit": "건",
        },
        {
            "metric_id": "M61-11",
            "label": "납기 이상",
            "value": sum(o["delivery_issue"] for o in orders),
            "unit": "건",
        },
        {
            "metric_id": "M61-12",
            "label": "품질 이상",
            "value": sum(o["quality_issue"] for o in orders),
            "unit": "건",
        },
    ]


def change_minutes(change: dict[str, Any]) -> dict[str, int | None]:
    return {
        "share_minutes": _minutes(change["received_at"], change["shared_at"]),
        "confirm_minutes": _minutes(change["shared_at"], change["confirmed_at"]),
        "supply_gap_minutes": _minutes(change["required_at"], change["supply_at"]),
    }


# ─────────────────────────── 보조 손익 ───────────────────────────


def quarter_profit(
    fc51_months: list[dict[str, Any]], months: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Q4 관리손익 보조 정보(SC06분기손익) — 다른 FC51 요인이 같다는 가정에서 FC51 관리손익에 **효과
    차이만** 더한다
    (효과 전액을 다시 더하지 않는다). 목표 차이 = 실적 − 목표(양수 초과). 연간 전망·Target을 바꾸지
    않는다.
    """
    rows = []
    for key in MONTHS:
        fc = next(m for m in fc51_months if m["period"] == key)
        eff = [m for m in months if m["month"] == key]
        confirmed = None if any(m["net"] is None for m in eff) else sum(m["net"] for m in eff)
        expected = int(fc["effect"])
        diff = None if confirmed is None else confirmed - expected
        actual = None if diff is None else int(fc["profit"]) + diff
        rows.append(
            {
                "period": key,
                "target": int(fc["target"]),
                "fc51_profit": int(fc["profit"]),
                "fc51_effect": expected,
                "confirmed_effect": confirmed,
                "effect_diff": diff,
                "profit": actual,
                "vs_target": None if actual is None else actual - int(fc["target"]),
            }
        )

    def total(key: str) -> int | None:
        values = [r[key] for r in rows]
        return None if any(v is None for v in values) else sum(values)

    return {
        "months": rows,
        "quarter": {k: total(k) for k in rows[0] if k != "period"},
    }


# ─────────────────────────── 대사 · 버전 ───────────────────────────


def snapshot_residual(baselines: list[dict[str, Any]], fc51_effects: list[dict[str, Any]]) -> int:
    """BASE61 기대 ↔ 장면 5 FC51 산정본의 같은 과제·월 효과. 0이어야 한다(CK61-14)."""
    total = 0
    for b in baselines:
        fc = [e for e in fc51_effects if e["task_id"] == b["task_id"] and e["month"] == b["month"]]
        if len(fc) != 1:
            raise CalcError(
                f"FC51 산정본에 {b['task_id']} {b['month']} 효과가 하나가 아니다({len(fc)}개)"
            )
        total += abs(expected_net(b) - int(fc[0]["net"]))
        total += (
            abs(expected_net(b) - b["expected_sheet"]) if b.get("expected_sheet") is not None else 0
        )
    return total


def calculation_hash(inputs: dict[str, Any]) -> str:
    """
    산정 입력의 지문 — 보고본이 묶인 산정과 지금 산정이 같은지 본다(버전 결합, 구현명세 8장 5단계).
    """
    body = json.dumps(inputs, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:16]
