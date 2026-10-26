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
import re
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

#: 시연 사용자 마스터 — 가상 인물이다. 역할은 구현명세 2장 표. 장면 1·2가 같은 가상 회사를 쓴다.
USERS: dict[str, dict[str, str]] = {
    "u-sales": {"name": "이도윤", "role": "영업담당"},
    "u-sales-lead": {"name": "박서진", "role": "영업팀장"},
    "u-prod": {"name": "김태오", "role": "생산담당"},
    "u-mat": {"name": "최유나", "role": "자재담당"},
    "u-fin": {"name": "정하윤", "role": "경영관리담당"},
    "u-plant": {"name": "한준호", "role": "공장장"},
    # 장면 2(SC02) — 구매 승인선. 구매담당·팀장·임원·대표는 서로 다른 사람이다(AUTH-03).
    # 원가 등록(ROLE-COST)은 Pilot에서 구매담당이 겸한다(구현명세 2장).
    "u-buy": {"name": "윤채원", "role": "구매담당"},
    "u-buy-lead": {"name": "서도현", "role": "구매팀장"},
    "u-buy-exec": {"name": "문지후", "role": "구매임원"},
    "u-ceo": {"name": "임하준", "role": "대표이사"},
    "u-demo": {"name": "시연관리자", "role": "시연관리자"},
}


class DomainError(Exception):
    """업무 규칙 위반. `status`는 API가 그대로 쓴다(API-03: 403·404·409·422)."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def user_id_of(value: str) -> str:
    """사용자 id 또는 **이름**을 id로. Chaeksas 결재 담당자·답한 사람은 이름이다(ADR-0080)."""
    if value in USERS:
        return value
    found = next((uid for uid, u in USERS.items() if u["name"] == value), None)
    if found is None:
        raise DomainError(f"모르는 사용자: {value}", 422)
    return found


def name_of(user_id: str) -> str:
    return USERS[user_id]["name"]


def user_for_role(role: str) -> str:
    """그 역할의 사용자 — SC01 가상 회사는 역할마다 한 사람이다."""
    return next(uid for uid, u in USERS.items() if u["role"] == role)


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


def ordered(records: dict[str, dict]) -> list[dict]:
    """
    기록을 **만든 순서**로 돌려준다(`seq`). 딕셔너리의 키 순서에 기대면 안 된다 — Postgres JSONB는
    키를 길이·바이트 순으로 다시 정렬해 저장한다. 운영계에서 업무 목록이 DQ·FIN·MAT·PROD·SALES로
    나왔다(SQLite는 넣은 순서라 로컬에서는 안 보였다).
    """
    return sorted(records.values(), key=lambda r: r.get("seq", 0))


def issue_id_for(model_id: str, period: date) -> str:
    return f"ISSUE-{model_id[-1].upper()}{period.month:02d}"


#: 시연 사례 → Agent 모드. EX08은 Agent 응답 실패를 재현한다(나머지 업무는 그대로 진행된다).
CASES = {"BASE": None, "EX08": "fail"}
#: BPMN을 누가 도는가(docs/chaeksas-integration.md §4·N2). 내장이 아니면 엔진은 이 문서에서 step하지
#: 않는다 — 바깥 실행의 진행은 그 실행이 부르는 작업으로만 안다.
EXECUTORS = ("embedded", "studio", "center")
#: 바깥 실행 위치의 이름 — 사유 문구에 쓴다.
EXECUTOR_LABEL = {"studio": "Studio 시험 실행", "center": "Center 서버 실행"}
#: 바깥 실행에 묶인 데모 실행에서 화면 조작이 거절될 때의 사유 — 어디서 답하는지 말한다.
ANSWER_ELSEWHERE = {
    "studio": "이 데모 실행은 Studio 시험 실행이 돈다 — 결재는 Studio에서 답하라",
    # center는 화면 답이 대리 답이다(N3) — 대리 답용 키가 없을 때만 이 사유를 앞에 붙여 503이다.
    "center": "이 데모 실행은 Center 서버 실행이 돈다 — 결재는 Center 결재함에서 답하라",
}


def new_demo_run(
    seed: Seed,
    demo_run_id: str,
    *,
    case_id: str,
    created_at: datetime,
    agent_mode: str = "mock",
    executor: str = "embedded",
) -> dict:
    """
    S0 — 기준 적재(2027-06-15 18:00). 승인 전망 F01과 기존 관심 이슈 A07·B07만 있다.
    CP02·F02는 아직 없다(AT01). 8·9월 관심 평가는 평가 결과일 뿐 이슈로 만들지 않는다(UI01-04).

    `executor`가 내장이 아니면 `bpm`을 처음부터 둔다 — 실행 위치는 데모 실행을 만들 때 정하고,
    바깥 실행 id는 첫 작업 호출에서 묶인다(`link_external_run`).
    """
    if executor not in EXECUTORS:
        raise DomainError(f"모르는 실행 위치: {executor} (가능: {', '.join(EXECUTORS)})", 422)
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
                "seq": 0,  # 기준 적재 — 비교 결과가 아니다
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
        "bpm": None if executor == "embedded" else external_bpm(executor),
        "agent_mode": CASES.get(case_id) or agent_mode,
        "agent_outputs": {},
        "alerts": [],
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
    earlier = ordered(doc["sources"])
    corrects = next(
        (s["source_id"] for s in earlier if s["customer_plan_id"] == plan_id), None
    ) or (earlier[0]["source_id"] if earlier else None)
    doc["sources"][sid] = {
        "source_id": sid,
        "seq": len(doc["sources"]) + 1,
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
        "seq": len(doc["forecasts"]) + 1,
        "source_id": source_id,
        "approval": "UNDER_REVIEW",  # 공식 승인 API는 SC01 범위 밖이다
        "created_at": doc["clock"],
        "quantities": _qty_rows(latest),
    }
    keys = sorted(r.key for r in rows)
    results = assess_all(keys, seed.plans["T01"], seed.plans["F01"], latest, seed)
    doc["calc_runs"][run_id] = {
        "run_id": run_id,
        "seq": len(doc["calc_runs"]),
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


def tasks_of(doc: dict, task_type: str) -> list[dict]:
    """그 종류의 업무를 만든 순서로 — 마지막이 가장 최근의 재검토 업무다."""
    return [t for t in ordered(doc["tasks"]) if t["type"] == task_type]


def active_task(doc: dict, task_type: str) -> dict | None:
    """그 종류의 **활성** 업무(완료 전). 같은 대상에 활성 업무는 하나뿐이다(WF-02)."""
    return next((t for t in reversed(tasks_of(doc, task_type)) if t["status"] != "COMPLETED"), None)


def latest_task(doc: dict, task_type: str) -> dict | None:
    found = tasks_of(doc, task_type)
    return found[-1] if found else None


def sync_tasks(doc: dict, pendings: dict[str, dict[str, Any]], variables: dict[str, Any]) -> None:
    """
    BPM의 사람 대기를 업무 기록으로 옮긴다. 대기가 생긴 시각이 배정 시각이다.

    * 같은 종류의 **활성** 업무가 있으면 새로 만들지 않고 이어 쓴다(WF-02). 보완 뒤 다시 배정돼도
      최초 배정 시각과 원래 기한은 보존한다(설계서 1.9).
    * 정정으로 새 계산이 생겼는데 이미 인수한 업무면 **새 근거를 붙이고 재확인을 요청한다** — 이전
      인수 이력은 지우지 않는다. 새 run에 대한 인수가 끝나야 최신 인계가 성립한다(WF-02).
    * **완료된 업무는 다시 쓰지 않는다.** 같은 종류의 대기가 또 오면 연결된 재검토 업무를 새로
      만든다(WF-03) — TASK-DQ가 끝났으면 TASK-DQ-2.
    """
    run_id = variables.get("계산ID") or None
    # 한 번에 여러 업무가 생기면(생산·자재) BPMN 노드 순서로 만든다 — 스냅샷 키 순서가 아니다.
    nodes = list(NODE_ROLES)
    by_node = sorted(
        pendings.items(),
        key=lambda kv: nodes.index(kv[1]["node_id"]) if kv[1]["node_id"] in nodes else len(nodes),
    )
    for request_id, p in by_node:
        spec = NODE_ROLES.get(p["node_id"])
        if spec is None or spec["task"] is None:
            continue
        task = active_task(doc, spec["task"])
        if task is not None and task["request_id"] == request_id:
            continue
        assignee = variables.get(spec.get("assignee_var", ""), "") or DEFAULT_ASSIGNEE.get(
            spec["role"]
        )
        if task is None:
            previous = latest_task(doc, spec["task"])
            count = len(tasks_of(doc, spec["task"]))
            task_id = f"TASK-{spec['task']}" + (f"-{count + 1}" if count else "")
            assigned = parse_at(doc["clock"])
            doc["tasks"][task_id] = {
                "task_id": task_id,
                "seq": len(doc["tasks"]) + 1,
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
                "run_id": run_id,
                "runs": [run_id] if run_id else [],
                "acks": [],
                "reconfirm": False,
                "reopens": previous["task_id"] if previous else None,
                "issue_id": variables.get("이슈ID") or None,
                "source_id": variables.get("원천ID"),
                "history": [
                    {
                        "at": doc["clock"],
                        "status": "ASSIGNED",
                        "by": "system",
                        "note": f"{previous['task_id']}의 재검토" if previous else None,
                    }
                ],
            }
            audit(
                doc, actor="system", action="task_assigned", task_id=task_id, assigned_to=assignee
            )
            continue

        task.update(request_id=request_id, node_id=p["node_id"], source_id=variables.get("원천ID"))
        # 보완 뒤가 아니면 같은 결재가 다시 열린 것이다 — 결정 기록이 거절돼 되돌아왔다(N1).
        note = "보완 후 재배정" if task["status"] == "NEEDS_INFO" else "같은 결재가 다시 열림"
        if run_id and run_id != task["run_id"]:
            task["run_id"] = run_id
            task["runs"].append(run_id)
            note = f"새 근거 {run_id}"
            if task["status"] == "IN_PROGRESS":
                task["reconfirm"] = True
                note += " — 재확인 요청"
        if task["status"] == "NEEDS_INFO":
            task["status"] = "ASSIGNED"
        task["history"].append(
            {"at": doc["clock"], "status": task["status"], "by": "system", "note": note}
        )


def task_for_node(doc: dict, node_id: str) -> dict | None:
    spec = NODE_ROLES.get(node_id)
    return active_task(doc, spec["task"]) if spec and spec["task"] else None


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
    ack = {"run_id": task["run_id"], "by": actor, "at": at}
    if outcome == "accepted" and task["reconfirm"]:
        # 재확인 — 상태는 그대로 진행 중이고 새 근거에 대한 확인만 남긴다.
        task["reconfirm"] = False
        task["acks"].append(ack)
        outcome, note = "reconfirmed", note or f"{task['run_id']} 재확인"
    elif outcome == "accepted":
        task.update(status="IN_PROGRESS", accepted_by=actor, accepted_at=at)
        task["acks"].append(ack)
    elif outcome == "completed":
        task.update(
            status="COMPLETED",
            completed_at=at,
            accepted_by=task["accepted_by"] or actor,
            accepted_at=task["accepted_at"] or at,
        )
        task["acks"].append(ack)
    elif outcome == "needs_info":
        task.update(status="NEEDS_INFO")
    task["history"].append({"at": at, "status": task["status"], "by": actor, "note": note})
    audit(doc, actor=actor, action=f"task_{outcome}", task_id=task["task_id"])


#: 기한 초과 알림을 받는 기능별 검토자(UI05-03). 생산·자재는 공장장, 원천 확인과 손익분석 요청은
#: 요청한 영업팀장이다. 영업 검토 자체의 상위 검토자는 권한표가 미정이다(설계서 1.8)
#: — 담당자만 받는다.
REVIEWER = {
    "DQ": "u-sales-lead",
    "SALES": None,
    "PROD": "u-plant",
    "MAT": "u-plant",
    "FIN": "u-sales-lead",
}


def raise_overdue_alerts(doc: dict) -> list[dict]:
    """
    가상시계가 기한을 넘기면 담당자와 기능별 검토자에게 화면 내 알림을 만든다(UI05-03·EX07).
    같은 업무·기한에는 한 번만 만든다. 이메일·메신저는 범위 밖이다.
    """
    alerts = doc.setdefault("alerts", [])
    seen = {(a["task_id"], a["due_at"]) for a in alerts}
    created = []
    for task in ordered(doc["tasks"]):
        if not overdue(task, doc["clock"]) or (task["task_id"], task["due_at"]) in seen:
            continue
        unaccepted = task["status"] == "ASSIGNED"
        alert = {
            "alert_id": f"ALERT-{len(alerts) + 1:03d}",
            "kind": "OVERDUE",
            "task_id": task["task_id"],
            "due_at": task["due_at"],
            "at": doc["clock"],
            "to": [u for u in (task["assigned_to"], REVIEWER.get(task["type"])) if u],
            "unaccepted": unaccepted,
            "message": f"{task['task_id']} 기한({task['due_at'][5:16].replace('T', ' ')}) 초과"
            + (" — 미인수" if unaccepted else " — 미완료"),
        }
        alerts.append(alert)
        created.append(alert)
        audit(doc, actor="system", action="overdue_alert", task_id=task["task_id"], to=alert["to"])
    return created


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
    # 최신 run에 대한 인수 확인이 있어야 한다 — 정정 전의 인수만으로는 최신 인계가 아니다(WF-02).
    tasks = {t: latest_task(doc, t) for t in required}
    accepted = {
        t: bool(x and x["assigned_to"] and any(a["run_id"] == run_id for a in x["acks"]))
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
    reasons = [
        f"{(tasks[t] or {}).get('task_id', 'TASK-' + t)} "
        + ("재확인 대기" if tasks[t] and tasks[t]["acks"] else "미인수")
        for t, ok in accepted.items()
        if not ok
    ]
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


# ─────────────────────────── 실행 위치 (N2) ───────────────────────────


def external_bpm(executor: str) -> dict:
    """
    바깥 실행의 자리. 스냅샷이 없다 — 대기·토큰은 바깥에 있다(§4 「진행 읽기」). Studio는 작업
    호출이 알려 준 노드(`visited`)만 안다. Center는 실행 기록(C3)을 폴링해 사람 대기(`waiting`)·
    토큰 위치(`position`)까지 채운다(N3) — `center`가 그 장부다.
    """
    bpm = {
        "executor": executor,
        "external_run_id": None,
        "run_id": None,
        "state": "not_started",
        "snapshot": None,
        "visited": [],
        "position": [],
        "waiting": [],
        "error": None,
    }
    if executor == "center":
        bpm["center"] = new_center_ledger()
    return bpm


def new_center_ledger() -> dict:
    """
    Center 실행의 장부(N3). `job` — NowView가 기동한 작업(C5). `last_seq` — 읽은 실행 기록의 끝.
    `relayed` — NowView가 대리 답한 결재 id: Center 기록에 `human_answered`가 오기 전까지 대기로
    다시 보이지 않게 한다. `problem` — 연동 설정이 없거나 Center가 거절한 사유(조용히
    넘어가지 않는다).
    """
    return {"job": None, "last_seq": 0, "relayed": [], "problem": None}


def executor_of(doc: dict) -> str:
    return (doc["bpm"] or {}).get("executor", "embedded")


def link_external_run(doc: dict, run_id: str | None, *, via: str | None = None) -> None:
    """
    바깥 작업 호출의 `run_id`(Chaeksas `{{run_id}}`)로 데모 실행과 바깥 실행을 묶는다.

    처음 오면 묶고, 같으면 지나가고, 다르면 409다 — 한 문서에서 두 실행이 업무를 적으면 누가 무엇을
    했는지 갈라 볼 수 없다. 정정(EX03)으로 대체된 실행은 `bpm_history`에 있고 그 뒤 새 실행이 묶인다
    (`receive_external`).

    `via`는 호출에 실린 키가 말하는 실행 위치다(N6 — 시험용 키면 studio, 운영 키면 center). 데모
    실행의 선언과 다르면 409다 — Studio 시험 실행이 Center용 데모 실행에 업무를 적게 된다.
    """
    executor = executor_of(doc)
    if executor == "embedded":
        raise DomainError(
            "이 데모 실행은 내장 BPM이 돈다 — 바깥 실행은 실행 위치를 studio·center로 만든 "
            "데모 실행에서 돌려라",
            409,
        )
    if via is not None and via != executor:
        raise DomainError(
            f"{EXECUTOR_LABEL[via]} 키로 왔는데 이 데모 실행은 "
            f"{EXECUTOR_LABEL[executor]}용이다 — 실행 위치를 맞춰 다시 만들어라",
            409,
        )
    if not run_id:
        raise DomainError(
            "바깥 실행 id(chaeksas_run_id)가 없다 — 확장 정의 0.3.0 이상이 필요하다", 422
        )
    bpm = doc["bpm"]
    if bpm["external_run_id"] == run_id:
        return
    if any(h["run_id"] == run_id for h in doc.get("bpm_history", [])):
        raise DomainError(f"정정본 수신으로 대체된 실행이다: {run_id}", 409)
    if bpm["external_run_id"] is not None:
        raise DomainError(
            f"이 데모 실행은 이미 바깥 실행 {bpm['external_run_id']}에 묶였다 (받은 값: {run_id})",
            409,
        )
    bpm.update(external_run_id=run_id, run_id=run_id, state="running")
    audit(doc, actor="system", action="external_run_linked", run_id=run_id, executor=executor)


def note_external_progress(
    doc: dict, node_id: str | None, *, decided: str | None = None, done: bool = False
) -> None:
    """
    작업을 부른 노드(`{{node_id}}`)를 지나온 노드에 쌓는다. 기록 작업이면 그 앞의 결재(`decided`)도
    지나왔다. 인계가 끝나면 흐름이 끝난 것으로 본다 — 인계 태스크 다음은 종료 이벤트뿐이다.

    토큰 위치(`position`)는 비워 둔다 — 작업 호출이 끝난 순간 토큰은 이미 다음으로 갔고, 어디로
    갔는지는 바깥만 안다. 「방금 부른 노드」를 진행 중으로 칠하면 틀린 그림이다.
    """
    bpm = doc["bpm"]
    for nid in (decided, node_id):
        if nid and nid not in bpm["visited"]:
            bpm["visited"].append(nid)
    if done:
        bpm["state"] = "done"


def receive_external(doc: dict, source_id: str) -> None:
    """
    바깥 실행에 묶인 데모 실행의 원천 수신 — **BPM을 시작하지 않는다**(시작은 Studio·Center가 한다).

    이미 묶인 실행이 있으면 내장과 같은 갈래다: 보완 대기 중이면 같은 실행이 정정본을 받아 다시
    검증하고(Studio에서 「원천정정」 메시지를 보낸다), 그 밖이면 이전 실행을 이력으로 옮긴다 — 그
    실행의 남은 작업 호출은 409로 막히고, 다음에 오는 새 run_id가 묶인다.
    """
    bpm = doc["bpm"]
    if bpm["external_run_id"] is None:
        return
    # 보완 대기인지는 **바로 앞 원천**으로 본다 — 실행이 다루던 것이다. `corrects`는 같은
    # 고객계획의 첫 원천을 가리켜, 보완 → 정정 → 확인 뒤의 또 다른 정정본을 보완 대기로
    # 오인했다(N3에서 드러남).
    earlier = [s for s in ordered(doc["sources"]) if s["source_id"] != source_id]
    if earlier and earlier[-1]["status"] == "NEEDS_INFO":
        return
    supersede_bpm(doc, source_id=source_id, final_state="superseded")


# ─────────────────────────── 고객계획 접수 가상 직원 (N5) ───────────────────────────

#: 접수 Bot을 깨우는 메시지 — `sc01-intake.bpmn`의 메시지 시작 이름이다.
INTAKE_MESSAGE = "고객계획접수"
INTAKE_DECISIONS = ("승인", "반려")


def change_summary(doc: dict, seed: Seed, source_id: str) -> list[dict[str, Any]]:
    """
    직전 원천(시드 CP01) 대비 바뀐 행 — 일괄 결재가 보이는 「변경 요약」이다. UI02의 원천 비교와
    같은 기준이고(CP01 → 수신본), 전망 비교(F01 → F02)가 아니다(UI02-02). 누락은 `None` 그대로다.
    """
    before = {(r.model_id, r.period.isoformat()): r.quantity for r in seed.customer_plans["CP01"]}
    out = []
    for r in doc["sources"][source_id]["rows"]:
        prior = before.get((r["model_id"], r["period"]))
        if prior != r["quantity"]:
            out.append(
                {"model": r["model_id"], "period": r["period"], "from": prior, "to": r["quantity"]}
            )
    return out


def note_processor(doc: dict, name: str) -> None:
    """
    위임된 SC01이 실어 온 처리자(가상 직원 이름, SC01 입력 `처리자`)를 그 실행에 남긴다 — 화면이
    「접수 가상 직원이 기동한 실행」이라고 말한다. 혼자 기동한 SC01은 `None`이라 여기 오지 않는다.
    """
    bpm = doc["bpm"]
    if bpm is None or bpm.get("processed_by") == name:
        return
    bpm["processed_by"] = name
    audit(
        doc, actor="system", action="processed_by_virtual_worker", name=name, run_id=bpm["run_id"]
    )


def screen_source(
    doc: dict, seed: Seed, source_id: str, *, processed_by: str | None
) -> dict[str, Any]:
    """
    접수 Bot의 원천 검증 — SC01의 자동 검증과 같은 검사(`validate_source`)에 변경 요약을 붙여 일괄
    결재에 보인다. **데모 실행을 바깥 실행에 묶지 않는다** — 묶는 것은 위임된 SC01의 첫 호출이다.
    """
    errors = validate_source(doc, seed, source_id)
    s = doc["sources"][source_id]
    summary = {
        "원천ID": source_id,
        "고객계획": s["customer_plan_id"],
        "검증통과": not errors,
        "검증오류수": len(errors),
        "검증오류": [f"{e['row']} {e['message']}" for e in errors][:5],
        "변경": change_summary(doc, seed, source_id),
    }
    s["screened_by"] = processed_by
    return summary


def record_intake(
    doc: dict,
    source_id: str,
    *,
    decision: str,
    opinion: str,
    by: str,
    how: dict[str, Any],
    intake_run: str | None,
    processed_by: str | None,
) -> None:
    """
    감독자의 일괄 결정(N5). **반려면 SC01을 시작하지 않는다** — 원천을 NEEDS_INFO로 두고 영업담당의
    원천 확인 업무(TASK-DQ)를 보완 요청 상태로 연다. 정정본이 와서 다시 승인되면 위임된 SC01의 원천
    확인이 같은 업무를 「보완 후 재배정」으로 잇는다(`sync_tasks`). 승인이면 감사 이력만 남긴다 —
    업무는 SC01의 원천 확인 결재가 열 때 생긴다.
    """
    if decision not in INTAKE_DECISIONS:
        raise DomainError(f"접수 결정은 {'·'.join(INTAKE_DECISIONS)} 중 하나다: {decision}", 422)
    if source_id not in doc["sources"]:
        raise DomainError(f"없는 원천: {source_id}", 404)
    if decision == "반려" and not opinion.strip():
        raise DomainError("반려에는 보완할 내용(의견)이 필요하다", 422)
    ledger = ((doc["bpm"] or {}).get("center")) or {}
    job = ledger.get("job") or {}
    if job.get("via") == "intake" and job.get("source_id") == source_id:
        job["decision"] = decision
    audit(
        doc,
        actor=by,
        action="intake_reviewed",
        source_id=source_id,
        decision=decision,
        opinion=opinion,
        intake_run=intake_run,
        processed_by=processed_by,
        **how,
    )
    if decision == "승인":
        return
    request_fix(doc, source_id, actor=by, opinion=opinion)
    sync_tasks(
        doc,
        {f"intake:{intake_run}:{source_id}": {"node_id": "Approve_DQ"}},
        {"원천ID": source_id},
    )
    mark_task(
        doc,
        "Approve_DQ",
        actor=by,
        outcome="needs_info",
        note=f"접수 일괄 반려 — 보완 요청: {opinion}",
    )


# ─────────────────────────── 정정 (EX03·WF-03) ───────────────────────────


def supersede_bpm(doc: dict, *, source_id: str, final_state: str) -> None:
    """
    진행 중이거나 끝난 BPM 실행을 새 원천의 실행으로 대체한다. **이전 실행·인계는 지우지 않는다** —
    이력으로 옮긴다. 끝난 장면의 인계 기록은 역사로 남고 최신 run의 장면은 다시 ACTIVE다(WF-03).
    """
    old = doc["bpm"]
    doc.setdefault("bpm_history", []).append(
        {
            "run_id": old["run_id"],
            "executor": old.get("executor", "embedded"),
            "state": final_state,
            "visited": old.get("visited", []),
            "superseded_at": doc["clock"],
            "by_source": source_id,
        }
    )
    # 이전 실행에서 기다리던 업무는 새 계산이 그 지점에 닿을 때 새 근거로 이어진다 — 표시만 남긴다.
    # 바깥 실행은 스냅샷이 없다 — 업무가 기록 때 열리고 곧바로 닫히므로 기다리던 업무가 없다.
    waiting = {p["request_id"] for p in (old["snapshot"] or {"pendings": {}})["pendings"].values()}
    for task in doc["tasks"].values():
        if task["request_id"] in waiting and task["status"] != "COMPLETED":
            task["history"].append(
                {
                    "at": doc["clock"],
                    "status": task["status"],
                    "by": "system",
                    "note": f"정정본 {source_id} 수신 — 새 계산 대기",
                }
            )
    if doc.get("handoff"):
        doc.setdefault("handoff_history", []).append(doc["handoff"])
        doc["handoff"] = None
    executor = old.get("executor", "embedded")
    doc["bpm"] = None if executor == "embedded" else external_bpm(executor)
    audit(doc, actor="system", action="bpm_superseded", old_run=old["run_id"], source_id=source_id)


# ─────────────────────────── Agent 초안 (AG-01~03) ───────────────────────────


def request_agent(
    doc: dict,
    run_id: str,
    *,
    payload: dict,
    payload_hash: str,
    mode: str,
    actor: str,
    manual: bool,
    now_real: str,
) -> str:
    """
    초안 요청을 기록하고 작업 대기열(저장하지 않는 `_agent_queue`)에 올린다.

    자동 요청(계산 직후)은 같은 입력 해시의 성공한 초안이 있으면 재사용한다(AG-02). 담당자의
    재생성 요청은 항상 새로 만든다 — 이전 초안은 보존한다.
    """
    outputs = doc.setdefault("agent_outputs", {})
    if not manual:
        for out in ordered(outputs):
            if out["input_hash"] == payload_hash and out["status"] == "SUCCEEDED":
                return out["output_id"]
    output_id = f"AGT-{len(outputs) + 1:03d}"
    outputs[output_id] = {
        "output_id": output_id,
        "seq": len(outputs) + 1,
        "run_id": run_id,
        "status": "RUNNING",
        "mode": mode,
        "prompt_version": None,
        "input_hash": payload_hash,
        "input": payload,
        "requested_by": actor,
        "requested_at": doc["clock"],
        "requested_real": now_real,
        "finished_real": None,
        "attempts": 0,
        "provenance": None,
        "model": None,
        "latency_ms": None,
        "draft": None,
        "errors": [],
        "adopted_by": None,
        "adopted_at": None,
    }
    doc.setdefault("_agent_queue", []).append(output_id)
    audit(
        doc,
        actor=actor,
        action="agent_requested",
        output_id=output_id,
        run_id=run_id,
        manual=manual,
    )
    return output_id


def finish_agent(doc: dict, output_id: str, *, result: dict) -> bool:
    """작업 결과를 기록한다. 이미 끝난 기록(다른 워커·초기화)이면 덮지 않는다."""
    out = doc.get("agent_outputs", {}).get(output_id)
    if out is None or out["status"] != "RUNNING":
        return False
    out.update(result)
    audit(
        doc,
        actor="system",
        action=f"agent_{out['status'].lower()}",
        output_id=output_id,
        attempts=out["attempts"],
    )
    return True


def adopt_agent(doc: dict, output_id: str, *, actor: str) -> None:
    """초안 채택 기록(AG-03). 원본 초안은 그대로 두고 누가 언제 가져다 썼는지만 남긴다."""
    out = doc.get("agent_outputs", {}).get(output_id)
    if out is None:
        raise DomainError(f"없는 초안: {output_id}", 404)
    if out["status"] != "SUCCEEDED":
        raise DomainError("검증을 통과한 초안만 채택할 수 있다", 409)
    out.update(adopted_by=actor, adopted_at=doc["clock"])
    audit(doc, actor=actor, action="agent_adopted", output_id=output_id)


# ─────────────────────────── 멱등키 (API-01·AT13) ───────────────────────────


def check_idempotency(doc: dict, key: str | None, body: Any) -> bool:
    """
    같은 키 + 같은 본문이면 True(이미 처리됨 — 다시 실행하지 않는다), 같은 키 + 다른 본문이면 409.
    타임아웃 뒤 재요청이 두 번 실행되지 않게 한다(API-03).
    """
    if not key:
        return False
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    seen = doc.setdefault("idempotency", {})
    if key in seen:
        if seen[key] != digest:
            raise DomainError("같은 멱등키로 다른 요청을 보냈다", 409)
        return True
    seen[key] = digest
    return False


# ─────────────────────────── 문서 형식 ───────────────────────────


def _digits(text: str) -> int:
    found = re.findall(r"\d+", text)
    return int(found[-1]) if found else 0


def upgrade(doc: dict) -> dict:
    """
    이전 형식의 문서(Agent·정정·알림 이전)를 읽을 수 있게 채운다. 저장된 데모 실행을 버리지 않는다 —
    로컬·운영 DB에 남은 실행으로 조작하면 KeyError로 500이 났다.
    """
    doc.setdefault("agent_mode", "mock")
    doc.setdefault("agent_outputs", {})
    doc.setdefault("alerts", [])
    # 실행 위치(N2) 이전 문서는 전부 내장 실행이다.
    if doc.get("bpm") is not None:
        doc["bpm"].setdefault("executor", "embedded")
        doc["bpm"].setdefault("external_run_id", None)
        doc["bpm"].setdefault("waiting", [])
        if doc["bpm"]["executor"] == "center":
            doc["bpm"].setdefault("center", new_center_ledger())
    for old in doc.get("bpm_history", []):
        old.setdefault("executor", "embedded")
    # 순번(`seq`) 이전에 저장된 문서 — id의 숫자와 배정 시각으로 만든 순서를 되살린다.
    for name, key in (
        ("sources", lambda r: _digits(r["source_id"])),
        ("forecasts", lambda r: _digits(r["version_id"])),
        ("calc_runs", lambda r: _digits(r["run_id"].split("-")[1])),
        ("agent_outputs", lambda r: _digits(r["output_id"])),
        ("tasks", lambda r: (r["assigned_at"], _digits(r["task_id"]) or 1, r["task_id"])),
    ):
        records = doc.get(name, {})
        if any("seq" not in r for r in records.values()):
            for i, r in enumerate(sorted(records.values(), key=key)):
                r["seq"] = i + 1
    if "RUN-F01-001" in doc.get("calc_runs", {}):
        doc["calc_runs"]["RUN-F01-001"]["seq"] = 0
    for task in doc.get("tasks", {}).values():
        task.setdefault("runs", [task["run_id"]] if task.get("run_id") else [])
        task.setdefault(
            "acks",
            [{"run_id": task.get("run_id"), "by": task["accepted_by"], "at": task["accepted_at"]}]
            if task.get("accepted_at")
            else [],
        )
        task.setdefault("reconfirm", False)
        task.setdefault("reopens", None)
    return doc
