"""
시나리오 2 장면 2 규칙 계산 — 수행계획 제안·검사(A03·Y01, N03A)·생산계획 변경안(A02, N04)·반영본
대조(U04, N06)·주문별 납기 재평가(U05, N07).

숫자는 여기서만 만든다. 입력은 장면 1의 분석(ANA-01 — 배정 입고분·사용 가능 시각)과 회사 시스템의
원천 칸(SC02생산안의 빈 라인 시간·조립·준비 시간, SC02정기차, 원계획 PROD-V1)이다. 통합가상데이터
v0.2의 파생 칸(제안 착수·종료, 반영본 대조, 출하 준비·이용 정기차·예상 도착·여유·후속 경로,
SC02요약)은
시험이 대조하는 기대값이다 — 화면·기록에 상수로 쓰지 않는다.

구현명세 §3·§4:
* 제안 착수 = 자재 사용 가능시각과 모델별 빈 라인 시작 중 늦은 시각. 종료 = 착수 + 조립시간. 빈 시간
  종료 전에 완료하고 배정수량·라인·품질 조건을 충족해야 한다. 다른 주문을 밀어내는 안은 보완
  대상이다.
* 출하 준비 = **저장된**(재조회 일치) 조립 종료 + 품질·상차 준비. 그 약정의 정기차 중 마감 ≥ 준비인
  차량을 출발 순으로 고른다(같으면 탑승 가능 — T08). 여유(분) = 고객 약정 − 예상 도착. 0 이상은 인수
  관찰, 음수는 운송 확인. 대조 미완료·근거 누락·산출 불가는 보류하고 이유를 남긴다(0분으로 메우지
  않는다).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

from app.platform import catalog
from app.s2.sc01.calc import at, iso, minutes

#: 수행계획 버전(SC02수행계획 머리) — 사건마다 첫 판이 V1이다
PLAN_PREFIX = "CP-S2-V"
DRAFT_PREFIX = "PP-DRAFT-V"
#: 반영이 올리는 생산계획 버전 — 원계획 PROD-V1 다음 판(SC02확인 「반영 버전」)
TARGET_VERSION = "PROD-V2"
#: 장면 2가 고치는 주문 — 장면 1 Case의 영향 약정(대표 S·R). 배경 c·d·e는 원계획 그대로다.
OBSERVE, TRANSPORT, HOLD = "OBSERVE", "TRANSPORT", "HOLD"
ROUTE_LABEL = {OBSERVE: "인수 관찰", TRANSPORT: "운송 확인", HOLD: "판정 보류"}
MATCHED, MISMATCH, NOT_APPLIED, UNKNOWN = "MATCHED", "MISMATCH", "NOT_APPLIED", "UNKNOWN"
MATCH_LABEL = {
    MATCHED: "일치",
    MISMATCH: "불일치",
    NOT_APPLIED: "미반영",
    UNKNOWN: "결과 미확인",
}
PASS, BLOCKED = "PASS", "BLOCKED"


def _min(a: datetime, b: datetime) -> int:
    return minutes(a - b)


def _hm(value: str | None) -> str:
    """사유 글의 시각 — 같은 날(11/5 예정)의 비교라 시:분만."""
    found = at(value)
    return "미확인" if found is None else iso(found)[11:16]


# ─────────────────────────── N03A — 수행계획(A03 제안 · Y01 검사) ───────────────────────────

#: 장면 2의 업무 조합 — 통합 점검 → 변경안 → 사람 확인 → 반영 → 재평가(구현명세 §2 SC02수행계획)
SEQUENCE = ("U01", "U02", "U03", "U04", "U05")
REASON = {
    "U01": "ANA-01 및 입고 개정 재사용 — 필수 H03 확인 포함",
    "U02": "분할 입고로 기존 착수가 어렵다 — 배정과 모델별 빈 라인으로 조립 배치",
    "U03": "생산계획을 바꾸는 단계 — 두 주문을 포함한 변경안 한 버전을 사람이 확인",
    "U04": "확인된 버전만 반영하고 저장소에서 다시 읽어 대조",
    "U05": "반영본으로 주문별 납기를 다시 판정 — 남은 위험만 후속",
}


def propose(handoff: dict[str, Any], *, omit: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """
    A03 — 사건에 필요한 업무 단위를 카탈로그(U01~U09)에서 고른다. `omit`은 시험 사례(필수 확인을
    빠뜨린
    제안, T01)다. 선행은 앞 항목이고 첫 항목은 장면 1 인계다.
    """
    chosen = [u for u in SEQUENCE if u not in omit]
    items = []
    for i, unit in enumerate(chosen):
        spec = catalog.UNITS[unit]
        plan = catalog.UNIT_PLAN[unit]
        items.append(
            {
                "seq": i + 1,
                "unit": unit,
                "name": spec["name"],
                "steps": spec["steps"],
                "selection": spec["selection"],
                "delegation": plan["delegation"],
                "owner": plan["owner"],
                "predecessor": handoff["handoff_id"] if i == 0 else chosen[i - 1],
                "reason": REASON[unit],
                "link_mode": "new",
            }
        )
    return items


def check(items: list[dict[str, Any]], handoff_id: str) -> dict[str, Any]:
    """
    Y01 — 위임 범위와 필수 사람 확인을 검사한다(CP28·30). 누락·순환·미등록·권한 초과면 적용 차단.
    정상 흐름에 구성 승인을 더하지 않는다(위임 범위 안 조합은 자동 적용).
    """
    issues: list[dict[str, str]] = []
    units = [i["unit"] for i in items]
    for unit in units:
        if unit not in catalog.UNITS:
            issues.append({"unit": unit, "rule": "registered", "message": f"미등록 업무 {unit}"})
    for unit, spec in catalog.UNITS.items():
        if spec["selection"] == "required" and unit in SEQUENCE and unit not in units:
            issues.append({"unit": unit, "rule": "required", "message": f"필수 업무 {unit} 누락"})
    changes = any(catalog.UNIT_PLAN.get(u, {}).get("delegation") == "B" for u in units) or (
        "U02" in units
    )
    if changes and "U03" not in units:
        issues.append(
            {
                "unit": "U03",
                "rule": "required_if_change",
                "message": "생산계획을 바꾸는 조합에 사람 확인 U03이 없다",
            }
        )
    seen = {handoff_id}
    for item in items:
        if item["predecessor"] not in seen:
            issues.append(
                {
                    "unit": item["unit"],
                    "rule": "order",
                    "message": (
                        f"{item['unit']}의 선행 {item['predecessor']}이 앞에 없다(누락·순환)"
                    ),
                }
            )
        seen.add(item["unit"])
    # 위임 수준 B(사람 확인 후 반영)는 사람 확인 뒤에만 — C(사전 조건 내 자동 실행)는 이 사건에 없다
    for i, item in enumerate(items):
        before = {x["unit"] for x in items[:i]}
        if item["delegation"] == "B" and "U03" not in before:
            issues.append(
                {
                    "unit": item["unit"],
                    "rule": "delegation",
                    "message": f"{item['unit']}({item['delegation']})는 사람 확인 U03 뒤에만 실행",
                }
            )
        if item["delegation"] == "C":
            issues.append(
                {"unit": item["unit"], "rule": "delegation", "message": "위임 범위 초과(C)"}
            )
    return {
        "result": BLOCKED if issues else PASS,
        "issues": issues,
        "rules": ["registered", "required", "required_if_change", "order", "delegation"],
        "needs_approval": False,  # 위임 범위 안 조합 — 구성 승인 요청 없음
    }


# ─────────────────────────── N04 — 생산계획 변경안(A02) ───────────────────────────


def _overlaps(a0: datetime, a1: datetime, b0: datetime | None, b1: datetime | None) -> bool:
    return b0 is not None and b1 is not None and a0 < b1 and b0 < a1


def draft(
    analysis_rows: list[dict[str, Any]],
    master: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    """
    A02 — 장면 1 분석의 배정(입고분·사용 가능)을 그대로 쓰고(자재를 다시 배정하지 않는다) 모델별 빈
    라인 시간에 조립을 놓는다. 대상 약정 행과 점검표, 배경 주문의 원계획 유지 여부를 낸다.
    `plan`은 지금 생산계획(원천 재조회)이다.
    """
    production = {p["commitment_id"]: p for p in master["production"]}
    trucks = _trucks_by(master)
    rows_now = {r["commitment_id"]: r for r in plan["rows"]}
    targets = [r["commitment_id"] for r in analysis_rows]
    rows = []
    for a in analysis_rows:
        cid = a["commitment_id"]
        p = production.get(cid) or {}
        issues: list[str] = []
        usable, w0, w1 = (
            at(a.get("available_at")),
            at(p.get("window_start")),
            at(p.get("window_end")),
        )
        assembly, prep = p.get("assembly_min"), p.get("prep_min")
        if usable is None:
            issues.append("자재 사용 가능시각 없음")
        if w0 is None or w1 is None:
            issues.append("빈 라인 시간 없음")
        if assembly is None:
            issues.append("조립시간 누락")
        if prep is None:
            issues.append("품질 확인·상차 준비시간 누락")
        need = int(a["qty"]) * int(a.get("per_set") or 1)
        if a.get("allocated_qty") != need or p.get("secured_qty") != a.get("allocated_qty"):
            issues.append(
                f"배정 {a.get('allocated_qty')} · 확보 {p.get('secured_qty')} · 소요 {need} 불일치"
            )
        lots = [lot["lot_id"] for lot in a.get("lots") or []]
        if p.get("lot_id") and lots != [p["lot_id"]]:
            issues.append(f"배정 입고분 {lots} ≠ 확보 {p['lot_id']}")
        start = end = ready = None
        conflicts: list[dict[str, Any]] = []
        if usable is not None and w0 is not None and assembly is not None:
            start = max(usable, w0)
            end = start + timedelta(minutes=int(assembly))
            if w1 is not None and end > w1:
                issues.append(f"빈 시간 종료({iso(w1)}) 뒤 완료")
            for other, r in rows_now.items():
                if other in targets or r.get("line_id") != p.get("line_id"):
                    continue
                if _overlaps(start, end, at(r.get("start")), at(r.get("end"))):
                    conflicts.append(
                        {
                            "commitment_id": other,
                            "line_id": r["line_id"],
                            "start": r["start"],
                            "end": r["end"],
                        }
                    )
            if conflicts:
                issues.append("다른 주문의 라인 시간과 겹친다 — 다른 주문을 밀어내지 않는다")
            if prep is not None:
                ready = end + timedelta(minutes=int(prep))
        first = (trucks.get(cid) or [None])[0]
        rows.append(
            {
                "commitment_id": cid,
                "order_id": a.get("order_id"),
                "model": a.get("model"),
                "qty": int(a["qty"]),
                "lot_id": lots[0] if lots else None,
                "allocated_qty": a.get("allocated_qty"),
                "extra_stock": a.get("extra_stock"),
                "line_id": p.get("line_id"),
                "original_start": a.get("assembly_start"),
                "available_at": a.get("available_at"),
                "window_start": p.get("window_start"),
                "window_end": p.get("window_end"),
                "assembly_min": assembly,
                "prep_min": prep,
                "start": iso(start),
                "end": iso(end),
                "ready_at": iso(ready),
                "promised_at": a.get("promised_at"),
                "first_truck": None
                if first is None
                else {
                    "truck_id": first["truck_id"],
                    "cutoff": first["cutoff"],
                    "boardable": None if ready is None else ready <= at(first["cutoff"]),
                },
                "conflicts": conflicts,
                "issues": issues,
                "ok": not issues,
            }
        )
    background = [
        {
            "commitment_id": r["commitment_id"],
            "model": r["model"],
            "line_id": r["line_id"],
            "qty": r["qty"],
            "start": r["start"],
            "end": r["end"],
            "version": r.get("version"),
            "kept": True,
        }
        for r in plan["rows"]
        if r["commitment_id"] not in targets
    ]
    return {
        "base_version": plan["version"],
        "rows": rows,
        "background": background,
        "confirmable": all(r["ok"] for r in rows),
        "checks": {
            "material": all(not any("배정" in i or "자재" in i for i in r["issues"]) for r in rows),
            "line": all(not r["conflicts"] for r in rows),
            "quality": all(r["prep_min"] is not None for r in rows),
            "background_kept": len(background),
        },
    }


def content_hash(found: dict[str, Any]) -> str:
    """변경안 내용 식별값 — 기준 원계획·대상 행(수량·라인·착수·종료·준비)이 같으면 같다."""
    keys = ("commitment_id", "qty", "line_id", "lot_id", "start", "end", "prep_min")
    body = {
        "base_version": found["base_version"],
        "rows": [{k: r[k] for k in keys} for r in found["rows"]],
    }
    text = json.dumps(body, ensure_ascii=False, sort_keys=True)
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()[:16]


# ─────────────────────────── N06 — 반영본 대조(U04) ───────────────────────────


def compare(
    approved: list[dict[str, Any]], stored: dict[str, Any], approval_id: str
) -> dict[str, dict[str, Any]]:
    """
    원천에서 다시 읽은 행을 승인본과 대조한다 — 저장 버전·확인 ID·수량·착수·종료·빈 시간 종료 안.
    확인 ID가 붙지 않은 행은 미반영(응답 유실과 실패를 가르는 근거)이고, 붙었는데 값이 다르면
    불일치다.
    """
    rows = {r["commitment_id"]: r for r in stored["rows"]}
    out = {}
    for a in approved:
        cid = a["commitment_id"]
        s = rows.get(cid)
        if s is None or s.get("approval_id") != approval_id:
            out[cid] = {"match": NOT_APPLIED, "diffs": [], "stored": s}
            continue
        diffs = []
        if s.get("version") != TARGET_VERSION:
            diffs.append("version")
        if int(s.get("qty") or -1) != int(a["qty"]):
            diffs.append("qty")
        for k in ("start", "end"):
            if at(s.get(k)) != at(a[k]):
                diffs.append(k)
        if a.get("window_end") and at(s.get("end")) and at(s["end"]) > at(a["window_end"]):
            diffs.append("window_end")
        out[cid] = {"match": MISMATCH if diffs else MATCHED, "diffs": diffs, "stored": s}
    return out


# ─────────────────────────── N07 — 주문별 납기 재평가(U05) ───────────────────────────


def _trucks_by(master: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by: dict[str, list[dict[str, Any]]] = {}
    for t in master.get("trucks") or []:
        by.setdefault(t["commitment_id"], []).append(t)
    for rows in by.values():
        rows.sort(key=lambda t: (at(t["departure"]) or datetime.max, t["seq"]))
    return by


def reassess(
    targets: list[dict[str, Any]],
    readback: dict[str, dict[str, Any]],
    master: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    U05 — 재조회 일치 행만 쓴다(승인 초안이 아니다). 출하 준비 = 저장된 종료 + 준비시간. 그 약정의
    유효 정기차 중 마감 ≥ 준비인 첫 차(출발 순). 여유 = 약정 − 예상 도착(분). 보류는 이유를 남긴다.
    """
    trucks = _trucks_by(master)
    promised = {c["commitment_id"]: c["promised_at"] for c in master["commitments"]}
    out = []
    for a in targets:
        cid = a["commitment_id"]
        rb = readback.get(cid) or {"match": UNKNOWN, "stored": None}
        row: dict[str, Any] = {
            "commitment_id": cid,
            "model": a.get("model"),
            "qty": a["qty"],
            "match": rb["match"],
            "match_label": MATCH_LABEL[rb["match"]],
            "stored_end": None,
            "ready_at": None,
            "prep_min": a.get("prep_min"),
            "truck_id": None,
            "cutoff": None,
            "departure": None,
            "arrival": None,
            "promised_at": promised.get(cid),
            "margin_min": None,
            "missed": [],
            "route": HOLD,
            "route_label": ROUTE_LABEL[HOLD],
            "reasons": [],
            "missing": [],
        }
        out.append(row)
        if rb["match"] != MATCHED:
            row["reasons"].append(f"반영본 대조 {MATCH_LABEL[rb['match']]} — 재조회 필요")
            continue
        end = at(rb["stored"]["end"])
        row["stored_end"] = iso(end)
        if a.get("prep_min") is None:
            row["missing"].append("prep_min")
            row["reasons"].append("준비시간 누락 — 출하 준비 산출 불가")
            continue
        ready = end + timedelta(minutes=int(a["prep_min"]))
        row["ready_at"] = iso(ready)
        mine = trucks.get(cid) or []
        if not mine:
            row["missing"].append("trucks")
            row["reasons"].append("정기차 자료 누락 — 납기 판정 미확인")
            continue
        boardable = [t for t in mine if at(t["cutoff"]) is not None and at(t["cutoff"]) >= ready]
        row["missed"] = [
            {
                "truck_id": t["truck_id"],
                "cutoff": t["cutoff"],
                "late_min": _min(ready, at(t["cutoff"])),
            }
            for t in mine
            if t not in boardable and at(t["cutoff"]) is not None
        ]
        if not boardable:
            row["reasons"].append("준비시각 뒤에 마감되는 정기차가 없다 — 산출 불가")
            continue
        t = boardable[0]
        if row["promised_at"] is None or at(t.get("arrival")) is None:
            row["missing"].append("promised_at" if row["promised_at"] is None else "arrival")
            row["reasons"].append("약정·도착 시각 누락 — 여유 산출 불가")
            continue
        margin = _min(at(row["promised_at"]), at(t["arrival"]))
        route = OBSERVE if margin >= 0 else TRANSPORT
        row.update(
            truck_id=t["truck_id"],
            cutoff=t["cutoff"],
            departure=t["departure"],
            arrival=t["arrival"],
            margin_min=margin,
            route=route,
            route_label=ROUTE_LABEL[route],
        )
        for m in row["missed"]:
            row["reasons"].append(
                f"{m['truck_id']} 마감 {_hm(m['cutoff'])}에 {m['late_min']}분 늦어 다음 정기차 적용"
            )
        row["reasons"].append(
            f"준비 {_hm(iso(ready))} ≤ {t['truck_id']} 마감 {_hm(t['cutoff'])} — 도착 "
            f"{_hm(t['arrival'])} · 약정 {_hm(row['promised_at'])} · 여유 {margin}분"
        )
    return out


def summary(
    case_commitments: list[str],
    readback: dict[str, dict[str, Any]] | None,
    assessed: list[dict[str, Any]],
    confirmations: int,
) -> dict[str, Any]:
    """SC02요약의 칸 — 최초 영향·반영 대조 일치·관찰·잔여 위험·보류·사람 확인 횟수."""
    routes = [r["route"] for r in assessed]
    return {
        "initial_impact": len(case_commitments),
        "matched": sum(1 for r in (readback or {}).values() if r["match"] == MATCHED),
        "observe": routes.count(OBSERVE),
        "residual": routes.count(TRANSPORT),
        "hold": routes.count(HOLD),
        "confirmations": confirmations,
    }


__all__ = [
    "BLOCKED",
    "HOLD",
    "MATCHED",
    "MISMATCH",
    "NOT_APPLIED",
    "OBSERVE",
    "PASS",
    "TARGET_VERSION",
    "TRANSPORT",
    "UNKNOWN",
    "check",
    "compare",
    "content_hash",
    "draft",
    "propose",
    "reassess",
    "summary",
]
