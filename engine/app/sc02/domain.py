"""
SC02 업무 기록 — 데모 실행 하나의 요청·보고·단가안·분석·협상·기안·결재·원가·인계·업무·감사 이력.

SC01과 같은 원칙이다(`app/sc01/domain.py`): **한 데모 실행 = 문서 하나**, 순수 함수, 저장·BPM은
`process.py`. 데모 실행 id는 **장면 1의 데모 실행 id와 같다**(DATA-22 「execution_id는 장면 1의
demo_run_id와 같은 실행 구분자」) — 장면 2는 장면 1의 인계 결과에서 시작한다.

상태 축은 서로 독립이다(구현명세 10장): 요청·협상 · 계산 · 기안 승인 · 원가 · 인계 · 위험 · 전망.
**승인·인계가 위험 해소나 전망 승인이 아니다**(SCOPE-01) — 끝나도 risk=OPEN,
forecast=REVIEW_PENDING.

* 완료 run·상신 기안·승인 결정·등록 원가는 **고치지 않는다**(DATA-24). 바뀌면 새 버전이다.
* 장면 1 결과는 시작할 때 **스냅샷**으로 둔다(`sc01`). 장면 1을 초기화해도 장면 2의 근거는 그 시점의
  것으로 남는다 — 완료된 승인과 당시 근거를 보존한다(ERR-24).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.sc01.domain import (
    KST,
    USERS,
    DomainError,
    audit,
    due_at,
    name_of,
    ordered,
    overdue,
    parse_at,
    user_for_role,
    user_id_of,
)
from app.sc02 import agent, calc
from app.sc02.calc import Option
from app.sc02.seed import MonthRow, Seed

SEED_ID = "SYN-SC02-v0.2"
PART_ID = "P-COM01"
SUPPLIER_ID = "SUP-01"
REQUEST_ID = "REQ-2706-01"
REVIEW_ID = "MR-2706-01"
COST_ISSUE_ID = "ISSUE-COST01"
VOLUME_ISSUE_ID = "ISSUE-B07"
#: D00 — 장면 1 결과 확인(업무이력 시트 S0).
START_CLOCK = datetime(2027, 6, 17, 8, 50, tzinfo=KST)

#: 시연 사례(ERR-21). BASE와 X 사례는 **별도 데모 실행**으로 돈다 — 기본 승인 이력을 덮지 않는다.
#: 자료를 바꾸는 사례(X09-A·X10)는 물량 표를 이 문서 안에서만 바꾼다. 나머지는 각본의 답이 다르다.
CASES: dict[str, str] = {
    "BASE": "기본 시연",
    "X01": "X01 임원 추가 협상지시",
    "X02": "X02 기안가 2,050원 — 대표 비대상",
    "X04": "X04 협상 적용일 8/1",
    "X05": "X05 기안가 2,130원 — 협상가와 다름",
    "X06": "X06 협상 미합의",
    "X07R": "X07 팀장 보완 → 재상신",
    "X07J": "X07 팀장 반려",
    "X09A": "X09 2028-06 b 수량 누락",
    "X09B": "X09 Agent 요약 실패",
    "X10": "X10 월·모델 중복 행",
}
_CASE_ROWS: dict[str, dict[str, list[tuple[str, str]]]] = {
    "X09A": {"null": [("2028-06-01", "A-b")]},
    "X10": {"duplicate": [("2027-09-01", "A-a")]},
}

#: BPMN 노드 → 업무 종류·담당 역할·기한(영업일). `days`가 None이면 기한을 사람이 넣는다(외부 협상).
NODE_ROLES: dict[str, dict[str, Any]] = {
    "Verify_Request": {"task": "VERIFY", "role": "구매담당", "days": 1},
    "Report_Lead": {"task": "REPORT", "role": "구매담당", "days": 1},
    "Confirm_Analysis": {"task": "ANALYSIS", "role": "구매담당", "days": 2},
    "Record_Negotiation": {"task": "NEGOTIATION", "role": "구매담당", "days": None},
    "Confirm_Reanalysis": {"task": "REANALYSIS", "role": "구매담당", "days": 2},
    "Draft_Proposal": {"task": "PROPOSAL", "role": "구매담당", "days": 1},
    "Approve_Lead": {"task": "APPROVE_TEAM", "role": "구매팀장", "days": 1, "step": "TEAM"},
    "Approve_Exec": {"task": "APPROVE_EXEC", "role": "구매임원", "days": 1, "step": "EXEC"},
    "Approve_CEO": {"task": "APPROVE_CEO", "role": "대표이사", "days": 1, "step": "CEO"},
    "Register_Cost": {"task": "COST", "role": "구매담당", "days": 1},
    "Request_Handoff": {"task": "HANDOFF", "role": "구매담당", "days": 1},
    "Accept_Handoff": {
        "task": "ACCEPT",
        "role": "경영관리담당",
        "days": 1,
        "assignee_var": "경영관리담당자",
    },
}
#: 기한 초과 알림을 함께 받는 기능별 검토자 — 구매 업무는 구매팀장, 팀장 결재는 임원.
REVIEWER = {
    "VERIFY": "u-buy-lead",
    "REPORT": "u-buy-lead",
    "ANALYSIS": "u-buy-lead",
    "NEGOTIATION": "u-buy-lead",
    "REANALYSIS": "u-buy-lead",
    "PROPOSAL": "u-buy-lead",
    "APPROVE_TEAM": "u-buy-exec",
    "APPROVE_EXEC": None,
    "APPROVE_CEO": None,
    "COST": "u-buy-lead",
    "HANDOFF": "u-buy-lead",
    "ACCEPT": None,
    "RENEG": "u-buy-exec",
}
STEP_PENDING = {
    "TEAM": "TEAM_APPROVAL_PENDING",
    "EXEC": "EXEC_APPROVAL_PENDING",
    "CEO": "CEO_APPROVAL_PENDING",
}
DECISIONS = ("승인", "보완", "반려", "추가협상지시")


def _d(value: Any) -> Decimal:
    return Decimal(str(value))


def _date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as exc:
        raise DomainError(f"{field}: 날짜(YYYY-MM-DD)가 아니다 — {value!r}", 422) from exc


def _at(value: Any, field: str) -> datetime:
    try:
        return parse_at(str(value).strip())
    except ValueError as exc:
        raise DomainError(f"{field}: 시각(ISO8601)이 아니다 — {value!r}", 422) from exc


def _hash(body: Any) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _seq(records: dict) -> int:
    return len(records) + 1


# ─────────────────────────── 장면 1 기준 (D00) ───────────────────────────


def baseline_from_sc01(sc01_doc: dict, seed: Seed) -> dict[str, Any]:
    """
    장면 1 인계 결과 → 장면 2의 출발점. **F02의 2027 물량이 통합 데이터와 같아야 한다** — 다르면
    (정정 EX03 등) 장면 2의 기대값이 정의되지 않은 물량이다. 임의로 보정하지 않고 거절한다.
    """
    if sc01_doc["scene"] != "HANDED_OFF" or not sc01_doc.get("handoff"):
        raise DomainError(
            "장면 1이 아직 인계되지 않았다 — 장면 2는 장면 1 인계 결과에서 시작한다", 409
        )
    run_id = sc01_doc["handoff"]["run_id"]
    run = sc01_doc["calc_runs"][run_id]
    version = run["versions"]["latest"]
    forecast = sc01_doc["forecasts"][version]
    got = {(m, p): q for m, p, q in forecast["quantities"]}
    want = {(r.model_id, r.period.isoformat()): r.f02 for r in seed.rows if r.period.year == 2027}
    if got != want:
        diff = sorted(k for k in want if got.get(k) != want[k])[:3]
        raise DomainError(
            f"장면 1의 {version} 물량이 통합 가상 데이터 v0.2와 다르다"
            f"({', '.join(map(str, diff))}…) — "
            "장면 2 기대값은 기본 F02 기준이다. 장면 1을 초기화해 기본 시연으로 다시 돌린다",
            409,
        )
    issue = sc01_doc["issues"].get(VOLUME_ISSUE_ID)
    if issue is None:
        raise DomainError(f"장면 1에 {VOLUME_ISSUE_ID}가 없다", 409)
    return {
        "demo_run_id": sc01_doc["demo_run_id"],
        "run_id": run_id,
        "forecast": version,
        "forecast_approval": forecast["approval"],
        "handed_off_at": sc01_doc["handoff"]["at"],
        "issue": {
            "issue_id": issue["issue_id"],
            "risk": issue["risk"],
            "status": issue["status"],
            "model_id": issue["model_id"],
            "period": issue["period"],
            "runs": list(issue["runs"]),
        },
    }


def new_demo_run(
    seed: Seed, demo_run_id: str, *, case_id: str, created_at: datetime, baseline: dict
) -> dict:
    """
    D00 — 장면 1 완료 데이터만 있다. 요청·협상·승인·원가·인계는 단계 실행 때 생긴다(DEMO-01·T21).
    """
    if case_id not in CASES:
        raise DomainError(f"모르는 시연 사례: {case_id} (가능: {', '.join(CASES)})", 422)
    return {
        "demo_run_id": demo_run_id,
        "seed_id": SEED_ID,
        "case_id": case_id,
        "created_at": created_at.isoformat(),
        "clock": START_CLOCK.isoformat(),
        "step": "D00",
        "scene": "READY",
        "sc01": baseline,
        "rows_override": _CASE_ROWS.get(case_id, {}),
        "agent_mode": "fail" if case_id == "X09B" else "mock",
        "request": None,
        "report": None,
        "price_versions": {},
        "runs": {},
        "negotiations": {},
        "proposals": {},
        "decisions": [],
        "approval_status": None,
        "instruction": None,
        "cost_versions": {},
        "issue": None,
        "review": {
            "review_id": REVIEW_ID,
            "links": [
                {
                    "issue_id": VOLUME_ISSUE_ID,
                    "issue_type": "VOLUME",
                    "latest_run_id": baseline["run_id"],
                    "risk_status": "OPEN",
                }
            ],
            "bundles": [],
        },
        "handoff": None,
        "handoff_history": [],
        "evidence_ids": [],
        "agent_outputs": {},
        "tasks": {},
        "alerts": [],
        "audit": [],
        "bpm": None,
    }


def rows_for(doc: dict, seed: Seed) -> list[MonthRow]:
    """이 데모 실행의 물량 표 — 시연 사례(X09-A 누락·X10 중복)가 바꾼 것. 시드는 그대로다."""
    rows = list(seed.rows)
    change = doc.get("rows_override") or {}
    nulls = {tuple(k) for k in change.get("null", [])}
    rows = [
        replace(r, f02=None) if (r.period.isoformat(), r.model_id) in nulls else r for r in rows
    ]
    for period, model in change.get("duplicate", []):
        rows.append(next(r for r in rows if (r.period.isoformat(), r.model_id) == (period, model)))
    return rows


# ─────────────────────────── 요청 접수 (U21 · S01 · CT21) ───────────────────────────

#: 시연 요청 원천. 기본은 DOC-REQ01(SUP-01 → P-COM01 2,000 → 2,200원, 7/1). 누락 변형은 CT21
#: 검사용이다.
REQUEST_FIXTURES: dict[str, dict[str, Any]] = {
    REQUEST_ID: {},
    "REQ-2706-01-MISSING": {"effective_date": None},
}


def receive_request(doc: dict, seed: Seed, fixture_id: str, *, actor: str) -> tuple[str, bool]:
    """
    요청 등록. **같은 문서 키 + 같은 내용이면 기존 요청을 돌려준다**(U21-03). 같은 키·다른 내용은
    정정
    버전으로 보존한다 — 이번 범위에서는 기본 경로 시작 전에만 받는다(시작 뒤 정정은 후속 범위).
    """
    if fixture_id not in REQUEST_FIXTURES:
        raise DomainError(f"모르는 시연 요청: {fixture_id}", 404)
    item = {
        "part_id": PART_ID,
        "unit": "EA",
        "currency": "KRW",
        "tax_basis": "VAT_EXCLUDED",
        "old_price": str(seed.setting_decimal("old_price")),
        "requested_price": str(seed.setting_decimal("request_price")),
        "effective_date": seed.setting_date("effective_date").isoformat(),
        "reason": "원재료 및 가공비 상승",
        **REQUEST_FIXTURES[fixture_id],
    }
    body = {"supplier_id": SUPPLIER_ID, "source_doc_id": "DOC-REQ01", "items": [item]}
    digest = _hash(body)
    current = doc["request"]
    if current is not None:
        if current["source_hash"] == digest:
            return current["request_id"], False
        if doc["bpm"] is not None:
            raise DomainError("이미 진행 중인 요청이다 — 진행 뒤의 정정은 이번 범위 밖이다", 409)
    doc["request"] = {
        "request_id": REQUEST_ID,
        "revision": 1 if current is None else current["revision"] + 1,
        "previous": None
        if current is None
        else {k: v for k, v in current.items() if k != "previous"},
        "supplier_id": SUPPLIER_ID,
        "supplier_name": "가상 정밀부품",
        "source_doc_id": "DOC-REQ01",
        "source_text": seed.evidence["DOC-REQ01"]["내용"],
        "received_at": doc["clock"],
        "received_by": actor,
        "status": "RECEIVED",
        "verified_at": None,
        "verified_by": None,
        "opinion": None,
        "source_hash": digest,
        "items": [item],
        "errors": [],
        "fixture_id": fixture_id,
    }
    doc["scene"] = "ACTIVE"
    _evidence(doc, "DOC-REQ01")
    audit(doc, actor=actor, action="request_received", request_id=REQUEST_ID, fixture=fixture_id)
    return REQUEST_ID, True


def _evidence(doc: dict, *ids: str) -> None:
    for e in ids:
        if e not in doc["evidence_ids"]:
            doc["evidence_ids"].append(e)


def screen_request(doc: dict, seed: Seed, request_id: str) -> list[dict[str, str]]:
    """S01 자동 검사 — 필수값·통화·VAT·월초 적용·공급사-품목 매핑·기존가 = C01 부품가(U21-02)."""
    req = _request(doc, request_id)
    errors: list[dict[str, str]] = []
    for it in req["items"]:
        for field in (
            "part_id",
            "unit",
            "currency",
            "old_price",
            "requested_price",
            "effective_date",
        ):
            if it.get(field) in (None, ""):
                errors.append({"field": field, "message": f"{field} 누락 — 보완 대기"})
        if it.get("currency") != "KRW" or it.get("tax_basis") != "VAT_EXCLUDED":
            errors.append({"field": "currency", "message": "KRW·VAT 제외만 받는다"})
        if it.get("effective_date") and _date(it["effective_date"], "적용일").day != 1:
            errors.append(
                {"field": "effective_date", "message": "월초 적용만 받는다(월중 적용 미지원)"}
            )
        links = [p for p in seed.parts if p.part_id == it["part_id"]]
        if not links or any(p.supplier_id != req["supplier_id"] for p in links):
            errors.append({"field": "part_id", "message": "공급사-품목 매핑이 맞지 않는다"})
        if it.get("old_price") not in (None, "") and _d(it["old_price"]) != seed.setting_decimal(
            "old_price"
        ):
            errors.append({"field": "old_price", "message": "기존가가 C01 부품 단가와 다르다"})
    req["errors"] = errors
    audit(doc, actor="system", action="request_screened", errors=len(errors))
    return errors


def _request(doc: dict, request_id: str | None = None) -> dict:
    req = doc["request"]
    if req is None or (request_id and req["request_id"] != request_id):
        raise DomainError(f"없는 요청: {request_id}", 404)
    return req


def record_verification(doc: dict, *, result: str, opinion: str, by: str) -> None:
    req = _request(doc)
    if result == "확인완료":
        req.update(status="VERIFIED", verified_at=doc["clock"], verified_by=by, opinion=opinion)
        _price_version(doc, "PV-REQ01", "REQUEST", req, _d(req["items"][0]["requested_price"]))
    else:
        req.update(status="NEEDS_INFO", opinion=opinion)
    audit(
        doc, actor=by, action="request_verified" if result == "확인완료" else "request_needs_info"
    )


def record_report(doc: dict, args: dict[str, Any], *, by: str) -> None:
    req = _request(doc)
    go = args["need"] == "검토진행"
    doc["report"] = {
        "report_id": "NOTE-REPORT01",
        "request_id": req["request_id"],
        "reported_at": doc["clock"],
        "reported_by": by,
        "participants": args.get("participants") or "",
        "summary": args.get("summary") or "",
        "need": args["need"],
        "negotiation_direction": args.get("direction") or "",
        "conclusion": args.get("conclusion") or "",
    }
    req["status"] = "PRE_REVIEW" if go else "CLOSED"
    if not go:
        doc["scene"] = "CLOSED"
    _evidence(doc, "NOTE-REPORT01")
    audit(doc, actor=by, action="report_recorded", need=args["need"])


# ─────────────────────────── 단가안 · 분석 (U22 · S03 · S05) ───────────────────────────


def _price_version(
    doc: dict,
    version_id: str,
    kind: str,
    req: dict,
    price: Decimal | None,
    *,
    effective: date | None = None,
    predecessor: str | None = None,
) -> dict:
    pv = doc["price_versions"].get(version_id)
    if pv is not None:
        return pv
    item = req["items"][0]
    pv = doc["price_versions"][version_id] = {
        "version_id": version_id,
        "seq": _seq(doc["price_versions"]),
        "kind": kind,
        "request_id": req["request_id"],
        "part_id": item["part_id"],
        "supplier_id": req["supplier_id"],
        "old_price": item["old_price"],
        "new_price": None if price is None else str(price),
        "effective_date": (effective or _date(item["effective_date"], "적용일")).isoformat(),
        "predecessor_id": predecessor,
        "created_at": doc["clock"],
        "run_id": None,
    }
    return pv


def _option(pv: dict) -> Option:
    return Option(
        pv["version_id"],
        pv["kind"],
        pv["part_id"],
        pv["supplier_id"],
        _d(pv["old_price"]),
        None if pv["new_price"] is None else _d(pv["new_price"]),
        date.fromisoformat(pv["effective_date"]),
    )


def _run_id(doc: dict, version_id: str) -> str:
    # PV-REQ01 → RUN-REQ01. 같은 안을 다시 분석하면 RUN-REQ01-2 — 완료 run은 고치지 않는다(DATA-24).
    base = "RUN-" + version_id.removeprefix("PV-")
    n = sum(1 for r in doc["runs"].values() if r["price_version_id"] == version_id)
    return base if n == 0 else f"{base}-{n + 1}"


def run_analysis(doc: dict, seed: Seed, version_id: str, *, by: str) -> dict:
    """
    단가안 하나를 분석해 새 run을 남긴다(U22-03 — 입력을 고정해 새 run). 같은 안의 이전 run은 그대로
    두되 낡음 표시한다. 기준 비교안은 요청안이다(PERIOD-03). 위험 이슈는 요청건·원가 원인으로 하나만
    두고 run마다 평가 이력을 더한다(WF-25).
    """
    pv = doc["price_versions"][version_id]
    base = doc["price_versions"].get("PV-REQ01")
    result = calc.analyze(
        seed,
        _option(pv),
        rows=rows_for(doc, seed),
        base=None if base is None or version_id == "PV-REQ01" else _option(base),
    )
    if version_id == "PV-REQ01" and result["comparison"] is None and result["computable"]:
        result["comparison"] = calc.comparison(rows_for(doc, seed), seed, _option(pv), _option(pv))
    inputs = {"option": pv, "rows": doc.get("rows_override"), "seed": SEED_ID}
    run_id = _run_id(doc, version_id)
    for old in doc["runs"].values():
        if old["price_version_id"] == version_id:
            old["is_stale"] = True
    doc["runs"][run_id] = {
        "run_id": run_id,
        "seq": _seq(doc["runs"]),
        "price_version_id": version_id,
        "kind": pv["kind"],
        "status": "SUCCEEDED" if result["computable"] else "BLOCKED",
        "input_hash": _hash(inputs),
        "at": doc["clock"],
        "by": by,
        "is_stale": False,
        "result": result,
    }
    pv["run_id"] = run_id
    _assess_issue(doc, run_id, result)
    audit(
        doc,
        actor=by,
        action="analyzed",
        run_id=run_id,
        version=version_id,
        risk=result["risk"],
        computable=result["computable"],
    )
    return doc["runs"][run_id]


def _assess_issue(doc: dict, run_id: str, result: dict) -> None:
    issue = doc["issue"]
    if issue is None:
        issue = doc["issue"] = {
            "issue_id": COST_ISSUE_ID,
            "cause": "PURCHASE_PRICE",
            "request_id": REQUEST_ID,
            "plant_id": "ULS",
            "models": ["A-a", "A-b"],
            "status": "OPEN",
            "risk": None,
            "history": [],
        }
        doc["review"]["links"].append(
            {
                "issue_id": COST_ISSUE_ID,
                "issue_type": "COST",
                "latest_run_id": run_id,
                "risk_status": "OPEN",
            }
        )
    issue["risk"] = result["risk"]
    issue["history"].append({"at": doc["clock"], "run_id": run_id, "risk": result["risk"]})
    for link in doc["review"]["links"]:
        if link["issue_id"] == COST_ISSUE_ID:
            link["latest_run_id"] = run_id


def analyze_request(doc: dict, seed: Seed, *, offer_price: Any, due_at_text: Any, by: str) -> dict:
    req = _request(doc)
    if req["status"] != "PRE_REVIEW" and req["status"] != "NEGOTIATION_READY":
        raise DomainError("팀장 보고(검토 진행) 뒤에 분석한다", 409)
    due = _at(due_at_text, "외부 협상기한")
    req_run = run_analysis(doc, seed, "PV-REQ01", by=by)
    offer = _price_version(doc, "PV-OFFER01", "OFFER", req, _d(offer_price), predecessor="PV-REQ01")
    offer_run = run_analysis(doc, seed, offer["version_id"], by=by)
    req["status"] = "NEGOTIATION_READY"
    req["negotiation_due"] = {
        "due_at": due.isoformat(),
        "history": [
            {"at": doc["clock"], "by": by, "due_at": due.isoformat(), "reason": "최초 입력"}
        ],
    }
    _evidence(doc, "NOTE-ANALYSIS01")
    return {
        "request_run": req_run["run_id"],
        "offer_run": offer_run["run_id"],
        "risk": req_run["result"]["risk"] or "",
    }


def change_negotiation_due(doc: dict, *, due: str, reason: str, actor: str) -> None:
    """
    외부 협상기한 변경(U23-02) — 기존·새 기한·사유·변경자·시각을 보존한다. 내부 분석기한과 따로다 —
    협상 업무의 기한만 바뀐다(외부 협상 진행만으로 내부 업무기한을 연장하지 않는다).
    """
    req = _request(doc)
    if not reason.strip():
        raise DomainError("기한 변경 사유가 필요하다", 422)
    record = req.get("negotiation_due")
    if record is None:
        raise DomainError("아직 외부 협상기한이 없다 — 요청안 분석 때 넣는다", 409)
    new = _at(due, "외부 협상기한").isoformat()
    record["history"].append(
        {
            "at": doc["clock"],
            "by": actor,
            "due_at": new,
            "previous": record["due_at"],
            "reason": reason,
        }
    )
    record["due_at"] = new
    task = _active_task(doc, "NEGOTIATION")
    if task is not None:
        task["history"].append(
            {
                "at": doc["clock"],
                "status": task["status"],
                "by": actor,
                "note": f"외부 협상기한 {task['due_at'][5:16]} → {new[5:16]} ({reason})",
            }
        )
        task["due_at"] = new
    audit(doc, actor=actor, action="negotiation_due_changed", due_at=new, reason=reason)


def record_negotiation(doc: dict, args: dict[str, Any], *, by: str) -> str:
    """
    1차 협상 결과(U23). 잠정합의는 승인이 아니다 — 저장 후 **재분석 필요**다(U23-03). 미합의는 단가
    NULL이다(0원이 아니다).
    """
    req = _request(doc)
    outcome = args["outcome"]
    price = args.get("price")
    eff = _date(args["effective_date"], "적용일")
    neg_id = "NEG01"
    previous = doc["negotiations"].get(neg_id)
    doc["negotiations"][neg_id] = {
        "negotiation_id": neg_id,
        "revision": 1 if previous is None else previous["revision"] + 1,
        "round_no": 1,
        "request_id": req["request_id"],
        "held_at": doc["clock"],
        "recorded_by": by,
        "participants": args.get("participants") or "",
        "outcome": outcome,
        "price": None if outcome != "잠정합의" or price is None else str(_d(price)),
        "effective_date": eff.isoformat(),
        "unresolved": args.get("unresolved") or "",
        "due_at": (req.get("negotiation_due") or {}).get("due_at"),
        "evidence_ids": ["NOTE-NEG01"],
        "analysis_required": outcome == "잠정합의",
    }
    if outcome == "잠정합의":
        req["status"] = "TENTATIVE_AGREEMENT"
        _price_version(
            doc, "PV-NEG01", "NEGOTIATION", req, _d(price), effective=eff, predecessor="PV-OFFER01"
        )
        # 같은 안의 이전 분석은 이제 낡았다 — 가격이 같고 적용일만 바뀌어도 새 분석이다(U23-03).
        for r in doc["runs"].values():
            if r["price_version_id"] == "PV-NEG01":
                r["is_stale"] = True
    else:
        req["status"] = "NEGOTIATION_UNRESOLVED"
        doc["scene"] = "UNRESOLVED"
    _evidence(doc, "NOTE-NEG01")
    audit(
        doc,
        actor=by,
        action="negotiation_recorded",
        outcome=outcome,
        price=price,
        effective_date=eff.isoformat(),
    )
    return neg_id


def analyze_negotiation(doc: dict, seed: Seed, *, by: str) -> dict:
    req = _request(doc)
    if req["status"] not in ("TENTATIVE_AGREEMENT", "PROPOSAL_READY"):
        raise DomainError("잠정합의된 협상안이 없다", 409)
    run = run_analysis(doc, seed, "PV-NEG01", by=by)
    doc["negotiations"]["NEG01"]["analysis_required"] = False
    # 최신 입력과 run이 일치할 때만 기안 가능이다(WF-21).
    req["status"] = "PROPOSAL_READY" if run["status"] == "SUCCEEDED" else "TENTATIVE_AGREEMENT"
    return run


def latest_run(doc: dict, version_id: str) -> dict | None:
    pv = doc["price_versions"].get(version_id)
    return None if pv is None or pv["run_id"] is None else doc["runs"][pv["run_id"]]


# ─────────────────────────── 기안 (U24 · S06 · CT26) ───────────────────────────


def current_proposal(doc: dict) -> dict | None:
    found = ordered(doc["proposals"])
    return found[-1] if found else None


def proposal_problems(doc: dict, seed: Seed, args: dict[str, Any]) -> tuple[Option, dict]:
    """
    상신 검증(U24) — **부수 효과 없이** 기안안 분석을 미리 계산해 본다. 필수값, 최신 협상 분석,
    협상안과 다르면 차이 사유, 계산 가능(월중 적용·누락·중복이면 상신 불가), 결재자 지정.
    """
    req = _request(doc)
    neg_run = latest_run(doc, "PV-NEG01")
    if neg_run is not None and not neg_run["is_stale"] and neg_run["status"] == "BLOCKED":
        reasons = "; ".join(p["message"] for p in neg_run["result"]["problems"][:3])
        raise DomainError(f"협상안 분석이 미산출이다 — 상신 불가: {reasons}", 409)
    if req["status"] != "PROPOSAL_READY" or neg_run is None or neg_run["is_stale"]:
        raise DomainError("협상안 재분석이 최신이 아니다 — 재분석한 뒤 상신한다(AT21)", 409)
    if not str(args.get("reason") or "").strip():
        raise DomainError("인상 필요성이 필요하다", 422)
    neg = doc["price_versions"]["PV-NEG01"]
    price = args.get("price")
    if price is None:
        raise DomainError("기안 단가가 필요하다", 422)
    eff = _date(args.get("effective_date"), "적용일")
    differs = _d(price) != _d(neg["new_price"]) or eff.isoformat() != neg["effective_date"]
    if differs and not str(args.get("diff_reason") or "").strip():
        raise DomainError("기안가·적용일이 협상안과 다르다 — 차이 사유가 필요하다(X05)", 422)
    for role in ("구매팀장", "구매임원", "대표이사"):
        if not any(u["role"] == role for u in USERS.values()):
            raise DomainError(f"{role} 결재자가 지정되지 않았다 — 사용자 지정이 필요하다", 409)
    revision = len(doc["proposals"]) + 1
    item = req["items"][0]
    option = Option(
        f"PV-PROP{revision:02d}",
        "PROPOSAL",
        item["part_id"],
        req["supplier_id"],
        _d(item["old_price"]),
        _d(price),
        eff,
    )
    preview = calc.analyze(
        seed, option, rows=rows_for(doc, seed), base=_option(doc["price_versions"]["PV-REQ01"])
    )
    if not preview["computable"]:
        reasons = "; ".join(p["message"] for p in preview["problems"])
        raise DomainError(f"기안안 분석을 확정할 수 없다 — 상신 불가: {reasons}", 409)
    return option, preview


def submit_proposal(doc: dict, seed: Seed, args: dict[str, Any], *, by: str) -> dict[str, Any]:
    """
    상신 — 기안 버전을 **불변 스냅샷**으로 고정하고 그 버전의 분석 run을 연결한다(U24-02). 협상안과
    단가·조건이 같아도 기안 버전에 분석 근거를 명시적으로 잇는다(U24-01). 보완 뒤 재상신은 새
    버전이고
    팀장부터 다시 받는다 — 이전 승인은 보존하되 승계하지 않는다.
    """
    option, _preview = proposal_problems(doc, seed, args)
    req = _request(doc)
    revision = len(doc["proposals"]) + 1
    key = f"PROP01-v{revision}"
    previous = current_proposal(doc)
    pv = _price_version(
        doc,
        option.version_id,
        "PROPOSAL",
        req,
        option.new_price,
        effective=option.effective,
        predecessor="PV-NEG01" if previous is None else previous["price_version_id"],
    )
    run = run_analysis(doc, seed, pv["version_id"], by=by)
    doc["proposals"][key] = {
        "proposal_key": key,
        "proposal_id": "PROP01",
        "revision": revision,
        "seq": revision,
        "request_id": req["request_id"],
        "price_version_id": pv["version_id"],
        "run_id": run["run_id"],
        "price": pv["new_price"],
        "effective_date": pv["effective_date"],
        "reason": args["reason"],
        "diff_reason": args.get("diff_reason") or "",
        "evidence_ids": [
            e for e in ("DOC-REQ01", "NOTE-REPORT01", "NOTE-NEG01") if e in doc["evidence_ids"]
        ],
        "status": "TEAM_APPROVAL_PENDING",
        "submitted_at": doc["clock"],
        "submitted_by": by,
        "input_hash": run["input_hash"],
        "ceo_expected": run["result"]["ceo_required"],
        "previous": None if previous is None else previous["proposal_key"],
    }
    doc["approval_status"] = "TEAM_APPROVAL_PENDING"
    _evidence(doc, "DOC-PROP01")
    audit(doc, actor=by, action="proposal_submitted", proposal=key, run_id=run["run_id"])
    return {
        "proposal_id": key,
        "run_id": run["run_id"],
        "ceo_expected": bool(run["result"]["ceo_required"]),
    }


# ─────────────────────────── 결재 (U25 · S07~S10 · S14) ───────────────────────────


def decision_problems(doc: dict, node_id: str, answer: dict[str, Any]) -> None:
    """결재 사전 검사 — 순서·버전·결정별 필수 칸(U25-01·03). 부수 효과 없음."""
    step = NODE_ROLES[node_id]["step"]
    prop = current_proposal(doc)
    if prop is None or prop["status"] != STEP_PENDING[step]:
        raise DomainError(f"{step} 결재 차례가 아니다 (기안 상태 {prop and prop['status']})", 409)
    decision = answer.get("결정")
    if decision not in DECISIONS:
        raise DomainError(f"결정은 {'·'.join(DECISIONS)} 중 하나다", 422)
    if decision == "추가협상지시" and step == "TEAM":
        raise DomainError("추가 협상지시는 임원·대표만 한다", 422)
    if not str(answer.get("결재의견") or "").strip():
        raise DomainError("결재 의견(보완·반려·지시는 사유)이 필요하다", 422)
    if decision == "추가협상지시":
        if not str(answer.get("지시요구조건") or "").strip():
            raise DomainError("추가 협상 요구조건이 필요하다", 422)
        _at(answer.get("지시기한") or "", "추가 협상기한")


def record_decision(doc: dict, seed: Seed, node_id: str, args: dict[str, Any], *, by: str) -> None:
    step = NODE_ROLES[node_id]["step"]
    prop = current_proposal(doc)
    if prop is None or prop["proposal_key"] != args.get("proposal_id"):
        raise DomainError("다른 기안 버전에 대한 결정이다", 409)
    if any(
        d["proposal_key"] == prop["proposal_key"] and d["step"] == step for d in doc["decisions"]
    ):
        return  # 이미 처리된 결정 — 중복 저장하지 않는다(U25-03)
    decision = args["decision"]
    record = {
        "decision_id": f"APP-{step[0]}{len(doc['decisions']) + 1:02d}",
        "proposal_key": prop["proposal_key"],
        "step": step,
        "actor": by,
        "decision": decision,
        "comment": args.get("comment") or "",
        "decided_at": doc["clock"],
        "authority_version": calc.AUTHORITY_VERSION,
    }
    doc["decisions"].append(record)
    if decision == "승인":
        if step == "TEAM":
            prop["status"] = doc["approval_status"] = "EXEC_APPROVAL_PENDING"
        elif step == "EXEC":
            prop["status"] = doc["approval_status"] = "EXEC_APPROVED"  # 곧바로 S09가 판정한다
        else:
            _approve(doc, seed, prop, by=by, final_step="CEO")
    elif decision == "보완":
        prop["status"] = doc["approval_status"] = "RETURNED"
        record["assignee"] = user_for_role("구매담당")
        record["due_at"] = due_at(parse_at(doc["clock"]), 1).isoformat()
    elif decision == "반려":
        prop["status"] = doc["approval_status"] = "REJECTED"
        doc["scene"] = "REJECTED"
    else:  # 추가협상지시 — S14. 기록·배정·조회까지만이다(U25-02)
        prop["status"] = doc["approval_status"] = "NEEDS_RENEGOTIATION"
        doc["scene"] = "RENEGOTIATION"
        due = _at(args.get("due_at") or "", "추가 협상기한").isoformat()
        doc["instruction"] = {
            "instruction_id": "INSTR-RENEG01",
            "proposal_key": prop["proposal_key"],
            "by": by,
            "step": step,
            "reason": args.get("comment") or "",
            "condition": args.get("condition") or "",
            "assignee": user_for_role("구매담당"),
            "due_at": due,
            "at": doc["clock"],
            "status": "OPEN",
        }
        _open_task(
            doc,
            "RENEG",
            node_id="S14",
            assignee=user_for_role("구매담당"),
            due=due,
            note="추가 협상지시 — 2차 협상 상세는 후속 범위",
        )
        # 미확정 자료로 장면 3에 보일 수 있다 — 장면 2 상태는 재협상 대기다(H23·HAND-01).
        _bundle(doc, run_id=prop["run_id"], provisional=True, reason="추가 협상지시 — 미확정")
        _evidence(doc, "INSTR-RENEG01")
    _evidence(doc, record["decision_id"])
    audit(
        doc,
        actor=by,
        action="decision_recorded",
        step=step,
        decision=decision,
        proposal=prop["proposal_key"],
    )


def judge_authority(doc: dict, seed: Seed) -> bool:
    """
    S09 — AUTH02-v1로 대표 상신 여부. **최종 기안**의 향후 12개월 구매 증가액이다(AUTH-01).
    비대상이면
    임원 최종 승인과 함께 근거 금액·권한표 버전을 남긴다(AUTH-02). 위험이 중요여도 금액 미만이면
    대표를 더하지 않는다.
    """
    prop = current_proposal(doc)
    if prop is None or prop["status"] != "EXEC_APPROVED":
        raise DomainError("임원 승인 뒤에 대표 대상을 판정한다", 409)
    result = doc["runs"][prop["run_id"]]["result"]
    required = result["ceo_required"]
    if required is None:
        raise DomainError("12개월 구매 증가액 미산출 — 대표 대상 판정 보류", 409)
    basis = {
        "amount": result["next12"]["increase"],
        "threshold": str(seed.setting_decimal("ceo_threshold")),
        "authority_version": calc.AUTHORITY_VERSION,
        "required": required,
        "at": doc["clock"],
    }
    prop["authority"] = basis
    if required:
        prop["status"] = doc["approval_status"] = "CEO_APPROVAL_PENDING"
    else:
        _approve(doc, seed, prop, by="system", final_step="EXEC")
    audit(doc, actor="system", action="authority_judged", **basis)
    return bool(required)


def _approve(doc: dict, seed: Seed, prop: dict, *, by: str, final_step: str) -> None:
    """승인 완료 — 승인안 PV-APP01과 그 run을 만든다. 공식 F02·Target은 바꾸지 않는다(S11)."""
    prop["status"] = doc["approval_status"] = "APPROVED"
    prop["approved_at"] = doc["clock"]
    prop["final_step"] = final_step
    req = _request(doc)
    pv = doc["price_versions"][prop["price_version_id"]]
    app = _price_version(
        doc,
        "PV-APP01",
        "APPROVED",
        req,
        _d(pv["new_price"]),
        effective=date.fromisoformat(pv["effective_date"]),
        predecessor=pv["version_id"],
    )
    run_analysis(doc, seed, app["version_id"], by=by)


# ─────────────────────────── 원가 (U26 · S11 · CT29) ───────────────────────────


def cost_problems(doc: dict, check: Any) -> dict:
    prop = current_proposal(doc)
    if doc.get("instruction") is not None:
        raise DomainError("추가 협상지시 중이다 — 원가 등록 금지(X01)", 409)
    if prop is None or prop["status"] != "APPROVED":
        raise DomainError("필요한 승인이 모두 끝나지 않았다 — 원가를 등록할 수 없다", 409)
    if check != "일치":
        raise DomainError(
            "승인 조건과 다른 값은 직접 등록하지 않는다 — 기안 변경 절차로 돌린다(U26-01)", 409
        )
    return prop


def register_cost(doc: dict, seed: Seed, *, check: Any, note: str, by: str) -> str:
    """
    C02-APP01 — 승인 근거·적용기간·부품 구성·대상 모델·등록자. 같은 승인 버전의 중복 등록은 기존
    버전을
    돌려준다(COST-02). 적용일 전이면 적용 예정이다 — 상태는 시계에서 파생한다(적용일 도래는 사람
    승인이나 전망 승인 이벤트가 아니다).
    """
    prop = cost_problems(doc, check)
    for cv in doc["cost_versions"].values():
        if cv["approved_proposal"] == prop["proposal_key"]:
            return cv["cost_version_id"]
    app = doc["price_versions"]["PV-APP01"]
    cv_id = "C02-APP01"
    doc["cost_versions"][cv_id] = {
        "cost_version_id": cv_id,
        "seq": _seq(doc["cost_versions"]),
        "parent_cost_version": "C01",
        "approved_proposal": prop["proposal_key"],
        "price_version_id": app["version_id"],
        "run_id": app["run_id"],
        "part_id": app["part_id"],
        "old_price": app["old_price"],
        "new_price": app["new_price"],
        "effective_from": app["effective_date"],
        "models": calc.new_outsource(
            seed, app["part_id"], _d(app["old_price"]), _d(app["new_price"])
        ),
        "registered_by": by,
        "registered_at": doc["clock"],
        "note": note,
    }
    _evidence(doc, "REG-C02")
    audit(
        doc,
        actor=by,
        action="cost_registered",
        cost_version=cv_id,
        effective_from=app["effective_date"],
    )
    return cv_id


def cost_status(cv: dict, clock: str) -> str:
    return (
        "EFFECTIVE"
        if parse_at(clock).date() >= date.fromisoformat(cv["effective_from"])
        else ("REGISTERED_FUTURE")
    )


# ─────────────────────────── 장면 3 인계 (U27 · S12·S13 · CT30) ───────────────────────────


def _bundle(doc: dict, *, run_id: str, provisional: bool, reason: str) -> dict:
    """상위 검토건에 자료 한 벌을 잇는다. 과거 자료는 지우지 않는다(HAND-01)."""
    prop = current_proposal(doc)
    body = {
        "request_id": REQUEST_ID,
        "proposal": None if prop is None else prop["proposal_key"],
        "price_run": run_id,
        "quantity_run": doc["sc01"]["run_id"],
        "cost_version": next(iter(doc["cost_versions"]), None),
        "issues": [VOLUME_ISSUE_ID, COST_ISSUE_ID],
        "evidence": list(doc["evidence_ids"]),
        "decisions": [d["decision_id"] for d in doc["decisions"]],
    }
    bundle = {
        "bundle_id": f"BND-{len(doc['review']['bundles']) + 1:02d}",
        "at": doc["clock"],
        "provisional": provisional,
        "reason": reason,
        "hash": _hash(body)[:16],
        **body,
    }
    doc["review"]["bundles"].append(bundle)
    return bundle


def handoff_conditions(doc: dict) -> dict[str, Any]:
    """D11 인계 요청에서 서버가 확인할 조건(구현명세 6장 표) — 하나라도 없으면 완료 불가(T29)."""
    prop = current_proposal(doc)
    app = latest_run(doc, "PV-APP01")
    cv = next(iter(ordered(doc["cost_versions"])), None)
    conditions = {
        "approved": bool(prop and prop["status"] == "APPROVED"),
        "cost_registered": cv is not None,
        "run_matches_approval": bool(
            app
            and cv
            and prop
            and app["result"]["new_price"] == prop["price"]
            and app["result"]["effective_date"] == prop["effective_date"]
            and cv["new_price"] == prop["price"]
        ),
        "sc01_run_valid": doc["sc01"]["forecast_approval"] == "UNDER_REVIEW",
        "evidence_complete": all(
            e in doc["evidence_ids"]
            for e in ("DOC-REQ01", "NOTE-REPORT01", "NOTE-NEG01", "DOC-PROP01")
        )
        and bool(doc["decisions"]),
        "no_renegotiation": doc.get("instruction") is None,
    }
    labels = {
        "approved": "필요 승인 미완료",
        "cost_registered": "C02 원가 미등록",
        "run_matches_approval": "승인 조건과 분석·원가가 다르다",
        "sc01_run_valid": "장면 1 run이 유효하지 않다",
        "evidence_complete": "원천·협상·기안·승인 근거가 빠졌다",
        "no_renegotiation": "추가 협상지시 — 재협상 대기",
    }
    return {
        "conditions": conditions,
        "met": all(conditions.values()),
        "reasons": [labels[k] for k, ok in conditions.items() if not ok],
    }


def request_handoff(doc: dict, *, fin: Any, note: str, by: str) -> dict[str, Any]:
    check = handoff_conditions(doc)
    if not check["met"]:
        raise DomainError("인계 조건 미충족: " + ", ".join(check["reasons"]), 409)
    fin_id = _user(fin)
    if USERS.get(fin_id, {}).get("role") != "경영관리담당":
        raise DomainError(f"경영관리 담당이어야 한다 (받은 값: {fin or '없음'})", 422)
    app = latest_run(doc, "PV-APP01")
    bundle = _bundle(doc, run_id=app["run_id"], provisional=False, reason=note)  # type: ignore[index]
    revision = 1 if doc["handoff"] is None else doc["handoff"]["revision"] + 1
    if doc["handoff"] is not None:
        doc["handoff_history"].append(doc["handoff"])
    doc["handoff"] = {
        "handoff_id": "HANDOFF-01",
        "revision": revision,
        "review_id": REVIEW_ID,
        "selected_run": app["run_id"],  # type: ignore[index]
        "bundle_id": bundle["bundle_id"],
        "bundle_hash": bundle["hash"],
        "assignee": fin_id,
        "requested_by": by,
        "requested_at": doc["clock"],
        "due_at": due_at(parse_at(doc["clock"]), 1).isoformat(),
        "note": note,
        "provisional": False,
        "status": "FINANCE_PENDING",
        "accepted_by": None,
        "accepted_at": None,
        "opinion": None,
        "sc03_due_at": None,
    }
    _evidence(doc, "HANDOFF-01")
    audit(
        doc,
        actor=by,
        action="handoff_requested",
        handoff="HANDOFF-01",
        fin=fin_id,
        bundle=bundle["bundle_id"],
    )
    return {"fin_name": name_of(fin_id), "handoff_id": "HANDOFF-01"}


def accept_handoff(doc: dict, *, opinion: str, by: str, bundle_hash: str | None = None) -> None:
    """
    D12 — 지정 담당자가 최신 자료 버전·범위·가정을 확인하고 인수한다. 장면 3 분석 기한은 두 번째
    영업일 18시다. **장면 2 인계 완료, 장면 3 손익 검토 대기** — 위험·전망은 그대로다(SCOPE-01).
    """
    h = doc["handoff"]
    if h is None or h["status"] != "FINANCE_PENDING":
        raise DomainError("인수할 인계가 없다", 409)
    if bundle_hash is not None and bundle_hash != h["bundle_hash"]:
        raise DomainError("본 자료가 최신 인계 자료가 아니다 — 새로 고친 뒤 다시 인수한다", 409)
    if by != h["assignee"]:
        raise DomainError("지정된 경영관리 담당자만 인수할 수 있다", 403)
    if not handoff_conditions(doc)["met"]:
        raise DomainError("인계 조건이 더는 성립하지 않는다 — 다시 인계 요청이 필요하다", 409)
    h.update(
        status="HANDED_OFF",
        accepted_by=by,
        accepted_at=doc["clock"],
        opinion=opinion,
        sc03_due_at=due_at(parse_at(doc["clock"]), 2).isoformat(),
    )
    doc["scene"] = "HANDED_OFF"
    _evidence(doc, "ACK-01")
    audit(doc, actor=by, action="SC02_HANDED_OFF", handoff=h["handoff_id"], bundle=h["bundle_id"])


def _user(value: Any) -> str:
    try:
        return user_id_of(str(value or ""))
    except DomainError:
        return str(value or "")


# ─────────────────────────── Agent (AG21~24) ───────────────────────────


def agent_draft(doc: dict, *, kind: str, run_id: str) -> str:
    """
    초안 하나 — 같은 종류·같은 입력 해시의 성공 초안은 다시 쓰고, 자료가 바뀌면 새로 만든다(AG-24).
    실패해도 업무는 계속된다(X09-B) — 실패 사유만 남긴다. 검토 완료나 승인이 아니다(AG-23).
    """
    if kind not in agent.KINDS:
        raise DomainError(f"모르는 Agent 지원: {kind}", 422)
    run = doc["runs"].get(run_id)
    if run is None:
        raise DomainError(f"없는 분석: {run_id}", 404)
    payload = agent.build_input(doc, kind, run)
    digest = agent.input_hash(payload)
    for o in ordered(doc["agent_outputs"]):
        if o["kind"] == kind and o["input_hash"] == digest and o["status"] == "SUCCEEDED":
            return o["output_id"]
        if o["kind"] == kind:
            o["stale"] = True  # 이전 자료 기준 — 표시한다
    output_id = f"{kind}-{len(doc['agent_outputs']) + 1:03d}"
    record: dict[str, Any] = {
        "output_id": output_id,
        "seq": _seq(doc["agent_outputs"]),
        "kind": kind,
        "run_id": run_id,
        "input_hash": digest,
        "prompt_version": agent.PROMPT_VERSION,
        "mode": doc.get("agent_mode", "mock"),
        "created_at": doc["clock"],
        "status": "FAILED",
        "draft": None,
        "errors": [],
        "stale": False,
        "adopted_by": None,
        "adopted_at": None,
    }
    for attempt in (1, 2):  # 자동 재시도 1회(AG-24)
        try:
            out = agent.run(payload, record["mode"])
        except agent.AgentFailure as exc:
            record["errors"].append(f"{attempt}차: {exc}")
            continue
        problems = agent.validate(out, payload)
        if problems:
            record["errors"].append(f"{attempt}차 검증 실패: " + "; ".join(problems))
            continue
        record.update(status="SUCCEEDED", draft=out)
        break
    doc["agent_outputs"][output_id] = record
    audit(doc, actor="system", action="agent_draft", output_id=output_id, status=record["status"])
    return output_id


def adopt_agent(doc: dict, output_id: str, *, actor: str) -> None:
    o = doc["agent_outputs"].get(output_id)
    if o is None or o["status"] != "SUCCEEDED":
        raise DomainError("채택할 초안이 없다", 404)
    o.update(adopted_by=actor, adopted_at=doc["clock"])
    audit(doc, actor=actor, action="agent_adopted", output_id=output_id)


# ─────────────────────────── 업무 (공통 업무함) ───────────────────────────


def tasks_of(doc: dict, task_type: str) -> list[dict]:
    return [t for t in ordered(doc["tasks"]) if t["type"] == task_type]


def _active_task(doc: dict, task_type: str) -> dict | None:
    return next((t for t in reversed(tasks_of(doc, task_type)) if t["status"] != "COMPLETED"), None)


def task_for_node(doc: dict, node_id: str) -> dict | None:
    spec = NODE_ROLES.get(node_id)
    return _active_task(doc, spec["task"]) if spec else None


def _open_task(
    doc: dict,
    task_type: str,
    *,
    node_id: str,
    assignee: str,
    due: str,
    note: str | None = None,
    request_id: str | None = None,
) -> dict:
    previous = tasks_of(doc, task_type)
    task_id = f"TASK-{task_type}" + (f"-{len(previous) + 1}" if previous else "")
    task = doc["tasks"][task_id] = {
        "task_id": task_id,
        "seq": _seq(doc["tasks"]),
        "type": task_type,
        "node_id": node_id,
        "request_id": request_id,
        "assigned_to": assignee,
        "assigned_at": doc["clock"],
        "due_at": due,
        "status": "ASSIGNED",
        "completed_at": None,
        "completed_by": None,
        "reopens": previous[-1]["task_id"] if previous else None,
        "history": [{"at": doc["clock"], "status": "ASSIGNED", "by": "system", "note": note}],
    }
    audit(doc, actor="system", action="task_assigned", task_id=task_id, assigned_to=assignee)
    return task


def sync_tasks(doc: dict, pendings: dict[str, dict[str, Any]], variables: dict[str, Any]) -> None:
    """
    BPM의 사람 대기 → 업무. 대기가 생긴 시각이 배정 시각이다. 같은 대기면 새로 만들지 않는다. 끝난
    업무를 다시 쓰지 않는다 — 보완으로 기안이 다시 열리면 TASK-PROPOSAL-2가 생긴다(WF-23: 새 기한,
    이전 지연·소요시간은 보존).
    """
    nodes = list(NODE_ROLES)
    for request_id, p in sorted(
        pendings.items(),
        key=lambda kv: nodes.index(kv[1]["node_id"]) if kv[1]["node_id"] in nodes else 99,
    ):
        spec = NODE_ROLES.get(p["node_id"])
        if spec is None:
            continue
        task = _active_task(doc, spec["task"])
        if task is not None and task["request_id"] == request_id:
            continue
        assignee = _user(variables.get(spec.get("assignee_var", ""))) or user_for_role(spec["role"])
        if spec["days"] is None:
            due = (doc["request"] or {}).get("negotiation_due", {}).get("due_at") or due_at(
                parse_at(doc["clock"]), 1
            ).isoformat()
        else:
            due = due_at(parse_at(doc["clock"]), spec["days"]).isoformat()
        _open_task(
            doc,
            spec["task"],
            node_id=p["node_id"],
            assignee=assignee,
            due=due,
            request_id=request_id,
        )


def complete_task(doc: dict, node_id: str, *, actor: str, note: str | None = None) -> None:
    task = task_for_node(doc, node_id)
    if task is None:
        return
    task.update(status="COMPLETED", completed_at=doc["clock"], completed_by=actor)
    task["history"].append({"at": doc["clock"], "status": "COMPLETED", "by": actor, "note": note})
    audit(doc, actor=actor, action="task_completed", task_id=task["task_id"])


def check_actor(doc: dict, node_id: str, actor: str) -> None:
    """
    역할·담당자 검사 — 시연의 역할 전환도 통과해야 한다(AUTH-03). Agent·시스템은 결재 주체가 아니다.
    """
    user = USERS.get(actor)
    if user is None:
        raise DomainError(f"모르는 사용자: {actor}", 403)
    spec = NODE_ROLES[node_id]
    if user["role"] != spec["role"]:
        raise DomainError(f"{spec['role']}만 할 수 있다 (현재 {user['role']})", 403)
    task = task_for_node(doc, node_id)
    if task is not None and task["assigned_to"] and task["assigned_to"] != actor:
        raise DomainError("배정된 담당자만 처리할 수 있다", 403)


def raise_overdue_alerts(doc: dict) -> list[dict]:
    """
    가상 현재시각 > 기한이고 미완료면 담당자·검토자에게 화면 내 알림 — 같은 업무·기한에 한
    번만(WF-24).
    """
    alerts = doc["alerts"]
    seen = {(a["task_id"], a["due_at"]) for a in alerts}
    created = []
    for task in ordered(doc["tasks"]):
        if not overdue(task, doc["clock"]) or (task["task_id"], task["due_at"]) in seen:
            continue
        alert = {
            "alert_id": f"ALERT-{len(alerts) + 1:03d}",
            "kind": "OVERDUE",
            "task_id": task["task_id"],
            "due_at": task["due_at"],
            "at": doc["clock"],
            "to": [u for u in (task["assigned_to"], REVIEWER.get(task["type"])) if u],
            "message": f"{task['task_id']} 기한({task['due_at'][5:16].replace('T', ' ')}) "
            "초과 — 미완료",
        }
        alerts.append(alert)
        created.append(alert)
        audit(doc, actor="system", action="overdue_alert", task_id=task["task_id"], to=alert["to"])
    return created


# ─────────────────────────── 사전 검사 (입력 보존) ───────────────────────────


def check_answer(doc: dict, seed: Seed, node_id: str, answer: dict[str, Any]) -> None:
    """
    폼이 못 거는 업무 규칙 — **부수 효과가 없다.** 답을 엔진에 넣기 전에 불러 입력을 지우지 않고
    거절한다(SC01 4.6과 같다). 기록 작업도 같은 규칙으로 막는다.
    """
    if node_id == "Verify_Request":
        if answer.get("확인결과") == "확인완료" and (doc["request"] or {}).get("errors"):
            raise DomainError("검사 오류가 남아 있어 확인 완료할 수 없다 — 보완 요청하라", 409)
    elif node_id == "Report_Lead":
        if answer.get("검토필요성") not in ("검토진행", "검토종결"):
            raise DomainError("검토 필요성을 고른다", 422)
    elif node_id == "Confirm_Analysis":
        price = answer.get("내부제시단가")
        if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0:
            raise DomainError("내부 제시 단가는 양수(원)다", 422)
        _at(answer.get("협상기한") or "", "외부 협상기한")
    elif node_id == "Record_Negotiation":
        outcome = answer.get("협상결과")
        price = answer.get("협상단가")
        if outcome == "잠정합의" and (price is None or price == "" or float(price) <= 0):
            raise DomainError("잠정합의면 잠정 단가가 필요하다", 422)
        if outcome == "미합의" and price not in (None, ""):
            raise DomainError(
                "미합의면 단가를 비워 둔다 — 0원이나 임의 단가로 확정하지 않는다", 422
            )
        _date(answer.get("협상적용일"), "적용일")
    elif node_id == "Draft_Proposal":
        proposal_problems(
            doc,
            seed,
            {
                "price": answer.get("기안단가"),
                "effective_date": answer.get("기안적용일"),
                "reason": answer.get("인상필요성"),
                "diff_reason": answer.get("차이사유"),
            },
        )
    elif node_id in ("Approve_Lead", "Approve_Exec", "Approve_CEO"):
        decision_problems(doc, node_id, answer)
    elif node_id == "Register_Cost":
        cost_problems(doc, answer.get("대조결과"))
    elif node_id == "Request_Handoff":
        check = handoff_conditions(doc)
        if not check["met"]:
            raise DomainError("인계 조건 미충족: " + ", ".join(check["reasons"]), 409)
        if USERS.get(_user(answer.get("경영관리담당자")), {}).get("role") != "경영관리담당":
            raise DomainError("경영관리 담당을 고른다", 422)
    elif node_id == "Accept_Handoff":
        if not str(answer.get("인수의견") or "").strip():
            raise DomainError("인수 의견이 필요하다", 422)


# ─────────────────────────── 상태 (구현명세 10장) ───────────────────────────


def statuses(doc: dict) -> dict[str, Any]:
    """상태 축을 칩 하나로 뭉치지 않는다 — 요청·승인·원가·인계·위험·전망·장면."""
    cv = next(iter(ordered(doc["cost_versions"])), None)
    h = doc["handoff"]
    scene = doc["scene"]
    return {
        "request": (doc["request"] or {}).get("status"),
        "approval": doc["approval_status"],
        "cost": None if cv is None else cost_status(cv, doc["clock"]),
        "handoff": None if h is None else h["status"],
        "risk": "OPEN",
        "forecast": "REVIEW_PENDING",
        "scene": scene,
        "sceneCode": "SC02_HANDED_OFF / SC03_PENDING" if scene == "HANDED_OFF" else scene,
    }
