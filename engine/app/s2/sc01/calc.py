"""
시나리오 2 장면 1 규칙 계산 — 경보 판정(Y01, N01~02)·영향 분석(A01, N03)·납기 상황판(UI-D01).

숫자는 여기서만 만든다(구현명세 AG-01과 같은 원칙). 입력은 회사 시스템의 원천
칸이고(`/company/s2/master`·구매 개정
수신 문서), 통합가상데이터 v0.1의 파생 칸(마감판정·사용 가능 예정·착수차질·판정)은 시험이 대조한다.

구현명세 §3 Y01:
1. 같은 발주 납기행·개정의 재수신은 평가 전에 거른다(프로세스가 한다). 한 개정 안의 분할 입고분은
   한 변경이다.
2. 판정일 포함 최근 3개 공장 영업일의 **실제 변경** 수를 센다(최초 등록 제외). 첫 변경은 필요
   시각의 수량 부족
   > 0 또는 최소 착수 여유 < 15분이면 경보, 아니면 기록만. 창 안의 두 번째 변경부터는 규모와
   관계없이 경보.
3. 사용 가능 = 입고예정 + 검수. 착수 여유 = 기존 착수 − 필요 수량이 사용 가능해지는 시각. 부족량 =
   착수 시각까지
   확보된 배정수량과 가용재고를 소요에서 뺀 양(최저 0). 발주행의 여유는 주문별 최솟값, 부족량은
   주문별 최댓값.
4. 반복 변경이면 자료 일부가 없어도 경보를 유지한다. 첫 변경의 판정에 필요한 자료가 없고 다른
   조건으로 경보를
   확정할 수 없으면 평가 보류.

**배정은 계산이다** — 같은 부품의 입고분을 기존 조립 착수가 이른 약정부터 차례로 채운다(타 주문
재고를 옮기지
않는다). 대표 사건 P-v2에서 COM-S ← L2S 80개, COM-R ← L2R 240개가 나오고(주문영향 시트의 「배정
입고분」), 앞
개정(P-v1의 L1 320개)에도 같은 규칙이 맞는다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

KST = timezone(timedelta(hours=9))

#: 현행 KRI 기준 버전 — 개선(장면 4 N13~16)이 새 버전을 낸다. 지난 평가는 이 버전으로 남는다.
RULE_VERSION = "KRI-S2-SUPPLY-v1"
#: 첫 변경의 경보 경계 — 착수 여유가 이것 **미만**이면 경보(정확히 15분은 기록만, T02)
SLACK_ALERT_MIN = 15
#: 반복 변경을 세는 창 — 판정일 포함 공장 영업일 수
WINDOW_BUSINESS_DAYS = 3
#: 시연 기준 OTD 목표(구현명세 §1 D01) — 관리 기준(M15)이다
OTD_TARGET = Decimal("0.98")
#: 직전 마감기간(10월) — [시작, 끝)
CLOSED_PERIOD = (date(2026, 10, 1), date(2026, 11, 1))
CLOSED_LABEL = "2026년 10월"

FIRST, RECORD, ALERT, HOLD = "FIRST", "RECORD", "ALERT", "HOLD"
JUDGMENT_LABEL = {FIRST: "최초", RECORD: "기록", ALERT: "경보", HOLD: "평가 보류"}


def at(value: str | None) -> datetime | None:
    if value is None:
        return None
    found = datetime.fromisoformat(value)
    return found if found.tzinfo else found.replace(tzinfo=KST)


def iso(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(KST).isoformat()


def minutes(delta: timedelta) -> int:
    """분 — 엑셀 `ROUND((I-H)*1440, 0)`처럼 반올림(초 단위 경계는 판정이 따로 본다)."""
    return int(Decimal(delta.total_seconds() / 60).quantize(Decimal(1), ROUND_HALF_UP))


def is_business_day(d: date) -> bool:
    return d.weekday() < 5  # 데모 달력: 월~금, 공휴일 없음(11/2~4는 연속 영업일)


def business_window(day: date, n: int = WINDOW_BUSINESS_DAYS) -> list[date]:
    """판정일을 포함한 최근 n개 공장 영업일(오래된 날부터)."""
    found: list[date] = []
    d = day
    while len(found) < n:
        if is_business_day(d):
            found.append(d)
        d -= timedelta(days=1)
    return sorted(found)


# ─────────────────────────── 배정 ───────────────────────────


def _lot_view(lot: dict[str, Any]) -> dict[str, Any]:
    planned = at(lot["planned_at"])
    usable = None if planned is None else planned + timedelta(minutes=int(lot["inspection_min"]))
    return {**lot, "available_at": iso(usable)}


def allocate(
    lots: list[dict[str, Any]], demand: list[dict[str, Any]], qty_of: dict[str, int]
) -> dict[str, dict[str, Any]]:
    """
    부품마다 입고분을 기존 조립 착수가 이른 약정부터 채운다. 약정 → {입고분 조각·사용 가능·착수
    여유·부족량·
    착수 차질·누락}. 착수 시각이 없는 약정은 맨 뒤에 채우고 여유를 내지 않는다(누락 — 0이 아니다).
    """
    out: dict[str, dict[str, Any]] = {}
    by_part: dict[str, list[dict[str, Any]]] = {}
    for row in demand:
        by_part.setdefault(row["part_id"], []).append(row)
    for part, rows in by_part.items():
        queue = sorted(
            (_lot_view(lot) for lot in lots if lot["part_id"] == part),
            key=lambda lot: (
                at(lot["available_at"]) or datetime.max.replace(tzinfo=KST),
                lot["lot_id"],
            ),
        )
        left = {lot["lot_id"]: int(lot["qty"]) for lot in queue}
        ordered = sorted(
            rows,
            key=lambda r: (
                r["assembly_start"] is None,
                at(r["assembly_start"]) or datetime.min,
                r["commitment_id"],
            ),
        )
        for row in ordered:
            cid = row["commitment_id"]
            stock = int(row.get("extra_stock") or 0)
            need = max(0, qty_of[cid] * int(row["per_set"]) - stock)
            pieces = []
            rest = need
            for lot in queue:
                if rest == 0:
                    break
                take = min(rest, left[lot["lot_id"]])
                if take <= 0:
                    continue
                left[lot["lot_id"]] -= take
                rest -= take
                pieces.append(
                    {
                        "lot_id": lot["lot_id"],
                        "qty": take,
                        "planned_at": lot["planned_at"],
                        "inspection_min": lot["inspection_min"],
                        "available_at": lot["available_at"],
                    }
                )
            start = at(row["assembly_start"])
            missing = []
            if start is None:
                missing.append("assembly_start")
            if rest > 0:
                missing.append(
                    "lots"
                )  # 입고 예정이 소요를 다 채우지 못한다 — 사용 가능 시각을 모른다
            usable = None
            if need == 0:
                usable = None
            elif rest == 0:
                usable = max(at(p["available_at"]) for p in pieces)
            slack = None
            shortage = None
            if start is not None:
                ready = sum(p["qty"] for p in pieces if at(p["available_at"]) <= start)
                shortage = max(0, need - ready)
                if need == 0:
                    slack = None  # 가용재고로 충분 — 입고에 묶이지 않는다
                elif usable is not None:
                    slack = minutes(start - usable)
            out[cid] = {
                "commitment_id": cid,
                "part_id": part,
                "per_set": int(row["per_set"]),
                "required_qty": qty_of[cid] * int(row["per_set"]),
                "extra_stock": stock,
                "allocated_qty": need - rest,
                "lots": pieces,
                "available_at": iso(usable),
                "assembly_start": row["assembly_start"],
                "slack_min": slack,
                "slack_seconds": None
                if usable is None or start is None
                else int((start - usable).total_seconds()),
                "start_delay_min": None if slack is None and need > 0 else max(0, -(slack or 0)),
                "shortage_at_start": shortage,
                "truck_cutoff": row.get("truck_cutoff"),
                "missing": missing,
            }
    return out


# ─────────────────────────── Y01 경보 판정 ───────────────────────────


def evaluate(
    revision: dict[str, Any],
    earlier: list[dict[str, Any]],
    master: dict[str, Any],
) -> dict[str, Any]:
    """
    구매 개정 한 건(한 통지)을 판정한다. `earlier` — 같은 발주행에서 앞서 평가한 개정들(판정 결과).
    재수신은
    부르는 쪽이 이미 걸렀다.
    """
    registered = at(revision["registered_at"])
    window = business_window(registered.date())
    changes = sorted(
        {
            e["revision_id"]
            for e in [*earlier, revision]
            if e["po_line"] == revision["po_line"]
            and int(e["revision_no"]) >= 1
            and at(e["registered_at"]).date() in window
            and at(e["registered_at"]) <= registered
        }
    )
    count = len(changes)
    lots = [_lot_view(lot) for lot in revision["lots"]]
    parts = {lot["part_id"] for lot in lots}
    qty_of = {c["commitment_id"]: int(c["qty"]) for c in master["commitments"]}
    demand = [d for d in master["demand"] if d["part_id"] in parts]
    rows = allocate(lots, demand, qty_of)
    slacks = [r["slack_min"] for r in rows.values() if r["slack_min"] is not None]
    seconds = [r["slack_seconds"] for r in rows.values() if r["slack_seconds"] is not None]
    shortages = [
        r["shortage_at_start"] for r in rows.values() if r["shortage_at_start"] is not None
    ]
    missing = sorted({f"{cid}:{m}" for cid, r in rows.items() for m in r["missing"]})
    if not demand:
        missing.append("demand")
    min_slack = min(slacks) if slacks else None
    shortage = max(shortages) if shortages else None
    reasons: list[str] = []
    short_by_time = bool(seconds) and min(seconds) < SLACK_ALERT_MIN * 60
    if int(revision["revision_no"]) == 0:
        judgment, reasons = FIRST, ["최초 예정 — 변경 횟수에서 제외"]
    elif count >= 2:
        judgment = ALERT
        reasons.append(f"최근 {WINDOW_BUSINESS_DAYS}영업일 내 {count}차 변경")
        if shortage:
            reasons.append(f"필요 시각 부족 {shortage}개")
        if short_by_time:
            reasons.append(f"최소 착수 여유 {min_slack}분")
    else:
        if shortage:
            reasons.append(f"필요 시각 부족 {shortage}개")
        if short_by_time:
            reasons.append(f"착수 여유 {min_slack}분 — {SLACK_ALERT_MIN}분 미만")
        if reasons:
            judgment = ALERT
        elif missing:
            judgment, reasons = (
                HOLD,
                ["첫 변경의 판정에 필요한 자료가 없다 — 정상으로 판정하지 않는다"],
            )
        else:
            judgment = RECORD
            reasons = [
                f"첫 변경 — 수량 충분·최소 착수 여유 {min_slack}분"
                f"(경계 {SLACK_ALERT_MIN}분 미만이 아님)"
            ]
    return {
        "revision_id": revision["revision_id"],
        "po_line": revision["po_line"],
        "revision_no": int(revision["revision_no"]),
        "registered_at": revision["registered_at"],
        "lots": lots,
        "total_qty": sum(int(lot["qty"]) for lot in lots),
        "window": [d.isoformat() for d in window],
        "changes_in_window": changes,
        "change_count": count,
        "min_slack_min": min_slack,
        "shortage": shortage,
        "judgment": judgment,
        "judgment_label": JUDGMENT_LABEL[judgment],
        "reasons": reasons,
        "missing": missing,
        "affected": [d["commitment_id"] for d in demand],  # 원천(주문영향) 순서
        "rows": rows,
        "rule_version": RULE_VERSION,
    }


# ─────────────────────────── A01 영향 분석 ───────────────────────────


def analyze(
    event: dict[str, Any], commitment_ids: list[str], master: dict[str, Any]
) -> list[dict[str, Any]]:
    """
    영향 약정별 근거 행 — 주문·부품·배정 입고분·사용 가능·기존 착수·착수 차질·차량 마감·고객 약정.
    수치나 배차
    가능성을 지어내지 않는다 — 자료가 없으면 그 칸은 `None`이고 `missing`에 남는다(T07).
    """
    by_id = {c["commitment_id"]: c for c in master["commitments"]}
    demand = {d["commitment_id"]: d for d in master["demand"]}
    out = []
    for cid in commitment_ids:
        c = by_id[cid]
        r = event["rows"].get(cid) or {}
        d = demand.get(cid) or {}
        missing = list(r.get("missing") or [])
        if not d.get("truck_cutoff"):
            missing.append("truck_cutoff")
        out.append(
            {
                "commitment_id": cid,
                "order_id": c["order_id"],
                "model": c["model"],
                "plant": c["plant"],
                "product": c["product"],
                "demo_role": c["demo_role"],
                "qty": c["qty"],
                "promised_at": c["promised_at"],
                "part_id": r.get("part_id"),
                "per_set": r.get("per_set"),
                "required_qty": r.get("required_qty"),
                "extra_stock": r.get("extra_stock"),
                "allocated_qty": r.get("allocated_qty"),
                "lots": r.get("lots") or [],
                "available_at": r.get("available_at"),
                "assembly_start": r.get("assembly_start"),
                "start_delay_min": r.get("start_delay_min"),
                "slack_min": r.get("slack_min"),
                "truck_cutoff": d.get("truck_cutoff"),
                # 출하 영향은 운송 가능 여부를 추정해 확정하지 않는다 — 마감 자료가 없으면 미확인
                "shipment": "미확인" if not d.get("truck_cutoff") else "자료 있음",
                "missing": missing,
            }
        )
    return out


# ─────────────────────────── 상황판 (UI-D01) ───────────────────────────


def _rate(num: int, den: int) -> str | None:
    if den == 0:
        return None  # 대상 없음 — 0%가 아니다(G03)
    return str((Decimal(num) / Decimal(den)).quantize(Decimal("0.0001"), ROUND_HALF_UP))


def on_time(c: dict[str, Any]) -> bool:
    """
    약정시각까지 약정수량을 전량 인수했나(G01). 출하만으로는 아니다 — 인수 실적이 없으면
    미준수.
    """
    accepted = at(c.get("accepted_at"))
    return (
        c.get("accepted_qty") is not None
        and int(c["accepted_qty"]) >= int(c["qty"])
        and accepted is not None
        and accepted <= at(c["promised_at"])
    )


def otd(master: dict[str, Any], as_of: str) -> dict[str, Any]:
    """
    직전 마감기간 OTD — 분모는 그 기간 약정시각이 기준시각까지 도래한 고유 약정, 분자는 그 시각까지
    전량 인수된
    약정(구현명세 §4). 아직 도래하지 않은 약정은 지연 실적으로 세지 않는다(G03).
    """
    now = at(as_of)
    start, end = CLOSED_PERIOD
    due = [
        c
        for c in master["commitments"]
        if start <= at(c["promised_at"]).date() < end and at(c["promised_at"]) <= now
    ]
    models = sorted({c["model"] for c in master["commitments"]})
    by_model = []
    for m in models:
        mine = [c for c in due if c["model"] == m]
        hit = sum(1 for c in mine if on_time(c))
        by_model.append(
            {"model": m, "due": len(mine), "on_time": hit, "otd": _rate(hit, len(mine))}
        )
    hit = sum(1 for c in due if on_time(c))
    rate = _rate(hit, len(due))
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat(), "label": CLOSED_LABEL},
        "numerator": hit,
        "denominator": len(due),
        "otd": rate,
        "target": str(OTD_TARGET),
        "meets_target": None if rate is None else Decimal(rate) >= OTD_TARGET,
        "late": [c["commitment_id"] for c in due if not on_time(c)],
        "by_model": by_model,
    }


def open_commitments(
    master: dict[str, Any], lots: list[dict[str, Any]], as_of: str
) -> list[dict[str, Any]]:
    """
    아직 도래하지 않은 시연 약정(11월 8건) — 지금 알려진 입고 예정으로 계산한 기존 착수 차질. 대표
    S·R은 사건
    약정이고 c·d·e는 정상 배경 목록이다(배경도 같은 계산, G08).
    """
    now = at(as_of)
    upcoming = [c for c in master["commitments"] if at(c["promised_at"]) > now]
    qty_of = {c["commitment_id"]: int(c["qty"]) for c in master["commitments"]}
    known = [*master["background_lots"], *lots]
    ids = {c["commitment_id"] for c in upcoming}
    rows = allocate(known, [d for d in master["demand"] if d["commitment_id"] in ids], qty_of)
    out = []
    for c in upcoming:
        r = rows.get(c["commitment_id"]) or {}
        out.append(
            {
                "commitment_id": c["commitment_id"],
                "order_id": c["order_id"],
                "model": c["model"],
                "demo_role": c["demo_role"],
                "qty": c["qty"],
                "promised_at": c["promised_at"],
                "part_id": r.get("part_id"),
                "available_at": r.get("available_at"),
                "assembly_start": r.get("assembly_start"),
                "start_delay_min": r.get("start_delay_min"),
                "truck_cutoff": r.get("truck_cutoff"),
            }
        )
    return out


__all__ = [
    "ALERT",
    "FIRST",
    "HOLD",
    "OTD_TARGET",
    "RECORD",
    "RULE_VERSION",
    "SLACK_ALERT_MIN",
    "allocate",
    "analyze",
    "business_window",
    "evaluate",
    "open_commitments",
    "otd",
]
