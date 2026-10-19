"""
SC01 업무 기록 — 데모 실행 하나의 원천·전망·계산·이슈·업무·감사 이력.

**한 데모 실행 = 문서 하나**다. 계산 결과 저장·이슈 갱신·BPM 스냅샷이 한 번의 쓰기로 함께
저장되므로 "계산은 성공했는데 이슈가 안 바뀌었다"가 생기지 않는다(API-04의 트랜잭션 요구).
데모 실행끼리는 서로 보지 않으므로(DATA-05) 실행 사이의 조회가 필요 없다.

이 모듈은 순수 함수다 — 시드와 문서(dict)를 받아 문서를 고친다. 저장·BPM은 `process.py`다.
상태 축은 서로 독립이다(구현명세 9장): 자료 확인 · 계산 · 전망 승인 · 업무 · 위험 · 이슈 · 장면.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.sc01.calc import Assessment, Risk, assess_all, build_forecast
from app.sc01.seed import Key, Seed, SourceRow

KST = ZoneInfo("Asia/Seoul")
CUSTOMERS = {"CUS-HK"}
PLANTS = {"ULS"}
SOURCE_MONTHS = {date(2027, m, 1) for m in (7, 8, 9)}

#: 시연 사용자 마스터 — 가상 인물이다. 역할은 구현명세 2장 표.
USERS: dict[str, dict[str, str]] = {
    "u-sales": {"name": "이도윤", "role": "영업담당"},
    "u-sales-lead": {"name": "박서진", "role": "영업팀장"},
    "u-prod": {"name": "김태오", "role": "생산담당"},
    "u-mat": {"name": "최유나", "role": "자재담당"},
    "u-fin": {"name": "정하윤", "role": "경영관리담당"},
    "u-plant": {"name": "한준호", "role": "공장장"},
    "u-demo": {"name": "시연관리자", "role": "시연관리자"},
}


class DomainError(Exception):
    """업무 규칙 위반. `status`는 API가 그대로 쓴다(API-03: 403·404·409·422)."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


# ─────────────────────────── 시간·달력 (WF-04) ───────────────────────────


def parse_at(value: str) -> datetime:
    at = datetime.fromisoformat(value)
    return at if at.tzinfo else at.replace(tzinfo=KST)


def _is_business_day(d: date) -> bool:
    return d.weekday() < 5  # 데모 달력: 월~금, 공휴일 없음


def _next_business_day(d: date) -> date:
    d += timedelta(days=1)
    while not _is_business_day(d):
        d += timedelta(days=1)
    return d


def due_at(assigned: datetime, business_days: int) -> datetime:
    """
    배정 시각에서 기한을 낸다. 일반 업무는 다음 영업일 18시, 손익분석은 두 번째 영업일 18시.
    비영업일이나 18시 이후 배정은 다음 영업일을 배정 기준일로 삼는다.
    """
    local = assigned.astimezone(KST)
    basis = local.date()
    if not _is_business_day(basis) or local.time() >= time(18):
        basis = _next_business_day(basis)
    for _ in range(business_days):
        basis = _next_business_day(basis)
    return datetime.combine(basis, time(18), tzinfo=KST)


# ─────────────────────────── 시연 원천 (EX 변형 포함) ───────────────────────────

#: fixture_id → (customer_plan_id, {(모델, 월): 바꿀 수량}). 기본 데이터에 예외값을 섞지 않고
#: 각 변형을 CP02 기준에서 따로 만든다(ERR-01). None은 누락이다 — 0과 다르다.
FIXTURES: dict[str, tuple[str, dict[tuple[str, int], int | None]]] = {
    "CP02": ("CP02", {}),
    "EX01": ("CP02", {("A-b", 7): 9500, ("A-c", 7): 5900}),
    "EX02": ("CP02", {("A-b", 7): None}),
    "CP03": ("CP03", {("A-b", 7): 9000}),
    "EX04": ("CP02", {("A-c", 7): 6500}),
    "EX05": ("CP02", {("A-b", 7): 0}),
}


def fixture_rows(seed: Seed, fixture_id: str) -> tuple[str, list[SourceRow]]:
    if fixture_id not in FIXTURES:
        raise DomainError(f"모르는 시연 원천: {fixture_id}", 404)
    plan_id, overrides = FIXTURES[fixture_id]
    rows = []
    for row in seed.customer_plans["CP02"]:
        q = overrides.get((row.model_id, row.period.month), row.quantity)
        rows.append(replace(row, customer_plan_id=plan_id, quantity=q))
    return plan_id, rows


def _row_json(r: SourceRow) -> dict[str, Any]:
    d = asdict(r)
    d["period"] = r.period.isoformat()
    return d


def _row_from(d: dict[str, Any]) -> SourceRow:
    return SourceRow(**{**d, "period": date.fromisoformat(d["period"])})


def _content_hash(rows: list[SourceRow]) -> str:
    body = sorted(
        (r.customer_id, r.plant_id, r.model_id, r.period.isoformat(), r.quantity) for r in rows
    )
    return hashlib.sha256(json.dumps(body).encode()).hexdigest()


# ─────────────────────────── 문서 ───────────────────────────


def _qty_rows(plan: dict[Key, int | None]) -> list[list[Any]]:
    return [[k[2], k[3].isoformat(), q] for k, q in sorted(plan.items())]


def _plan_from(rows: list[list[Any]]) -> dict[Key, int | None]:
    return {("CUS-HK", "ULS", m, date.fromisoformat(p)): q for m, p, q in rows}


def _assessment_json(a: Assessment) -> dict[str, Any]:
    return {
        "model_id": a.model_id,
        "period": a.period.isoformat(),
        "target": a.target,
        "prior": a.prior,
        "latest": a.latest,
        "unit_cm": str(a.unit_cm),
        "risk": a.risk.value if a.risk else None,
        "partial": a.partial,
        "metrics": {
            mid: {
                "metric_id": m.metric_id,
                # 금액·정밀 비율은 문자열 DECIMAL로 싣는다(API-02) — float면 경계값이 흔들린다.
                "value": None if m.value is None else str(m.value),
                "unit": m.unit,
                "computable": m.computable,
                "risk_level": m.risk.value if m.risk else None,
                "reason": m.reason,
            }
            for mid, m in a.metrics.items()
        },
    }


def issue_id_for(model_id: str, period: date) -> str:
    return f"ISSUE-{model_id[-1].upper()}{period.month:02d}"


def new_demo_run(seed: Seed, demo_run_id: str, *, case_id: str, created_at: datetime) -> dict:
    """
    S0 — 기준 적재(2027-06-15 18:00). 승인 전망 F01과 기존 관심 이슈 A07·B07만 있다.
    CP02·F02는 아직 없다(AT01). 8·9월 관심 평가는 평가 결과일 뿐 이슈로 만들지 않는다(UI01-04).
    """
    clock = datetime(2027, 6, 15, 18, 0, tzinfo=KST)
    s0_keys = sorted(k for k in seed.plans["F01"] if k[3] in SOURCE_MONTHS)
    s0 = assess_all(s0_keys, seed.plans["T01"], seed.plans["F01"], seed.plans["F01"], seed)
    issues = {}
    for a in s0:
        if a.period == date(2027, 7, 1) and a.risk in (Risk.ATTENTION, Risk.CRITICAL):
            iid = issue_id_for(a.model_id, a.period)
            issues[iid] = {
                "issue_id": iid,
                "cause": "CUSTOMER_VOLUME",
                "customer_id": "CUS-HK",
                "plant_id": "ULS",
                "model_id": a.model_id,
                "period": a.period.isoformat(),
                "risk": a.risk.value,
                "status": "OPEN",
                "owner_role": "영업팀장",
                "runs": ["RUN-F01-001"],
                "history": [
                    {"at": clock.isoformat(), "run_id": "RUN-F01-001", "risk": a.risk.value}
                ],
            }
    return {
        "demo_run_id": demo_run_id,
        "seed_id": "SYN-SC01-v0.2",
        "case_id": case_id,
        "created_at": created_at.isoformat(),
        "clock": clock.isoformat(),
        "step": "S0",
        "scene": "READY",
        "sources": {},
        "forecasts": {},
        "calc_runs": {
            "RUN-F01-001": {
                "run_id": "RUN-F01-001",
                "status": "SUCCEEDED",
                "versions": {
                    "target": "T01",
                    "prior": "F01",
                    "latest": "F01",
                    "cost": "C01",
                    "rule": "R01-v1",
                    "fixed": "FC01",
                },
                "source_id": "SRC01",
                "at": clock.isoformat(),
                "results": [_assessment_json(a) for a in s0],
            }
        },
        "issues": issues,
        "tasks": {},
        "reviews": {},
        "handoff": None,
        "audit": [],
        "bpm": None,
    }


def audit(
    doc: dict, *, actor: str, action: str, event_code: str | None = None, **detail: Any
) -> None:
    """모든 상태 변경에 행위자·시각·근거를 남긴다(AT15)."""
    user = USERS.get(actor, {"name": actor, "role": "system"})
    doc["audit"].append(
        {
            "seq": len(doc["audit"]) + 1,
            "at": doc["clock"],
            "event_code": event_code,
            "actor": actor,
            "actor_name": user["name"],
            "actor_role": user["role"],
            "action": action,
            "detail": detail,
        }
    )


# ─────────────────────────── 원천 (UI02·UI03) ───────────────────────────


def receive_source(doc: dict, seed: Seed, fixture_id: str, *, actor: str) -> tuple[str, bool]:
    """시연 원천 수신. 같은 내용 재수신은 기존 접수를 돌려준다 — (source_id, 새로 만들었나)."""
    plan_id, rows = fixture_rows(seed, fixture_id)
    digest = _content_hash(rows)
    for sid, s in doc["sources"].items():
        if s["hash"] == digest:
            return sid, False
    sid = f"SRC{len(doc['sources']) + 2:02d}"  # SRC01은 시드(CP01)다
    corrects = next(
        (x for x, s in doc["sources"].items() if s["customer_plan_id"] == plan_id), None
    ) or next(iter(doc["sources"]), None)
    doc["sources"][sid] = {
        "source_id": sid,
        "fixture_id": fixture_id,
        "customer_plan_id": plan_id,
        "received_at": doc["clock"],
        "hash": digest,
        "status": "RECEIVED",
        "corrects": corrects,  # 정정본이면 이전 원천과의 관계를 남긴다(이전 것은 지우지 않는다)
        "rows": [_row_json(r) for r in rows],
        "errors": [],
        "verified_by": None,
        "verified_at": None,
    }
    # 새 계획 수신이 장면의 시작이다. 인계 뒤에 정정본이 오면 다시 ACTIVE다(WF-03).
    doc["scene"] = "ACTIVE"
    audit(doc, actor=actor, action="source_received", source_id=sid, fixture_id=fixture_id)
    return sid, True


def validate_source(doc: dict, seed: Seed, source_id: str) -> list[dict[str, Any]]:
    """UI03-01 자동 검증. 오류가 있으면 확인 완료와 계산이 막힌다. 0과 누락을 구분한다."""
    s = doc["sources"][source_id]
    rows = [_row_from(r) for r in s["rows"]]
    errors: list[dict[str, Any]] = []
    seen: set[tuple[str, date]] = set()
    for r in rows:
        where = f"{r.model_id} {r.period:%Y-%m}"
        if (
            r.customer_id not in CUSTOMERS
            or r.plant_id not in PLANTS
            or r.model_id not in seed.models
        ):
            errors.append({"row": where, "code": "UNMAPPED", "message": "고객·공장·모델 미매핑"})
        if r.period not in SOURCE_MONTHS:
            errors.append({"row": where, "code": "PERIOD", "message": "대상 기간(7~9월) 밖"})
        if r.quantity is None:
            errors.append(
                {"row": where, "code": "MISSING", "message": "수량 누락 — 0으로 대체하지 않는다"}
            )
        elif r.quantity < 0:
            errors.append({"row": where, "code": "NEGATIVE", "message": "음수 수량"})
        if r.quantity_scope != "FULL_MONTH":
            errors.append({"row": where, "code": "SCOPE", "message": "월 전체 물량이 아니다"})
        if r.allocation_scope != "ASSIGNED_SUPPLY":
            errors.append(
                {"row": where, "code": "ALLOCATION", "message": "당사 배정 물량이 아니다"}
            )
        if (r.model_id, r.period) in seen:
            errors.append({"row": where, "code": "DUPLICATE", "message": "모델·월 중복"})
        seen.add((r.model_id, r.period))
    expected = {(m, p) for m in seed.models for p in SOURCE_MONTHS}
    for m, p in sorted(expected - seen):
        errors.append({"row": f"{m} {p:%Y-%m}", "code": "INCOMPLETE", "message": "예상 행 누락"})
    s["errors"] = errors
    if errors:
        s["status"] = "NEEDS_INFO"
    return errors


def verify_source(doc: dict, source_id: str, *, actor: str, opinion: str, evidence: str) -> None:
    """원천 확인 완료 — VERIFIED. **전망 승인은 하지 않는다**(UI03-02)."""
    s = doc["sources"][source_id]
    if s["errors"]:
        raise DomainError("검증 오류가 남아 있어 확인 완료할 수 없다 — 보완 요청하라", 409)
    s.update(
        status="VERIFIED",
        verified_by=actor,
        verified_at=doc["clock"],
        opinion=opinion,
        evidence=evidence,
    )


def request_fix(doc: dict, source_id: str, *, actor: str, opinion: str) -> None:
    s = doc["sources"][source_id]
    s.update(status="NEEDS_INFO", fix_requested_by=actor, fix_opinion=opinion)


# ─────────────────────────── 비교 계산 (UI03-02·UI04) ───────────────────────────

_RISK_ORDER = [Risk.NORMAL, Risk.ATTENTION, Risk.CRITICAL]


def compare(doc: dict, seed: Seed, source_id: str) -> dict[str, Any]:
    """
    F01 복제 + 확인된 원천 → 새 전망(F02, 정정이면 F03…), 새 run에서 15행 지표를 계산한다.

    직전은 **승인 전망 F01**이다 — F02는 검토 중이라 다음 비교의 직전이 되지 못한다(EX03).
    이슈는 같은 키(고객·공장·모델·월·원인)의 열린 이슈에 run을 잇고, 이번에 바뀌었고 관심
    이상인 키만 새로 연다. 위험 수준은 사람이 바꾸지 않는다(UI04-05).
    """
    s = doc["sources"][source_id]
    if s["status"] != "VERIFIED":
        raise DomainError("확인되지 않은 원천으로 계산할 수 없다", 409)
    rows = [_row_from(r) for r in s["rows"]]
    latest = build_forecast(seed.plans["F01"], rows)
    version = f"F{len(doc['forecasts']) + 2:02d}"
    run_id = f"RUN-{version}-001"
    doc["forecasts"][version] = {
        "version_id": version,
        "source_id": source_id,
        "approval": "UNDER_REVIEW",  # 공식 승인 API는 SC01 범위 밖이다
        "created_at": doc["clock"],
        "quantities": _qty_rows(latest),
    }
    keys = sorted(r.key for r in rows)
    results = assess_all(keys, seed.plans["T01"], seed.plans["F01"], latest, seed)
    doc["calc_runs"][run_id] = {
        "run_id": run_id,
        "status": "SUCCEEDED",
        "versions": {
            "target": "T01",
            "prior": "F01",
            "latest": version,
            "cost": "C01",
            "rule": "R01-v1",
            "fixed": "FC01",
        },
        "source_id": source_id,
        "at": doc["clock"],
        "results": [_assessment_json(a) for a in results],
    }

    changed = [a for a in results if a.metrics["M01"].value not in (None, 0)]
    for a in results:
        iid = issue_id_for(a.model_id, a.period)
        issue = doc["issues"].get(iid)
        is_changed = a in changed
        if issue is None and not (is_changed and a.risk in (Risk.ATTENTION, Risk.CRITICAL)):
            continue
        if issue is None:
            issue = doc["issues"][iid] = {
                "issue_id": iid,
                "cause": "CUSTOMER_VOLUME",
                "customer_id": a.key[0],
                "plant_id": a.key[1],
                "model_id": a.model_id,
                "period": a.period.isoformat(),
                "risk": None,
                "status": "OPEN",
                "owner_role": "영업팀장",
                "runs": [],
                "history": [],
            }
        risk = a.risk.value if a.risk else None
        issue["runs"].append(run_id)
        issue["history"].append({"at": doc["clock"], "run_id": run_id, "risk": risk})
        issue["risk"] = risk

    def rank(a: Assessment) -> int:
        return _RISK_ORDER.index(a.risk) if a.risk else -1

    top = max(changed, key=rank, default=None)
    risk = top.risk.value if top is not None and top.risk else Risk.NORMAL.value
    primary = issue_id_for(top.model_id, top.period) if top is not None else ""
    if primary and primary not in doc["issues"]:
        primary = ""
    doc["scene"] = "ACTIVE"
    audit(doc, actor="system", action="calculated", run_id=run_id, forecast=version, risk=risk)
    return {"run_id": run_id, "risk": risk, "issue_id": primary}


# ─────────────────────────── 업무 (UI05) ───────────────────────────

#: BPMN 노드 → 업무 종류·담당 역할·기한(영업일). 업무가 아닌 조작(배정·요청·계산 실행)은
#: `task`가 None이다 — 역할 검사만 한다.
NODE_ROLES: dict[str, dict[str, Any]] = {
    "Approve_DQ": {"task": "DQ", "role": "영업담당", "days": 1, "kind": "complete"},
    "Confirm_Calc": {"task": None, "role": "영업담당"},
    "Approve_Sales": {"task": "SALES", "role": "영업팀장", "days": 1, "kind": "complete"},
    "Approve_Dispatch": {"task": None, "role": "영업팀장"},
    "Approve_Review": {"task": None, "role": "영업팀장"},
    "Accept_PROD": {
        "task": "PROD",
        "role": "생산담당",
        "days": 1,
        "kind": "accept",
        "assignee_var": "생산담당자",
    },
    "Accept_MAT": {
        "task": "MAT",
        "role": "자재담당",
        "days": 1,
        "kind": "accept",
        "assignee_var": "자재담당자",
    },
    "Accept_FIN": {
        "task": "FIN",
        "role": "경영관리담당",
        "days": 2,
        "kind": "accept",
        "assignee_var": "경영관리담당자",
    },
}

DEFAULT_ASSIGNEE = {"영업담당": "u-sales", "영업팀장": "u-sales-lead"}


def sync_tasks(doc: dict, pendings: dict[str, dict[str, Any]], variables: dict[str, Any]) -> None:
    """
    BPM의 사람 대기를 업무 기록으로 옮긴다. 대기가 생긴 시각이 배정 시각이다.

    같은 종류의 활성 업무가 이미 있으면 새로 만들지 않고 이어 쓴다(WF-02). 보완 뒤 다시
    배정돼도 최초 배정 시각과 원래 기한은 보존한다(설계서 1.9).
    """
    for request_id, p in pendings.items():
        spec = NODE_ROLES.get(p["node_id"])
        if spec is None or spec["task"] is None:
            continue
        task_id = f"TASK-{spec['task']}"
        task = doc["tasks"].get(task_id)
        if task is not None and task["request_id"] == request_id:
            continue
        assignee = variables.get(spec.get("assignee_var", ""), "") or DEFAULT_ASSIGNEE.get(
            spec["role"]
        )
        if task is None:
            assigned = parse_at(doc["clock"])
            doc["tasks"][task_id] = {
                "task_id": task_id,
                "type": spec["task"],
                "node_id": p["node_id"],
                "request_id": request_id,
                "owner_role": spec["role"],
                "assigned_to": assignee,
                "assigned_at": assigned.isoformat(),
                "due_at": due_at(assigned, spec["days"]).isoformat(),
                "status": "ASSIGNED",
                "accepted_by": None,
                "accepted_at": None,
                "completed_at": None,
                "run_id": variables.get("계산ID") or None,
                "issue_id": variables.get("이슈ID") or None,
                "source_id": variables.get("원천ID"),
                "history": [{"at": doc["clock"], "status": "ASSIGNED", "by": "system"}],
            }
            audit(
                doc, actor="system", action="task_assigned", task_id=task_id, assigned_to=assignee
            )
        else:
            task.update(
                request_id=request_id,
                status="ASSIGNED",
                run_id=variables.get("계산ID") or task["run_id"],
                source_id=variables.get("원천ID"),
            )
            task["history"].append(
                {"at": doc["clock"], "status": "ASSIGNED", "by": "system", "note": "보완 후 재배정"}
            )


def task_for_node(doc: dict, node_id: str) -> dict | None:
    spec = NODE_ROLES.get(node_id)
    return doc["tasks"].get(f"TASK-{spec['task']}") if spec and spec["task"] else None


def check_actor(doc: dict, node_id: str, actor: str) -> None:
    """역할·담당자 검사(UI05-02·AT13). 시연의 역할 전환도 이 검사를 통과해야 한다."""
    user = USERS.get(actor)
    if user is None:
        raise DomainError(f"모르는 사용자: {actor}", 403)
    spec = NODE_ROLES[node_id]
    if user["role"] != spec["role"]:
        raise DomainError(f"{spec['role']}만 할 수 있다 (현재 {user['role']})", 403)
    task = task_for_node(doc, node_id)
    if task is not None and task["assigned_to"] and task["assigned_to"] != actor:
        raise DomainError("배정된 담당자만 인수할 수 있다", 403)


def mark_task(
    doc: dict, node_id: str, *, actor: str, outcome: str, note: str | None = None
) -> None:
    task = task_for_node(doc, node_id)
    if task is None:
        return
    at = doc["clock"]
    if outcome == "accepted":
        task.update(status="IN_PROGRESS", accepted_by=actor, accepted_at=at)
    elif outcome == "completed":
        task.update(
            status="COMPLETED",
            completed_at=at,
            accepted_by=task["accepted_by"] or actor,
            accepted_at=task["accepted_at"] or at,
        )
    elif outcome == "needs_info":
        task.update(status="NEEDS_INFO")
    task["history"].append({"at": at, "status": task["status"], "by": actor, "note": note})
    audit(doc, actor=actor, action=f"task_{outcome}", task_id=task["task_id"])


def overdue(task: dict, clock: str) -> bool:
    """기한 초과는 진행 상태와 독립된 플래그다(UI05-03)."""
    return task["status"] != "COMPLETED" and parse_at(clock) > parse_at(task["due_at"])


# ─────────────────────────── 인계 (UI06) ───────────────────────────


def handoff_conditions(doc: dict, run_id: str) -> dict[str, Any]:
    """장면 완료 조건별 참·거짓과 미충족 이유(GET /issues/{id}/handoff)."""
    run = doc["calc_runs"].get(run_id)
    source = doc["sources"].get(run["source_id"]) if run else None
    review = doc["reviews"].get(run_id)
    required = ["PROD", "MAT"]
    if run and (_top_risk(run) == Risk.CRITICAL.value or (review or {}).get("manual_review")):
        required.append("FIN")
    tasks = {t: doc["tasks"].get(f"TASK-{t}") for t in required}
    accepted = {
        t: bool(x and x["assigned_to"] and x["accepted_by"] and x["accepted_at"])
        for t, x in tasks.items()
    }
    blocked = any(
        s["status"] == "NEEDS_INFO"
        for s in doc["sources"].values()
        if run and s["source_id"] == run["source_id"]
    )
    conditions = {
        "valid_evidence": bool(
            run and run["status"] == "SUCCEEDED" and source and source["status"] == "VERIFIED"
        ),
        "sales_reviewed": bool(review and review.get("opinion") and review.get("evidence")),
        "follow_ups_accepted": all(accepted.values()),
        "not_blocked": not blocked,
    }
    reasons = [f"TASK-{t} 미인수" for t, ok in accepted.items() if not ok]
    if not conditions["valid_evidence"]:
        reasons.append("확인된 원천·성공한 계산이 연결되지 않았다")
    if not conditions["sales_reviewed"]:
        reasons.append("영업 검토 의견·근거 없음")
    if blocked:
        reasons.append("미해결 데이터 오류")
    return {
        "run_id": run_id,
        "required": required,
        "accepted": accepted,
        "conditions": conditions,
        "met": all(conditions.values()),
        "reasons": reasons,
    }


def _top_risk(run: dict) -> str:
    changed = [r for r in run["results"] if r["metrics"]["M01"]["value"] not in (None, "0")]
    order = [r.value for r in _RISK_ORDER]
    levels = [r["risk"] for r in changed if r["risk"]]
    return max(levels, key=order.index, default=Risk.NORMAL.value)


def hand_off(doc: dict, run_id: str) -> bool:
    """조건을 다시 확인하고 SCENE_HANDED_OFF를 **한 번만** 남긴다."""
    check = handoff_conditions(doc, run_id)
    if not check["met"]:
        raise DomainError("인계 조건 미충족: " + ", ".join(check["reasons"]), 409)
    if doc["handoff"] and doc["handoff"]["run_id"] == run_id:
        return True
    doc["handoff"] = {"run_id": run_id, "at": doc["clock"]}
    doc["scene"] = "HANDED_OFF"
    audit(doc, actor="system", action="SCENE_HANDED_OFF", run_id=run_id)
    return True
