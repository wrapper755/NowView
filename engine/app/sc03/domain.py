"""
SC03 업무 기록 — 수익성 변동의 통합 분석과 수시 경영검토(MR-2706-01).

장면 1·2와 같은 원칙이다: **한 데모 실행 = 문서 하나**, 순수 함수, 저장·BPM은 `process.py`. 데모
실행
id는 장면 1·2와 같다. 장면 3은 **장면 2 인계 결과에서 시작한다**(P33) — 그 결과는 시작할 때 스냅샷
(`sc02`)으로 둔다. 장면 2를 초기화해도 장면 3의 근거는 그 시점의 것이다.

**상태 축은 서로 독립이다**(구현명세 10장): 검토건 상태(`review.state`) · 검토
결론(`review.outcome`) ·
계산·보고·회신·과제 각자의 상태 · Risk(OPEN) · Forecast(REVIEW_PENDING) · Target(UNCHANGED). 장면을
끝내도
위험·전망·목표는 바뀌지 않는다(P37) — 이벤트의 결과 상태로 검토건 상태를 덮지 않는다.

* 확정 보고서·회의록·완료 인계는 **고치지 않는다**. 바뀌면 새 버전이다(CT36·CT40).
* 업무 효과는 결재 뒤의 「… 기록」 작업이 낸다(장면 1·2 N1과 같다). 각 작업은 **검사가 부수 효과보다
  먼저**다 — `check(doc, operation, args)`가 같은 규칙을 화면 답의 사전 검사와 기록 작업 양쪽에서
  건다.
* 사람의 결론·판단·인수는 사람만 한다. 시스템은 계산·근거 연결·이력, Agent는 초안까지다(P39).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.sc01.domain import (
    EXECUTORS,
    KST,
    USERS,
    DomainError,
    audit,
    due_at,
    external_bpm,
    name_of,
    ordered,
    parse_at,
    user_for_role,
    user_id_of,
)
from app.sc02.calc import Option
from app.sc03 import agent, calc
from app.sc03.seed import SEED_ID, Seed, kst

REVIEW_ID = "MR-2706-01"
VOLUME_ISSUE_ID = "ISSUE-B07"
COST_ISSUE_ID = "ISSUE-COST01"
MEETING_ID = "MT31"
NEXT_MEETING_ID = "MT41"
HANDOFF_ID = "HANDOFF31"

FIN, CFO, FINLEAD = "u-fin", "u-fin-exec", "u-fin-lead"
SALES, BUY, PROD = "u-sales-lead", "u-buy-lead", "u-prod-lead"

#: 부서 확인(S34~S36) — 자기 부서만 회신을 확정한다(U33). 무응답은 동의가 아니다.
DEPTS: dict[str, dict[str, str]] = {
    "SALES": {"label": "영업", "user": SALES, "node": "Confirm_Sales"},
    "BUY": {"label": "구매", "user": BUY, "node": "Confirm_Buy"},
    "PROD": {"label": "생산", "user": PROD, "node": "Confirm_Prod"},
}
#: MT31 참석(SC03회의 ATT31-1~6). 품질·대표는 넣지 않는다(구현명세 2장 — 자동 삽입 금지).
ATTENDEES = (CFO, FIN, PROD, BUY, SALES, FINLEAD)
#: 분석과제 → 책임자 노드(인수·재배정). 과제 id는 데이터 그대로다(AT31~AT34).
TASK_NODES = {
    "AT31": ("Accept_AT31", "Reassign_AT31"),
    "AT32": ("Accept_AT32", "Reassign_AT32"),
    "AT33": ("Accept_AT33", "Reassign_AT33"),
    "AT34": ("Accept_AT34", "Reassign_AT34"),
}


def _at(y: int, mo: int, d: int, h: int, mi: int = 0) -> str:
    return datetime(y, mo, d, h, mi, tzinfo=KST).isoformat()


#: 시연 일정(업무설계표 MT31·MT32, 구현명세 12장 CAL-DEMO01) — 2027년 가상 업무 일정이다.
SCHEDULE = {
    "confirm_due": _at(2027, 6, 28, 18),  # 부서 회신기한
    "freeze_at": _at(2027, 6, 29, 9),  # 자료 확정
    "meeting_at": _at(2027, 6, 29, 10),  # MT31 개회
    "meeting_end": _at(2027, 6, 29, 11),
    "accept_due": _at(2027, 6, 30, 12),  # 과제 인수기한
    "submit_due": _at(2027, 7, 6, 18),  # 분석 제출기한
    "consolidate_due": _at(2027, 7, 8, 18),  # 경영관리 취합
    "next_meeting_at": _at(2027, 7, 12, 10),  # MT41 대표 주재 월간회의
}

#: 시연 사례 — BASE와 E 사례는 **별도 데모 실행**이다(구현명세 13장: 기본 결과와 섞지 않는다).
#: E35(권한·필수값)는 엔진 시험으로 잠근다 — 실행 사례가 아니다.
CASES: dict[str, str] = {
    "BASE": "기본 시연",
    "E31": "E31 구매 이견 → 보완·재확인",
    "E32": "E32 AT31 반려 → 재배정·재인수",
    "E33": "E33 고정비 중복 — 계산 차단",
    "E34": "E34 자료 확정 뒤 새 전망 버전",
    "E36": "E36 Agent 초안 실패 → 수동 작성",
    "E37": "E37 완료 뒤 제출 지연 (7/6 18:01)",
}

#: BPMN 사람 노드 → 업무 종류·역할·기한. `due`는 SCHEDULE 키 또는 영업일 수다. 인수 노드의 담당은
#: 과제 책임자다(`owner_of`) — 역할표와 별개로 그 사람만 답한다.
NODE_ROLES: dict[str, dict[str, Any]] = {
    "Save_Analysis": {"task": "ANALYSIS", "role": "경영관리담당", "due": "analysis"},
    "Fix_Calc": {"task": "FIX_CALC", "role": "경영관리담당", "due": 1},
    "Request_Confirm": {"task": "REQUEST", "role": "경영관리담당", "due": 1},
    "Confirm_Sales": {"task": "CONFIRM_SALES", "role": "영업팀장", "due": "confirm"},
    "Confirm_Buy": {"task": "CONFIRM_BUY", "role": "구매팀장", "due": "confirm"},
    "Revise_Sales": {"task": "REVISE_SALES", "role": "경영관리담당", "due": "confirm"},
    "Revise_Buy": {"task": "REVISE_BUY", "role": "경영관리담당", "due": "confirm"},
    "Revise_Prod": {"task": "REVISE_PROD", "role": "경영관리담당", "due": "confirm"},
    "Confirm_Prod": {"task": "CONFIRM_PROD", "role": "생산팀장", "due": "confirm"},
    "Register_Gap": {"task": "GAP", "role": "경영관리팀장", "due": "confirm"},
    "Judge_Questions": {"task": "JUDGE", "role": "경영관리임원", "due": "freeze_at"},
    "Freeze_Report": {"task": "FREEZE", "role": "경영관리임원", "due": "freeze_at"},
    "Distribute": {"task": "DISTRIBUTE", "role": "경영관리담당", "due": "meeting_at"},
    "Report_Meeting": {"task": "REPORT", "role": "경영관리담당", "due": "meeting_end"},
    "Decide_Review": {"task": "DECIDE", "role": "경영관리임원", "due": "meeting_end"},
    "Confirm_Minutes": {"task": "MINUTES", "role": "경영관리임원", "due": 1},
    "Assign_Tasks": {"task": "ASSIGN", "role": "경영관리임원", "due": 1},
    "Accept_AT31": {
        "task": "ACCEPT_AT31",
        "role": "생산팀장",
        "due": "accept_due",
        "owner_of": "AT31",
    },
    "Accept_AT32": {
        "task": "ACCEPT_AT32",
        "role": "구매팀장",
        "due": "accept_due",
        "owner_of": "AT32",
    },
    "Accept_AT33": {
        "task": "ACCEPT_AT33",
        "role": "영업팀장",
        "due": "accept_due",
        "owner_of": "AT33",
    },
    "Accept_AT34": {
        "task": "ACCEPT_AT34",
        "role": "경영관리팀장",
        "due": "accept_due",
        "owner_of": "AT34",
    },
    "Reassign_AT31": {"task": "REASSIGN_AT31", "role": "경영관리임원", "due": "accept_due"},
    "Reassign_AT32": {"task": "REASSIGN_AT32", "role": "경영관리임원", "due": "accept_due"},
    "Reassign_AT33": {"task": "REASSIGN_AT33", "role": "경영관리임원", "due": "accept_due"},
    "Reassign_AT34": {"task": "REASSIGN_AT34", "role": "경영관리임원", "due": "accept_due"},
    "Complete_Scene": {"task": "COMPLETE", "role": "경영관리담당", "due": "accept_due"},
}
#: 기한 초과 알림을 함께 받는 사람 — 부서·과제는 경영관리 담당, 경영관리 업무는 임원.
REVIEWER = {"CONFIRM_SALES": FIN, "CONFIRM_BUY": FIN, "CONFIRM_PROD": FIN, "GAP": FIN}

DECISIONS = {
    "수용": "ACCEPTED",
    "조건부수용": "CONDITIONAL_ACCEPT",
    "보완후재검토": "REWORK_REQUIRED",
}
CANDIDATE_DECISIONS = {"상세분석": "INCLUDE", "이번제외": "EXCLUDE_THIS_REVIEW"}
CANDIDATES = ("C31", "C32", "C33", "C34", "C35", "C36")
QUESTION_SLOTS = ("Q31", "Q32")


class PrerequisiteError(DomainError):
    """완료 조건 미충족 — 누락 항목을 함께 낸다(구현명세 11장 「완료 실패 예시」)."""

    def __init__(self, message: str, items: list[str], code: str) -> None:
        super().__init__(message, 422)
        self.items = items
        self.code = code


def _hash(body: Any) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _seq(records: dict | list) -> int:
    return len(records) + 1


def _text(args: dict[str, Any], key: str) -> str:
    return str(args.get(key) or "").strip()


def _user(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return user_id_of(str(value))
    except DomainError:
        return None


def _when(value: Any, field: str) -> str:
    try:
        return parse_at(str(value).strip()).isoformat()
    except ValueError as exc:
        raise DomainError(f"{field}: 시각(ISO8601)이 아니다 — {value!r}", 422) from exc


def _require(by: str, user: str, what: str, *, strict: bool = True) -> None:
    """
    그 사람만 — 역할·담당 검사(구현명세 2장). `strict=False`면 답한 사람이 사용자 마스터 밖(콘솔
    관리자)이다 — 「담당자만」은 바깥 Chaeksas가 결재 담당자로 이미 막았다(장면 1·2와 같다).
    """
    if strict and by != user:
        holder = USERS.get(user, {})
        raise DomainError(f"{what}은 {holder.get('role')}({holder.get('name')})만 한다", 403)


# ─────────────────────────── 장면 2 기준 (D30) ───────────────────────────


def baseline_from_sc02(sc02_doc: dict) -> dict[str, Any]:
    """
    장면 2 인계 결과 → 장면 3의 출발점(CT31). 승인 원가 등록·경영관리 인수가 끝나야 한다 — 없으면
    착수 오류다(U31). 기본 경로는 승인 단가만 반영한다(잠정 자료는 받지 않는다).
    """
    h = sc02_doc.get("handoff") or {}
    if sc02_doc.get("scene") != "HANDED_OFF" or h.get("status") != "HANDED_OFF":
        raise DomainError(
            "외주 단가 인상 검토가 아직 경영관리 인수 전이다 — 수익성 통합 분석은 승인 원가 "
            "등록·인수 완료에서 시작한다",
            409,
        )
    if sc02_doc.get("case_id") != "BASE":
        raise DomainError(
            f"외주 단가 인상 검토가 기본 시연이 아니다({sc02_doc.get('case_id')}) — "
            "수익성 통합 분석 기대값은 기본 경로 기준이다",
            409,
        )
    pv = sc02_doc["price_versions"].get("PV-APP01")
    cv = sc02_doc["cost_versions"].get("C02-APP01")
    if pv is None or cv is None or sc02_doc.get("approval_status") != "APPROVED":
        raise DomainError("외주 단가 인상 검토의 승인 단가(PV-APP01)·원가 버전(C02-APP01)이 "
                          "없다", 409)
    sc01 = sc02_doc["sc01"]
    return {
        "demo_run_id": sc02_doc["demo_run_id"],
        "executor": (sc02_doc.get("bpm") or {}).get("executor", "embedded"),
        "handoff": {
            k: h.get(k)
            for k in (
                "handoff_id",
                "bundle_id",
                "bundle_hash",
                "selected_run",
                "accepted_by",
                "accepted_at",
                "sc03_due_at",
            )
        },
        "price": {
            k: pv[k]
            for k in ("version_id", "part_id", "old_price", "new_price", "effective_date", "run_id")
        },
        "request_price": next(
            (
                v["new_price"]
                for v in sc02_doc["price_versions"].values()
                if v["version_id"] == "PV-REQ01"
            ),
            None,
        ),
        "cost": {
            k: cv[k]
            for k in ("cost_version_id", "parent_cost_version", "effective_from", "registered_at")
        },
        "issues": [
            {
                "issue_id": sc01["issue"]["issue_id"],
                "type": "VOLUME",
                "risk": sc01["issue"]["risk"],
                "status": sc01["issue"]["status"],
                "run_id": sc01["run_id"],
                "summary": "b모델 7월 9,500 → 8,800대분 (고객 생산계획 변경 대응)",
            },
            {
                "issue_id": sc02_doc["issue"]["issue_id"],
                "type": "COST",
                "risk": sc02_doc["issue"]["risk"],
                "status": sc02_doc["issue"]["status"],
                "run_id": pv["run_id"],
                "summary": "공통부품 P-COM01 2,000 → 2,120원 7/1 적용 (외주 단가 인상 검토)",
            },
        ],
        "sc01_run": sc01["run_id"],
        "forecast_approval": sc01["forecast_approval"],
    }


def new_demo_run(
    seed: Seed,
    demo_run_id: str,
    *,
    case_id: str,
    created_at: datetime,
    baseline: dict,
    executor: str = "embedded",
) -> dict:
    """
    D30 — 장면 2 인수 완료, 장면 3 미착수. 회신·결론·과제·인수는 단계 실행 때 생긴다(구현명세 13장:
    미래 결론·인수값을 초기 상태에 노출하지 않는다). 사례는 이 문서 안에서만 무엇을 바꾸는지 적는다.
    """
    if case_id not in CASES:
        raise DomainError(f"모르는 시연 사례: {case_id} (가능: {', '.join(CASES)})", 422)
    if executor not in EXECUTORS:
        raise DomainError(f"모르는 실행 위치: {executor} (가능: {', '.join(EXECUTORS)})", 422)
    return {
        "demo_run_id": demo_run_id,
        "seed_id": SEED_ID,
        "case_id": case_id,
        "created_at": created_at.isoformat(),
        "clock": baseline["handoff"]["accepted_at"],
        "step": "D30",
        "sc02": baseline,
        # E33 — 고정비 중복 입력(계수 2)을 계산에 주입한다. 정정하면 1로 돌아간다.
        "calc_override": {"fixed_multiplier": 2 if case_id == "E33" else 1},
        # E31 — 부서 확인용 복제 초안이 적용월을 잘못 적었다(승인 원천은 그대로다).
        "draft_typo": case_id == "E31",
        "agent_mode": "fail" if case_id == "E36" else "mock",
        "review": {
            "review_id": REVIEW_ID,
            "state": "PENDING",
            "outcome": None,
            "risk": "OPEN",
            "forecast": "REVIEW_PENDING",
            "target": "UNCHANGED",
            "links": [dict(i) for i in baseline["issues"]],
            "started_at": None,
            "started_by": None,
            "completed_at": None,
        },
        "runs": {},
        "reports": {},
        "confirmation": None,
        "replies": [],
        "facts": {},
        "questions": {},
        "meetings": {},
        "candidates": {},
        "decision": None,
        "minutes": {},
        "assignments": {},
        "revisions": [],
        "handoff": None,
        "agent_outputs": {},
        "tasks": {},
        "alerts": [],
        "audit": [],
        "bpm": None if executor == "embedded" else external_bpm(executor),
    }


def price_option(doc: dict) -> Option:
    """승인 단가·적용일은 장면 2 승인 기록에서 읽는다 — 요청가·협상가를 쓰지 않는다(구현명세
    3장)."""
    p = doc["sc02"]["price"]
    return Option(
        p["version_id"],
        "APPROVED",
        p["part_id"],
        "SUP-01",
        Decimal(p["old_price"]),
        Decimal(p["new_price"]),
        date.fromisoformat(p["effective_date"]),
    )


# ─────────────────────────── S31 착수 (U31 · CT31) ───────────────────────────


def start_review(doc: dict, *, by: str) -> bool:
    """
    검토 착수 — 기존 MR-2706-01에 두 사건을 잇는다(새 검토건을 만들지 않는다). **같은 검토건의
    재착수는
    기존 결과를 돌려준다**(T31 — 중복 이벤트 없음). 돌려주는 값은 새로 착수했는가다.
    """
    _require(by, FIN, "검토 착수")
    r = doc["review"]
    if r["started_at"] is not None:
        return False
    if doc["sc02"]["handoff"].get("accepted_by") != FIN:
        raise DomainError("외주 단가 인상 검토 인수 근거가 경영관리 담당 인수가 아니다 — 착수할 수 "
                          "없다", 409)
    r.update(state="ANALYSIS_IN_PROGRESS", started_at=doc["clock"], started_by=by)
    audit(doc, actor=by, action="review_started", review_id=REVIEW_ID, event_code="EV31-01")
    return True


def open_review(doc: dict) -> dict[str, Any]:
    """BPM 첫 작업 — 착수된 검토건인지 본다. 바깥 실행은 착수 뒤에 Studio·Center에서 시작한다."""
    if doc["review"]["started_at"] is None:
        raise DomainError("아직 착수하지 않은 검토건이다 — 화면에서 분석 시작을 먼저 누른다", 409)
    return {"review_id": REVIEW_ID, "assignee_name": name_of(FIN)}


# ─────────────────────────── S32·S33 통합 분석 (U32 · CT32·CT33) ───────────────────────────


def latest_run(doc: dict) -> dict | None:
    runs = ordered(doc["runs"])
    return runs[-1] if runs else None


def current_draft(doc: dict) -> dict | None:
    drafts = [r for r in ordered(doc["reports"]) if r["kind"] == "DRAFT"]
    return drafts[-1] if drafts else None


def frozen_report(doc: dict) -> dict | None:
    frozen = [r for r in ordered(doc["reports"]) if r["kind"] == "FROZEN"]
    return frozen[-1] if frozen else None


def _draft_id(doc: dict) -> str:
    frozen = sum(1 for r in doc["reports"].values() if r["kind"] == "FROZEN")
    since = [
        r
        for r in ordered(doc["reports"])
        if r["kind"] == "DRAFT" and r.get("after_frozen", 0) == frozen
    ]
    if frozen == 0:
        return "REP31-v0" if not since else f"REP31-v0.{len(since)}"
    return f"REP31-v{frozen}.{len(since) + 1}"


def _basis_text(doc: dict, *, typo: bool) -> str:
    p = doc["sc02"]["price"]
    eff = date.fromisoformat(p["effective_date"])
    month = eff.month + 1 if typo else eff.month  # E31 — 복제 초안의 잘못된 적용월
    return (
        f"승인단가 {int(Decimal(p['new_price'])):,}원 · {month}/1 적용 · a·b 각 1개 · "
        f"F02+EXT28-v1 · C02-APP01 · FC01/FC28-v1"
    )


def _kpis(run: dict) -> dict[str, Any]:
    y = run["result"]["periods"]["year"]
    return {
        k: y.get(k)
        for k in (
            "target",
            "f01",
            "volume_effect",
            "cost_effect",
            "event_effect",
            "combined",
            "existing_gap",
            "total_gap",
        )
    }


def _new_draft(doc: dict, run: dict, *, by: str, reason: str, affects: list[str]) -> dict:
    report_id = _draft_id(doc)
    frozen = sum(1 for r in doc["reports"].values() if r["kind"] == "FROZEN")
    previous = current_draft(doc)
    draft = doc["reports"][report_id] = {
        "report_id": report_id,
        "seq": _seq(doc["reports"]),
        "kind": "DRAFT",
        "status": "DRAFT",
        "run_id": run["run_id"],
        "created_at": doc["clock"],
        "created_by": by,
        "basis_text": _basis_text(doc, typo=doc.get("draft_typo", False)),
        "kpis": _kpis(run),
        "previous": None if previous is None else previous["report_id"],
        "change_summary": reason,
        # 이 버전이 바꾼 확인 범위 — 그 부서의 이전 확인은 STALE이다(U33).
        "affects": affects,
        "after_frozen": frozen,
    }
    if previous is not None:
        previous["status"] = "SUPERSEDED"
    return draft


def run_analysis(doc: dict, seed: Seed, *, by: str, memo: str = "") -> dict[str, Any]:
    """
    통합 분석 실행(RUN-SC03-xx). 원천 버전과 결과를 보존한다 — 재실행은 새 실행 ID다(구현명세 3장).
    정합을
    통과하면 보고 초안을 만든다(미검토·미확정). 실패하면 초안 없이 `CALCULATION_BLOCKED`로
    남는다(E33).
    """
    _require(by, FIN, "통합 분석")
    rows = list(seed.numbers.rows)
    for period_iso, model, qty in doc.get("rows_override", []):
        rows = [
            replace(r, f02=qty) if (r.period.isoformat(), r.model_id) == (period_iso, model) else r
            for r in rows
        ]
    result = calc.integrated(
        seed.numbers,
        price_option(doc),
        rows=rows,
        fixed_multiplier=doc["calc_override"]["fixed_multiplier"],
    )
    run_id = f"RUN-SC03-{len(doc['runs']) + 1:02d}"
    run = doc["runs"][run_id] = {
        "run_id": run_id,
        "seq": _seq(doc["runs"]),
        "review_id": REVIEW_ID,
        "created_at": doc["clock"],
        "created_by": by,
        "memo": memo,
        "sources": [doc["sc02"]["sc01_run"], doc["sc02"]["price"]["run_id"]],
        "result": result,
        "status": result["status"],
    }
    audit(
        doc,
        actor=by,
        action="analysis_run",
        run_id=run_id,
        status=result["status"],
        event_code="EV31-02" if result["passed"] else None,
    )
    if result["passed"]:
        affects = [] if not doc["reports"] else list(DEPTS)
        _new_draft(doc, run, by=by, reason=memo or "통합 분석 초안", affects=affects)
        doc["review"]["state"] = "ANALYSIS_IN_PROGRESS"
    return {"run_id": run_id, "passed": result["passed"]}


def fix_calc(doc: dict, seed: Seed, *, note: str, by: str) -> dict[str, Any]:
    """E33 정정 — 고정비 입력을 바로잡고 다시 계산한다. 실패 실행은 지우지 않는다(정합 실패
    기록)."""
    _require(by, FIN, "계산 정정")
    latest = latest_run(doc)
    if latest is None or latest["result"]["passed"]:
        raise DomainError("정정할 계산 오류가 없다", 409)
    doc["calc_override"]["fixed_multiplier"] = 1
    audit(doc, actor=by, action="calc_fixed", run_id=latest["run_id"], note=note)
    return run_analysis(doc, seed, by=by, memo=f"정정 후 재계산 — {note}")


# ─────────────────────────── S34~S37 부서 확인 (U33 · CT34·CT35) ───────────────────────────


def request_confirmation(doc: dict, *, due: Any, memo: str, by: str) -> None:
    _require(by, FIN, "부서 확인 요청")
    run = latest_run(doc)
    draft = current_draft(doc)
    if run is None or not run["result"]["passed"] or draft is None:
        raise DomainError("정합이 확인된 분석 초안이 없다 — 부서 확인을 요청할 수 없다(CT33)", 409)
    due_iso = _when(due or SCHEDULE["confirm_due"], "회신기한")
    doc["confirmation"] = {
        "report_id": draft["report_id"],
        "run_id": run["run_id"],
        "departments": list(DEPTS),
        "recipients": [d["user"] for d in DEPTS.values()],
        "due_at": due_iso,
        "requested_at": doc["clock"],
        "requested_by": by,
        "memo": memo,
    }
    draft["status"] = "CONFIRMATION_PENDING"
    doc["review"]["state"] = "CONFIRMATION_PENDING"
    audit(
        doc,
        actor=by,
        action="confirmation_requested",
        report=draft["report_id"],
        due=due_iso,
        event_code="EV31-03",
    )


def _fact(
    doc: dict,
    *,
    dept: str,
    category: str,
    statement: str,
    evidence: str,
    by: str,
    state: str,
    report_id: str,
) -> dict:
    fact_id = f"F{31 + len(doc['facts'])}"
    fact = doc["facts"][fact_id] = {
        "fact_id": fact_id,
        "seq": _seq(doc["facts"]),
        "dept": dept,
        "category": category,
        "statement": statement,
        "evidence_ref": evidence,
        "reviewer": by,
        "confirmed_at": doc["clock"],
        "state": state,
        "report_id": report_id,
        "followup_ref": None,
    }
    return fact


def _question(
    doc: dict,
    *,
    fact: dict,
    question: str,
    owner: str,
    blocking: bool | None,
    kind: str = "FOLLOWUP",
) -> dict:
    """쟁점 — 미확인(Q31·Q32)과 이견(QD)은 번호를 따로 센다(데이터의 Q31·Q32를 지킨다)."""
    if kind == "DISPUTE":
        qid = f"QD{31 + sum(1 for q in doc['questions'].values() if q['kind'] == 'DISPUTE')}"
    else:
        qid = f"Q{31 + sum(1 for q in doc['questions'].values() if q['kind'] == 'FOLLOWUP')}"
    q = doc["questions"][qid] = {
        "question_id": qid,
        "seq": _seq(doc["questions"]),
        "kind": kind,
        "fact_ref": fact["fact_id"],
        "question": question,
        "blocking": blocking,
        "owner": owner,
        "due_at": None,
        "decision_by": None,
        "decided_at": None,
        "treatment": None,
        "state": "OPEN",
        "history": [],
    }
    fact["followup_ref"] = qid
    return q


def check_confirmation(doc: dict, dept: str, args: dict[str, Any]) -> None:
    if dept not in DEPTS:
        raise DomainError(f"모르는 부서: {dept}", 422)
    if doc["confirmation"] is None:
        raise DomainError("부서 확인 요청이 아직 없다", 409)
    reply = args.get("reply")
    if reply not in ("확인", "이견"):
        raise DomainError("회신은 「확인」 또는 「이견」이다 — 무응답은 동의가 아니다", 422)
    if not _text(args, "fact"):
        raise DomainError("확인한 사실(또는 이견 내용)을 적는다", 422)
    if not _text(args, "evidence"):
        raise DomainError("근거를 적는다", 422)
    if reply == "이견" and not _text(args, "opinion"):
        raise DomainError("이견이면 의견·보완 요청을 적는다", 422)
    if _text(args, "unconfirmed") and not _text(args, "question"):
        raise DomainError("미확인 사항에는 확인할 질문을 붙인다", 422)


def record_confirmation(
    doc: dict, dept: str, args: dict[str, Any], *, by: str, strict: bool = True
) -> None:
    """
    부서 회신 — 사실·가정·미확인을 따로 적는다(CT34). 자기 부서만 확정한다. 이견이면 원 의견을
    보존하고
    차단 쟁점(QD)을 연다 — 초안을 고쳐 재확인할 때까지 보고 확정이 막힌다(E31).
    """
    check_confirmation(doc, dept, args)
    _require(by, DEPTS[dept]["user"], f"{DEPTS[dept]['label']} 확인", strict=strict)
    draft = current_draft(doc)
    report_id = draft["report_id"] if draft else doc["confirmation"]["report_id"]
    evidence = _text(args, "evidence")
    facts: list[str] = []
    if args["reply"] == "이견":
        fact = _fact(
            doc,
            dept=dept,
            category="FACT",
            statement=_text(args, "fact"),
            evidence=evidence,
            by=by,
            state="DISPUTED",
            report_id=report_id,
        )
        _question(
            doc,
            fact=fact,
            question=_text(args, "opinion"),
            owner=FIN,
            blocking=True,
            kind="DISPUTE",
        )
        facts.append(fact["fact_id"])
    else:
        # 이 부서의 앞선 이견은 재확인으로 닫힌다 — 원 의견은 그대로 둔다.
        for q in doc["questions"].values():
            if (
                q["kind"] == "DISPUTE"
                and doc["facts"][q["fact_ref"]]["dept"] == dept
                and q["state"] == "REVISED"
            ):
                q.update(state="RESOLVED")
                q["history"].append({"at": doc["clock"], "state": "RESOLVED", "by": by})
        facts.append(
            _fact(
                doc,
                dept=dept,
                category="FACT",
                statement=_text(args, "fact"),
                evidence=evidence,
                by=by,
                state="CONFIRMED",
                report_id=report_id,
            )["fact_id"]
        )
        if _text(args, "assumption"):
            facts.append(
                _fact(
                    doc,
                    dept=dept,
                    category="ASSUMPTION",
                    statement=_text(args, "assumption"),
                    evidence=evidence,
                    by=by,
                    state="CONFIRMED_AS_ASSUMPTION",
                    report_id=report_id,
                )["fact_id"]
            )
        if _text(args, "unconfirmed"):
            fact = _fact(
                doc,
                dept=dept,
                category="UNCONFIRMED",
                statement=_text(args, "unconfirmed"),
                evidence=evidence,
                by=by,
                state="FOLLOWUP_REQUIRED",
                report_id=report_id,
            )
            _question(doc, fact=fact, question=_text(args, "question"), owner=by, blocking=None)
            facts.append(fact["fact_id"])
    doc["replies"].append(
        {
            "seq": len(doc["replies"]) + 1,
            "dept": dept,
            "reply": args["reply"],
            "by": by,
            "at": doc["clock"],
            "report_id": report_id,
            "facts": facts,
            "opinion": _text(args, "opinion"),
            "state": "DISPUTED" if args["reply"] == "이견" else "RESPONDED",
        }
    )
    audit(doc, actor=by, action="confirmation_replied", dept=dept, reply=args["reply"], facts=facts)


def _report_after(doc: dict, report_id: str) -> list[dict]:
    seq = doc["reports"][report_id]["seq"]
    return [r for r in ordered(doc["reports"]) if r["seq"] > seq and r["kind"] == "DRAFT"]


def dept_status(doc: dict, dept: str) -> dict[str, Any]:
    """
    부서 확인 현황 — 최신 회신이 유효한가. 그 뒤의 초안이 이 부서 범위를 바꿨으면 STALE이다(U33).
    회신이
    없으면 미회신이다(동의로 보지 않는다).
    """
    replies = [r for r in doc["replies"] if r["dept"] == dept]
    if not replies:
        return {"dept": dept, "state": "PENDING", "reply": None}
    last = replies[-1]
    stale = any(dept in r["affects"] for r in _report_after(doc, last["report_id"]))
    state = "STALE" if stale else last["state"]
    return {"dept": dept, "state": state, "reply": last}


def check_revision(doc: dict, args: dict[str, Any]) -> None:
    if not any(q["kind"] == "DISPUTE" and q["state"] == "OPEN" for q in doc["questions"].values()):
        raise DomainError("보완할 이견이 없다", 409)
    if not _text(args, "change"):
        raise DomainError("보완 내용(변경 요약)을 적는다", 422)


def record_revision(doc: dict, args: dict[str, Any], *, by: str) -> str:
    """
    E31 — 이견을 반영해 초안을 고친다. **새 버전**이고 이견 부서의 확인은 STALE이다(재확인 필요).
    승인
    원천은 그대로다 — 고치는 것은 초안의 표기다.
    """
    check_revision(doc, args)
    _require(by, FIN, "초안 보완")
    disputes = [
        q for q in ordered(doc["questions"]) if q["kind"] == "DISPUTE" and q["state"] == "OPEN"
    ]
    depts = sorted({doc["facts"][q["fact_ref"]]["dept"] for q in disputes})
    doc["draft_typo"] = False
    run = latest_run(doc)
    draft = _new_draft(doc, run, by=by, reason=_text(args, "change"), affects=depts)  # type: ignore[arg-type]
    for q in disputes:
        q.update(state="REVISED")
        q["history"].append(
            {"at": doc["clock"], "state": "REVISED", "by": by, "report": draft["report_id"]}
        )
    if doc["confirmation"]:
        doc["confirmation"]["report_id"] = draft["report_id"]
    audit(doc, actor=by, action="draft_revised", report=draft["report_id"], affects=depts)
    return draft["report_id"]


def check_gap(doc: dict, args: dict[str, Any]) -> None:
    if args.get("result") not in ("미확인등록", "쟁점없음"):
        raise DomainError("확인 결과를 고른다", 422)
    if not _text(args, "content") or not _text(args, "evidence"):
        raise DomainError("내용과 근거를 적는다", 422)
    if args["result"] == "미확인등록" and not _text(args, "question"):
        raise DomainError("미확인 사항에는 확인할 질문을 붙인다", 422)


def record_gap(doc: dict, args: dict[str, Any], *, by: str, strict: bool = True) -> None:
    """
    S37 기존 목표 부족 쟁점 — 부족 금액은 검증됐지만 세부 원인은 근거가 없다(F37·Q32). 새 사건의
    원인으로
    임의 설명하지 않는다.
    """
    check_gap(doc, args)
    _require(by, FINLEAD, "기존 부족 쟁점 확인", strict=strict)
    draft = current_draft(doc)
    rid = draft["report_id"] if draft else ""
    if args["result"] == "미확인등록":
        fact = _fact(
            doc,
            dept="FIN",
            category="UNCONFIRMED",
            statement=_text(args, "content"),
            evidence=_text(args, "evidence"),
            by=by,
            state="FOLLOWUP_REQUIRED",
            report_id=rid,
        )
        _question(doc, fact=fact, question=_text(args, "question"), owner=by, blocking=None)
    else:
        _fact(
            doc,
            dept="FIN",
            category="FACT",
            statement=_text(args, "content"),
            evidence=_text(args, "evidence"),
            by=by,
            state="CONFIRMED",
            report_id=rid,
        )
    audit(doc, actor=by, action="gap_registered", result=args["result"], event_code="EV31-07")


def open_followups(doc: dict) -> list[dict]:
    return [
        q
        for q in ordered(doc["questions"])
        if q["kind"] == "FOLLOWUP" and q["state"] not in ("CLOSED",)
    ]


def check_judgement(doc: dict, args: dict[str, Any]) -> None:
    """CT35 — 열린 미확인마다 차단 여부·담당·기한·처리방향이 있어야 한다. 중대한 오류는 차단이다."""
    for q in open_followups(doc):
        if q["question_id"] not in QUESTION_SLOTS:
            raise DomainError(f"이 폼이 다루지 않는 쟁점이 있다: {q['question_id']}", 409)
    for slot in QUESTION_SLOTS:
        if slot not in doc["questions"]:
            continue
        a = args.get(slot) or {}
        if a.get("blocking") not in ("비차단", "차단"):
            raise DomainError(f"{slot}: 차단 여부를 고른다", 422)
        if not _text(a, "treatment"):
            raise DomainError(f"{slot}: 처리방향(판단 사유)을 적는다", 422)
        if a["blocking"] == "비차단":
            if _user(a.get("owner")) is None:
                raise DomainError(f"{slot}: 비차단이면 담당을 지정한다", 422)
            _when(a.get("due"), f"{slot} 기한")
    for q in ordered(doc["questions"]):
        if q["kind"] == "DISPUTE" and q["state"] != "RESOLVED":
            raise DomainError(
                f"{q['question_id']} 이견이 아직 닫히지 않았다 — 재확인이 먼저다", 409
            )


def judge_questions(doc: dict, args: dict[str, Any], *, by: str) -> dict[str, Any]:
    """
    S37 쟁점 처리 확정(EV31-08) — 임원이 차단 여부를 판단한다. 비차단은 담당·기한·처리방향을 붙여
    후속 확인으로 남는다(OPEN_FOLLOWUP). 차단이 하나라도 있으면 재분석으로 돌아간다.
    """
    check_judgement(doc, args)
    _require(by, CFO, "쟁점 차단 판단")
    blocked = False
    for slot in QUESTION_SLOTS:
        q = doc["questions"].get(slot)
        if q is None:
            continue
        a = args[slot]
        block = a["blocking"] == "차단"
        blocked = blocked or block
        before = {k: q[k] for k in ("blocking", "owner", "due_at", "treatment", "state")}
        q.update(
            blocking=block,
            owner=_user(a.get("owner")) or q["owner"],
            due_at=None if block else _when(a.get("due"), "기한"),
            treatment=_text(a, "treatment"),
            decision_by=by,
            decided_at=doc["clock"],
            state="BLOCKING" if block else "OPEN_FOLLOWUP",
        )
        q["history"].append({"at": doc["clock"], "by": by, "before": before, "state": q["state"]})
    audit(doc, actor=by, action="questions_judged", blocked=blocked, event_code="EV31-08")
    return {"blocked": blocked}


# ─────────────────────────── S38 자료 확정·배포 (U34 · CT35·CT36) ───────────────────────────


def freeze_problems(doc: dict) -> list[str]:
    """자료 확정을 막는 것 — 핵심 회신 누락·차단 쟁점·계산 검증 실패(U34). 버튼 비활성은 보조다."""
    items = []
    run = latest_run(doc)
    if run is None or not run["result"]["passed"]:
        items.append("계산 검증을 통과한 분석이 없다(CT33)")
    for dept, d in DEPTS.items():
        st = dept_status(doc, dept)["state"]
        if st != "RESPONDED":
            label = {"PENDING": "미회신", "STALE": "재확인 필요", "DISPUTED": "이견"}.get(st, st)
            items.append(f"{d['label']} 확인 {label}")
    for q in ordered(doc["questions"]):
        if q["state"] in ("BLOCKING",) or (q["kind"] == "DISPUTE" and q["state"] != "RESOLVED"):
            items.append(f"{q['question_id']} 차단 쟁점")
        elif q["kind"] == "FOLLOWUP" and q["state"] == "OPEN":
            items.append(f"{q['question_id']} 차단 여부 미판단")
    return items


def freeze_report(doc: dict, *, opinion: str, by: str) -> str:
    """
    REP31-v1 확정(EV31-09) — 입력 버전·계산 결과·확인 상태를 스냅샷으로 고정한다. 수치는 다시
    계산하지
    않는다(같은 run). 확정본은 고치지 않는다 — 수정은 새 버전이다.
    """
    _require(by, CFO, "보고자료 확정")
    problems = freeze_problems(doc)
    if problems:
        raise DomainError("자료를 확정할 수 없다: " + ", ".join(problems), 409)
    draft = current_draft(doc)
    run = doc["runs"][draft["run_id"]]  # type: ignore[index]
    n = sum(1 for r in doc["reports"].values() if r["kind"] == "FROZEN") + 1
    snapshot = {
        "run_id": run["run_id"],
        "basis": run["result"]["basis"],
        "kpis": _kpis(run),
        "facts": {f["fact_id"]: f["state"] for f in ordered(doc["facts"])},
        "questions": {q["question_id"]: q["state"] for q in ordered(doc["questions"])},
        "draft": draft["report_id"],  # type: ignore[index]
    }
    report_id = f"REP31-v{n}"
    doc["reports"][report_id] = {
        "report_id": report_id,
        "seq": _seq(doc["reports"]),
        "kind": "FROZEN",
        "status": "FROZEN",
        "run_id": run["run_id"],
        "created_at": doc["clock"],
        "created_by": by,
        "frozen_by": by,
        "frozen_at": doc["clock"],
        "opinion": opinion,
        "basis_text": _basis_text(doc, typo=False),
        "kpis": snapshot["kpis"],
        "snapshot": snapshot,
        "source_hash": _hash(snapshot)[:16],
        "distributed_at": None,
    }
    draft["status"] = "CONFIRMED"  # type: ignore[index]
    audit(doc, actor=by, action="report_frozen", report=report_id, event_code="EV31-09")
    return report_id


def distribute(doc: dict, seed: Seed, *, memo: str, by: str) -> None:
    """내부 자료 배포(EV31-10) — 실제 메일 없이 내부 배포 기록이다. 검토건 MEETING_READY."""
    _require(by, FIN, "자료 배포")
    rep = frozen_report(doc)
    if rep is None:
        raise DomainError("확정된 보고자료가 없다", 409)
    rep["distributed_at"] = doc["clock"]
    rep["distributed_by"] = by
    m = seed.by_id("SC03회의")[MEETING_ID]
    doc["meetings"][MEETING_ID] = {
        "meeting_id": MEETING_ID,
        "seq": _seq(doc["meetings"]),
        "type": "AD_HOC_REVIEW",
        "subject": str(m["subject"]),
        "agenda": str(m["content"]),
        "chair": CFO,
        "scheduled_at": kst(m["event_at"]),
        "report_version": rep["report_id"],
        "state": "READY",
        "opened_at": None,
        "attendance": [],
        "records": [],
        "memo": memo,
    }
    doc["review"]["state"] = "MEETING_READY"
    audit(
        doc,
        actor=by,
        action="report_distributed",
        report=rep["report_id"],
        meeting=MEETING_ID,
        event_code="EV31-10",
    )


# ─────────────────────────── S39~S41 수시회의 (U35 · CT35~CT37) ───────────────────────────


def check_open_meeting(doc: dict) -> None:
    m = doc["meetings"].get(MEETING_ID)
    if m is None or m["state"] != "READY":
        raise DomainError("배포된 회의자료가 없다 — 자료 확정·배포가 먼저다", 409)
    if parse_at(doc["clock"]) < parse_at(m["scheduled_at"]):
        raise DomainError(f"회의 시각({m['scheduled_at'][5:16].replace('T', ' ')}) 전이다", 409)


def open_meeting(doc: dict, seed: Seed, *, summary: str, by: str) -> None:
    """
    MT31 개회·보고(EV31-11). 보고는 확정본 고정이다(REP31-v1). 참석은 SC03회의의 참석 기록 그대로 —
    품질·
    대표를 넣지 않는다. 탐색 후보(C31~C36)는 부서가 준비한 정성적 설명이다 — 효과액은 없다(NULL).
    """
    check_open_meeting(doc)
    _require(by, FIN, "통합 영향 보고")
    m = doc["meetings"][MEETING_ID]
    m.update(state="IN_PROGRESS", opened_at=doc["clock"], report_summary=summary)
    m["attendance"] = [
        {"record_id": f"ATT31-{i + 1}", "actor": u, "state": "PRESENT", "at": doc["clock"]}
        for i, u in enumerate(ATTENDEES)
    ]
    for i, row in enumerate(seed.rows("SC03후보")):
        cid = str(row["candidate_id"])
        doc["candidates"][cid] = {
            "candidate_id": cid,
            "seq": i + 1,
            "meeting_id": MEETING_ID,
            "dept": str(row["dept"]),
            "candidate": str(row["candidate"]),
            "mechanism": str(row["expected_mechanism"]),
            "constraints": str(row["constraints"]),
            "evidence_ref": str(row["evidence_ref"]),
            # 효과는 미산정 — 0이 아니다. 상세 비교는 장면 4다.
            "effect_2027": None,
            "effect_12m": None,
            "decision": None,
            "decision_reason": None,
            "decided_by": None,
            "decided_at": None,
            "task_id": None,
        }
    doc["review"]["state"] = "IN_REVIEW"
    audit(
        doc,
        actor=by,
        action="meeting_opened",
        meeting=MEETING_ID,
        report=m["report_version"],
        event_code="EV31-11",
    )


RECORD_TYPES = ("QUESTION", "ANSWER", "EXPLANATION", "NOTE")


def add_meeting_record(
    doc: dict, *, record_type: str, subject: str, content: str, related: str, by: str
) -> str:
    """회의 질의·답변·설명(U35) — 참석자만 적는다. BPM 밖의 기록이다(회의 진행 중에만)."""
    m = doc["meetings"].get(MEETING_ID)
    if m is None or m["state"] != "IN_PROGRESS":
        raise DomainError("진행 중인 회의가 없다", 409)
    if by not in [a["actor"] for a in m["attendance"]]:
        raise DomainError("MT31 참석자만 기록한다", 403)
    if record_type not in RECORD_TYPES:
        raise DomainError(f"기록 종류: {', '.join(RECORD_TYPES)}", 422)
    if not content.strip():
        raise DomainError("내용을 적는다", 422)
    rid = f"QA{31 + sum(1 for r in m['records'] if r['record_type'] != 'NOTE')}"
    m["records"].append(
        {
            "record_id": rid,
            "record_type": record_type,
            "meeting_id": MEETING_ID,
            "actor_id": by,
            "event_at": doc["clock"],
            "subject": subject,
            "content": content,
            "related_ref": related,
            "state": "ANSWERED" if record_type == "QUESTION" else "RECORDED",
        }
    )
    audit(doc, actor=by, action="meeting_record", record_id=rid, record_type=record_type)
    return rid


def check_decision(doc: dict, args: dict[str, Any]) -> None:
    """
    결론과 후보 판단은 **한 명령으로** 검증한다 — 하나라도 빠지면 전체를 저장하지 않는다(구현명세
    11장).
    조건부 수용으로 중대한 오류를 우회할 수 없다(CT35).
    """
    m = doc["meetings"].get(MEETING_ID)
    if m is None or m["state"] != "IN_PROGRESS":
        raise DomainError("진행 중인 회의가 없다", 409)
    outcome = DECISIONS.get(str(args.get("outcome") or ""))
    if outcome is None:
        raise DomainError("결론은 수용·조건부수용·보완후재검토 중 하나다", 422)
    if not _text(args, "content"):
        raise DomainError("결론 내용을 적는다", 422)
    if outcome == "REWORK_REQUIRED":
        return
    blocking = [q["question_id"] for q in doc["questions"].values() if q["state"] == "BLOCKING"]
    if blocking:
        raise DomainError(f"차단 쟁점({', '.join(blocking)})이 있다 — 수용할 수 없다", 409)
    if outcome == "CONDITIONAL_ACCEPT":
        if not _text(args, "conditions"):
            raise DomainError("조건부 수용에는 잔여 질문·조건을 적는다", 422)
        missing = [
            q["question_id"]
            for q in open_followups(doc)
            if not (q["owner"] and q["due_at"] and q["treatment"])
        ]
        if missing:
            raise DomainError(f"잔여 질문에 담당·기한·처리방향이 없다: {', '.join(missing)}", 422)
    errors = []
    for cid in CANDIDATES:
        if cid not in doc["candidates"]:
            continue
        c = (args.get("candidates") or {}).get(cid) or {}
        if c.get("decision") not in CANDIDATE_DECISIONS:
            errors.append(f"{cid} 판단 없음")
        elif not _text(c, "reason"):
            errors.append(f"{cid} {'제외' if c['decision'] == '이번제외' else '포함'} 사유 없음")
    if errors:
        raise DomainError(
            "후보 판단이 완전하지 않다 — 결론과 판단 전체를 저장하지 않았다: " + ", ".join(errors),
            422,
        )


def decide_review(doc: dict, seed: Seed, args: dict[str, Any], *, by: str) -> dict[str, Any]:
    """
    REV31(EV31-12) — 통합 영향 검토 결론과 상세 분석 대상 특정. **포함은 상세 분석 지시이지 실행안
    선택이
    아니다.** 제외 후보에는 과제를 만들지 않는다. 포함 후보는 과제 초안(SC03과제)에 묶는다 —
    C32·C33은
    AT32 한 건이다(T36). AT34는 후보 없는 원인분석이다(Q32가 열려 있으면 만든다).
    """
    check_decision(doc, args)
    _require(by, CFO, "검토 결론")
    outcome = DECISIONS[args["outcome"]]
    doc["decision"] = {
        "decision_id": "REV31",
        "meeting_id": MEETING_ID,
        "outcome": outcome,
        "content": _text(args, "content"),
        "conditions": _text(args, "conditions"),
        "open_questions": [q["question_id"] for q in open_followups(doc)],
        "decided_by": by,
        "decided_at": doc["clock"],
        "report_version": doc["meetings"][MEETING_ID]["report_version"],
    }
    doc["review"]["outcome"] = outcome
    if outcome == "REWORK_REQUIRED":
        doc["review"]["state"] = "REWORK_REQUIRED"
        doc["meetings"][MEETING_ID]["state"] = "HELD"
        audit(doc, actor=by, action="review_rework", reason=_text(args, "content"))
        return {"outcome": outcome, "rework": True}
    included: list[str] = []
    for cid in CANDIDATES:
        c = doc["candidates"].get(cid)
        if c is None:
            continue
        a = args["candidates"][cid]
        c.update(
            decision=CANDIDATE_DECISIONS[a["decision"]],
            decision_reason=_text(a, "reason"),
            decided_by=by,
            decided_at=doc["clock"],
        )
        if c["decision"] == "INCLUDE":
            included.append(cid)
    _draft_tasks(doc, seed, included)
    doc["review"]["state"] = "REVIEWED"
    doc["meetings"][MEETING_ID]["state"] = "HELD"
    audit(
        doc,
        actor=by,
        action="review_decided",
        outcome=outcome,
        included=included,
        event_code="EV31-12",
    )
    return {"outcome": outcome, "rework": False}


def _draft_tasks(doc: dict, seed: Seed, included: list[str]) -> None:
    """과제 초안 — 데이터의 과제 원문에서 포함 후보에 걸린 것만(제외 후보는 과제가 없다)."""
    for i, row in enumerate(seed.rows("SC03과제")):
        tid = str(row["task_id"])
        refs = [c for c in str(row["candidate_refs"] or "").split(";") if c]
        picked = [c for c in refs if c in included]
        if refs and not picked:
            continue
        if not refs and "Q32" not in doc["questions"]:
            continue
        doc["assignments"][tid] = {
            "task_id": tid,
            "seq": i + 1,
            "review_id": REVIEW_ID,
            "candidate_refs": picked,
            "title": str(row["title"]),
            "owner": _owner(str(row["owner_id"])),
            "collaborators": [_owner(c) for c in str(row["collaborators"] or "").split(";") if c],
            "question": str(row["analysis_question"]),
            "deliverable": str(row["deliverable"]),
            "dependency": str(row["dependency"] or ""),
            "due_at": kst(row["due_at"]),
            "basis": str(row["basis_ref"]),
            "effect_2027": None,  # 미산정 — 0이 아니다
            "effect_12m": None,
            "assignment_version": 0,
            "state": "DRAFT",
            "assigned_at": None,
            "accepted_at": None,
            "accepted_version": None,
            "submitted_at": None,
            "history": [
                {
                    "at": doc["clock"],
                    "state": "DRAFT",
                    "by": "system",
                    "note": "회의 결론의 포함 후보로 초안 작성",
                }
            ],
        }
        for cid in picked:
            doc["candidates"][cid]["task_id"] = tid


#: 데이터의 가상 계정 → NowView 사용자
ACCOUNTS = {
    "USR-FIN": FIN,
    "USR-CFO": CFO,
    "USR-PROD": PROD,
    "USR-BUY": BUY,
    "USR-SALES": SALES,
    "USR-FINLEAD": FINLEAD,
    "USR-QA": "u-qa-lead",
    "USR-CEO": "u-ceo",
}


def _owner(account: str) -> str:
    return ACCOUNTS[account.strip()]


def confirm_minutes(doc: dict, seed: Seed, *, opinion: str, by: str) -> str:
    """
    MIN31-v1(EV31-13) — 주재자 확인. 분석 대상·제외 사유·잔여 질문·과제 초안·7/12 보고 계획. 확인된
    회의록은 고치지 않는다. MT41은 계획만 등록한다(대표 주재 — 장면 3 승인권자 아님).
    """
    _require(by, CFO, "회의록 확인")
    dec = doc["decision"]
    if dec is None or dec["outcome"] == "REWORK_REQUIRED":
        raise DomainError("확인할 검토 결론이 없다", 409)
    n = len(doc["minutes"]) + 1
    mid = f"MIN31-v{n}"
    doc["minutes"][mid] = {
        "minutes_id": mid,
        "seq": n,
        "meeting_id": MEETING_ID,
        "decision": dec["decision_id"],
        "outcome": dec["outcome"],
        "included": [
            c["candidate_id"] for c in ordered(doc["candidates"]) if c["decision"] == "INCLUDE"
        ],
        "excluded": [
            {"candidate_id": c["candidate_id"], "reason": c["decision_reason"]}
            for c in ordered(doc["candidates"])
            if c["decision"] == "EXCLUDE_THIS_REVIEW"
        ],
        "open_questions": dec["open_questions"],
        "tasks": [a["task_id"] for a in ordered(doc["assignments"])],
        "next_meeting": NEXT_MEETING_ID,
        "confirmed_by": by,
        "confirmed_at": doc["clock"],
        "opinion": opinion,
        "agent_drafts": [
            o["output_id"]
            for o in ordered(doc["agent_outputs"])
            if o["kind"] == "AG31" and o.get("adopted_by")
        ],
        "state": "CONFIRMED",
    }
    row = seed.by_id("SC03회의")[NEXT_MEETING_ID]
    doc["meetings"][NEXT_MEETING_ID] = {
        "meeting_id": NEXT_MEETING_ID,
        "seq": _seq(doc["meetings"]),
        "type": "MONTHLY",
        "subject": str(row["subject"]),
        "agenda": str(row["content"]),
        "chair": "u-ceo",
        "scheduled_at": kst(row["event_at"]),
        "report_version": None,
        "state": "PLANNED",
        "attendance": [],
        "records": [],
    }
    audit(doc, actor=by, action="minutes_confirmed", minutes=mid, event_code="EV31-13")
    return mid


# ─────────────────────────── S41~S43 과제 배정·인수 (U36 · CT37~CT39) ───────────────────────────

TASK_FIELDS = ("owner", "collaborators", "question", "deliverable", "dependency", "due_at", "basis")


def task_problems(a: dict) -> list[str]:
    """CT38 — 단일 책임자·협조·질문·산출물·의존관계·기한·기준 버전 필수. 효과액은 요구하지
    않는다."""
    out = []
    owner = a.get("owner")
    if not owner or owner not in USERS:
        out.append("책임자 없음")
    if not a.get("collaborators"):
        out.append("협조부서 없음")
    for key, label in (
        ("question", "분석 질문"),
        ("deliverable", "산출물"),
        ("dependency", "의존관계"),
        ("basis", "기준 버전"),
    ):
        if not str(a.get(key) or "").strip():
            out.append(f"{label} 없음")
    if not a.get("due_at"):
        out.append("제출기한 없음")
    return out


def edit_task(doc: dict, task_id: str, changes: dict[str, Any], *, by: str, reason: str) -> None:
    """
    과제 초안 수정(배정 전) — 경영관리가 정리한다. 전후값을 남긴다. 배정된 과제는 재배정(임원)으로만
    바꾼다. 과제 삭제·배정 취소로 인수율을 높이는 길은 두지 않는다(구현명세 6장).
    """
    if by not in (FIN, CFO):
        raise DomainError("과제 초안은 경영관리 담당·임원이 고친다", 403)
    a = doc["assignments"].get(task_id)
    if a is None:
        raise DomainError(f"없는 과제: {task_id}", 404)
    if a["state"] != "DRAFT":
        raise DomainError("배정된 과제는 재배정으로만 바꾼다", 409)
    unknown = set(changes) - set(TASK_FIELDS)
    if unknown:
        raise DomainError(f"고칠 수 없는 칸: {', '.join(sorted(unknown))}", 422)
    before = {k: a[k] for k in changes}
    for k, v in changes.items():
        if k == "owner":
            v = _user(v)
        elif k == "collaborators":
            v = [u for u in (_user(x) for x in (v or [])) if u]
        elif k == "due_at" and v:
            v = _when(v, "제출기한")
        a[k] = v
    a["history"].append(
        {
            "at": doc["clock"],
            "state": "DRAFT",
            "by": by,
            "note": reason,
            "before": before,
            "after": {k: a[k] for k in changes},
        }
    )
    audit(doc, actor=by, action="task_draft_edited", task_id=task_id, fields=sorted(changes))


def check_assign(doc: dict) -> None:
    if not doc["minutes"]:
        raise DomainError("회의록 확인이 먼저다(CT36)", 409)
    drafts = [a for a in ordered(doc["assignments"]) if a["state"] == "DRAFT"]
    if not drafts:
        raise DomainError("배정할 과제가 없다 — 0건 배정은 할 수 없다", 409)
    rows = [f"{a['task_id']}: {', '.join(p)}" for a in drafts if (p := task_problems(a))]
    if rows:
        raise DomainError(
            "필수 항목이 빠진 과제가 있다 — 전건 배정을 보류했다: " + " / ".join(rows), 422
        )


def assign_tasks(doc: dict, *, memo: str, by: str) -> dict[str, Any]:
    """
    배정·통보(EV31-14~17) — 전건 검증 뒤 한 번에. 배정버전 1, 인수기한 6/30 12시. 실행 승인이
    아니다.
    돌려주는 값은 그림의 인수 갈래가 쓴다(배정 여부·책임자 이름·배정버전).
    """
    check_assign(doc)
    _require(by, CFO, "과제 배정")
    for a in ordered(doc["assignments"]):
        if a["state"] != "DRAFT":
            continue
        a.update(
            state="ASSIGNED",
            assignment_version=1,
            assigned_at=doc["clock"],
            assigned_by=by,
            accept_due=SCHEDULE["accept_due"],
        )
        a["history"].append(
            {"at": doc["clock"], "state": "ASSIGNED", "by": by, "note": memo, "version": 1}
        )
    doc["review"]["state"] = "TASKS_ASSIGNED"
    audit(
        doc,
        actor=by,
        action="tasks_assigned",
        tasks=[a["task_id"] for a in ordered(doc["assignments"])],
        event_code="EV31-14",
    )
    return assignment_outputs(doc)


def assignment_outputs(doc: dict) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for tid in TASK_NODES:
        a = doc["assignments"].get(tid)
        on = a is not None and a["state"] in ("ASSIGNED", "ACCEPTED", "RETURNED")
        out[f"{tid.lower()}_assigned"] = on
        out[f"{tid.lower()}_owner"] = name_of(a["owner"]) if on else ""  # type: ignore[index]
        out[f"{tid.lower()}_version"] = a["assignment_version"] if on else 0  # type: ignore[index]
    return out


def check_acceptance(doc: dict, task_id: str, args: dict[str, Any]) -> None:
    a = doc["assignments"].get(task_id)
    if a is None:
        raise DomainError(f"없는 과제: {task_id}", 404)
    if a["state"] != "ASSIGNED":
        raise DomainError(f"{task_id}는 인수 대기가 아니다 ({a['state']})", 409)
    if args.get("decision") not in ("인수", "반려"):
        raise DomainError("인수 또는 반려를 고른다", 422)
    if args["decision"] == "반려" and not _text(args, "reason"):
        raise DomainError("반려에는 사유가 필요하다", 422)
    version = args.get("version")
    if version not in (None, "") and int(version) != a["assignment_version"]:
        raise DomainError(
            f"본 배정버전({version})이 최신({a['assignment_version']})이 아니다 — "
            "새 버전을 인수한다",
            409,
        )


def accept_task(
    doc: dict, task_id: str, args: dict[str, Any], *, by: str, strict: bool = True
) -> None:
    """
    인수·반려(EV31-18~21) — **그 과제 책임자만**(타부서 403, 임원도 대신 못 한다). 구버전 인수는 새
    버전
    인수가 아니다(409). 반려는 사유와 함께 RETURNED — 임원이 고쳐 재배정한다(E32).
    """
    check_acceptance(doc, task_id, args)
    a = doc["assignments"][task_id]
    _require(by, a["owner"], f"{task_id} 인수", strict=strict)
    if args["decision"] == "인수":
        a.update(
            state="ACCEPTED",
            accepted_at=doc["clock"],
            accepted_by=by,
            accepted_version=a["assignment_version"],
        )
    else:
        a.update(state="RETURNED", returned_at=doc["clock"], return_reason=_text(args, "reason"))
    a["history"].append(
        {
            "at": doc["clock"],
            "state": a["state"],
            "by": by,
            "version": a["assignment_version"],
            "note": _text(args, "reason"),
        }
    )
    audit(
        doc,
        actor=by,
        action="task_accepted" if args["decision"] == "인수" else "task_returned",
        task_id=task_id,
        version=a["assignment_version"],
    )


def check_reassign(doc: dict, task_id: str, args: dict[str, Any]) -> None:
    a = doc["assignments"].get(task_id)
    if a is None or a["state"] != "RETURNED":
        raise DomainError(f"{task_id}는 반려된 과제가 아니다", 409)
    if not _text(args, "reason"):
        raise DomainError("변경 사유를 적는다", 422)
    owner = args.get("owner")
    if owner not in (None, "") and _user(owner) is None:
        raise DomainError(f"모르는 책임자: {owner}", 422)


def reassign_task(doc: dict, task_id: str, args: dict[str, Any], *, by: str) -> dict[str, Any]:
    """재배정 — 변경 사유와 전후값을 남기고 배정버전을 올린다. 원 반려·배정 이력은 그대로다."""
    check_reassign(doc, task_id, args)
    _require(by, CFO, f"{task_id} 재배정")
    a = doc["assignments"][task_id]
    changes: dict[str, Any] = {}
    if _text(args, "dependency"):
        changes["dependency"] = _text(args, "dependency")
    if _text(args, "deliverable"):
        changes["deliverable"] = _text(args, "deliverable")
    if args.get("collaborators"):
        extra = [u for u in (_user(x.strip()) for x in str(args["collaborators"]).split(",")) if u]
        changes["collaborators"] = list(dict.fromkeys([*a["collaborators"], *extra]))
    if args.get("owner") not in (None, ""):
        changes["owner"] = _user(args["owner"])
    before = {k: a[k] for k in changes}
    a.update(changes)
    if task_problems(a):
        raise DomainError(f"{task_id}: " + ", ".join(task_problems(a)), 422)
    a["assignment_version"] += 1
    a["state"] = "ASSIGNED"
    a["history"].append(
        {
            "at": doc["clock"],
            "state": "ASSIGNED",
            "by": by,
            "version": a["assignment_version"],
            "note": _text(args, "reason"),
            "before": before,
            "after": changes,
        }
    )
    audit(doc, actor=by, action="task_reassigned", task_id=task_id, version=a["assignment_version"])
    return {"owner": name_of(a["owner"]), "version": a["assignment_version"]}


def acceptance_rate(doc: dict) -> dict[str, Any]:
    """M39 — 현재 확정 배정 중 현재 버전 인수 비율. 배정 0건이면 N/A다(초안은 분모가 아니다)."""
    assigned = [a for a in doc["assignments"].values() if a["state"] != "DRAFT"]
    accepted = [
        a
        for a in assigned
        if a["state"] == "ACCEPTED" and a["accepted_version"] == a["assignment_version"]
    ]
    return {
        "assigned": len(assigned),
        "accepted": len(accepted),
        "rate": None if not assigned else str(Decimal(len(accepted)) / Decimal(len(assigned))),
    }


# ─────────────────────────── S44 종료·장면 4 인계 (U37 · CT39·CT40) ───────────────────────────


def completion_conditions(doc: dict) -> dict[str, Any]:
    """
    종료 판정(구현명세 1장) — 확정 보고에 유효한 확인·계산 검증, 열린 차단 0, 비차단 미확인의
    담당·기한·
    처리방향, 수용·조건부 수용 결론과 확인된 회의록, 배정 1건 이상의 현재 버전 전건 인수.
    """
    rep = frozen_report(doc)
    run = doc["runs"].get(rep["run_id"]) if rep else None
    rate = acceptance_rate(doc)
    pending = [
        a
        for a in ordered(doc["assignments"])
        if a["state"] != "DRAFT"
        and not (a["state"] == "ACCEPTED" and a["accepted_version"] == a["assignment_version"])
    ]
    items = [
        ("report", "확정 보고버전", rep is not None),
        ("calc", "계산 검증 통과", bool(run and run["result"]["passed"])),
        (
            "confirm",
            "부서 확인 유효(영업·구매·생산)",
            all(dept_status(doc, d)["state"] == "RESPONDED" for d in DEPTS),
        ),
        (
            "blocking",
            "열린 차단 쟁점 0건",
            not any(q["state"] == "BLOCKING" for q in doc["questions"].values()),
        ),
        (
            "followups",
            "비차단 미확인의 담당·기한·처리방향",
            all(q["owner"] and q["due_at"] and q["treatment"] for q in open_followups(doc)),
        ),
        (
            "decision",
            "수용 또는 조건부 수용 결론",
            (doc["decision"] or {}).get("outcome") in ("ACCEPTED", "CONDITIONAL_ACCEPT"),
        ),
        (
            "minutes",
            "확인된 회의록",
            any(m["state"] == "CONFIRMED" for m in doc["minutes"].values()),
        ),
        ("assigned", "배정 과제 1건 이상", rate["assigned"] > 0),
        (
            "accepted",
            f"현재 배정버전 전건 인수 ({rate['accepted']}/{rate['assigned']})",
            rate["assigned"] > 0 and not pending,
        ),
    ]
    blocking = [label for key, label, ok in items if not ok and key != "accepted"]
    blocking += [f"{a['task_id']} 현재 배정버전 미인수 ({name_of(a['owner'])})" for a in pending]
    return {
        "items": [{"id": k, "label": label, "ok": ok} for k, label, ok in items],
        "met": all(ok for _k, _l, ok in items),
        "blocking": blocking,
        "rate": rate,
    }


def check_complete(doc: dict) -> None:
    if doc["handoff"] is not None:
        raise DomainError("이미 완료된 업무다 — 완료본은 바꾸지 않는다", 409)
    check = completion_conditions(doc)
    if not check["met"]:
        raise PrerequisiteError(
            "종료 조건 미충족: " + ", ".join(check["blocking"]),
            check["blocking"],
            "COMPLETION_PREREQUISITE_FAILED",
        )


def business_hours(start: str, end: str) -> Decimal:
    """CAL-DEMO01 — 평일 09~18시, 주말 제외, 휴일·점심 공제 없음. 시간 단위 Decimal."""
    a, b = parse_at(start), parse_at(end)
    total = timedelta(0)
    d = a.date()
    while d <= b.date():
        if d.weekday() < 5:
            open_, close = (datetime(d.year, d.month, d.day, h, tzinfo=KST) for h in (9, 18))
            lo, hi = max(a, open_), min(b, close)
            if hi > lo:
                total += hi - lo
        d += timedelta(days=1)
    return Decimal(int(total.total_seconds())) / Decimal(3600)


def complete_scene(doc: dict, *, memo: str, by: str) -> str:
    """
    장면 완료(EV31-22) — 조건을 서버가 다시 검증하고 HANDOFF31과 완료를 **함께** 저장한다. Risk
    OPEN·
    Forecast REVIEW_PENDING·Target UNCHANGED는 그대로다(T39). 인계는 복사가 아니라 고정 버전의
    연결이다.
    """
    check_complete(doc)
    _require(by, FIN, "업무 종료")
    rep = frozen_report(doc)
    mins = max(doc["minutes"].values(), key=lambda m: m["seq"])
    dec = doc["decision"]
    started = doc["review"]["started_at"]
    doc["handoff"] = {
        "handoff_id": HANDOFF_ID,
        "review_id": REVIEW_ID,
        "report_version": rep["report_id"],  # type: ignore[index]
        "analysis_run": rep["run_id"],  # type: ignore[index]
        "minutes_version": mins["minutes_id"],
        "decision": dec["decision_id"],
        "outcome": dec["outcome"],
        "open_questions": [q["question_id"] for q in open_followups(doc)],
        "accepted_tasks": [
            {
                "task_id": a["task_id"],
                "version": a["assignment_version"],
                "accepted_at": a["accepted_at"],
                "owner": a["owner"],
            }
            for a in ordered(doc["assignments"])
        ],
        "excluded_candidates": [
            {
                "candidate_id": c["candidate_id"],
                "reason": c["decision_reason"],
                "evidence_ref": c["evidence_ref"],
            }
            for c in ordered(doc["candidates"])
            if c["decision"] == "EXCLUDE_THIS_REVIEW"
        ],
        "next_meeting": {"meeting_id": NEXT_MEETING_ID, "at": SCHEDULE["next_meeting_at"]},
        "analysis_due": SCHEDULE["submit_due"],
        "consolidation_due": SCHEDULE["consolidate_due"],
        "basis": "F02+EXT28-v1, C02-APP01, FC01/FC28-v1",
        "risk_status": "OPEN",
        "forecast_status": "REVIEW_PENDING",
        "target_status": "UNCHANGED",
        "comparison_rule": (
            "잔여2027 / 향후12개월 구분 — 일회성·반복·시작일·중복효과·가정·제약 명시"
        ),
        "pending_revisions": [r["report_id"] for r in doc["revisions"]],
        "as_of": doc["clock"],
        "completed_by": by,
        "memo": memo,
        # M40 — 실제 투입시간이 아니다. 경과와 CAL-DEMO01 영업시간을 분 단위로 둔다.
        "elapsed_minutes": int((parse_at(doc["clock"]) - parse_at(started)).total_seconds()) // 60,
        "business_minutes": int(business_hours(started, doc["clock"]) * 60),
    }
    doc["review"].update(state="SC03_COMPLETED", completed_at=doc["clock"])
    audit(doc, actor=by, action="SC03_COMPLETED", handoff=HANDOFF_ID, event_code="EV31-22")
    return HANDOFF_ID


# ─────────────────────────── E34 새 전망 버전 ───────────────────────────


def new_forecast(doc: dict, seed: Seed, *, reason: str, by: str) -> str:
    """
    E34 — 자료 확정 뒤 새 전망(b 7월 8,800 → 8,700). **별도 실행·별도 보고버전**이고 확정본은
    그대로다.
    기본 F02를 덮지 않는다. 임원 재확인 전에는 회의가 확정본으로 간다(REVISION_PENDING).
    """
    _require(by, FIN, "새 전망 입력")
    if doc["case_id"] != "E34":
        raise DomainError("새 전망 버전은 검수용 변형이다 — E34 사례 실행에서만 받는다", 409)
    rep = frozen_report(doc)
    if rep is None:
        raise DomainError("확정된 보고자료가 없다 — 확정 뒤의 변경을 재현하는 사례다", 409)
    if not reason.strip():
        raise DomainError("변경 근거를 적는다", 422)
    base = doc["runs"][rep["run_id"]]
    keep = doc["calc_override"]["fixed_multiplier"]
    doc["rows_override"] = [["2027-07-01", "A-b", 8700]]
    result = calc.integrated(
        seed.numbers,
        price_option(doc),
        rows=[
            replace(r, f02=8700)
            if (r.period.isoformat(), r.model_id) == ("2027-07-01", "A-b")
            else r
            for r in seed.numbers.rows
        ],
        fixed_multiplier=keep,
    )
    run_id = f"RUN-SC03-E34-{len(doc['revisions']) + 1:02d}"
    doc["runs"][run_id] = {
        "run_id": run_id,
        "seq": _seq(doc["runs"]),
        "review_id": REVIEW_ID,
        "created_at": doc["clock"],
        "created_by": by,
        "memo": reason,
        "sources": ["F02-E34 (b 7월 8,700)", doc["sc02"]["price"]["run_id"]],
        "result": result,
        "status": result["status"],
        "variant": "E34",
    }
    report_id = f"REP31-v{int(rep['report_id'].split('v')[1]) + 1}-E34"
    doc["revisions"].append(
        {
            "report_id": report_id,
            "run_id": run_id,
            "base_report": rep["report_id"],
            "status": "REVISION_PENDING",
            "reason": reason,
            "changes": calc.compare(base["result"], result),
            "created_at": doc["clock"],
            "created_by": by,
            "reconfirm": ["경영관리임원 재확인", "영업 재확인"],
        }
    )
    doc["rows_override"] = []  # 기본 분석의 물량은 그대로다 — 새 버전은 그 실행에만 있다
    audit(doc, actor=by, action="forecast_revision", report=report_id, run_id=run_id)
    return report_id


# ─────────────────────────── Agent (구현명세 12장) ───────────────────────────


def agent_draft(doc: dict, *, kind: str) -> str:
    """
    초안 하나 — 같은 입력이면 이전 성공 초안을 다시 쓴다. 실패해도 업무는 계속된다(E36 — 수동 작성).
    초안에는 draft_id·source_version·generated_at·prompt_version·review_status가 있다.
    """
    if kind not in agent.KINDS:
        raise DomainError(f"모르는 Agent 지원: {kind}", 422)
    record: dict[str, Any] = {
        "output_id": f"{kind}-{len(doc['agent_outputs']) + 1:03d}",
        "seq": _seq(doc["agent_outputs"]),
        "kind": kind,
        "prompt_version": agent.PROMPT_VERSION,
        "mode": doc.get("agent_mode", "mock"),
        "created_at": doc["clock"],
        "status": "FAILED",
        "draft": None,
        "errors": [],
        "source_version": None,
        "input_hash": None,
        "adopted_by": None,
        "adopted_at": None,
        "review_status": "UNREVIEWED",
    }
    try:
        payload = agent.build_input(doc, kind)
    except agent.AgentFailure as exc:
        record["errors"].append(str(exc))
        payload = None
    if payload is not None:
        digest = agent.input_hash(payload)
        record.update(source_version=payload["run_id"], input_hash=digest)
        for o in ordered(doc["agent_outputs"]):
            if o["kind"] == kind and o["input_hash"] == digest and o["status"] == "SUCCEEDED":
                return o["output_id"]
        for attempt in (1, 2):
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
    doc["agent_outputs"][record["output_id"]] = record
    audit(
        doc,
        actor="system",
        action="agent_draft",
        output_id=record["output_id"],
        status=record["status"],
    )
    return record["output_id"]


def adopt_agent(doc: dict, output_id: str, *, actor: str) -> None:
    """채택 기록 — 원 초안은 그대로, 검토자·시각만. 결론·인수를 대신하지 않는다."""
    if actor != FIN:
        raise DomainError("초안 채택은 경영관리 담당이 한다", 403)
    o = doc["agent_outputs"].get(output_id)
    if o is None or o["status"] != "SUCCEEDED":
        raise DomainError("채택할 초안이 없다", 404)
    o.update(adopted_by=actor, adopted_at=doc["clock"], review_status="ADOPTED")
    audit(doc, actor=actor, action="agent_adopted", output_id=output_id)


# ─────────────────────────── 작업 → 업무 효과 (기록 작업의 몸통) ───────────────────────────

#: 결재 뒤의 기록 작업 → 결재 노드. 같은 작업이 여러 결재 뒤에 있으면 입력의 `node_id`로 가른다.
RECORDS = (
    "run_analysis",
    "fix_calc",
    "request_confirmation",
    "record_confirmation",
    "record_revision",
    "record_gap",
    "judge_questions",
    "freeze_report",
    "distribute_report",
    "open_meeting",
    "decide_review",
    "confirm_minutes",
    "assign_tasks",
    "accept_task",
    "reassign_task",
    "complete_scene",
)


def _slots(args: dict[str, Any]) -> dict[str, Any]:
    """판단 폼의 평평한 칸(q31_blocking…) → 쟁점별 묶음."""
    out = {}
    for slot in QUESTION_SLOTS:
        p = slot.lower()
        out[slot] = {
            "blocking": args.get(f"{p}_blocking"),
            "owner": args.get(f"{p}_owner"),
            "due": args.get(f"{p}_due"),
            "treatment": args.get(f"{p}_treatment"),
        }
    return out


def _candidates(args: dict[str, Any]) -> dict[str, Any]:
    return {
        cid: {
            "decision": args.get(f"{cid.lower()}_decision"),
            "reason": args.get(f"{cid.lower()}_reason"),
        }
        for cid in CANDIDATES
    }


def check(doc: dict, operation: str, args: dict[str, Any]) -> None:
    """
    기록 작업의 사전 검사 — **부수 효과가 없다**. 화면 답(내장·대리 답)은 답을 넣기 전에, 기록
    작업은
    적기 전에 같은 검사를 한다(Studio·Center 콘솔 답은 NowView 사전 검사를 거치지 않는다).
    """
    if operation == "fix_calc":
        latest = latest_run(doc)
        if latest is None or latest["result"]["passed"]:
            raise DomainError("정정할 계산 오류가 없다", 409)
    elif operation == "request_confirmation":
        run = latest_run(doc)
        if run is None or not run["result"]["passed"] or current_draft(doc) is None:
            raise DomainError("정합이 확인된 분석 초안이 없다(CT33)", 409)
        # 형식도 여기서 본다 — 기록 작업에서만 보면 대리 답은 통과하고 기록이 422로 거절되어
        # 같은 결재로 조용히 돌아왔다(화면 직접 진행 실측: 기본값에 이어 친 「…+09:006/28 18:00」)
        _when(args.get("due") or SCHEDULE["confirm_due"], "회신기한")
    elif operation == "record_confirmation":
        check_confirmation(doc, str(args.get("dept") or ""), args)
    elif operation == "record_revision":
        check_revision(doc, args)
    elif operation == "record_gap":
        check_gap(doc, args)
    elif operation == "judge_questions":
        check_judgement(doc, _slots(args))
    elif operation == "freeze_report":
        problems = freeze_problems(doc)
        if problems:
            raise DomainError("자료를 확정할 수 없다: " + ", ".join(problems), 409)
    elif operation == "distribute_report":
        if frozen_report(doc) is None:
            raise DomainError("확정된 보고자료가 없다", 409)
    elif operation == "open_meeting":
        check_open_meeting(doc)
    elif operation == "decide_review":
        check_decision(doc, {**args, "candidates": _candidates(args)})
    elif operation == "confirm_minutes":
        if doc["decision"] is None or doc["decision"]["outcome"] == "REWORK_REQUIRED":
            raise DomainError("확인할 검토 결론이 없다", 409)
    elif operation == "assign_tasks":
        check_assign(doc)
    elif operation == "accept_task":
        check_acceptance(doc, str(args.get("task_id") or ""), args)
    elif operation == "reassign_task":
        check_reassign(doc, str(args.get("task_id") or ""), args)
    elif operation == "complete_scene":
        check_complete(doc)


def apply(
    doc: dict, seed: Seed, operation: str, args: dict[str, Any], *, by: str, strict: bool
) -> dict[str, Any]:
    """기록 작업 하나의 업무 효과. 검사는 `check`가 먼저 했다. 출력은 그림의 `output` 대응이
    쓴다."""
    if operation == "run_analysis":
        out = run_analysis(doc, seed, by=by, memo=_text(args, "memo"))
        return {"run_id": out["run_id"], "passed": out["passed"]}
    if operation == "fix_calc":
        out = fix_calc(doc, seed, note=_text(args, "note"), by=by)
        return {"run_id": out["run_id"], "passed": out["passed"]}
    if operation == "request_confirmation":
        request_confirmation(doc, due=args.get("due"), memo=_text(args, "memo"), by=by)
        return {"report_id": current_draft(doc)["report_id"]}  # type: ignore[index]
    if operation == "record_confirmation":
        record_confirmation(doc, str(args["dept"]), args, by=by, strict=strict)
        return {}
    if operation == "record_revision":
        return {"report_id": record_revision(doc, args, by=by)}
    if operation == "record_gap":
        record_gap(doc, args, by=by, strict=strict)
        return {}
    if operation == "judge_questions":
        return judge_questions(doc, _slots(args), by=by)
    if operation == "freeze_report":
        return {"report_id": freeze_report(doc, opinion=_text(args, "opinion"), by=by)}
    if operation == "distribute_report":
        distribute(doc, seed, memo=_text(args, "memo"), by=by)
        return {}
    if operation == "open_meeting":
        open_meeting(doc, seed, summary=_text(args, "summary"), by=by)
        return {}
    if operation == "decide_review":
        out = decide_review(doc, seed, {**args, "candidates": _candidates(args)}, by=by)
        return {"rework": out["rework"]}
    if operation == "confirm_minutes":
        return {"minutes_id": confirm_minutes(doc, seed, opinion=_text(args, "opinion"), by=by)}
    if operation == "assign_tasks":
        return assign_tasks(doc, memo=_text(args, "memo"), by=by)
    if operation == "accept_task":
        accept_task(doc, str(args["task_id"]), args, by=by, strict=strict)
        return {}
    if operation == "reassign_task":
        return reassign_task(doc, str(args["task_id"]), args, by=by)
    if operation == "complete_scene":
        return {"handoff_id": complete_scene(doc, memo=_text(args, "memo"), by=by)}
    raise DomainError(f"모르는 작업: {operation}", 404)  # pragma: no cover


# ─────────────────────────── 업무 (공통 업무함) ───────────────────────────


def tasks_of(doc: dict, task_type: str) -> list[dict]:
    return [t for t in ordered(doc["tasks"]) if t["type"] == task_type]


def _active_task(doc: dict, task_type: str) -> dict | None:
    return next((t for t in reversed(tasks_of(doc, task_type)) if t["status"] != "COMPLETED"), None)


def task_for_node(doc: dict, node_id: str) -> dict | None:
    spec = NODE_ROLES.get(node_id)
    return _active_task(doc, spec["task"]) if spec else None


def assignee_of(doc: dict, node_id: str) -> str:
    spec = NODE_ROLES[node_id]
    if "owner_of" in spec:
        a = doc["assignments"].get(spec["owner_of"])
        if a is not None and a.get("owner"):
            return a["owner"]
    return user_for_role(spec["role"])


def _due(doc: dict, node_id: str) -> str:
    spec = NODE_ROLES[node_id]
    due = spec["due"]
    if due == "analysis":
        return (
            doc["sc02"]["handoff"].get("sc03_due_at")
            or due_at(parse_at(doc["clock"]), 2).isoformat()
        )
    if due == "confirm":
        return (doc["confirmation"] or {}).get("due_at") or SCHEDULE["confirm_due"]
    if isinstance(due, str):
        target = SCHEDULE[due]
        # 정해진 시각이 이미 지났으면(되돌아온 업무) 다음 영업일 18시다
        if parse_at(target) > parse_at(doc["clock"]):
            return target
        due = 1
    return due_at(parse_at(doc["clock"]), int(due)).isoformat()


def _open_task(doc: dict, node_id: str, *, request_id: str | None, late: bool = False) -> dict:
    spec = NODE_ROLES[node_id]
    previous = tasks_of(doc, spec["task"])
    task_id = f"TASK-{spec['task']}" + (f"-{len(previous) + 1}" if previous else "")
    assignee = assignee_of(doc, node_id)
    task = doc["tasks"][task_id] = {
        "task_id": task_id,
        "seq": _seq(doc["tasks"]),
        "type": spec["task"],
        "node_id": node_id,
        "request_id": request_id,
        "assigned_to": assignee,
        "assigned_at": doc["clock"],
        "due_at": _due(doc, node_id),
        "status": "ASSIGNED",
        "completed_at": None,
        "completed_by": None,
        "reopens": previous[-1]["task_id"] if previous else None,
        "opened_late": late,
        "history": [
            {
                "at": doc["clock"],
                "status": "ASSIGNED",
                "by": "system",
                "note": "바깥 실행 — 대기가 열린 시각을 모른다(결정 기록 시점에 만듦)"
                if late
                else None,
            }
        ],
    }
    audit(doc, actor="system", action="task_assigned", task_id=task_id, assigned_to=assignee)
    return task


def sync_tasks(doc: dict, pendings: dict[str, dict[str, Any]]) -> None:
    """BPM의 사람 대기 → 업무. 같은 대기면 새로 만들지 않는다. 끝난 업무는 다시 쓰지 않는다."""
    nodes = list(NODE_ROLES)
    for request_id, p in sorted(
        pendings.items(),
        key=lambda kv: nodes.index(kv[1]["node_id"]) if kv[1]["node_id"] in nodes else 99,
    ):
        if p["node_id"] not in NODE_ROLES:
            continue
        task = task_for_node(doc, p["node_id"])
        if task is not None and task["request_id"] == request_id:
            continue
        if task is not None and task["request_id"] is None:
            task["request_id"] = request_id  # 늦게 연 업무에 대기를 잇는다
            continue
        if task is not None:
            # 끝나지 않은 업무에 같은 결재가 새 id로 왔다 — 기록이 거절되어 그림이 같은 결재로
            # 돌아온 것이다(오류 경계). 새 업무를 열면 앞 업무가 영영 「진행」으로 남아 끝난 일에
            # 지연 알림이 생겼다(화면 직접 진행 실측) — 같은 업무에 잇는다.
            task["request_id"] = request_id
            task["history"].append(
                {
                    "at": doc["clock"],
                    "status": task["status"],
                    "by": "system",
                    "note": "기록이 거절되어 같은 결재가 다시 열렸다",
                }
            )
            continue
        _open_task(doc, p["node_id"], request_id=request_id)


def ensure_task(doc: dict, node_id: str) -> None:
    """결정이 기록되는데 업무가 없으면 지금 연다 — 늦게 열었다고 표시한다(Studio, 장면 1·2와
    같다)."""
    if node_id in NODE_ROLES and task_for_node(doc, node_id) is None:
        _open_task(doc, node_id, request_id=None, late=True)


def note_rejection(doc: dict, node_id: str, *, status: int, reason: str) -> None:
    """
    기록 작업이 거절한 답의 사유를 그 업무에 남긴다 — 화면이 다시 열린 결재 폼 위에 보인다.
    Center·Studio 콘솔 답은 사전 검사를 거치지 않으므로 기록이 막는 수밖에 없는데, 그림은 같은
    결재로 돌아갈 뿐 사유를 폼에 싣지 않는다(4.5).
    """
    task = task_for_node(doc, node_id)
    if task is not None:
        task["rejected"] = {"at": doc["clock"], "status": status, "reason": reason}


def complete_task(doc: dict, node_id: str, *, actor: str) -> None:
    task = task_for_node(doc, node_id)
    if task is None:
        return
    task.pop("rejected", None)
    task.update(status="COMPLETED", completed_at=doc["clock"], completed_by=actor)
    task["history"].append({"at": doc["clock"], "status": "COMPLETED", "by": actor, "note": None})
    audit(doc, actor=actor, action="task_completed", task_id=task["task_id"])


def check_actor(doc: dict, node_id: str, actor: str) -> None:
    """역할·담당 검사 — 인수는 그 과제 책임자만, 나머지는 역할표의 사람이다(403)."""
    user = USERS.get(actor)
    if user is None:
        raise DomainError(f"모르는 사용자: {actor}", 403)
    spec = NODE_ROLES[node_id]
    if "owner_of" in spec:
        owner = assignee_of(doc, node_id)
        if actor != owner:
            raise DomainError(f"{spec['owner_of']} 책임자({name_of(owner)})만 인수·반려한다", 403)
        return
    if user["role"] != spec["role"]:
        raise DomainError(f"{spec['role']}만 할 수 있다 (현재 {user['role']})", 403)


def is_overdue(due: str | None, clock: str) -> bool:
    return due is not None and parse_at(clock) > parse_at(due)


def raise_overdue_alerts(doc: dict) -> list[dict]:
    """
    기한 초과 알림 — 업무(미완료)·과제 인수(미인수)·과제 제출(미제출, E37). 같은 대상·기한에 한
    번만.
    **지연은 장면 완료를 취소하지 않는다** — 후속 준비에서 관리한다(CT39).
    """
    alerts = doc["alerts"]
    seen = {(a["target"], a["due_at"]) for a in alerts}
    targets: list[tuple[str, str, list[str], str]] = []
    for t in ordered(doc["tasks"]):
        if t["status"] != "COMPLETED" and is_overdue(t["due_at"], doc["clock"]):
            targets.append(
                (
                    t["task_id"],
                    t["due_at"],
                    [t["assigned_to"], REVIEWER.get(t["type"])],
                    "업무 미완료",
                )
            )
    for a in ordered(doc["assignments"]):
        if a["state"] in ("ASSIGNED", "RETURNED") and is_overdue(a.get("accept_due"), doc["clock"]):
            targets.append(
                (
                    f"{a['task_id']}:accept",
                    a["accept_due"],
                    [a["owner"], FIN],
                    f"{a['task_id']} 인수 지연",
                )
            )
        if (
            a["state"] == "ACCEPTED"
            and a["submitted_at"] is None
            and is_overdue(a["due_at"], doc["clock"])
        ):
            targets.append(
                (
                    f"{a['task_id']}:submit",
                    a["due_at"],
                    [a["owner"], FIN],
                    f"{a['task_id']} 분석 미제출 — 지연",
                )
            )
    created = []
    for target, due, to, what in targets:
        if (target, due) in seen:
            continue
        alert = {
            "alert_id": f"ALERT-{len(alerts) + 1:03d}",
            "kind": "OVERDUE",
            "target": target,
            "due_at": due,
            "at": doc["clock"],
            "to": [u for u in dict.fromkeys(to) if u],
            "message": f"{what} — 기한 {due[5:16].replace('T', ' ')} 초과",
        }
        alerts.append(alert)
        created.append(alert)
        audit(doc, actor="system", action="overdue_alert", target=target, to=alert["to"])
    return created


def delayed_tasks(doc: dict) -> list[str]:
    """M40 — 제출기한이 지났는데 미제출인 과제(E37). 완료된 장면과 따로 본다."""
    return [
        a["task_id"]
        for a in ordered(doc["assignments"])
        if a["state"] == "ACCEPTED"
        and a["submitted_at"] is None
        and is_overdue(a["due_at"], doc["clock"])
    ]


# ─────────────────────────── 상태 (구현명세 10장) ───────────────────────────


def statuses(doc: dict) -> dict[str, Any]:
    """독립 배지 — 검토건 · 결론 · 위험 · 공식 전망 · 목표. 장면 완료와 위험 해소는 다른 말이다."""
    r = doc["review"]
    return {
        "review": r["state"],
        "outcome": r["outcome"],
        "risk": r["risk"],
        "forecast": r["forecast"],
        "target": r["target"],
        "scene": "SC03_COMPLETED"
        if r["state"] == "SC03_COMPLETED"
        else ("PENDING" if r["started_at"] is None else "ACTIVE"),
    }


#: Studio는 끝을 작업 호출로만 안다 — 이 작업이 기록되면 흐름이 끝난다.
def ends_flow(operation: str) -> bool:
    return operation == "complete_scene"


__all__ = ["CASES", "NODE_ROLES", "RECORDS", "SEED_ID", "check", "apply"]
