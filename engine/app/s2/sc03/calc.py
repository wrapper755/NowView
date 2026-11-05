"""
시나리오 2 장면 3 규칙 계산 — 수행계획 v2 제안·검사(A03·Y01, N03A 재진입)·원업무 회신 연결(U06,
N09)·전량 대안 비교(A01, N09)·재보고 기준(Y01)·결정 이후 재보고 조건(N10 뒤).

숫자는 여기서만 만든다. 입력은 장면 2 인계(HAND-02 — R의 출하 준비·이용 정기차·예상 도착)와 회사
시스템의 원천(SC03운송회신의 회신 칸, SC03고객권한의 고객 소요·전결 한도, SC02정기차)이다.
통합가상데이터 v0.3의 파생 칸(SC03대안비교의 필요량·대수·운송 가능량·추가비·여유·초과액·판정,
SC03요약)은 시험이 대조하는 기대값이다 — 화면·기록에 상수로 쓰지 않는다.

구현명세 §2:
* 공통 입력은 준비 16:00 · 고객 약정 18:30 · 전량 240세트. 금액은 기본 운임 대비 추가비(원), 시간
  비교는 같은 날짜·시간대. 고객 검수 조건상 **분할 납품은 후보로 만들지 않는다**.
* 정기차 유지 — 장면 2의 R-2(16:30 마감, 17:00 출발). 여유 = 약정 − 도착.
* 전량 긴급 — 필요 대수 = 올림(필요량 ÷ 대당 세트), 운송 가능량 = min(필요 대수, 가능 대수) × 대당
  세트, 추가비 = 필요 대수 × 대당 추가비, 초과액 = max(0, 추가비 − 전결 한도).
* 견적은 회신 수신 뒤에만 쓴다. **판단시각 ≥ 예약 유효시각이면 재확인**이다(기한 전에 예약할 수
  있어야 한다). 약정·비용·차량·운행 가능시각 중 하나라도 미확인이면 실행 가능으로 확정하지 않는다.
* 재보고는 추가비 > 유효 전결 한도일 때다 — 한도와 같으면 금액만으로 재보고하지 않는다(T05). 한도
  초과는 보고 경로를 정할 뿐 대응안을 고르지 않는다.
"""

from __future__ import annotations

import math
import re
from typing import Any

from app.platform import catalog
from app.s2.sc01.calc import at, iso, minutes

PLAN_ID = "CP-S2-V2"
BASE_PLAN_ID = "CP-S2-V1"
LINK_ID = "LINK-03"
COMPARISON_ID = "CMP-03"
ESCALATION_ID = "ESC-03"
DECISION_ID = "DEC-03"
ACTION_ID = "ACT-03"
HANDOFF_ID = "HAND-03"
ALT_REG, ALT_EXP = "ALT-REG", "ALT-EXP"
#: 대안 이름(SC03대안비교 「대안」)과 결정 표시(SC03요약 「H05 결정」)
ALT_NAMES = {ALT_REG: "정기차 유지", ALT_EXP: "전량 긴급차"}
DECISION_LABEL = {ALT_REG: "정기차 유지", ALT_EXP: "전량 긴급 운송"}
PASS, BLOCKED = "PASS", "BLOCKED"

#: 대안 판정(SC03대안비교 「판정」의 글 그대로) — 회신이 없을 때의 「조건 미확인」만 더했다
SHORT, ON_TIME = "SHORT", "ON_TIME"
RECHECK, UNCONFIRMED = "RECHECK", "UNCONFIRMED"
ESCALATE, WITHIN = "ESCALATE", "WITHIN_LIMIT"
VERDICT_LABEL = {
    SHORT: "납기 부족",
    ON_TIME: "기한 내 전망",
    RECHECK: "조건 재확인",
    UNCONFIRMED: "조건 미확인",
    ESCALATE: "임원 재보고",
    WITHIN: "한도 이내",
}
#: 실행 가능으로 확정하지 않는 판정 — 이 안은 권고·결정할 수 없다(갱신 요청)
NOT_EXECUTABLE = (RECHECK, UNCONFIRMED)
#: 회신 상태 — 수신 전 대기 · 유효 · 예약 유효시각 경과
WAITING, VALID, EXPIRED = "WAITING", "VALID", "EXPIRED"
REPLY_LABEL = {WAITING: "회신 대기", VALID: "회신 유효", EXPIRED: "예약 유효시각 경과"}


def _hm(value: str | None) -> str:
    found = at(value)
    return "미확인" if found is None else iso(found)[11:16]


def _version_no(source_id: str) -> int:
    """근거 id의 판(`Q-R-v2` → 2). 판이 없으면 1."""
    found = re.search(r"-v(\d+)$", source_id or "")
    return int(found.group(1)) if found else 1


def latest(sources: list[dict[str, Any]], kind: str, commitment_id: str) -> dict | None:
    """
    그 약정의 가장 새 근거 — 판이 높은 것(같으면 늦게 받은 것). 늦게 온 옛 판이 지금 값을 덮지
    않는다(구현명세 §1 「더 오래된 버전으로 현재값을 덮어쓰지 않는다」).
    """
    rows = [s for s in sources if s["kind"] == kind and s.get("commitment_id") == commitment_id]
    if not rows:
        return None
    return max(rows, key=lambda s: (_version_no(s["source_id"]), s["seq"]))


# ─────────────────────────── N03A 재진입 — 수행계획 v2(A03 제안 · Y01 검사) ───────────────


def propose(
    base: dict[str, Any],
    handoff: dict[str, Any],
    inquiry: dict[str, Any] | None,
    *,
    new_inquiry: bool = False,
) -> list[dict[str, Any]]:
    """
    A03 — v1의 완료 항목은 그대로 두고(재실행하지 않는다) R에 필요한 업무만 더한다: U06(진행 중인
    운송 문의를 **참조**)과 조건부 U07(재보고가 있을 때만 활성). `new_inquiry`는 시험 사례 —
    진행 중인 원업무가 있는데 새 문의를 만드는 제안(Y01이 막는다).
    """
    [item] = handoff["items"]
    cid = item["commitment_id"]
    items = [
        {**i, "carried_from": base["plan_id"], "carried_state": "완료", "target": None}
        for i in base["items"]
    ]
    why = (
        f"{cid} {item['qty']}세트 준비 {_hm(item['ready_at'])} · 정기차 {item['truck_id']} 도착 "
        f"{_hm(item['arrival'])} > 약정 {_hm(item['promised_at'])} ({item['shortfall_min']}분 부족)"
    )
    work = None if inquiry is None or new_inquiry else inquiry["work_id"]
    for i, (unit, pred) in enumerate((("U06", handoff["handoff_id"]), ("U07", "U06"))):
        spec, plan = catalog.UNITS[unit], catalog.UNIT_PLAN[unit]
        reference = unit == "U06" and work is not None
        items.append(
            {
                "seq": len(base["items"]) + i + 1,
                "unit": unit,
                "name": spec["name"],
                "steps": spec["steps"],
                "selection": spec["selection"],
                "delegation": plan["delegation"],
                "owner": plan["owner"],
                "predecessor": pred,
                "reason": (
                    f"{why} — 출하팀의 기존 운송 문의 {work}를 참조한다(새로 배정하지 않는다)"
                    if reference
                    else (
                        f"{why} — 운송 문의를 새로 만든다"
                        if unit == "U06"
                        else "재보고(전결 한도 초과)가 있을 때만 활성 — 결정은 생산총괄 임원(H05)"
                    )
                ),
                "link_mode": "reference" if reference else "new",
                "ref_work_id": work if reference else None,
                "ref_owner_role": inquiry["owner_role"] if reference and inquiry else None,
                "activation": "conditional" if unit == "U07" else "always",
                "target": cid,
                "carried_from": None,
                "carried_state": None,
            }
        )
    return items


def check(
    items: list[dict[str, Any]],
    handoff_id: str,
    *,
    base_version: str,
    current_version: str,
    inquiry: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Y01 — 허용 업무·선후행·위임·중복을 검사한다(구현명세 §1 D06). 기준 버전이 지금 계획이 아니거나
    권한을 넘으면 적용하지 않는다(기존 계획 유지). 완료 항목은 다시 검사하지 않는다(보존).
    """
    issues: list[dict[str, str]] = []
    new = [i for i in items if not i.get("carried_from")]
    if base_version != current_version:
        issues.append(
            {
                "unit": "-",
                "rule": "base_version",
                "message": f"기준 버전 {base_version}이 지금 계획 {current_version}이 아니다",
            }
        )
    for item in new:
        if item["unit"] not in catalog.UNITS:
            issues.append(
                {
                    "unit": item["unit"],
                    "rule": "registered",
                    "message": f"미등록 업무 {item['unit']}",
                }
            )
    seen = {handoff_id} | {i["unit"] for i in items if i.get("carried_from")}
    for item in new:
        if item["predecessor"] not in seen:
            issues.append(
                {
                    "unit": item["unit"],
                    "rule": "order",
                    "message": f"{item['unit']}의 선행 {item['predecessor']}이 앞에 없다",
                }
            )
        seen.add(item["unit"])
        if item["delegation"] == "C":
            issues.append(
                {"unit": item["unit"], "rule": "delegation", "message": "위임 범위 초과(C)"}
            )
    busy = inquiry is not None and inquiry.get("state") == "IN_PROGRESS"
    for item in new:
        if item["unit"] != "U06" or not busy:
            continue
        if item["link_mode"] != "reference" or item.get("ref_work_id") != inquiry["work_id"]:
            issues.append(
                {
                    "unit": "U06",
                    "rule": "duplicate",
                    "message": (
                        f"진행 중인 원업무 {inquiry['work_id']}(담당 {inquiry['owner_role']})가 "
                        "있는데 새 문의를 만든다 — 참조로 연결한다"
                    ),
                }
            )
    for item in new:
        human = [r for r in item["owner"] if catalog.ROLES.get(r, {}).get("kind") == catalog.HUMAN]
        if item["unit"] == "U07" and ("H05" not in human or item["activation"] != "conditional"):
            issues.append(
                {
                    "unit": "U07",
                    "rule": "decision",
                    "message": "경영검토는 재보고가 있을 때만 활성이고 결정은 사람(H05)이다",
                }
            )
    return {
        "result": BLOCKED if issues else PASS,
        "issues": issues,
        "rules": ["base_version", "registered", "order", "delegation", "duplicate", "decision"],
        "needs_approval": False,  # 위임 범위 안 조합 — 구성 승인 요청 없음
    }


# ─────────────────────────── N09 — 원업무 회신 연결(U06) ───────────────────────────


def reply_state(reply: dict[str, Any] | None, now: str) -> str:
    """회신 상태 — 판단시각 ≥ 예약 유효시각이면 경과(재확인 대상)."""
    if reply is None:
        return WAITING
    until = at(reply.get("valid_until"))
    if until is None or at(now) >= until:
        return EXPIRED
    return VALID


def link_state(
    inquiry: dict[str, Any] | None,
    sources: list[dict[str, Any]],
    commitment_id: str,
    now: str,
    used: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """
    원업무의 지금 회신과 고객 소요 확인 — 비교해도 되는가(`ready`). `used`는 갱신 요청·근거 변경으로
    물린 비교의 근거(회신 id, 고객 확인 id) — 그것과 다른 새 근거가 와야 다시 비교한다.
    """
    replies = [] if inquiry is None else inquiry.get("replies") or []
    reply = latest(replies, "transport_reply", commitment_id)
    customer = latest(sources, "customer_condition", commitment_id)
    state = reply_state(reply, now)
    reasons: list[str] = []
    if inquiry is None or inquiry.get("state") != "IN_PROGRESS":
        reasons.append("원업무 운송 문의가 아직 없다")
    if state == WAITING:
        reasons.append("운송사 회신 대기 — 문의 진행 중")
    elif state == EXPIRED:
        reasons.append(
            f"{reply['source_id']} 예약 유효시각 {_hm(reply['valid_until'])} 경과 — 갱신 필요"
        )
    if customer is None:
        reasons.append("영업의 고객 소요 확인 대기")
    basis = (
        None if reply is None or customer is None else (reply["source_id"], customer["source_id"])
    )
    ready = state == VALID and customer is not None
    if ready and used is not None and basis == used:
        ready = False
        reasons.append("갱신 요청 — 같은 근거로는 다시 비교하지 않는다. 새 회신 대기")
    return {
        "reply": reply,
        "reply_state": state,
        "customer": customer,
        "basis": basis,
        "ready": ready,
        "reasons": reasons,
    }


# ─────────────────────────── N09 — 전량 대안 비교(A01) ───────────────────────────


def _margin(promised: str | None, arrival: str | None) -> int | None:
    if at(promised) is None or at(arrival) is None:
        return None
    return minutes(at(promised) - at(arrival))


def compare(
    *,
    reply: dict[str, Any] | None,
    customer: dict[str, Any] | None,
    authority: dict[str, Any],
    regular: dict[str, Any],
    judged_at: str,
) -> dict[str, Any]:
    """
    CMP-03 — 정기차 유지와 전량 긴급차 두 안만(분할 납품은 만들지 않는다). `regular`는 장면 2
    판정의 정기차(차량편·출발·도착)와 R의 출하 준비다. 판단시각은 비교 시각이다.
    """
    need = None if customer is None else customer.get("qty")
    promised = None if customer is None else customer.get("promised_at")
    effective = at(authority.get("effective_at"))
    limit = authority["limit"] if effective is not None and effective <= at(judged_at) else None
    missing: list[str] = []
    if customer is None:
        missing.append("customer_condition")
    if limit is None:
        missing.append("authority")

    def excess(cost: int | None) -> int | None:
        return None if cost is None or limit is None else max(0, cost - limit)

    reg_margin = _margin(promised, regular.get("arrival"))
    reg = {
        "alternative_id": ALT_REG,
        "name": ALT_NAMES[ALT_REG],
        "need_qty": need,
        "trucks": 0,
        "capacity": need,
        "extra_cost": 0,
        "departure": regular.get("departure"),
        "arrival": regular.get("arrival"),
        "promised_at": promised,
        "margin_min": reg_margin,
        "excess": excess(0),
        "truck_id": regular.get("truck_id"),
        "basis": f"장면 2 판정의 정기차 {regular.get('truck_id')}",
    }
    reg["verdict"] = UNCONFIRMED if reg_margin is None else (SHORT if reg_margin < 0 else ON_TIME)
    exp: dict[str, Any] = {
        "alternative_id": ALT_EXP,
        "name": ALT_NAMES[ALT_EXP],
        "need_qty": need,
        "trucks": None,
        "capacity": None,
        "extra_cost": None,
        "departure": None,
        "arrival": None,
        "promised_at": promised,
        "margin_min": None,
        "excess": None,
        "available_vehicles": None,
        "sets_per_vehicle": None,
        "cost_per_vehicle": None,
        "valid_until": None,
        "basis": None,
        "conditions": [],
    }
    if reply is None:
        missing.append("transport_reply")
        exp["verdict"] = UNCONFIRMED
        exp["conditions"].append("운송사 회신 없음 — 차량·운임·출발 미확인")
    else:
        sets, per = reply.get("sets_per_vehicle"), reply.get("extra_cost_per_vehicle")
        vehicles = reply.get("vehicles")
        exp.update(
            available_vehicles=vehicles,
            sets_per_vehicle=sets,
            cost_per_vehicle=per,
            departure=reply.get("departure"),
            arrival=reply.get("arrival"),
            valid_until=reply.get("valid_until"),
            basis=f"운송사 회신 {reply['source_id']} (수신 {_hm(reply.get('received_at'))})",
        )
        if need is not None and sets:
            trucks = math.ceil(need / sets)
            exp["trucks"] = trucks
            if vehicles is not None:
                exp["capacity"] = min(trucks, vehicles) * sets
            if per is not None:
                exp["extra_cost"] = trucks * per
        exp["margin_min"] = _margin(promised, exp["arrival"])
        exp["excess"] = excess(exp["extra_cost"])
        conds = exp["conditions"]
        unknown = [
            k
            for k, v in (
                ("약정", promised),
                ("비용", exp["extra_cost"]),
                ("차량", exp["capacity"]),
                ("운행 가능시각", exp["departure"]),
            )
            if v is None
        ]
        if unknown:
            conds.append(f"미확인: {', '.join(unknown)}")
        if exp["capacity"] is not None and need is not None and exp["capacity"] < need:
            conds.append(
                f"가능 {vehicles}대 × {sets}세트 = {exp['capacity']}세트 < 필요 {need}세트 "
                "— 전량 불가"
            )
        if at(exp["valid_until"]) is None or at(judged_at) >= at(exp["valid_until"]):
            conds.append(f"판단시각 ≥ 예약 유효시각 {_hm(exp['valid_until'])} — 재확인")
        ready_at = regular.get("ready_at")
        if at(ready_at) and at(exp["departure"]) and at(ready_at) > at(exp["departure"]):
            conds.append(f"출하 준비 {_hm(ready_at)} > 출발 {_hm(exp['departure'])}")
        if unknown:
            exp["verdict"] = UNCONFIRMED
        elif conds:
            exp["verdict"] = RECHECK
        elif exp["excess"] is None:
            exp["verdict"] = UNCONFIRMED
        else:
            exp["verdict"] = ESCALATE if exp["excess"] > 0 else WITHIN
    for alt in (reg, exp):
        alt["verdict_label"] = VERDICT_LABEL[alt["verdict"]]
    faster = (
        None
        if at(reg["arrival"]) is None or at(exp["arrival"]) is None
        else minutes(at(reg["arrival"]) - at(exp["arrival"]))
    )
    return {
        "alternatives": [reg, exp],
        "excluded": []
        if customer is None
        else [{"alternative": "분할 납품", "reason": customer.get("condition")}],
        "authority": {**authority, "applied_limit": limit},
        "faster_min": faster,
        "missing": missing,
        "judged_at": judged_at,
    }


def alternative(comparison: dict[str, Any], alt_id: str) -> dict[str, Any]:
    return next(a for a in comparison["alternatives"] if a["alternative_id"] == alt_id)


def needs_escalation(cost: int | None, limit: int | None) -> bool | None:
    """추가비 > 유효 전결 한도면 재보고(한도와 같으면 아니다, T05). 모르면 None."""
    if cost is None or limit is None:
        return None
    return cost > limit


# ─────────────────────────── 결정 이후 — 재보고 조건(T09) ───────────────────────────


def re_report_triggers(
    decision: dict[str, Any], reply: dict[str, Any] | None, customer: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """
    결정 조건(3대 확보 · 추가비 한도 · 약정 전 도착)과 새 근거를 대조한다 — 하나라도 어기면 H05
    재보고다. 변경 조건으로 자동 집행하거나 사건을 끝내지 않는다.
    """
    if decision["selected"] != ALT_EXP or reply is None:
        return []
    base = decision["terms"]
    need = (customer or {}).get("qty") or base["need_qty"]
    promised = (customer or {}).get("promised_at") or base["promised_at"]
    found = []
    sets = reply.get("sets_per_vehicle")
    trucks = None if not sets else math.ceil(need / sets)
    vehicles = reply.get("vehicles")
    if trucks is None or vehicles is None or vehicles < base["trucks"] or vehicles < trucks:
        found.append(
            {
                "rule": "vehicles",
                "label": f"{base['trucks']}대 미확보",
                "before": base["trucks"],
                "after": vehicles,
            }
        )
    per = reply.get("extra_cost_per_vehicle")
    cost = None if trucks is None or per is None else trucks * per
    if cost is None or cost > decision["limit"]:
        found.append(
            {
                "rule": "cost",
                "label": "추가비 결정 한도 초과",
                "before": decision["limit"],
                "after": cost,
            }
        )
    if at(reply.get("arrival")) is None or at(reply["arrival"]) > at(promised):
        found.append(
            {
                "rule": "arrival",
                "label": f"약정 {_hm(promised)} 이후 도착 전망",
                "before": base["arrival"],
                "after": reply.get("arrival"),
            }
        )
    return found


def summary(
    comparison: dict[str, Any] | None,
    decision: dict[str, Any] | None,
    action: dict[str, Any] | None,
) -> dict[str, Any]:
    """SC03요약의 칸 — 두 안의 여유·긴급 추가비(견적)·팀장 한도 초과·H05 결정·H04 과제."""
    reg = exp = None
    if comparison is not None:
        reg, exp = alternative(comparison, ALT_REG), alternative(comparison, ALT_EXP)
    return {
        "regular_margin_min": None if reg is None else reg["margin_min"],
        "express_margin_min": None if exp is None else exp["margin_min"],
        "express_extra_cost": None if exp is None else exp["extra_cost"],
        "express_excess": None if exp is None else exp["excess"],
        "decision": None if decision is None else DECISION_LABEL[decision["selected"]],
        "action": None
        if action is None
        else {"ASSIGNED": "배정", "ACCEPTED": "인수"}.get(action["state"], action["state"]),
    }


__all__ = [
    "ALT_EXP",
    "ALT_REG",
    "BLOCKED",
    "PASS",
    "alternative",
    "check",
    "compare",
    "latest",
    "link_state",
    "needs_escalation",
    "propose",
    "re_report_triggers",
    "reply_state",
    "summary",
]
