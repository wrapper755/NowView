"""
시나리오 2 장면 4 규칙 계산 — 실행 결과 대조(N11, U08)·당시 자료 재현(SNAP-0900 초기선별)·정규노선
조정 요청의 접수·회신·채택 판정(N14 재현)·시험 분기와 인수시험(N14)·기준 적용 상태와 사건별 적용
버전(N15·N16).

숫자는 여기서만 만든다. 입력은 앞 장면 문서(장면 2의 분석 사본·반영본 재평가, 장면 3의 결정·과제·
인계)와 회사 시스템의 원천(SC04실적의 증빙 칸, SC04요청이력의 계약·재현 시각, SC04회신재현의
시험 분기 입력)이다. 통합가상데이터 v0.4의 파생 칸(SC04실적의 여유·결과, SC04초기선별 전부,
SC04회신재현의 마감여유·도착 후보·처리 경로·채택 ETA·여유·비용 전망·회피액, SC04기준적용의
집계·판정, SC04요약)은 시험이 대조하는 기대값이다 — 화면·기록에 상수로 쓰지 않는다.

구현명세:
* §1 결과 — 약정 ID로 원결정과 후속 증빙을 잇는다. 인수수량 = 약정수량이고 인수가 약정시각 이내면
  「정시 전량」. 수량·시각이 없으면 인수 미확인, 정산이 없으면 비용 미확인 — 각각 따로 갱신한다.
* §2 재현 — SNAP-0900은 11/4 09:00까지 가용한 자료(P-v2·배정·라인·작업시간·정기차·계약)만 묶는다.
  09:12 승인·09:14 반영본·운송사 회신은 그 뒤 사건이다. 변경 접수 마감 = 기점 출발 − 24시간.
* §3 채택 — 접수 ≤ 마감 · 수락 · 전량 수용 · 타 고객 차질 없음 · 추가운임 0원 · 도착 ≤ 약정 ·
  반영본 재조회 일치 · 출하 준비 ≤ 울산 출발이 모두일 때만 조정 정규편이다. 수락 시점(09:08)에는
  생산 반영 확인 대기다. 회피 가능액은 **조건부**이고 실제 절감이 아니다.
* §4 인수시험 01~09와 SC04기준적용(1·1·7 → 표본 일치).
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from app.s2.sc01 import calc as sc01_calc
from app.s2.sc01.calc import at, iso
from app.s2.sc02 import calc as sc02_calc

OUTCOME_ID = "OUT-04"
IMPROVEMENT_ID = "IMP-04"
REPLAY_ID = "RPL-04"
SNAPSHOT_ID = "SNAP-0900"
REQUEST_ID, ACK_ID, REPLY_ID = "REQ-R-04", "ACK-R-04", "REP-R-04"
TEST_ID, APPROVAL_ID, CONFIG_ID = "TEST-04", "APP-04", "CFG-04"
#: 검증본(SC04기준적용 「검증본」) — 개정한 KRI·Control 묶음
KRI_VERSION = "KRI-CTL-v2"
#: 기존 사건이 쓰는 기준(SC04기준적용 CASE-S2-01 「기존 버전」) — 장면 1의 공급 KRI 규칙
PREVIOUS_LABEL = "기존 버전"
PREVIOUS_RULES = (sc01_calc.RULE_VERSION,)
#: 다음 신규 사건 예시(SC04기준적용 CASE-NEXT-01 「11/9 09:00 신규 사건 예시」)
NEXT_CASE = "CASE-NEXT-01"
NEXT_CASE_AT = "2026-11-09T09:00:00+09:00"
CASE_ID = "CASE-S2-01"
TARGET = "COM-R"

#: 실적 판정(SC04실적 「결과」의 글)
ON_TIME_FULL, LATE, UNCONFIRMED = "정시 전량", "미준수", "미확인"
#: 초기선별 「조정 후보」의 글
CANDIDATE, OBSERVE, SUPPLEMENT, OUT_OF_SCOPE = "조정 후보", "관찰", "보완", "사건 범위 밖"
#: 회신재현 「처리 경로」의 글
ADOPT, EXISTING = "조정 정규편", "기존 운송 검토"
#: 기준적용 판정의 글
SAMPLE_MATCH, RETEST = "표본 일치", "보완·재시험"
APPLIED, HELD = "신규 사건 적용", "적용 보류"
KEEP = "기존 버전 유지"
#: 회사 채택 판정 — 수락 시점(생산 반영 전)과 최종을 가른다
AWAITING_PRODUCTION = "AWAITING_PRODUCTION"
ADOPTED, NOT_ADOPTED, ON_HOLD = "ADOPTED", "NOT_ADOPTED", "ON_HOLD"
ADOPTION_LABEL = {
    AWAITING_PRODUCTION: "생산 반영 확인 대기",
    ADOPTED: "조정 정규편 채택",
    NOT_ADOPTED: "기존 운송 검토로 복귀",
    ON_HOLD: "채택 보류 — 근거 보완",
}
#: 타 고객 기존 약정 차질 여부(구현명세 §3) — 0 차질 없음 · 1 차질 예상 · 공란 미확인
IMPACT_LABEL = {0: "차질 없음", 1: "차질 예상", None: "미확인"}


def _won(value: int | None) -> str:
    return "미확인" if value is None else f"{value:,}원"


def signed_min(value: int | None) -> str:
    """사람이 읽는 분 — +60분 · −30분(빼기 기호)."""
    if value is None:
        return "미확인"
    return f"+{value}분" if value > 0 else f"−{-value}분" if value < 0 else "0분"


def _hm(value: str | None) -> str:
    found = at(value)
    return "미확인" if found is None else iso(found)[11:16]


def round_min(delta: timedelta) -> int:
    """엑셀 `ROUND((a−b)*1440, 0)` — 분 단위 반올림(0.5는 올린다)."""
    sec = delta.total_seconds()
    return int(sec // 60 + (1 if sec % 60 >= 30 else 0)) if sec >= 0 else -round_min(-delta)


def _version_no(source_id: str) -> int:
    found = re.search(r"-v(\d+)$", source_id or "")
    return int(found.group(1)) if found else 1


def latest_evidence(evidence: list[dict[str, Any]], kind: str, cid: str) -> dict | None:
    """그 약정·종류의 가장 새 증빙 — 판이 높은 것(같으면 늦게 받은 것). 옛 판이 덮지 않는다."""
    rows = [e for e in evidence if e["kind"] == kind and e["commitment_id"] == cid]
    if not rows:
        return None
    return max(rows, key=lambda e: (_version_no(e["source_id"]), e["seq"]))


# ─────────────────────────── N11 — 결정과 실적 대조(D09) ───────────────────────────


def outcome(
    master: dict[str, Any],
    evidence: list[dict[str, Any]],
    links: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    약정별 결정·증빙 대조. `links`는 약정 → {결정·과제 표시, 결정 조건(한도·예약 기한·예상 도착),
    예약 필요 여부}다(장면 2·3 문서에서). 인수와 비용은 따로 판정한다 — 정산이 없어도 인수는
    정시일 수 있고, 인수가 없으면 비용이 있어도 정시가 아니다(미확인).
    """
    by_id = {c["commitment_id"]: c for c in master["commitments"]}
    rows = []
    for cid, link in links.items():
        c = by_id[cid]
        booking = latest_evidence(evidence, "booking", cid)
        pod = latest_evidence(evidence, "delivery_receipt", cid)
        settle = latest_evidence(evidence, "settlement", cid)
        expected = (["booking"] if link.get("needs_booking") else []) + [
            "delivery_receipt",
            "settlement",
        ]
        got = {"booking": booking, "delivery_receipt": pod, "settlement": settle}
        missing = [k for k in expected if got[k] is None]
        accepted_qty = None if pod is None else pod.get("accepted_qty")
        accepted_at = None if pod is None else pod.get("accepted_at")
        margin = (
            None if at(accepted_at) is None else round_min(at(c["promised_at"]) - at(accepted_at))
        )
        if accepted_qty is None or margin is None:
            result = UNCONFIRMED
            if pod is not None:
                missing.append("delivery_receipt.qty_or_time")
        elif accepted_qty == c["qty"] and margin >= 0:
            result = ON_TIME_FULL
        else:
            result = LATE
        cost = None if settle is None else settle.get("extra_cost")
        terms = link.get("terms") or {}
        checks: list[dict[str, Any]] = []
        if link.get("needs_booking"):
            due = terms.get("reservation_due")
            reserved = None if booking is None else booking.get("reserved_at")
            checks.append(
                {
                    "check": "reservation",
                    "label": f"예약 기한 {_hm(due)} 전 확보",
                    "planned": due,
                    "actual": reserved,
                    "ok": None
                    if at(reserved) is None or at(due) is None
                    else at(reserved) < at(due),
                }
            )
        if terms.get("limit") is not None:
            checks.append(
                {
                    "check": "cost",
                    "label": "결정 한도 이내 집행",
                    "planned": terms["limit"],
                    "actual": cost,
                    "ok": None if cost is None else cost <= terms["limit"],
                }
            )
        if terms.get("expected_arrival") is not None:
            checks.append(
                {
                    "check": "arrival",
                    "label": "결정 당시 도착 전망 대비 인수",
                    "planned": terms["expected_arrival"],
                    "actual": accepted_at,
                    "ok": None
                    if at(accepted_at) is None
                    else at(accepted_at) <= at(c["promised_at"]),
                }
            )
        transport = next(
            (e["transport"] for e in (booking, pod, settle) if e and e.get("transport")), None
        )
        rows.append(
            {
                "commitment_id": cid,
                "order_id": c["order_id"],
                "model": c["model"],
                "decision": link["label"],
                "decision_ids": link.get("ids") or [],
                "transport": transport,
                "reserved_at": None if booking is None else booking.get("reserved_at"),
                "qty": c["qty"],
                "accepted_qty": accepted_qty,
                "promised_at": c["promised_at"],
                "accepted_at": accepted_at,
                "margin_min": margin,
                "result": result,
                "extra_cost": cost,
                "cost_state": "미확인" if cost is None else "정산 확인",
                "evidence_ids": [e["source_id"] for e in (booking, pod, settle) if e],
                "missing": missing,
                "checks": checks,
            }
        )
    seen = [e["source_id"] for e in evidence]
    return {
        "rows": rows,
        "on_time_full": sum(1 for r in rows if r["result"] == ON_TIME_FULL),
        "unconfirmed": [r["commitment_id"] for r in rows if r["result"] == UNCONFIRMED],
        "actual_extra_cost": {r["commitment_id"]: r["extra_cost"] for r in rows},
        "duplicates": len(seen) - len(set(seen)),
        "ready": all(not r["missing"] for r in rows),
    }


# ─────────────────────────── N14 재현 — SNAP-0900 초기선별 ───────────────────────────


def snapshot_lots(master: dict[str, Any], snapshot_at: str) -> tuple[str | None, list[dict]]:
    """그 시각까지 등록된 가장 새 구매 개정(SNAP-0900 = P-v2)과 그 입고분."""
    known = [
        r
        for r in master["revisions"]
        if at(r["scheduled_registration"]) is not None
        and at(r["scheduled_registration"]) <= at(snapshot_at)
    ]
    if not known:
        return None, []
    last = max(known, key=lambda r: r["revision_no"])
    return last["revision_id"], last["lots"]


def route_cutoff(contract: dict[str, Any]) -> str:
    """변경 접수 마감 = 정규 순회차 기점 출발 − 24시간(울산 상차·고객 약정 기준이 아니다)."""
    return iso(at(contract["origin_departure"]) - timedelta(hours=contract["lead_hours"]))


def screen(
    master: dict[str, Any], analysis_rows: list[dict[str, Any]], snapshot_at: str
) -> dict[str, Any]:
    """
    SC04초기선별 — 같은 09:00 자료로 주문별 운송납기 여유(약정 − 미조정 정기차 도착)를 잠정
    계산한다.
    대표 S·R은 A02 변경안과 같은 규칙(자재 사용 가능·빈 라인 시작 중 늦은 시각 + 조립 + 준비)으로
    출하 준비를 내고 준비 ≤ 마감인 첫 정기차를 고른다. 배경 6건은 사건 범위 밖이다(요청 0건).
    승인본(09:12)·반영본(09:14)·운송사 회신은 쓰지 않는다.
    """
    revision, lots = snapshot_lots(master, snapshot_at)
    opens = sc01_calc.open_commitments(master, lots, snapshot_at)
    plan = master["production_plan"]
    drafted = sc02_calc.draft(analysis_rows, master, plan)
    by_draft = {r["commitment_id"]: r for r in drafted["rows"]}
    trucks = sc02_calc._trucks_by(master)
    rows = []
    for c in opens:
        cid = c["commitment_id"]
        d = by_draft.get(cid) if c["demo_role"] == "representative" else None
        ready = None if d is None else at(d.get("ready_at"))
        arrival = truck = None
        if ready is not None:
            for t in trucks.get(cid) or []:
                if at(t["cutoff"]) is not None and ready <= at(t["cutoff"]):
                    arrival, truck = t["arrival"], t["truck_id"]
                    break
        margin = None if arrival is None else round_min(at(c["promised_at"]) - at(arrival))
        if c["demo_role"] == "background":
            verdict = OUT_OF_SCOPE
        elif margin is None:
            verdict = SUPPLEMENT
        else:
            verdict = CANDIDATE if margin < 0 else OBSERVE
        rows.append(
            {
                "commitment_id": cid,
                "role": c["demo_role"],
                "promised_at": c["promised_at"],
                "available_at": c.get("available_at"),
                "line_start": None if d is None else d.get("start"),
                "assembly_min": None if d is None else d.get("assembly_min"),
                "prep_min": None if d is None else d.get("prep_min"),
                "ready_at": None if d is None else d.get("ready_at"),
                "truck_id": truck,
                "arrival": arrival,
                "margin_min": margin,
                "verdict": verdict,
            }
        )
    return {
        "snapshot_id": SNAPSHOT_ID,
        "data_as_of": snapshot_at,
        "revision_id": revision,
        "production_plan_version": plan["version"],
        "excluded_inputs": ["생산 승인(09:12)", "반영본 재조회(09:14)", "운송사 회신", "실제 인수"],
        # 그 시각 뒤에 등록된 구매 개정을 썼나 — 미래 정보 누출 점검(P07)
        "uses_after_snapshot": any(
            at(r["scheduled_registration"]) > at(snapshot_at)
            for r in master["revisions"]
            if r["revision_id"] == revision
        ),
        "rows": rows,
        "candidates": [r["commitment_id"] for r in rows if r["verdict"] == CANDIDATE],
    }


# ─────────────────────────── N14 재현 — 접수·회신·채택 ───────────────────────────


def evaluate_branch(
    branch: dict[str, Any],
    *,
    cutoff: str,
    need_qty: int,
    snapshot_ready: str | None,
    promised_at: str,
    reflect: dict[str, Any] | None,
    actual_cost: int | None,
) -> dict[str, Any]:
    """
    SC04회신재현 한 행 — 운송사 회신(접수·수락·수용량·추가운임·출발·운행)과 회사 조건(타 고객 영향·
    반영본 재조회·출하 준비)을 함께 본다. `reflect`는 장면 2 반영본 재평가의 R(일치·출하 준비)이고
    없으면 생산 반영 확인 전이다. 하나라도 어기면 기존 운송 검토 — 채택 ETA·비용 전망·회피액은 공란.
    """
    received = branch.get("received_at")
    deadline = None if at(received) is None else round_min(at(cutoff) - at(received))
    departure, run = branch.get("departure"), branch.get("run_min")
    candidate = None
    if at(departure) is not None and run is not None:
        candidate = iso(at(departure) + timedelta(minutes=run))
    impact, fare, cap = (
        branch.get("other_customer_impact"),
        branch.get("extra_fare"),
        branch.get("capacity"),
    )
    reasons: list[str] = []
    if received is None:
        reasons.append("접수증 없음 — 접수 미확인")
    elif deadline is not None and deadline < 0:
        reasons.append(f"접수 {_hm(received)} > 마감 {_hm(cutoff)} — 기한 경과")
    reply = branch.get("reply")
    if reply != "수락":
        reasons.append("운송사 거절" if reply == "거절" else "운송사 회신 대기 — 미회신")
    if reply == "수락":
        if cap is None or cap < need_qty:
            reasons.append(f"수용 {cap if cap is not None else '미확인'}세트 < 전량 {need_qty}세트")
        if impact is None:
            reasons.append("타 고객 기존 약정 영향 미확인 — 근거 보완")
        elif impact != 0:
            reasons.append("타 고객 기존 약정 차질 예상")
        if fare is None:
            reasons.append("추가운임 미확인")
        elif fare != 0:
            reasons.append(f"추가운임 {fare:,}원 — 계약 운임 초과")
        if candidate is None:
            reasons.append("도착 후보 미확인")
        elif at(candidate) > at(promised_at):
            reasons.append(f"도착 후보 {_hm(candidate)} > 약정 {_hm(promised_at)}")
        if at(departure) is not None and at(snapshot_ready) is not None:
            if at(departure) < at(snapshot_ready):
                reasons.append(f"출하 준비 {_hm(snapshot_ready)} > 울산 출발 {_hm(departure)}")
    production_wait = reflect is None
    if reflect is not None:
        if reflect.get("match") != sc02_calc.MATCHED:
            reasons.append("생산 반영본 재조회 불일치")
        elif at(departure) is not None and (
            at(reflect.get("ready_at")) is None or at(departure) < at(reflect["ready_at"])
        ):
            reasons.append(f"반영본 출하 준비 {_hm(reflect.get('ready_at'))} > 울산 출발")
    adopted = not reasons and not production_wait
    eta = candidate if adopted else None
    margin = None if eta is None else round_min(at(promised_at) - at(eta))
    cost = fare if adopted else None
    avoid = None if cost is None or actual_cost is None else actual_cost - cost
    if adopted:
        state = ADOPTED
    elif production_wait and not reasons:
        state = AWAITING_PRODUCTION
    elif reply == "수락" and impact is None and len(reasons) == 1:
        state = ON_HOLD
    else:
        state = NOT_ADOPTED
    return {
        "branch": branch.get("branch"),
        "reply": reply,
        "received_at": received,
        "deadline_margin_min": deadline,
        "capacity": cap,
        "other_customer_impact": impact,
        "impact_label": IMPACT_LABEL.get(impact, "미확인"),
        "extra_fare": fare,
        "departure": departure,
        "run_min": run,
        "arrival_candidate": candidate,
        "path": ADOPT if adopted else EXISTING,
        "state": state,
        "state_label": ADOPTION_LABEL[state],
        "eta": eta,
        "margin_min": margin,
        "cost_forecast": cost,
        "conditional_avoidance": avoid,
        "reasons": reasons,
    }


# ─────────────────────────── N14 — 인수시험 · SC04기준적용 ───────────────────────────


def application_state(test_verdict: str | None, confirmed: bool) -> str:
    """CFG-04 — 시험 표본 일치이고 H06 확인이 있어야 신규 사건에 적용한다(아니면 적용 보류)."""
    return APPLIED if test_verdict == SAMPLE_MATCH and confirmed else HELD


def version_for(case_at: str, effective_at: str | None) -> str:
    """사건별 적용 버전 — 효력시점 이후 생긴 신규 사건만 개선 버전이다(기존 사건 소급 금지)."""
    if effective_at is None or at(case_at) < at(effective_at):
        return PREVIOUS_LABEL
    return KRI_VERSION


def verify(
    *,
    master: dict[str, Any],
    screening: dict[str, Any],
    branch_results: list[dict[str, Any]],
    evaluate: Any,
    outcome_now: dict[str, Any],
    outcome_missing_pod: dict[str, Any],
    sends: int,
) -> dict[str, Any]:
    """
    인수시험 01~09(구현명세 §4)와 SC04기준적용 T-04-01~03·TEST-04. `evaluate`는 기본 수락 분기에
    칸을 바꿔 다시 판정하는 함수다(07 경계·06 미확인 — 구현명세가 정한 시험 입력). 판정은 기대
    결과와 실제 출력의 대조이고, 미실시를 통과로 미리 적지 않는다.
    """
    by = {b["branch"]: b for b in branch_results}
    rows: list[dict[str, Any]] = []

    def add(test_id: str, name: str, expected: str, actual: str, ok: bool) -> None:
        rows.append(
            {
                "test_id": test_id,
                "name": name,
                "expected": expected,
                "actual": actual,
                "diff": None if ok else "기대와 다름",
                "verdict": "PASS" if ok else "FAIL",
            }
        )

    on_time = outcome_now["on_time_full"]
    r_cost = outcome_now["actual_extra_cost"].get(TARGET)
    r_missing = next(r for r in outcome_missing_pod["rows"] if r["commitment_id"] == TARGET)
    add(
        "01",
        "인수·정산 증빙 및 재수신",
        "S·R 정시 2건 · R 집행 1,200,000원 · 중복 반영 0건 · 누락 항목은 미확인",
        f"정시 {on_time}건 · R {_won(r_cost)} · 중복 "
        f"{outcome_now['duplicates']}건 · 인수 증빙 없으면 R {r_missing['result']}",
        on_time == 2
        and r_cost == 1_200_000
        and outcome_now["duplicates"] == 0
        and r_missing["result"] == UNCONFIRMED
        and r_missing["extra_cost"] == r_cost,
    )
    margins = {r["commitment_id"]: r["margin_min"] for r in screening["rows"]}
    add(
        "02",
        "09:00 자료로 8건 선별",
        "S +60분 · R −30분 · R만 후보 · 이후 승인·회신 제외",
        f"S {signed_min(margins.get('COM-S'))} · R {signed_min(margins.get(TARGET))} · 후보 "
        f"{', '.join(screening['candidates']) or '없음'} · 8건 중 {len(screening['rows'])}",
        margins.get("COM-S") == 60
        and margins.get(TARGET) == -30
        and screening["candidates"] == [TARGET]
        and len(screening["rows"]) == 8
        and screening["production_plan_version"] == master["production_plan"]["version"]
        and not screening["uses_after_snapshot"],
    )
    base = by["기본 수락"]
    add(
        "03",
        "정상 접수·수락",
        "09:05 접수 · 마감까지 5분 · 반영본 확인 뒤 18:15 채택 · +15분 · 조건부 1,200,000원",
        f"{_hm(base['received_at'])} 접수 · {base['deadline_margin_min']}분 · "
        f"{_hm(base['eta'])} {base['path']} · {signed_min(base['margin_min'])} · "
        f"조건부 {_won(base['conditional_avoidance'])}",
        base["deadline_margin_min"] == 5
        and base["path"] == ADOPT
        and _hm(base["eta"]) == "18:15"
        and base["margin_min"] == 15
        and base["conditional_avoidance"] == 1_200_000,
    )
    fails = [by[n] for n in ("거절", "미회신", "접수증 없음")]
    add(
        "04",
        "거절 / 미회신 / 접수증 없음",
        "각각 기존 운송 검토 · 비용 전망 공란",
        " · ".join(f"{b['branch']} {b['path']}" for b in fails),
        all(b["path"] == EXISTING and b["cost_forecast"] is None for b in fails),
    )
    short, fare = by["적재 부족"], by["추가운임"]
    add(
        "05",
        "160세트만 수용 / 추가비 10만원",
        "각각 기존 운송 검토 · 전량·계약 운임 미충족 사유",
        f"{short['path']}({'; '.join(short['reasons'])}) · {fare['path']}"
        f"({'; '.join(fare['reasons'])})",
        short["path"] == EXISTING
        and any("전량" in r for r in short["reasons"])
        and fare["path"] == EXISTING
        and any("추가운임" in r for r in fare["reasons"]),
    )
    hit = by["타 고객 영향"]
    unknown = evaluate({"other_customer_impact": None})
    add(
        "06",
        "수락·전량·추가비 0원·타 고객 영향 1 / 미확인",
        "수락 유지 · 채택 보류 · R 도착 후보만 · 미확인값도 채택 보류",
        f"회신 {hit['reply']} · {hit['path']} · 후보 {_hm(hit['arrival_candidate'])} · ETA "
        f"{_hm(hit['eta'])} / 미확인 {unknown['state_label']}",
        hit["reply"] == "수락"
        and hit["path"] == EXISTING
        and hit["arrival_candidate"] is not None
        and hit["eta"] is None
        and unknown["path"] == EXISTING
        and unknown["state"] == ON_HOLD,
    )
    on_cut = evaluate({"received_at": "2026-11-04T09:10:00+09:00"})
    late = by["마감 경과"]
    mismatch = evaluate({}, reflect={"match": sc02_calc.MISMATCH, "ready_at": None})
    slow = evaluate({"departure": "2026-11-05T15:55:00+09:00"})
    add(
        "07",
        "마감 및 생산 경계",
        "09:10 접수 기한 내 · 09:11 경과 · 반영 불일치·준비 지연이면 채택 보류",
        f"09:10 {on_cut['path']} · 09:11 {late['path']} · 반영 불일치 {mismatch['path']} · "
        f"준비 지연 {slow['path']}",
        on_cut["path"] == ADOPT
        and late["path"] == EXISTING
        and mismatch["path"] == EXISTING
        and slow["path"] == EXISTING,
    )
    adopted = sum(1 for b in branch_results if b["path"] == ADOPT)
    existing = sum(1 for b in branch_results if b["path"] == EXISTING)
    add(
        "08",
        "시험 분기 집계",
        "8개 회신 표본 중 조정 정규편 1건 · 기존 운송 검토 7건 · 외부 송신 0건",
        f"{len(branch_results)}개 중 조정 {adopted} · 기존 {existing} · 외부 송신 {sends}",
        len(branch_results) == 8 and adopted == 1 and existing == 7 and sends == 0,
    )
    held = [application_state(RETEST, True), application_state(SAMPLE_MATCH, False)]
    old_case, new_case = (
        version_for("2026-11-04T09:00:00+09:00", "2026-11-09T00:00:00+09:00"),
        version_for(NEXT_CASE_AT, "2026-11-09T00:00:00+09:00"),
    )
    add(
        "09",
        "권한·효력·회귀",
        "미통과·H06 확인 누락은 적용 보류 · 신규 사건만 승인 버전 · 기존 사건은 당시 버전",
        f"{' · '.join(held)} · 신규 {new_case} · 기존 {old_case}",
        held == [HELD, HELD] and new_case == KRI_VERSION and old_case == PREVIOUS_LABEL,
    )
    sample = {
        "T-04-01": len(screening["candidates"]),
        "T-04-02": adopted,
        "T-04-03": existing,
    }
    matched = sample == {"T-04-01": 1, "T-04-02": 1, "T-04-03": 7}
    return {
        "test_id": TEST_ID,
        "version": KRI_VERSION,
        "data_as_of": screening["data_as_of"],
        "dataset_version": master["dataset_version"],
        "rows": rows,
        "sample": sample,
        "sample_expected": {"T-04-01": 1, "T-04-02": 1, "T-04-03": 7},
        "sample_verdict": SAMPLE_MATCH if matched else RETEST,
        "passed": matched and all(r["verdict"] == "PASS" for r in rows),
        "external_sends": sends,
    }


def summary(
    outcome_now: dict[str, Any] | None,
    screening: dict[str, Any] | None,
    early_min: int | None,
    request: dict[str, Any] | None,
    adoption: dict[str, Any] | None,
    october: dict[str, Any],
    application: str | None,
) -> dict[str, Any]:
    """SC04요약의 칸 — 실적·재현·수락 분기·10월 OTD·적용 상태. 재현 전망을 실적에 더하지 않는다."""
    r_margin = None
    if screening is not None:
        r_margin = next(
            (r["margin_min"] for r in screening["rows"] if r["commitment_id"] == TARGET), None
        )
    return {
        "on_time_full": None if outcome_now is None else outcome_now["on_time_full"],
        "r_actual_extra_cost": None
        if outcome_now is None
        else outcome_now["actual_extra_cost"].get(TARGET),
        "r_unadjusted_margin_min": r_margin,
        "detection_earlier_min": early_min,
        "receipt_margin_min": None if request is None else request.get("deadline_margin_min"),
        "adjusted_margin_min": None if adoption is None else adoption.get("margin_min"),
        "fare_forecast": None if adoption is None else adoption.get("cost_forecast"),
        "conditional_avoidance": None
        if adoption is None
        else adoption.get("conditional_avoidance"),
        "october_otd": october.get("otd"),
        "application": application,
    }


__all__ = [
    "ADOPT",
    "EXISTING",
    "KRI_VERSION",
    "application_state",
    "evaluate_branch",
    "outcome",
    "route_cutoff",
    "screen",
    "summary",
    "verify",
    "version_for",
]
