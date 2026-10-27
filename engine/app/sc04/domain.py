"""
SC04 업무 기록 — 수익성 개선 대응안 검토와 실행 승인(MR-2706-01, 대표 주재 월간 경영회의 MT41).

장면 1~3과 같은 원칙이다: **한 데모 실행 = 문서 하나**, 순수 함수, 저장·BPM은 `process.py`. 데모
실행 id는
장면 1~3과 같다. 장면 4는 **장면 3 인계(HANDOFF31)에서 시작한다** — 그 결과는 시작할 때
스냅샷(`sc03`)으로
둔다. 장면 3을 초기화해도 장면 4의 근거는 그 시점의 것이다.

**상태 축은 서로 독립이다**(구현명세 11장): 장면 상태(`review.state`) · 분석 결과 · 계산·보고 ·
대안 결정 ·
인수 · 조건(책임 인수와 이행이 따로) · Risk(OPEN) · Forecast(REVIEW_PENDING) · Target(UNCHANGED).
이벤트의
결과 상태를 장면 상태에 대입하지 않는다 — EXCLUDED는 AT33 검토 결과이지 과제 상태가 아니다.

* 확정 보고본(REP41-v1)·판단본(DEC41-v2)·승인서·회의록·완료 인계는 **고치지 않는다**. 바뀌면 새
  버전이다.
* 업무 효과는 결재 뒤의 「… 기록」 작업이 낸다(장면 1~3 N1과 같다). 각 작업은 **검사가 부수 효과보다
  먼저**다 — `check(doc, operation, args)`가 같은 규칙을 화면 답의 사전 검사와 기록 작업 양쪽에서
  건다.
* 추천·판단·승인·인수는 사람만 한다. 계산은 `calc`, Agent는 초안까지다(P413). 승인 효과는 예상치이고
  실적이 아니다 — 장면을 끝내도 위험·전망·목표는 그대로다(P412).
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime
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
from app.sc04 import agent, calc
from app.sc04.seed import SEED_ID, Seed, kst

REVIEW_ID = "MR-2706-01"
SOURCE_HANDOFF = "HANDOFF31"
MEETING_ID = "MT41"
HANDOFF_ID = "HANDOFF41"
REPORT_ID = "REP41-v1"

FIN, CFO, FINLEAD, CEO = "u-fin", "u-fin-exec", "u-fin-lead", "u-ceo"
PROD_LEAD, BUY_LEAD, SALES_LEAD = "u-prod-lead", "u-buy-lead", "u-sales-lead"
PROD_EXEC, BUY_EXEC, SALES_EXEC = "u-prod-exec", "u-buy-exec", "u-sales-exec"

#: 데이터의 가상 계정 → NowView 사용자(SC04계약 「행위자」). 실무 계정과 임원 계정은 다른 사람이다.
ACCOUNTS = {
    "USR-FIN": FIN,
    "USR-CFO": CFO,
    "USR-PROD": PROD_LEAD,
    "USR-BUY": BUY_LEAD,
    "USR-SALES": SALES_LEAD,
    "USR-FINLEAD": FINLEAD,
    "USR-CEO": CEO,
    "EX-PROD": PROD_EXEC,
    "EX-BUY": BUY_EXEC,
    "EX-SALES": SALES_EXEC,
}

#: 장면 3 분석과제 → 장면 4 분석 결과(구현명세 1장 「장면3와의 연속성」). 작성은 부서 책임자,
#: 확인은 담당 임원.
#: AT33은 검토 후 제외(RES43) — 실행과제를 만들지 않는다. AT34는 기존 부족 원인과 추가 발굴
#: 지시(DIR41)로.
RESULTS: dict[str, dict[str, Any]] = {
    "AT31": {
        "result_id": "RES41",
        "alts": ["ALT41"],
        "writer": PROD_LEAD,
        "confirmer": PROD_EXEC,
        "question": "Q31",
    },
    "AT32": {
        "result_id": "RES42",
        "alts": ["ALT42", "ALT43"],
        "writer": BUY_LEAD,
        "confirmer": BUY_EXEC,
        "question": None,
    },
    "AT33": {
        "result_id": "RES43",
        "alts": ["EXCL44"],
        "writer": SALES_LEAD,
        "confirmer": SALES_EXEC,
        "question": None,
    },
    "AT34": {
        "result_id": "RES44",
        "alts": [],
        "writer": FINLEAD,
        "confirmer": CFO,
        "question": "Q32",
    },
}
ALTS = ("ALT41", "ALT42", "ALT43")
EXCLUDED_ALT = "EXCL44"
#: 대안 → 실행 책임 임원·실무 담당(SC04예산과제). 실무 담당 지정은 임원 책임을 대체하지 않는다.
OWNERS = {"ALT41": PROD_EXEC, "ALT42": BUY_EXEC, "ALT43": BUY_EXEC}
WORKERS = {"ALT41": PROD_LEAD, "ALT42": BUY_LEAD, "ALT43": BUY_LEAD}
#: 인수 대상 → 인수·보완 노드. TOTAL은 전체 책임(DIR41 포함) — 반려 대신 그대로 인수한다.
ACCEPT_NODES = {
    "ACT41": ("Accept_ACT41", "Revise_ACT41"),
    "ACT42": ("Accept_ACT42", "Revise_ACT42"),
    "ACT43": ("Accept_ACT43", "Revise_ACT43"),
    "SUP41": ("Accept_SUP41", "Revise_SUP41"),
    "TOTAL": ("Accept_Overall", None),
}
#: MT41 참석 — 대표 주재, 경영관리 임원 보고, 담당 임원과 경영관리 담당(SC04회의).
ATTENDEES = (CEO, CFO, FIN, PROD_EXEC, BUY_EXEC, SALES_EXEC)
DECISIONS = {
    "승인": "APPROVED",
    "조건부승인": "CONDITIONAL",
    "보류": "HOLD",
    "미승인": "REJECTED",
}


def _at(y: int, mo: int, d: int, h: int, mi: int = 0) -> str:
    return datetime(y, mo, d, h, mi, tzinfo=KST).isoformat()


#: 시연 일정(구현명세 16장·SC04예산과제·조건지시) — 2027년 가상 업무 일정이다.
SCHEDULE = {
    "start_at": _at(2027, 7, 1, 8, 59),  # 초기 시점(장면 3 인계만 보인다)
    "submit_due": _at(2027, 7, 6, 18),  # 분석 결과 제출
    "verify_due": _at(2027, 7, 7, 18),  # 비용·중복 검증
    "consolidate_due": _at(2027, 7, 8, 18),  # 경영관리 취합·보고본
    "meeting_at": _at(2027, 7, 12, 10),  # MT41 대표 주재 월간회의
    "meeting_end": _at(2027, 7, 12, 12),
    "approval_due": _at(2027, 7, 12, 18),  # 승인서·회의록 확정
    "accept_due": _at(2027, 7, 13, 12),  # 책임 인수
    "complete_due": _at(2027, 7, 13, 18),
    "plan_due": _at(2027, 7, 16, 18),  # 장면 5 상세 계획 제출(기본값)
    "condition_due": _at(2027, 8, 20, 18),  # CON41·SUP41
    "discovery_due": _at(2027, 8, 9, 10),  # DIR41 후속 보고
}

#: 시연 사례 — BASE와 E 사례는 **별도 데모 실행**이다(구현명세 16장: 기본 결과와 섞지 않는다).
#: E406(조건이 남은 완료)은 기본 시연의 정상 결말이고, E407(예산 위임 조회)은 조회 화면이다 — 실행
#: 사례가
#: 아니다. 권한·버전(T408·T409·T413)은 엔진 시험으로 잠근다.
CASES: dict[str, str] = {
    "BASE": "기본 시연",
    "E401": "E401 감가상각비 절감 오인 → 검증 차단",
    "E402": "E402 구매 효과 중복 → 보고 확정 차단",
    "E403": "E403 대체 공급업체 능력 미확인 → 보류",
    "E404": "E404 총괄 한도·계획기한 누락 → 승인 불가",
    "E405": "E405 ACT43 반려 → 보완·재인수",
    "E408": "E408 Agent 초안 실패 → 수동 작성",
}

#: BPMN 사람 노드 → 업무 종류·역할·기한. `due`는 SCHEDULE 키 또는 영업일 수다. `owner_of`가 있으면
#: 담당은
#: 역할표가 아니라 그 대상의 책임자다(인수 · 검증 보완).
NODE_ROLES: dict[str, dict[str, Any]] = {
    "Submit_AT31": {"task": "SUBMIT_AT31", "role": "생산팀장", "due": "submit_due"},
    "Confirm_AT31": {"task": "CONFIRM_AT31", "role": "생산임원", "due": "submit_due"},
    "Submit_AT32": {"task": "SUBMIT_AT32", "role": "구매팀장", "due": "submit_due"},
    "Confirm_AT32": {"task": "CONFIRM_AT32", "role": "구매임원", "due": "submit_due"},
    "Submit_AT33": {"task": "SUBMIT_AT33", "role": "영업팀장", "due": "submit_due"},
    "Confirm_AT33": {"task": "CONFIRM_AT33", "role": "영업임원", "due": "submit_due"},
    "Submit_AT34": {"task": "SUBMIT_AT34", "role": "경영관리팀장", "due": "submit_due"},
    "Confirm_AT34": {"task": "CONFIRM_AT34", "role": "경영관리임원", "due": "submit_due"},
    "Verify_Effects": {"task": "VERIFY", "role": "경영관리담당", "due": "verify_due"},
    "Correct_Effects": {
        "task": "CORRECT",
        "role": "담당임원",
        "due": "verify_due",
        "owner_of": "rework",
    },
    "Recommend": {"task": "RECOMMEND", "role": "경영관리임원", "due": "consolidate_due"},
    "Freeze_Report": {"task": "FREEZE", "role": "경영관리임원", "due": "consolidate_due"},
    "Report_Meeting": {"task": "REPORT", "role": "경영관리임원", "due": "meeting_end"},
    "Draft_Decision": {"task": "DECISION_DRAFT", "role": "경영관리담당", "due": "meeting_end"},
    "Confirm_Decision": {"task": "DECISION_CONFIRM", "role": "경영관리임원", "due": "meeting_end"},
    "Decide": {"task": "DECIDE", "role": "대표이사", "due": "meeting_end"},
    "Draft_Approval": {"task": "APPROVAL_DRAFT", "role": "경영관리담당", "due": "approval_due"},
    "Finalize_Approval": {"task": "APPROVE", "role": "대표이사", "due": "approval_due"},
    "Register_Actions": {"task": "REGISTER", "role": "경영관리담당", "due": "approval_due"},
    "Accept_ACT41": {
        "task": "ACCEPT_ACT41",
        "role": "생산임원",
        "due": "accept_due",
        "owner_of": "ACT41",
    },
    "Accept_ACT42": {
        "task": "ACCEPT_ACT42",
        "role": "구매임원",
        "due": "accept_due",
        "owner_of": "ACT42",
    },
    "Accept_ACT43": {
        "task": "ACCEPT_ACT43",
        "role": "구매임원",
        "due": "accept_due",
        "owner_of": "ACT43",
    },
    "Accept_SUP41": {
        "task": "ACCEPT_SUP41",
        "role": "생산임원",
        "due": "accept_due",
        "owner_of": "SUP41",
    },
    "Accept_Overall": {
        "task": "ACCEPT_TOTAL",
        "role": "경영관리임원",
        "due": "accept_due",
        "owner_of": "TOTAL",
    },
    "Revise_ACT41": {"task": "REVISE_ACT41", "role": "경영관리임원", "due": "accept_due"},
    "Revise_ACT42": {"task": "REVISE_ACT42", "role": "경영관리임원", "due": "accept_due"},
    "Revise_ACT43": {"task": "REVISE_ACT43", "role": "경영관리임원", "due": "accept_due"},
    "Revise_SUP41": {"task": "REVISE_SUP41", "role": "경영관리임원", "due": "accept_due"},
    "Complete_Scene": {"task": "COMPLETE", "role": "경영관리담당", "due": "complete_due"},
}
#: 기한 초과 알림을 함께 받는 사람 — 제출·확인·인수는 경영관리 담당, 경영관리 업무는 임원.
REVIEWER = {**{f"SUBMIT_{t}": FIN for t in RESULTS}, **{f"CONFIRM_{t}": FIN for t in RESULTS}}


class PrerequisiteError(DomainError):
    """필수 조건 미충족 — 누락 항목을 함께 낸다(구현명세 13·15장의 실패 응답 `blocking_items`)."""

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
        return user_id_of(str(value).strip())
    except DomainError:
        return None


def _users(value: Any) -> list[str]:
    """「이름;이름」(또는 쉼표) → 사용자 id 목록. 모르는 이름은 422다 — 지어내지 않는다."""
    out = []
    for part in str(value or "").replace(",", ";").split(";"):
        if not part.strip():
            continue
        uid = _user(part)
        if uid is None:
            raise DomainError(f"모르는 사람: {part.strip()}", 422)
        out.append(uid)
    return out


def _when(value: Any, field: str) -> str:
    try:
        return parse_at(str(value).strip()).isoformat()
    except ValueError as exc:
        raise DomainError(f"{field}: 시각(ISO8601)이 아니다 — {value!r}", 422) from exc


def _money(value: Any) -> Decimal | None:
    """금액 칸 — 비어 있으면 None(미입력)이다. 0으로 메우지 않는다(E404)."""
    if value in (None, ""):
        return None
    try:
        d = Decimal(str(value).replace(",", "").strip())
    except ArithmeticError as exc:
        raise DomainError(f"금액이 아니다: {value!r}", 422) from exc
    if d < 0 or d != d.to_integral_value():
        raise DomainError(f"금액은 0 이상의 원 단위 정수다: {value!r}", 422)
    return d


def _require(by: str, user: str, what: str, *, strict: bool = True) -> None:
    """
    그 사람만 — 역할·담당 검사(구현명세 2장). `strict=False`면 답한 사람이 사용자 마스터 밖(콘솔
    관리자)이다 —
    「담당자만」은 바깥 Chaeksas가 결재 담당자로 이미 막았다(장면 1~3과 같다).
    """
    if strict and by != user:
        holder = USERS.get(user, {})
        raise DomainError(f"{what}은 {holder.get('role')}({holder.get('name')})만 한다", 403)


# ─────────────────────────── 장면 3 기준 (D400) ───────────────────────────


def baseline_from_sc03(sc03_doc: dict) -> dict[str, Any]:
    """
    장면 3 인계 → 장면 4의 출발점(CT401). 장면 3 완료와 AT31~AT34의 현재 배정버전 인수가 있어야
    한다 — 장면 3을
    다시 승인하지 않는다(P404).
    """
    h = sc03_doc.get("handoff") or {}
    if sc03_doc["review"].get("state") != "SC03_COMPLETED" or h.get("handoff_id") != SOURCE_HANDOFF:
        raise DomainError("수익성 통합 분석이 아직 완료 전이다 — 개선안 검토·실행 승인은 "
                          "HANDOFF31에서 시작한다", 409)
    if sc03_doc.get("case_id") != "BASE":
        raise DomainError(
            f"수익성 통합 분석이 기본 시연이 아니다({sc03_doc.get('case_id')}) — 개선안 검토·실행 "
            "승인 기대값은 기본 경로 "
            "기준이다",
            409,
        )
    tasks = []
    for a in ordered(sc03_doc["assignments"]):
        if a["state"] != "ACCEPTED" or a["accepted_version"] != a["assignment_version"]:
            raise DomainError(f"수익성 통합 분석 {a['task_id']}가 현재 배정버전으로 인수되지 "
                              "않았다", 409)
        tasks.append(
            {
                k: a.get(k)
                for k in (
                    "task_id",
                    "title",
                    "owner",
                    "collaborators",
                    "question",
                    "deliverable",
                    "due_at",
                    "candidate_refs",
                    "assignment_version",
                    "accepted_at",
                )
            }
        )
    if sorted(t["task_id"] for t in tasks) != sorted(RESULTS):
        raise DomainError("수익성 통합 분석 분석과제가 AT31~AT34가 아니다 — 개선안 검토·실행 승인 "
                          "연결을 지을 수 없다", 409)
    frozen = max(
        (r for r in sc03_doc["reports"].values() if r["kind"] == "FROZEN"), key=lambda r: r["seq"]
    )
    return {
        "demo_run_id": sc03_doc["demo_run_id"],
        "executor": (sc03_doc.get("bpm") or {}).get("executor", "embedded"),
        "handoff": {
            k: h.get(k)
            for k in (
                "handoff_id",
                "report_version",
                "minutes_version",
                "decision",
                "outcome",
                "next_meeting",
                "analysis_due",
                "consolidation_due",
                "as_of",
            )
        },
        "kpis": frozen["kpis"],
        "tasks": tasks,
        "questions": [
            {
                k: q.get(k)
                for k in ("question_id", "question", "owner", "due_at", "treatment", "state")
            }
            for q in ordered(sc03_doc["questions"])
            if q["question_id"] in ("Q31", "Q32")
        ],
        "excluded_candidates": h.get("excluded_candidates", []),
        "price": sc03_doc["sc02"]["price"],
    }


def price_option(baseline: dict) -> Option:
    """장면 2 승인 단가 — 장면 3 기준 손익을 같은 원천으로 다시 내는 데만 쓴다."""
    p = baseline["price"]
    return Option(
        p["version_id"],
        "APPROVED",
        p["part_id"],
        "SUP-01",
        Decimal(p["old_price"]),
        Decimal(p["new_price"]),
        date.fromisoformat(p["effective_date"]),
    )


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
    D400 — 장면 3 완료, 장면 4 미착수(7/1 08:59). 결과·검증·보고·결정·승인·인수는 단계 실행 때
    생긴다(구현명세
    16장: 미래 자료를 초기 응답에 보내지 않는다). 기준 손익(장면 3)만 계산해 둔다 — 보이는 근거다.
    """
    if case_id not in CASES:
        raise DomainError(f"모르는 시연 사례: {case_id} (가능: {', '.join(CASES)})", 422)
    if executor not in EXECUTORS:
        raise DomainError(f"모르는 실행 위치: {executor} (가능: {', '.join(EXECUTORS)})", 422)
    clock = max(parse_at(baseline["handoff"]["as_of"]), parse_at(SCHEDULE["start_at"]))
    return {
        "demo_run_id": demo_run_id,
        "seed_id": SEED_ID,
        "case_id": case_id,
        "created_at": created_at.isoformat(),
        "clock": clock.isoformat(),
        "step": "D400",
        "sc03": baseline,
        "baseline": calc.baseline(seed.numbers, price_option(baseline)),
        "agent_mode": "fail" if case_id == "E408" else "mock",
        "review": {
            "review_id": REVIEW_ID,
            "state": "PENDING",
            "risk": "OPEN",
            "forecast": "REVIEW_PENDING",
            "target": "UNCHANGED",
            "started_at": None,
            "started_by": None,
            "completed_at": None,
        },
        "results": {},
        "followups": [
            {
                **q,
                "history": [{"at": baseline["handoff"]["as_of"], "note": "수익성 통합 분석 인계 "
                                                                         "시점 상태"}],
            }
            for q in baseline["questions"]
        ],
        "assumptions": {},
        "assumption_log": [],
        "runs": {},
        "verification": None,
        "rework": [],
        "recommendation": None,
        "reports": {},
        "meeting": None,
        "directives": {},
        "decision": None,
        "approval_draft": None,
        "approvals": {},
        "minutes": {},
        "assignments": {},
        "handoff": None,
        "agent_outputs": {},
        "tasks": {},
        "alerts": [],
        "audit": [],
        "bpm": None if executor == "embedded" else external_bpm(executor),
    }


# ─────────────────────────── S01 착수 (U401 · CT401) ───────────────────────────


def start_review(doc: dict, *, by: str) -> bool:
    """
    장면 4 착수 — 기존 MR-2706-01에 HANDOFF31과 AT31~AT34를 잇는다(새 검토건을 만들지 않는다).
    **재착수는 기존
    결과를 돌려준다**(T401 — 중복 업무·이벤트 없음). 돌려주는 값은 새로 착수했는가다.
    """
    _require(by, FIN, "개선안 검토·실행 승인 착수")
    r = doc["review"]
    if r["started_at"] is not None:
        return False
    r.update(state="PREPARING", started_at=doc["clock"], started_by=by)
    for tid, spec in RESULTS.items():
        doc["results"][spec["result_id"]] = {
            "result_id": spec["result_id"],
            "seq": list(RESULTS).index(tid) + 1,
            "task_id": tid,
            "alts": spec["alts"],
            "writer": spec["writer"],
            "confirmer": spec["confirmer"],
            "state": "AWAITING",
            "versions": [],
        }
    audit(
        doc,
        actor=by,
        action="review_started",
        review_id=REVIEW_ID,
        source=SOURCE_HANDOFF,
        event_code="EV41-01",
    )
    return True


def open_review(doc: dict) -> dict[str, Any]:
    """BPM 첫 작업 — 착수된 검토건인지 본다. 바깥 실행은 착수 뒤에 Studio·Center에서 시작한다."""
    if doc["review"]["started_at"] is None:
        raise DomainError("아직 착수하지 않은 업무다 — 화면에서 착수를 먼저 누른다", 409)
    return {"review_id": REVIEW_ID, "assignee_name": name_of(FIN)}


# ─────────────────────────── S02 분석 결과 제출·임원 확인 (U401 · CT401·CT402)
# ───────────────────────────


def current_result(doc: dict, result_id: str) -> dict | None:
    versions = doc["results"][result_id]["versions"]
    return versions[-1] if versions else None


def _assumptions_for(seed: Seed, doc: dict, alt_ids: list[str]) -> list[dict[str, Any]]:
    """
    부서가 제출하는 산정 가정 — `SC04가정`의 행이다. 사례는 제출 초안만 바꾼다(원 가정은 그대로).
    """
    rows = seed.by_id("SC04가정")
    out = []
    for alt in alt_ids:
        if alt not in rows:
            continue
        a = calc.assumption_from_row(rows[alt])
        if doc["case_id"] == "E401" and alt == "ALT41":
            a["avoided_fixed"] = "120000000"  # 기존 설비 감가상각비를 절감으로 넣은 복제 초안
        if doc["case_id"] == "E402" and alt == "ALT42":
            a["duplicate_override"] = {m.isoformat(): "0" for m in calc.EFFECT_MONTHS[3:]}
        out.append(a)
    return out


def check_submit(doc: dict, task_id: str, args: dict[str, Any]) -> None:
    if task_id not in RESULTS:
        raise DomainError(f"모르는 분석과제: {task_id}", 422)
    if doc["review"]["started_at"] is None:
        raise DomainError("착수 전이다", 409)
    res = doc["results"][RESULTS[task_id]["result_id"]]
    if res["state"] in ("SUBMITTED", "CONFIRMED"):
        raise DomainError(
            f"{res['result_id']}는 이미 제출됐다 — 보완은 임원 보완 요청 뒤에 한다", 409
        )
    outcome = args.get("outcome")
    if outcome not in ("제출", "제외"):
        raise DomainError(
            "결과 유형은 「제출」 또는 「제외」다 — 미제출과 검토 후 제외는 다르다", 422
        )
    if not _text(args, "conclusion"):
        raise DomainError("결론을 적는다", 422)
    if not _text(args, "evidence"):
        raise DomainError("근거(근거 ID)를 적는다", 422)
    if outcome == "제외" and not _text(args, "reason"):
        raise DomainError("제외 결과에는 사유가 필요하다(CT401)", 422)
    if (
        outcome == "제외"
        and RESULTS[task_id]["alts"]
        and RESULTS[task_id]["alts"][0] != EXCLUDED_ALT
    ):
        raise DomainError(f"{task_id}는 실행 대안 산정 과제다 — 제외로 낼 수 없다", 422)


def submit_result(
    doc: dict, seed: Seed, task_id: str, args: dict[str, Any], *, by: str, strict: bool = True
) -> str:
    """
    결과 제출(AC402) — 새 버전이다. 산정 가정을 함께 묶는다(가정 버전). 작성자와 확인자는 따로
    기록된다 —
    제출만으로 확인되지 않는다. 제외(AT33)는 미제출이 아니라 검토 후 종결이다.
    """
    check_submit(doc, task_id, args)
    spec = RESULTS[task_id]
    _require(by, spec["writer"], f"{task_id} 결과 제출", strict=strict)
    res = doc["results"][spec["result_id"]]
    n = len(res["versions"]) + 1
    version_ref = f"{spec['result_id']}-v{n}"
    assumptions = _assumptions_for(seed, doc, spec["alts"])
    for a in assumptions:
        _set_assumption(doc, a, ref=version_ref, by=by, note="부서 제출 가정")
    res["versions"].append(
        {
            "version": n,
            "ref": version_ref,
            "outcome": "EXCLUDED" if args["outcome"] == "제외" else "SUBMITTED",
            "conclusion": _text(args, "conclusion"),
            "evidence_refs": [e.strip() for e in _text(args, "evidence").split(";") if e.strip()],
            "risks": _text(args, "risks"),
            "reason": _text(args, "reason") or None,
            "assumption_refs": [
                f"{a['alt_id']}-v{doc['assumptions'][a['alt_id']]['version']}" for a in assumptions
            ],
            "submitted_by": by,
            "submitted_at": doc["clock"],
            "confirmation": None,
            "causes": _causes(seed) if task_id == "AT34" else None,
        }
    )
    res["state"] = "SUBMITTED"
    audit(doc, actor=by, action="result_submitted", result=version_ref, outcome=args["outcome"])
    return version_ref


def _causes(seed: Seed) -> list[dict[str, Any]]:
    """
    RES44 — 기존 부족의 모델별 산술 기여(T01 − F01 수량 × C01 단위CM). 새 원인을 만들지
    않는다(EVDC49).
    """
    out = []
    for r in seed.causes:
        qty = int(r["T01 연간량"]) - int(r["F01 연간량"])
        out.append(
            {
                "model_id": str(r["모델"]),
                "t01": int(r["T01 연간량"]),
                "f01": int(r["F01 연간량"]),
                "unit_cm": str(r["C01 단위CM"]),
                "contribution": str(qty * Decimal(str(r["C01 단위CM"]))),
            }
        )
    return out


def _set_assumption(doc: dict, a: dict[str, Any], *, ref: str, by: str, note: str) -> None:
    prev = doc["assumptions"].get(a["alt_id"])
    a = {**a, "version": (prev["version"] + 1) if prev else 1, "result_ref": ref}
    doc["assumptions"][a["alt_id"]] = a
    doc["assumption_log"].append(
        {"alt_id": a["alt_id"], "version": a["version"], "at": doc["clock"], "by": by, "note": note}
    )


def check_confirm(doc: dict, task_id: str, args: dict[str, Any]) -> None:
    if task_id not in RESULTS:
        raise DomainError(f"모르는 분석과제: {task_id}", 422)
    res = doc["results"][RESULTS[task_id]["result_id"]]
    if res["state"] != "SUBMITTED":
        raise DomainError(f"{res['result_id']}는 확인할 제출본이 없다 ({res['state']})", 409)
    if args.get("decision") not in ("확인", "보완요청"):
        raise DomainError("「확인」 또는 「보완요청」을 고른다", 422)
    if not _text(args, "opinion"):
        raise DomainError("확인 의견을 적는다", 422)


def confirm_result(
    doc: dict, task_id: str, args: dict[str, Any], *, by: str, strict: bool = True
) -> None:
    """
    담당 임원 확인(AC402) — 확인 계정·시각·근거 해시를 고정한다. 보완 요청이면 같은 부서가 새
    버전을 낸다.
    장면 3의 미확인(Q31·Q32)은 과거 상태를 보존하고 7월 후속 확인 이력만 더한다.
    """
    check_confirm(doc, task_id, args)
    spec = RESULTS[task_id]
    _require(by, spec["confirmer"], f"{task_id} 임원 확인", strict=strict)
    res = doc["results"][spec["result_id"]]
    cur = res["versions"][-1]
    ok = args["decision"] == "확인"
    cur["confirmation"] = {
        "decision": "CONFIRMED" if ok else "REWORK_REQUESTED",
        "by": by,
        "at": doc["clock"],
        "opinion": _text(args, "opinion"),
        "evidence_hash": _hash([cur["conclusion"], cur["evidence_refs"], cur["assumption_refs"]])[
            :16
        ],
    }
    res["state"] = "CONFIRMED" if ok else "REWORK_REQUESTED"
    if ok and spec["question"]:
        for q in doc["followups"]:
            if q["question_id"] == spec["question"]:
                q["history"].append(
                    {
                        "at": doc["clock"],
                        "note": f"{cur['ref']} 근거 확인 — 위험 해소를 뜻하지 않는다",
                        "by": by,
                    }
                )
    events = {"AT31": "EV41-02", "AT32": "EV41-03", "AT33": "EV41-04", "AT34": "EV41-05"}
    audit(
        doc,
        actor=by,
        action="result_confirmed" if ok else "result_rework_requested",
        result=cur["ref"],
        event_code=events[task_id] if ok else None,
    )


# ─────────────────────────── S03·S04 효과 검증·보완 (U402 · CT402·CT403)
# ───────────────────────────


def assumption_list(doc: dict) -> list[dict[str, Any]]:
    return [doc["assumptions"][a] for a in ALTS if a in doc["assumptions"]]


def _assumption_hash(assumptions: list[dict[str, Any]]) -> str:
    body = [{k: v for k, v in a.items() if k not in ("version", "result_ref")} for a in assumptions]
    return _hash(body)[:16]


def _new_run(
    doc: dict,
    seed: Seed,
    assumptions: list[dict[str, Any]],
    *,
    kind: str,
    by: str,
    include: list[str] | None = None,
    conditional: list[str] | tuple[str, ...] = (),
    basis: str,
) -> dict:
    result = calc.run(
        assumptions, doc["baseline"], seed.numbers, include=include, conditional=conditional
    )
    run_id = f"RUN-SC04-{len(doc['runs']) + 1:02d}"
    run = doc["runs"][run_id] = {
        "run_id": run_id,
        "seq": _seq(doc["runs"]),
        "kind": kind,
        "basis_ref": basis,
        "assumptions": copy.deepcopy(assumptions),
        "assumptions_hash": _assumption_hash(assumptions),
        "include": include,
        "conditional": list(conditional),
        "calculated_at": doc["clock"],
        "created_by": by,
        "result": result,
        "status": result["status"],
    }
    return run


def check_verify(doc: dict) -> None:
    waiting = [r["result_id"] for r in ordered(doc["results"]) if r["state"] != "CONFIRMED"]
    if waiting:
        raise DomainError(f"임원 확인이 끝나지 않은 결과가 있다: {', '.join(waiting)}", 409)


def verify_effects(doc: dict, seed: Seed, *, memo: str, by: str) -> dict[str, Any]:
    """
    비용·중복 검증(EV41-06, AC403·AC404) — 확인된 결과의 가정으로 효과를 계산하고 검증한다. 차단
    오류가 있으면
    보완 요청(항목·사유·담당·기한)을 남기고 그 안의 담당 임원에게 돌린다 — 보고 확정이 막힌다.
    """
    check_verify(doc)
    _require(by, FIN, "효과 검증")
    run = _new_run(
        doc, seed, assumption_list(doc), kind="VERIFY", by=by, basis="SC03 통합손익 RUN-SC03-01"
    )
    errors = run["result"]["errors"]
    if not errors:
        doc["verification"] = {
            "run_id": run["run_id"],
            "assumptions_hash": run["assumptions_hash"],
            "verified_by": by,
            "verified_at": doc["clock"],
            "memo": memo,
            "state": "VERIFIED",
        }
        audit(doc, actor=by, action="effects_verified", run_id=run["run_id"], event_code="EV41-06")
        return {"run_id": run["run_id"], "passed": True, "corrector_name": ""}
    first = errors[0]["alt_id"]
    owner = OWNERS.get(first, CFO)
    doc["verification"] = {
        "run_id": run["run_id"],
        "assumptions_hash": run["assumptions_hash"],
        "verified_by": None,
        "verified_at": None,
        "memo": memo,
        "state": "VALIDATION_FAILED",
    }
    doc["rework"].append(
        {
            "rework_id": f"RW41-{len(doc['rework']) + 1}",
            "run_id": run["run_id"],
            "alt_id": first,
            "items": [e for e in errors if e["alt_id"] == first],
            "reason": errors[0]["message"],
            "owner": owner,
            "due_at": _due_at(doc, "verify_due"),
            "requested_by": by,
            "requested_at": doc["clock"],
            "state": "OPEN",
        }
    )
    audit(doc, actor=by, action="effects_blocked", run_id=run["run_id"], alt=first)
    return {"run_id": run["run_id"], "passed": False, "corrector_name": name_of(owner)}


def open_rework(doc: dict) -> dict | None:
    return next((r for r in reversed(doc["rework"]) if r["state"] == "OPEN"), None)


def check_correct(doc: dict, args: dict[str, Any]) -> None:
    if open_rework(doc) is None:
        raise DomainError("보완할 검증 오류가 없다", 409)
    if not _text(args, "content"):
        raise DomainError("보완 내용을 적는다", 422)


def correct_effects(doc: dict, args: dict[str, Any], *, by: str, strict: bool = True) -> None:
    """
    검증 보완(S04) — 담당 임원이 근거 없는 항목을 걷어 내고 다시 확인한다. 가정은 **새 버전**이고,
    보완된 결과에
    기댄 검증은 낡는다(STALE) — 다시 검증해야 보고로 간다. 기준 손익의 고정비는 그대로다(E401).
    """
    check_correct(doc, args)
    rw = open_rework(doc)
    _require(by, rw["owner"], "검증 보완", strict=strict)  # type: ignore[index]
    a = copy.deepcopy(doc["assumptions"][rw["alt_id"]])  # type: ignore[index]
    codes = {i["code"] for i in rw["items"]}  # type: ignore[index]
    if "FIXED_COST_NOT_AVOIDABLE" in codes:
        a["avoided_fixed"] = "0"
    if "DUPLICATE_NOT_REMOVED" in codes:
        a["duplicate_override"] = {}
    res = next(r for r in doc["results"].values() if rw["alt_id"] in r["alts"])  # type: ignore[index]
    prev = res["versions"][-1]
    ref = f"{res['result_id']}-v{len(res['versions']) + 1}"
    _set_assumption(doc, a, ref=ref, by=by, note=f"검증 보완 — {_text(args, 'content')}")
    res["versions"].append(
        {
            **copy.deepcopy(prev),
            "version": len(res["versions"]) + 1,
            "ref": ref,
            "assumption_refs": [
                f"{x}-v{doc['assumptions'][x]['version']}"
                for x in res["alts"]
                if x in doc["assumptions"]
            ],
            "submitted_by": by,
            "submitted_at": doc["clock"],
            "change": _text(args, "content"),
            # 담당 임원이 직접 보완했으므로 그 확인이 재확인이다(작성 계정과 별도로 남는다)
            "confirmation": {
                "decision": "CONFIRMED",
                "by": by,
                "at": doc["clock"],
                "opinion": _text(args, "content"),
                "evidence_hash": None,
            },
        }
    )
    rw.update(state="RESOLVED", resolved_by=by, resolved_at=doc["clock"])  # type: ignore[union-attr]
    if doc["verification"]:
        doc["verification"]["state"] = "STALE"
    audit(doc, actor=by, action="effects_corrected", alt=rw["alt_id"], result=ref)  # type: ignore[index]


# ─────────────────────────── S05 우선 실행안 제안 (U403 · CT404) ───────────────────────────


def verified_run(doc: dict) -> dict | None:
    v = doc["verification"]
    if v is None or v["state"] != "VERIFIED":
        return None
    return doc["runs"][v["run_id"]]


def check_recommend(doc: dict, args: dict[str, Any]) -> None:
    run = verified_run(doc)
    if run is None:
        raise DomainError("검증을 통과한 효과 계산이 없다 — 보고 구성 전에 검증한다(CT403)", 409)
    if run["assumptions_hash"] != _assumption_hash(assumption_list(doc)):
        raise DomainError("검증 이후 가정이 바뀌었다 — 다시 검증한다", 409)
    items = args.get("items") or {}
    picked = [a for a in ALTS if (items.get(a) or {}).get("pick") == "추천"]
    if not 2 <= len(picked) <= 3:
        raise DomainError("우선 실행안은 2~3개다 — 숫자를 맞추려 억지로 채우지 않는다(CT404)", 422)
    priorities = []
    for alt in ALTS:
        it = items.get(alt) or {}
        if it.get("pick") not in ("추천", "제외"):
            raise DomainError(f"{alt}: 추천 또는 제외를 고른다", 422)
        if not _text(it, "reason"):
            raise DomainError(f"{alt}: 선정·제외 사유를 적는다", 422)
        if it["pick"] == "추천":
            try:
                priorities.append(int(str(it.get("priority") or "").strip()))
            except ValueError as exc:
                raise DomainError(f"{alt}: 우선순위는 숫자다", 422) from exc
    if sorted(priorities) != list(range(1, len(picked) + 1)):
        raise DomainError("우선순위는 1부터 겹치지 않게 매긴다 — 효과액 자동 정렬이 아니다", 422)
    if not _text(args, "excluded_reason"):
        raise DomainError("물량 배분안(EXCL44) 제외 사유를 적는다(RES43)", 422)
    if args.get("owners") != "확인":
        raise DomainError("담당 임원 확인이 있어야 공동 제안이다", 422)


def recommend(doc: dict, args: dict[str, Any], *, by: str) -> str:
    """
    공동 추천(EV41-07, AC405) — 담당 임원들이 우선 실행할 안을 제안한다. 우선순위는 선행조건·착수
    순서의
    판단이다(ALT42가 1순위 — 공동 기준 준비가 먼저). 대응 조합 비교 화면은 만들지 않는다.
    """
    check_recommend(doc, args)
    _require(by, CFO, "우선 실행안 제안")
    run = verified_run(doc)
    nets = {a["alt_id"]: a for a in run["result"]["alts"]}  # type: ignore[index]
    rows = []
    for alt in ALTS:
        it = args["items"][alt]
        rows.append(
            {
                "alt_id": alt,
                "name": doc["assumptions"][alt]["name"],
                "recommended": it["pick"] == "추천",
                "priority": int(it["priority"]) if it["pick"] == "추천" else None,
                "reason": _text(it, "reason"),
                "owner": OWNERS[alt],
                "worker": WORKERS[alt],
                "net_2027": nets[alt]["net_2027"],
                "normal_annual": nets[alt]["normal_annual"],
                "start": nets[alt]["start"],
                "budget": doc["assumptions"][alt]["budget"],
            }
        )
    doc["recommendation"] = {
        "ref": "RCM41-v1",
        "run_id": run["run_id"],  # type: ignore[index]
        "items": rows,
        "excluded": [
            {
                "alt_id": EXCLUDED_ALT,
                "name": "고객·모델 물량 배분",
                "reason": _text(args, "excluded_reason"),
                "evidence": "RES43 / EVDC48",
                "effect": None,  # 미산정 — 합산 제외(0이 아니다)
            }
        ],
        "owner_confirmations": [
            {"by": u, "at": doc["clock"]} for u in dict.fromkeys(OWNERS[a] for a in ALTS)
        ],
        "confirmed_by": by,
        "confirmed_at": doc["clock"],
    }
    audit(doc, actor=by, action="recommended", ref="RCM41-v1", event_code="EV41-07")
    return "RCM41-v1"


def recommended(doc: dict) -> list[str]:
    rec = doc["recommendation"] or {"items": []}
    return [
        i["alt_id"]
        for i in sorted(
            (i for i in rec["items"] if i["recommended"]), key=lambda i: i["priority"] or 0
        )
    ]


# ─────────────────────────── S06·S07 보고본 확정·회의 보고 (U404 · CT404·CT405)
# ───────────────────────────


def check_freeze(doc: dict) -> None:
    if doc["recommendation"] is None:
        raise DomainError("공동 추천이 먼저다", 409)
    if REPORT_ID in doc["reports"]:
        raise DomainError("REP41-v1은 이미 확정됐다 — 확정본은 바꾸지 않는다", 409)
    run = verified_run(doc)
    if run is None or run["assumptions_hash"] != _assumption_hash(assumption_list(doc)):
        raise DomainError("검증된 계산과 현재 가정이 다르다 — 다시 검증한다(CT403)", 409)


def freeze_report(doc: dict, seed: Seed, *, conclusion: str, recipients: str, by: str) -> str:
    """
    REP41-v1 확정·내부 배포(EV41-08) — 입력 가정·계산 결과·근거·확인 버전을 고정한다. 결론은 「이
    과제들을
    우선 실행하되 이 조건·지원이 필요하다」다. 배포는 승인이 아니다 — 실제 메일 없이 내부 이력이다.
    """
    check_freeze(doc)
    _require(by, CFO, "보고본 확정")
    alts = recommended(doc)
    run = _new_run(
        doc,
        seed,
        assumption_list(doc),
        kind="REPORT",
        by=by,
        include=alts,
        basis=doc["verification"]["run_id"],
    )
    y = run["result"]["periods"]["year"]
    snapshot = {
        "run_id": run["run_id"],
        "assumptions_hash": run["assumptions_hash"],
        "recommended": alts,
        "results": {r["result_id"]: r["versions"][-1]["ref"] for r in ordered(doc["results"])},
        "confirmations": {
            r["result_id"]: (r["versions"][-1]["confirmation"] or {}).get("by")
            for r in ordered(doc["results"])
        },
        "gap_before": y["gap_before"],
        "effect": y["effect"],
        "gap": y["gap"],
    }
    doc["reports"][REPORT_ID] = {
        "report_id": REPORT_ID,
        "seq": _seq(doc["reports"]),
        "kind": "REPORT",
        "parent": None,
        "status": "FROZEN",
        "run_id": run["run_id"],
        "recommendation": doc["recommendation"]["ref"],
        "conclusion": conclusion,
        "snapshot": snapshot,
        "content_hash": _hash(snapshot)[:16],
        "frozen_by": by,
        "frozen_at": doc["clock"],
        "distribution": {
            "at": doc["clock"],
            "by": by,
            "recipients": [name_of(u) for u in ATTENDEES],
            "memo": recipients,
        },
    }
    doc["meeting"] = {
        "meeting_id": MEETING_ID,
        "type": "MONTHLY",
        "subject": "수익성 개선 대응안 검토 및 실행 승인",
        "chair": CEO,
        "reporter": CFO,
        "scheduled_at": SCHEDULE["meeting_at"],
        "report_version": REPORT_ID,
        "state": "READY",
        "opened_at": None,
        "attendance": [],
        "records": [],
    }
    doc["review"]["state"] = "REPORT_READY"
    audit(doc, actor=by, action="report_frozen", report=REPORT_ID, event_code="EV41-08")
    return REPORT_ID


def check_open_meeting(doc: dict) -> None:
    m = doc["meeting"]
    if m is None or m["state"] != "READY":
        raise DomainError("배포된 보고본이 없다 — 보고본 확정이 먼저다", 409)
    if parse_at(doc["clock"]) < parse_at(m["scheduled_at"]):
        raise DomainError(f"회의 시각({m['scheduled_at'][5:16].replace('T', ' ')}) 전이다", 409)


def open_meeting(doc: dict, *, summary: str, by: str) -> str:
    """MT41 개회·보고(EV41-09) — 보고는 REP41-v1 고정이다. 보고본 열람·배포는 대표 승인이 아니다."""
    check_open_meeting(doc)
    _require(by, CFO, "월간회의 보고")
    m = doc["meeting"]
    m.update(state="IN_PROGRESS", opened_at=doc["clock"], report_summary=summary)
    m["attendance"] = [
        {"record_id": f"ATT41-{i + 1}", "actor": u, "state": "PRESENT", "at": doc["clock"]}
        for i, u in enumerate(ATTENDEES)
    ]
    doc["review"]["state"] = "IN_REVIEW"
    audit(doc, actor=by, action="meeting_opened", meeting=MEETING_ID, event_code="EV41-09")
    return MEETING_ID


RECORD_TYPES = ("QUESTION", "ANSWER", "DIRECTIVE", "NOTE")


def add_meeting_record(
    doc: dict, *, record_type: str, subject: str, content: str, related: str, by: str
) -> str:
    """
    대표 질의·현업 답변·지원 지시(U405, AC407·AC408) — 질문과 실제 답변과 지시를 **다른 유형**으로
    남긴다. 질문·
    지시는 대표, 답변은 담당 임원이다. Agent 초안은 여기 들어오지 않는다(사람이 확인한 발언만).
    """
    m = doc["meeting"]
    if m is None or m["state"] != "IN_PROGRESS":
        raise DomainError("진행 중인 회의가 없다", 409)
    if by not in [a["actor"] for a in m["attendance"]]:
        raise DomainError("MT41 참석자만 기록한다", 403)
    if record_type not in RECORD_TYPES:
        raise DomainError(f"기록 종류: {', '.join(RECORD_TYPES)}", 422)
    if record_type in ("QUESTION", "DIRECTIVE") and by != CEO:
        raise DomainError("질의·지시는 주재자(대표이사)가 한다", 403)
    if record_type == "ANSWER" and by == CEO:
        raise DomainError("답변은 담당 임원이 한다", 403)
    if not content.strip():
        raise DomainError("내용을 적는다", 422)
    rid = f"QA41{1 + sum(1 for r in m['records'] if r['record_type'] != 'NOTE')}"
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
            "state": "RECORDED",
        }
    )
    codes = {"QA411": "EV41-10", "QA412": "EV41-11", "QA413": "EV41-12", "QA414": "EV41-13"}
    audit(
        doc,
        actor=by,
        action="meeting_record",
        record_id=rid,
        record_type=record_type,
        event_code=codes.get(rid),
    )
    return rid


# ─────────────────────────── S08·S09 판단본 (U405 · CT405·CT406) ───────────────────────────


def frozen_report(doc: dict) -> dict | None:
    return doc["reports"].get(REPORT_ID)


def decision_report(doc: dict, *, confirmed: bool | None = None) -> dict | None:
    reps = [r for r in ordered(doc["reports"]) if r["kind"] == "DECISION"]
    if confirmed is not None:
        reps = [r for r in reps if (r["status"] == "CONFIRMED") == confirmed]
    return reps[-1] if reps else None


def _directive_problems(d: dict[str, Any], label: str) -> list[str]:
    out = []
    if not d.get("content"):
        out.append(f"{label} 내용 없음")
    for key, what in (("owner", "책임"), ("verifier", "확인자"), ("due_at", "기한")):
        if not d.get(key):
            out.append(f"{label} {what} 없음")
    return out


def check_decision_draft(doc: dict, args: dict[str, Any]) -> None:
    m = doc["meeting"]
    if m is None or m["state"] != "IN_PROGRESS":
        raise DomainError("진행 중인 회의가 없다 — 판단 초안은 회의 질의 뒤에 쓴다", 409)
    if frozen_report(doc) is None:
        raise DomainError("원 보고본이 없다", 409)
    if decision_report(doc, confirmed=True) is not None:
        raise DomainError("판단본이 이미 확인됐다 — 바꾸려면 새 판단·승인 버전이다", 409)
    for c in args.get("changes") or []:
        if c.get("alt_id") not in ALTS:
            raise DomainError(f"모르는 대안: {c.get('alt_id')}", 422)
        if c["alt_id"] not in recommended(doc):
            raise DomainError(f"{c['alt_id']}는 보고 추천안이 아니다", 422)
        try:
            calc.normalize(str(c.get("field")), c.get("value"))
        except (ValueError, ArithmeticError) as exc:
            raise DomainError(f"가정 변경: {exc}", 422) from exc
    if args.get("changes"):
        if not _text(args, "reason"):
            raise DomainError("시점·금액 변경에는 변경 사유가 필요하다", 422)
        confirmer = _user(args.get("confirmed_by"))
        if confirmer not in OWNERS.values():
            raise DomainError("변경을 확인한 현업 임원을 지정한다(생산·구매 임원)", 422)
    for key, label in (("condition", "조건"), ("support", "지원")):
        d = args.get(key) or {}
        if not d.get("content"):
            continue
        for k in ("owner", "verifier"):
            if _user(d.get(k)) is None:
                raise DomainError(
                    f"{label}: {'책임' if k == 'owner' else '확인자'}을 지정한다", 422
                )
        _when(d.get("due_at"), f"{label} 기한")
        _users(d.get("collaborators"))


def _label_of(field: str) -> str:
    return calc.FIELDS.get(field, field)


def draft_decision(doc: dict, seed: Seed, args: dict[str, Any], *, by: str) -> str:
    """
    판단 초안(AC408·AC409) — 원 보고 가정을 **복제**해 바꾼 칸만 고치고 같은 규칙으로 재계산한다.
    원 보고본은
    그대로다. 질의에서 정한 선행조건(CON41)·지원 지시(SUP41)를 책임·협조·확인자·기한과 함께
    초안으로 남긴다 —
    초안 저장은 승인·확정이 아니다.
    """
    check_decision_draft(doc, args)
    _require(by, FIN, "판단 초안")
    base = frozen_report(doc)
    parent_run = doc["runs"][base["run_id"]]  # type: ignore[index]
    assumptions = copy.deepcopy(parent_run["assumptions"])
    by_alt = {a["alt_id"]: a for a in assumptions}
    changes = []
    for c in args.get("changes") or []:
        a = by_alt[c["alt_id"]]
        value = calc.normalize(str(c["field"]), c["value"])
        changes.append(
            {
                "alt_id": c["alt_id"],
                "field": c["field"],
                "label": _label_of(str(c["field"])),
                "before": a[c["field"]],
                "after": value,
            }
        )
        a[c["field"]] = value
    run = _new_run(
        doc,
        seed,
        assumptions,
        kind="DECISION",
        by=by,
        include=recommended(doc),
        basis=REPORT_ID,
    )
    if not run["result"]["passed"]:
        raise DomainError(
            "판단 초안의 재계산이 검증을 통과하지 못했다: "
            + "; ".join(e["message"] for e in run["result"]["errors"]),
            422,
        )
    n = (
        1
        + sum(1 for r in doc["reports"].values() if r["kind"] == "REPORT")
        + sum(1 for r in doc["reports"].values() if r["kind"] == "DECISION")
    )
    rid = f"DEC41-v{n}"
    for prev in doc["reports"].values():
        if prev["kind"] == "DECISION" and prev["status"] == "DRAFT":
            prev["status"] = "SUPERSEDED"
    doc["reports"][rid] = {
        "report_id": rid,
        "seq": _seq(doc["reports"]),
        "kind": "DECISION",
        "parent": REPORT_ID,
        "status": "DRAFT",
        "run_id": run["run_id"],
        "changes": changes,
        "reason": _text(args, "reason"),
        "change_confirmed_by": _user(args.get("confirmed_by")),
        "diff": calc.diff(parent_run["result"], run["result"]),
        "created_by": by,
        "created_at": doc["clock"],
        "frozen_by": None,
        "frozen_at": None,
        "content_hash": None,
    }
    for key, did, kind, ref in (
        ("condition", "CON41", "CONDITION", "ALT42"),
        ("support", "SUP41", "SUPPORT", "ALT42"),
    ):
        d = args.get(key) or {}
        if not d.get("content"):
            continue
        doc["directives"][did] = {
            "directive_id": did,
            "seq": list(("CON41", "SUP41", "DIR41")).index(did) + 1,
            "kind": kind,
            "alt_ref": d.get("alt_ref") or ref,
            "action_ref": None,
            "content": str(d["content"]).strip(),
            "owner": _user(d.get("owner")),
            "collaborators": _users(d.get("collaborators")),
            "verifier": _user(d.get("verifier")),
            "due_at": _when(d.get("due_at"), "기한"),
            "responsibility": "PENDING",
            "responsibility_at": None,
            "fulfillment": "OPEN",
            "expected_effect": None,  # 미산정 — 0이 아니다
            "state": "DRAFT",
            "source": rid,
        }
    audit(doc, actor=by, action="decision_drafted", report=rid, run_id=run["run_id"])
    return rid


def check_confirm_decision(doc: dict, args: dict[str, Any]) -> None:
    d = decision_report(doc, confirmed=False)
    if d is None or d["status"] != "DRAFT":
        raise DomainError("확인할 판단 초안이 없다", 409)
    if args.get("decision") != "확인":
        raise DomainError("판단본 확인을 고른다", 422)
    if not _text(args, "opinion"):
        raise DomainError("확인 의견을 적는다", 422)
    if d["changes"] and not d["change_confirmed_by"]:
        raise DomainError("변경에는 현업 임원 확인이 필요하다", 422)


def confirm_decision(doc: dict, *, opinion: str, by: str) -> str:
    """
    CONF41(EV41-14) — 관련 임원 확인과 재계산 결과를 확인하고 판단본을 고정한다. 원 보고본은
    그대로다.
    """
    check_confirm_decision(doc, {"decision": "확인", "opinion": opinion})
    _require(by, CFO, "판단본 확인")
    d = decision_report(doc, confirmed=False)
    run = doc["runs"][d["run_id"]]  # type: ignore[index]
    snapshot = {
        "run_id": run["run_id"],
        "assumptions_hash": run["assumptions_hash"],
        "parent": REPORT_ID,
        "changes": d["changes"],  # type: ignore[index]
        "effect": run["result"]["periods"]["year"]["effect"],
        "gap": run["result"]["periods"]["year"]["gap"],
    }
    d.update(  # type: ignore[union-attr]
        status="CONFIRMED",
        frozen_by=by,
        frozen_at=doc["clock"],
        opinion=opinion,
        snapshot=snapshot,
        content_hash=_hash(snapshot)[:16],
    )
    for x in doc["directives"].values():
        if x["source"] == d["report_id"]:  # type: ignore[index]
            x["state"] = "PROPOSED"
    audit(doc, actor=by, action="decision_confirmed", report=d["report_id"], event_code="EV41-14")  # type: ignore[index]
    return d["report_id"]  # type: ignore[index]


# ─────────────────────────── S10 대표 결정 (U406 · CT406) ───────────────────────────


def check_decide(doc: dict, args: dict[str, Any]) -> None:
    d = decision_report(doc, confirmed=True)
    if d is None:
        raise DomainError("확인된 판단본이 없다 — 결정은 최종 판단본으로 한다", 409)
    if doc["decision"] is not None:
        raise DomainError("REV41은 이미 내렸다 — 바꾸려면 새 판단·승인 버전이다", 409)
    items = args.get("items") or {}
    errors = []
    for alt in recommended(doc):
        it = items.get(alt) or {}
        if it.get("outcome") not in DECISIONS:
            errors.append(f"{alt} 결정 없음")
        elif not _text(it, "reason"):
            errors.append(f"{alt} 사유 없음")
    if errors:
        raise DomainError("과제별 결정이 완전하지 않다: " + ", ".join(errors), 422)
    conditional = [a for a in recommended(doc) if items[a]["outcome"] == "조건부승인"]
    refs = [r.strip() for r in _text(args, "condition_refs").split(";") if r.strip()]
    if conditional:
        if not refs:
            raise DomainError("조건부 승인에는 조건을 연결한다(CON41)", 422)
        for r in refs:
            c = doc["directives"].get(r)
            if c is None or c["kind"] != "CONDITION":
                raise DomainError(f"없는 조건: {r}", 404)
            problems = _directive_problems(c, r)
            if problems:
                raise DomainError(", ".join(problems), 422)
    if not any(items[a]["outcome"] in ("승인", "조건부승인") for a in recommended(doc)):
        raise DomainError("승인·조건부 승인이 하나도 없다 — 실행 승인 업무가 아니다", 422)
    disc = args.get("discovery") or {}
    if not str(disc.get("content") or "").strip():
        raise DomainError("잔여 부족분 추가 발굴 지시를 적는다(M409)", 422)
    if _user(disc.get("owner")) is None:
        raise DomainError("추가 발굴 책임자를 지정한다", 422)
    _when(disc.get("due_at"), "추가 발굴 보고기한")
    _users(disc.get("collaborators"))


def decide(doc: dict, seed: Seed, args: dict[str, Any], *, by: str) -> str:
    """
    REV41(EV41-15) — 대표가 과제별로 승인·조건부 승인·보류·미승인을 정한다. HOLD·REJECTED는
    실행과제를 만들지
    않는다(E403). 승인 범위 효과와 잔여 부족을 다시 계산한다 — 조건부 효과는 따로 보인다. 잔여
    부족분 추가
    발굴(DIR41)은 효과 미산정(NULL)이다.
    """
    check_decide(doc, args)
    _require(by, CEO, "과제별 결정")
    d = decision_report(doc, confirmed=True)
    base_run = doc["runs"][d["run_id"]]  # type: ignore[index]
    items = {}
    for alt in [a for a in ALTS if a in recommended(doc)]:  # 대안 번호 순 — 우선순위와 따로다
        it = args["items"][alt]
        items[alt] = {
            "alt_id": alt,
            "outcome": DECISIONS[it["outcome"]],
            "reason": _text(it, "reason"),
        }
    refs = [r.strip() for r in _text(args, "condition_refs").split(";") if r.strip()]
    # 대안 번호 순으로 둔다 — 우선순위는 추천의 판단이고 과제 번호와 따로다
    approved = [a for a in ALTS if items.get(a, {}).get("outcome") in ("APPROVED", "CONDITIONAL")]
    conditional = [a for a in ALTS if items.get(a, {}).get("outcome") == "CONDITIONAL"]
    for a in conditional:
        items[a]["condition_refs"] = refs
    run = _new_run(
        doc,
        seed,
        base_run["assumptions"],
        kind="APPROVED_SCOPE",
        by=by,
        include=approved,
        conditional=conditional,
        basis=d["report_id"],  # type: ignore[index]
    )
    y = run["result"]["periods"]["year"]
    disc = args["discovery"]
    doc["directives"]["DIR41"] = {
        "directive_id": "DIR41",
        "seq": 3,
        "kind": "DISCOVERY",
        "alt_ref": None,
        "action_ref": REVIEW_ID,
        "content": str(disc["content"]).strip(),
        "owner": _user(disc["owner"]),
        "collaborators": _users(disc.get("collaborators")),
        "verifier": by,
        "due_at": _when(disc["due_at"], "보고기한"),
        "responsibility": "PENDING",
        "responsibility_at": None,
        "fulfillment": "OPEN",
        "expected_effect": None,  # 발굴 전 기대효과는 미산정 — 임의의 절감액을 넣지 않는다
        "state": "PROPOSED",
        "source": "REV41",
    }
    # 보류·미승인 안에 걸린 지원·조건은 승인 대상에서 빠진다(실행과제가 없다)
    for x in doc["directives"].values():
        if x["alt_ref"] and x["alt_ref"] not in approved:
            x["state"] = "WITHDRAWN"
    doc["decision"] = {
        "decision_id": "REV41",
        "meeting_id": MEETING_ID,
        "report_ref": d["report_id"],  # type: ignore[index]
        "items": items,
        "approved": approved,
        "conditional": conditional,
        "run_id": run["run_id"],
        "approved_effect": y["effect"],
        "gap": y["gap"],
        "gap_excl_conditional": y["gap_excl_conditional"],
        "decided_by": by,
        "decided_at": doc["clock"],
    }
    doc["meeting"]["state"] = "HELD"
    doc["review"]["state"] = "DECIDED"
    audit(doc, actor=by, action="decided", approved=approved, event_code="EV41-15")
    return "REV41"


# ─────────────────────────── S10·S11 승인서·회의록 (U406 · CT407·CT408) ───────────────────────────

DELEGATION = (
    "한도 내 실행 품의는 담당 현업 임원과 경영관리 예산 임원이 처리하며 대표 재승인을 받지 않는다. "
    "과제 간 "
    "무보고 전용은 허용하지 않는다. 총괄 한도 안의 전용은 변경 보고 후 전체 책임 임원(경영관리 "
    "임원)이 승인한다. "
    "총괄 한도 초과가 예상되면 대표 별도 보고·승인 전 신규 약정을 제한한다."
)


def check_approval_draft(doc: dict, args: dict[str, Any]) -> None:
    if doc["decision"] is None:
        raise DomainError("대표 결정(REV41)이 먼저다", 409)
    if doc["approvals"]:
        raise DomainError("승인서가 이미 확정됐다 — 바꾸려면 새 승인 버전이다", 409)
    for key in ("total_budget",):
        _money(args.get(key))
    for alt in ALTS:
        it = (args.get("items") or {}).get(alt) or {}
        _money(it.get("budget"))
        if it.get("completion_due"):
            _when(it["completion_due"], f"{alt} 완료기한")
    if args.get("plan_due"):
        _when(args["plan_due"], "계획 제출기한")
    if args.get("overall_owner") and _user(args["overall_owner"]) is None:
        raise DomainError(f"모르는 전체 책임자: {args['overall_owner']}", 422)


def approval_problems(doc: dict, draft: dict | None) -> list[str]:
    """
    CT407 필수 — 전체·개별 책임자, 총괄 한도와 배분 합계, 두 기한(계획 ≤ 완료), 조건
    책임·확인자·기한, 추가 지시,
    위임 조항, 회의록 초안. 비어 있는 값을 0이나 임의 날짜로 채우지 않는다(E404).
    """
    if draft is None:
        return ["승인서 초안 없음"]
    out = []
    if not draft["overall_owner"]:
        out.append("전체 책임자 없음")
    total = draft["total_budget"]
    if total is None:
        out.append("총괄 예산 한도 없음")
    if not draft["plan_due"]:
        out.append("계획 제출기한 없음")
    alloc = Decimal(0)
    for alt in doc["decision"]["approved"]:
        it = draft["items"][alt]
        if not it["owner"]:
            out.append(f"{alt} 책임자 없음")
        if it["budget"] is None:
            out.append(f"{alt} 배분 한도 없음")
        else:
            alloc += Decimal(it["budget"])
        if not it["completion_due"]:
            out.append(f"{alt} 과제 완료기한 없음")
        elif draft["plan_due"] and parse_at(draft["plan_due"]) > parse_at(it["completion_due"]):
            out.append(f"{alt} 계획 제출기한이 완료기한보다 늦다")
    if (
        total is not None
        and not any("배분 한도 없음" in p for p in out)
        and alloc != Decimal(total)
    ):
        out.append(f"과제 배분 합계 {int(alloc):,}원 ≠ 총괄 한도 {int(Decimal(total)):,}원")
    for x in ordered(doc["directives"]):
        if x["state"] == "WITHDRAWN":
            continue
        out += _directive_problems(x, x["directive_id"])
    if not draft["delegation"]:
        out.append("위임 조항 없음")
    if not draft["minutes"]:
        out.append("회의록 초안 없음")
    return out


def draft_approval(doc: dict, args: dict[str, Any], *, by: str) -> dict[str, Any]:
    """
    승인서 초안(경영관리) — 필수 누락 목록을 함께 남긴다(초안은 저장된다, 확정은 대표가 한다). 계획
    제출기한과
    과제 완료기한은 따로 둔다(DEC403). 예산은 일회성 준비비 한도다 — 반복 운영비는 기존
    운영예산이다.
    """
    check_approval_draft(doc, args)
    _require(by, FIN, "승인서 초안")
    dec = doc["decision"]
    d_run = doc["runs"][dec["run_id"]]
    one_off = {a["alt_id"]: a["one_off"] for a in d_run["result"]["alts"]}
    items = {}
    for alt in dec["approved"]:
        it = (args.get("items") or {}).get(alt) or {}
        budget = _money(it.get("budget"))
        items[alt] = {
            "alt_id": alt,
            "decision": dec["items"][alt]["outcome"],
            "owner": OWNERS[alt],
            "worker": WORKERS[alt],
            "budget": None if budget is None else str(budget),
            "planned": one_off[alt],  # 미약정 예정 = 그 안의 일회성 준비비
            "plan_due": _when(args["plan_due"], "계획 제출기한") if args.get("plan_due") else None,
            "completion_due": _when(it["completion_due"], f"{alt} 완료기한")
            if it.get("completion_due")
            else None,
            "conditions": dec["items"][alt].get("condition_refs", []),
        }
    total = _money(args.get("total_budget"))
    n = 1 + (doc["approval_draft"] or {}).get("version", 0)
    draft = {
        "version": n,
        "decision_ref": dec["report_ref"],
        "overall_owner": _user(args.get("overall_owner")),
        "total_budget": None if total is None else str(total),
        "plan_due": _when(args["plan_due"], "계획 제출기한") if args.get("plan_due") else None,
        "items": items,
        "delegation": _text(args, "delegation"),
        "minutes": _text(args, "minutes"),
        "drafted_by": by,
        "drafted_at": doc["clock"],
    }
    draft["missing"] = approval_problems(doc, draft)
    doc["approval_draft"] = draft
    audit(doc, actor=by, action="approval_drafted", version=n, missing=draft["missing"])
    return {"version": n, "missing": len(draft["missing"])}


def check_finalize(doc: dict, args: dict[str, Any]) -> None:
    if doc["approval_draft"] is None:
        raise DomainError("승인서 초안이 없다", 409)
    if doc["approvals"]:
        raise DomainError("승인서가 이미 확정됐다", 409)
    if args.get("decision") not in ("확정", "보완요청"):
        raise DomainError("「확정」 또는 「보완요청」을 고른다", 422)
    if args["decision"] == "보완요청":
        if not _text(args, "opinion"):
            raise DomainError("보완 요청에는 사유를 적는다", 422)
        return
    problems = approval_problems(doc, doc["approval_draft"])
    if problems:
        raise PrerequisiteError(
            "승인서 필수 항목 누락 — 승인서·회의록을 확정하지 않았다: " + ", ".join(problems),
            problems,
            "APPROVAL_INCOMPLETE",
        )
    d = decision_report(doc, confirmed=True)
    if d is None or d["report_id"] != doc["approval_draft"]["decision_ref"]:
        raise DomainError("승인서의 판단본이 최신 확인 판단본이 아니다", 409)


def finalize_approval(doc: dict, args: dict[str, Any], *, by: str) -> dict[str, Any]:
    """
    APR41-v1·MIN41-v1 확정(EV41-16) — **둘을 함께** 확정한다(하나라도 빠지면 둘 다 없다). 판단본
    해시·위임 조항·
    대표 승인 계정·시각을 고정한다. 회의 결정과 유효 승인서는 다른 상태다. 보완 요청이면 초안으로
    돌아간다.
    """
    check_finalize(doc, args)
    _require(by, CEO, "승인서 확정")
    draft = doc["approval_draft"]
    if args["decision"] == "보완요청":
        draft["returned"] = {"at": doc["clock"], "by": by, "opinion": _text(args, "opinion")}
        audit(doc, actor=by, action="approval_returned", version=draft["version"])
        return {"approval_id": "", "returned": True}
    d = decision_report(doc, confirmed=True)
    dec = doc["decision"]
    total = Decimal(draft["total_budget"])
    planned = sum((Decimal(it["planned"]) for it in draft["items"].values()), Decimal(0))
    approval = {
        "approval_id": "APR41-v1",
        "version": 1,
        "decision_ref": d["report_id"],  # type: ignore[index]
        "decision_hash": d["content_hash"],  # type: ignore[index]
        "decision_id": dec["decision_id"],
        "overall_owner": draft["overall_owner"],
        "total_budget": draft["total_budget"],
        "items": copy.deepcopy(draft["items"]),
        "directives": [
            x["directive_id"] for x in ordered(doc["directives"]) if x["state"] != "WITHDRAWN"
        ],
        # 예산 구간 — 미약정 예정 · 기약정 미집행 · 집행 완료는 서로 겹치지 않는다. 여력 = 한도 −
        # 세 구간
        "budget_status": {
            "planned": str(planned),
            "committed": "0",
            "spent": "0",
            "headroom": str(total - planned),
        },
        "delegation": draft["delegation"],
        "policy_id": "POL41",
        "minutes_ref": "MIN41-v1",
        "approved_effect": dec["approved_effect"],
        "gap": dec["gap"],
        "approved_by": by,
        "approved_at": doc["clock"],
        "opinion": _text(args, "opinion"),
        "state": "VALID",
    }
    approval["content_hash"] = _hash({k: v for k, v in approval.items() if k != "opinion"})[:16]
    doc["approvals"]["APR41-v1"] = approval
    m = doc["meeting"]
    doc["minutes"]["MIN41-v1"] = {
        "minutes_id": "MIN41-v1",
        "meeting_id": MEETING_ID,
        "records": [r["record_id"] for r in m["records"]],
        "decision": dec["decision_id"],
        "approval": "APR41-v1",
        "body": draft["minutes"],
        "report": REPORT_ID,
        "decision_report": d["report_id"],  # type: ignore[index]
        "agent_drafts": [
            o["output_id"] for o in ordered(doc["agent_outputs"]) if o.get("adopted_by")
        ],
        "confirmed_by": by,
        "confirmed_at": doc["clock"],
        "state": "CONFIRMED",
    }
    for x in doc["directives"].values():
        if x["state"] == "PROPOSED":
            x["state"] = "APPROVED"
    doc["review"]["state"] = "APPROVED"
    audit(doc, actor=by, action="approval_finalized", approval="APR41-v1", event_code="EV41-16")
    return {"approval_id": "APR41-v1", "returned": False}


def valid_approval(doc: dict) -> dict | None:
    return next((a for a in reversed(ordered_approvals(doc)) if a["state"] == "VALID"), None)


def ordered_approvals(doc: dict) -> list[dict]:
    return sorted(doc["approvals"].values(), key=lambda a: a["version"])


# ─────────────────────────── S12·S13 실행과제 등록·인수 (U407 · CT408·CT409)
# ───────────────────────────


def check_register(doc: dict) -> None:
    if valid_approval(doc) is None:
        raise DomainError("유효한 승인서가 없다 — 과제는 승인서로만 만든다(CT407)", 409)
    if doc["assignments"]:
        raise DomainError("이미 등록됐다 — 같은 승인으로 과제를 두 번 만들지 않는다(T401)", 409)


def register_actions(doc: dict, *, memo: str, by: str) -> dict[str, Any]:
    """
    과제·조건·지시 등록(EV41-17, AC413) — 유효 승인서의 승인·조건부 안만 **전건 한 번에** 만든다.
    AT32에서
    두 과제가 나올 수 있어 분석과제에는 유일 제약을 걸지 않는다(승인·대안에 건다). 추가 발굴·지원
    지시·조건은
    실행과제 수에 넣지 않는다. 상세 활동계획은 장면 5다.
    """
    check_register(doc)
    _require(by, FIN, "실행과제 등록")
    apr = valid_approval(doc)
    dec = doc["decision"]
    run = doc["runs"][dec["run_id"]]
    nets = {a["alt_id"]: a["net_2027"] for a in run["result"]["alts"]}
    for alt in dec["approved"]:
        it = apr["items"][alt]  # type: ignore[index]
        aid = "ACT" + alt[3:]
        cond = dec["items"][alt]["outcome"] == "CONDITIONAL"
        doc["assignments"][aid] = _assignment(
            doc,
            aid,
            kind="ACTION",
            owner=it["owner"],
            by=by,
            extra={
                "alt_id": alt,
                "analysis_task": doc["assumptions"][alt]["task_id"],
                "approval_ref": apr["approval_id"],  # type: ignore[index]
                "decision": dec["items"][alt]["outcome"],
                "worker": it["worker"],
                "expected_effect": nets[alt],  # 예상치 — 실적이 아니다
                "budget": it["budget"],
                "plan_due": it["plan_due"],
                "completion_due": it["completion_due"],
                "conditions": it["conditions"],
                "execution_gate": (
                    "BLOCKED_BY_" + "_".join(it["conditions"])
                    if cond
                    else "PLAN_AND_APPROVAL_REQUIRED"
                ),
                "detail_plan": None,  # 장면 5 — 비어 있는 것이 정상이다
            },
        )
    for x in ordered(doc["directives"]):
        if x["state"] != "APPROVED":
            continue
        if x["alt_ref"]:
            x["action_ref"] = "ACT" + x["alt_ref"][3:]
        x["state"] = "REGISTERED"
    if "SUP41" in doc["directives"] and doc["directives"]["SUP41"]["state"] == "REGISTERED":
        sup = doc["directives"]["SUP41"]
        doc["assignments"]["SUP41"] = _assignment(
            doc,
            "SUP41",
            kind="SUPPORT",
            owner=sup["owner"],
            by=by,
            extra={"approval_ref": apr["approval_id"], "directive": "SUP41"},  # type: ignore[index]
        )
    doc["assignments"]["TOTAL"] = _assignment(
        doc,
        "TOTAL",
        kind="OVERALL",
        owner=apr["overall_owner"],  # type: ignore[index]
        by=by,
        extra={
            "approval_ref": apr["approval_id"],  # type: ignore[index]
            "total_budget": apr["total_budget"],  # type: ignore[index]
            "directive": "DIR41",
        },
    )
    doc["review"]["state"] = "AWAITING_ACCEPTANCE"
    audit(
        doc,
        actor=by,
        action="actions_registered",
        targets=list(doc["assignments"]),
        event_code="EV41-17",
    )
    return assignment_outputs(doc)


def _assignment(doc: dict, aid: str, *, kind: str, owner: str, by: str, extra: dict) -> dict:
    return {
        "target_id": aid,
        "seq": _seq(doc["assignments"]),
        "kind": kind,
        "owner": owner,
        "assignment_version": 1,
        "state": "ASSIGNED",
        "assigned_at": doc["clock"],
        "assigned_by": by,
        "accept_due": _due_at(doc, "accept_due"),
        "accepted_at": None,
        "accepted_by": None,
        "accepted_version": None,
        "history": [{"at": doc["clock"], "state": "ASSIGNED", "by": by, "version": 1}],
        **extra,
    }


def assignment_outputs(doc: dict) -> dict[str, Any]:
    """그림의 인수 갈래가 쓰는 값 — 배정 여부·책임자 이름·배정버전(대상마다)."""
    out: dict[str, Any] = {}
    for tid in ACCEPT_NODES:
        a = doc["assignments"].get(tid)
        on = a is not None
        key = tid.lower()
        out[f"{key}_assigned"] = on
        out[f"{key}_owner"] = name_of(a["owner"]) if on else ""  # type: ignore[index]
        out[f"{key}_version"] = a["assignment_version"] if on else 0  # type: ignore[index]
    return out


#: 인수 대상 → 같은 인수로 책임을 넘겨받는 조건·지시(복수 대상은 둘 다 검증한 뒤 한 번에 저장한다)
LINKED = {"ACT42": ("CON41",), "SUP41": ("SUP41",), "TOTAL": ("DIR41",)}


def check_acceptance(doc: dict, target: str, args: dict[str, Any]) -> None:
    a = doc["assignments"].get(target)
    if a is None:
        raise DomainError(f"없는 인수 대상: {target}", 404)
    if a["state"] != "ASSIGNED":
        raise DomainError(f"{target}는 인수 대기가 아니다 ({a['state']})", 409)
    choices = ("인수",) if target == "TOTAL" else ("인수", "반려")
    if args.get("decision") not in choices:
        raise DomainError(f"{' 또는 '.join(choices)}를 고른다", 422)
    if args["decision"] == "반려" and not _text(args, "reason"):
        raise DomainError("반려에는 사유가 필요하다", 422)
    version = args.get("version")
    if version not in (None, "") and int(version) != a["assignment_version"]:
        raise DomainError(
            f"본 배정버전({version})이 최신({a['assignment_version']})이 아니다 — 새 버전을 "
            "인수한다",
            409,
        )
    apr = valid_approval(doc)
    if apr is None or a["approval_ref"] != apr["approval_id"]:
        raise DomainError("배정의 승인서가 유효한 최신 승인서가 아니다", 409)


def accept(doc: dict, target: str, args: dict[str, Any], *, by: str, strict: bool = True) -> None:
    """
    책임 인수·반려(EV41-18~22, AC414·AC415) — **그 책임자만**(대리 인수 불가, 대표·임원도 대신 못
    한다). ACT42
    인수는 CON41 책임 인수를 함께 한다 — 조건 이행 완료가 아니다(책임 ACCEPTED · 이행 OPEN).
    """
    check_acceptance(doc, target, args)
    a = doc["assignments"][target]
    _require(by, a["owner"], f"{target} 인수", strict=strict)
    ok = args["decision"] == "인수"
    if ok:
        a.update(
            state="ACCEPTED",
            accepted_at=doc["clock"],
            accepted_by=by,
            accepted_version=a["assignment_version"],
        )
        for did in LINKED.get(target, ()):
            x = doc["directives"].get(did)
            if x is not None:
                x.update(responsibility="ACCEPTED", responsibility_at=doc["clock"])
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
    codes = {"ACT41": "EV41-18", "SUP41": "EV41-19", "ACT42": "EV41-20", "ACT43": "EV41-21"}
    codes["TOTAL"] = "EV41-22"
    audit(
        doc,
        actor=by,
        action="accepted" if ok else "returned",
        target=target,
        version=a["assignment_version"],
        event_code=codes.get(target) if ok else None,
    )


def check_revise(doc: dict, target: str, args: dict[str, Any]) -> None:
    a = doc["assignments"].get(target)
    if a is None or a["state"] != "RETURNED":
        raise DomainError(f"{target}는 반려된 대상이 아니다", 409)
    if not _text(args, "reason") or not _text(args, "change"):
        raise DomainError("변경 사유와 보완 내용을 적는다", 422)


def revise_assignment(doc: dict, target: str, args: dict[str, Any], *, by: str) -> dict[str, Any]:
    """
    반려 보완(AC415) — 승인 범위 안의 설명·조건 명확화만 새 배정버전으로 다시 낸다.
    범위·책임·한도·기한을 바꾸는
    중대 변경은 대표 재확인(새 승인 버전)이다 — 여기서는 받지 않는다. 원 반려 이력은 그대로다.
    """
    check_revise(doc, target, args)
    _require(by, CFO, f"{target} 보완")
    a = doc["assignments"][target]
    a["assignment_version"] += 1
    a["state"] = "ASSIGNED"
    a["clarification"] = _text(args, "change")
    a["history"].append(
        {
            "at": doc["clock"],
            "state": "ASSIGNED",
            "by": by,
            "version": a["assignment_version"],
            "note": _text(args, "reason"),
            "change": _text(args, "change"),
        }
    )
    audit(
        doc, actor=by, action="assignment_revised", target=target, version=a["assignment_version"]
    )
    return {"owner": name_of(a["owner"]), "version": a["assignment_version"]}


def acceptance_rate(doc: dict) -> dict[str, Any]:
    """
    M408 — 현재 배정된 실행과제 중 현재 버전을 인수한 수. 전체 책임·지시 인수는 따로 본다. 0건이면
    N/A.
    """
    actions = [a for a in doc["assignments"].values() if a["kind"] == "ACTION"]
    done = [a for a in actions if _accepted(a)]
    total = doc["assignments"].get("TOTAL")
    return {
        "assigned": len(actions),
        "accepted": len(done),
        "overall_accepted": bool(total and _accepted(total)),
        "rate": None if not actions else str(Decimal(len(done)) / Decimal(len(actions))),
    }


def _accepted(a: dict) -> bool:
    return a["state"] == "ACCEPTED" and a["accepted_version"] == a["assignment_version"]


# ─────────────────────────── S14 종료·장면 5 인계 (U408 · CT409·CT410) ───────────────────────────


def completion_conditions(doc: dict) -> dict[str, Any]:
    """
    종료 요건(구현명세 7장 U408) — 최신 승인서와 확인된 회의록, 전체·개별 최신 인수, 조건·지원·추가
    지시의
    책임·확인자·기한·책임 인수. **CON41 OPEN 자체는 차단이 아니다**(E406). 상세 계획 완성도 요건이
    아니다.
    """
    apr = valid_approval(doc)
    rate = acceptance_rate(doc)
    pending = [
        a for a in ordered(doc["assignments"]) if a["kind"] != "OVERALL" and not _accepted(a)
    ]
    directives = [x for x in ordered(doc["directives"]) if x["state"] != "WITHDRAWN"]
    items = [
        ("approval", "유효한 최신 승인서(APR41)", apr is not None),
        (
            "minutes",
            "확인된 회의록(MIN41)",
            any(m["state"] == "CONFIRMED" for m in doc["minutes"].values()),
        ),
        ("registered", "실행과제 등록", rate["assigned"] > 0),
        (
            "accepted",
            f"개별 과제 현재 버전 인수 ({rate['accepted']}/{rate['assigned']})",
            rate["assigned"] > 0 and not [a for a in pending if a["kind"] == "ACTION"],
        ),
        ("overall", "전체 책임 인수(경영관리 임원)", rate["overall_accepted"]),
        (
            "directives",
            "조건·지원·추가 지시의 책임·확인자·기한·책임 인수",
            bool(directives)
            and all(
                not _directive_problems(x, "") and x["responsibility"] == "ACCEPTED"
                for x in directives
            ),
        ),
        (
            "independent",
            "Risk OPEN · Forecast REVIEW_PENDING · Target UNCHANGED 유지",
            (doc["review"]["risk"], doc["review"]["forecast"], doc["review"]["target"])
            == ("OPEN", "REVIEW_PENDING", "UNCHANGED"),
        ),
    ]
    blocking = [
        label for key, label, ok in items if not ok and key not in ("accepted", "directives")
    ]
    blocking += [f"{a['target_id']} 현재 배정버전 미인수 ({name_of(a['owner'])})" for a in pending]
    for x in directives:
        if x["responsibility"] != "ACCEPTED" and not any(
            x["directive_id"] in LINKED.get(a["target_id"], ()) for a in pending
        ):
            blocking.append(f"{x['directive_id']} 책임 미인수")
        blocking += _directive_problems(x, x["directive_id"])
    return {
        "items": [{"id": k, "label": label, "ok": ok} for k, label, ok in items],
        "met": all(ok for _k, _l, ok in items),
        "blocking": list(dict.fromkeys(blocking)),
        "rate": rate,
        "open_conditions": [
            x["directive_id"]
            for x in directives
            if x["kind"] == "CONDITION" and x["fulfillment"] == "OPEN"
        ],
    }


def check_complete(doc: dict) -> None:
    if doc["handoff"] is not None:
        raise DomainError("이미 완료된 업무다 — 완료본은 바꾸지 않는다", 409)
    check = completion_conditions(doc)
    if not check["met"]:
        raise PrerequisiteError(
            "종료 요건 미충족: " + ", ".join(check["blocking"]),
            check["blocking"],
            "COMPLETION_BLOCKED",
        )


def complete_scene(doc: dict, *, memo: str, by: str) -> str:
    """
    장면 4 완료(EV41-23) — 요건을 서버가 다시 검사하고 HANDOFF41과 SC04_COMPLETED를 **함께**
    저장한다. 인계는
    UI 요약이 아니라 승인본·계산본·배정·인수 버전의 연결이다. Risk·Forecast·Target은 그대로다.
    """
    check_complete(doc)
    _require(by, FIN, "업무 종료")
    apr = valid_approval(doc)
    dec = doc["decision"]
    run = doc["runs"][dec["run_id"]]
    y = run["result"]["periods"]["year"]
    total = doc["assignments"]["TOTAL"]
    doc["handoff"] = {
        "handoff_id": HANDOFF_ID,
        "review_id": REVIEW_ID,
        "source_handoff": SOURCE_HANDOFF,
        "meeting": MEETING_ID,
        "report": REPORT_ID,
        "decision": dec["report_ref"],
        "approval": apr["approval_id"],  # type: ignore[index]
        "minutes": apr["minutes_ref"],  # type: ignore[index]
        "overall_owner": total["owner"],
        "acceptance_ref": {"version": total["assignment_version"], "at": total["accepted_at"]},
        "actions": [
            {
                k: a.get(k)
                for k in (
                    "target_id",
                    "alt_id",
                    "analysis_task",
                    "owner",
                    "budget",
                    "expected_effect",
                    "plan_due",
                    "completion_due",
                    "assignment_version",
                    "accepted_at",
                    "execution_gate",
                    "decision",
                )
            }
            for a in ordered(doc["assignments"])
            if a["kind"] == "ACTION"
        ],
        "conditions": [
            {
                k: x[k]
                for k in (
                    "directive_id",
                    "content",
                    "owner",
                    "collaborators",
                    "verifier",
                    "due_at",
                    "fulfillment",
                    "responsibility",
                    "action_ref",
                )
            }
            for x in ordered(doc["directives"])
            if x["kind"] == "CONDITION" and x["state"] != "WITHDRAWN"
        ],
        "directives": [
            {
                k: x[k]
                for k in (
                    "directive_id",
                    "kind",
                    "content",
                    "owner",
                    "verifier",
                    "due_at",
                    "responsibility",
                    "expected_effect",
                )
            }
            for x in ordered(doc["directives"])
            if x["kind"] != "CONDITION" and x["state"] != "WITHDRAWN"
        ],
        "excluded": [
            {"alt_id": EXCLUDED_ALT, "result": "RES43", "evidence": "EVDC48"},
            *[
                {"alt_id": a, "decision": it["outcome"], "reason": it["reason"]}
                for a, it in dec["items"].items()
                if it["outcome"] in ("HOLD", "REJECTED")
            ],
        ],
        "financial_snapshot": {
            "baseline": y["base"],
            "target": y["target"],
            "effect": y["effect"],
            "gap": y["gap"],
            # 조건부 효과는 예상치로 따로 — 기본 효과와 합산하지 않는다
            "conditional_effect": str(
                sum(
                    (
                        Decimal(a["net_2027"])
                        for a in run["result"]["alts"]
                        if a["alt_id"] in dec["conditional"]
                    ),
                    Decimal(0),
                )
            ),
            "gap_excl_conditional": y["gap_excl_conditional"],
            "normal_annual_reference": run["result"]["normal_annual_total"],
        },
        "execution_gates": [
            {"target_id": a["target_id"], "gate": a["execution_gate"]}
            for a in ordered(doc["assignments"])
            if a["kind"] == "ACTION"
        ],
        "budget": {"total": apr["total_budget"], **apr["budget_status"]},  # type: ignore[index]
        "detail_plan": "PLAN_PENDING",  # 장면 5 — 빈 계획을 완료로 처리하지 않는다
        "state_snapshot": {
            "scene": "SC04_COMPLETED",
            "risk": "OPEN",
            "forecast": "REVIEW_PENDING",
            "target": "UNCHANGED",
        },
        "as_of": doc["clock"],
        "completed_by": by,
        "memo": memo,
    }
    doc["review"].update(state="SC04_COMPLETED", completed_at=doc["clock"])
    audit(doc, actor=by, action="SC04_COMPLETED", handoff=HANDOFF_ID, event_code="EV41-23")
    return HANDOFF_ID


# ─────────────────────────── 예산 위임 조회 (E407) ───────────────────────────


def budget_policy(doc: dict, request: dict[str, Any]) -> dict[str, Any]:
    """
    승인서의 위임 조항으로 판단만 한다 — 전용·초과 거래를 만들지 않는다(실제 처리는 후속 실행).
    """
    apr = valid_approval(doc)
    if apr is None:
        raise DomainError("유효한 승인서가 없다", 409)
    alloc = {
        "ACT" + alt[3:]: Decimal(it["budget"]) for alt, it in apr["items"].items() if it["budget"]
    }
    try:
        return calc.budget_policy(Decimal(apr["total_budget"]), alloc, request)
    except (KeyError, ValueError, ArithmeticError) as exc:
        raise DomainError(f"조회 입력이 맞지 않다: {exc}", 422) from exc


# ─────────────────────────── Agent (구현명세 15장) ───────────────────────────


def agent_draft(doc: dict, *, kind: str) -> str:
    """
    초안 하나 — 같은 입력이면 이전 성공 초안을 다시 쓴다. 실패해도 업무는 계속된다(E408 — 수동
    작성).
    초안에는 draft_id·source_hash·cited_refs·generated_at·prompt_version·status가 있다.
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
    """채택 기록 — 원 초안은 그대로, 검토자·시각만. 추천·승인·인수를 대신하지 않는다."""
    if actor not in (FIN, CFO):
        raise DomainError("초안 채택은 경영관리 담당·임원이 한다", 403)
    o = doc["agent_outputs"].get(output_id)
    if o is None or o["status"] != "SUCCEEDED":
        raise DomainError("채택할 초안이 없다", 404)
    o.update(adopted_by=actor, adopted_at=doc["clock"], review_status="ADOPTED")
    audit(doc, actor=actor, action="agent_adopted", output_id=output_id)


# ─────────────────────────── 작업 → 업무 효과 (기록 작업의 몸통) ───────────────────────────

RECORDS = (
    "submit_result",
    "confirm_result",
    "verify_effects",
    "correct_effects",
    "recommend",
    "freeze_report",
    "open_meeting",
    "draft_decision",
    "confirm_decision",
    "decide",
    "draft_approval",
    "finalize_approval",
    "register_actions",
    "accept",
    "revise_assignment",
    "complete_scene",
)


def _rec_items(args: dict[str, Any]) -> dict[str, Any]:
    return {
        alt: {
            "pick": args.get(f"{alt.lower()}_pick"),
            "priority": args.get(f"{alt.lower()}_priority"),
            "reason": args.get(f"{alt.lower()}_reason"),
        }
        for alt in ALTS
    }


def _decision_args(args: dict[str, Any]) -> dict[str, Any]:
    changes = []
    if args.get("change_alt") not in (None, "", "없음"):
        field = next(
            (k for k, v in calc.FIELDS.items() if v == args.get("change_field")),
            args.get("change_field"),
        )
        changes.append(
            {"alt_id": args["change_alt"], "field": field, "value": args.get("change_value")}
        )
    return {
        "changes": changes,
        "reason": args.get("reason"),
        "confirmed_by": args.get("confirmed_by"),
        "condition": {
            "content": args.get("condition"),
            "owner": args.get("condition_owner"),
            "collaborators": args.get("condition_collaborators"),
            "verifier": args.get("condition_verifier"),
            "due_at": args.get("condition_due"),
        },
        "support": {
            "content": args.get("support"),
            "owner": args.get("support_owner"),
            "collaborators": args.get("support_collaborators"),
            "verifier": args.get("support_verifier"),
            "due_at": args.get("support_due"),
        },
    }


def _decide_args(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "items": {
            alt: {
                "outcome": args.get(f"{alt.lower()}_outcome"),
                "reason": args.get(f"{alt.lower()}_reason"),
            }
            for alt in ALTS
        },
        "condition_refs": args.get("condition_refs"),
        "discovery": {
            "content": args.get("discovery"),
            "owner": args.get("discovery_owner"),
            "collaborators": args.get("discovery_collaborators"),
            "due_at": args.get("discovery_due"),
        },
    }


def _approval_args(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "overall_owner": args.get("overall_owner"),
        "total_budget": args.get("total_budget"),
        "plan_due": args.get("plan_due"),
        "items": {
            alt: {
                "budget": args.get(f"{alt.lower()}_budget"),
                "completion_due": args.get(f"{alt.lower()}_due"),
            }
            for alt in ALTS
        },
        "delegation": args.get("delegation"),
        "minutes": args.get("minutes"),
    }


def check(doc: dict, operation: str, args: dict[str, Any]) -> None:
    """
    기록 작업의 사전 검사 — **부수 효과가 없다**. 화면 답(내장·대리 답)은 답을 넣기 전에, 기록
    작업은 적기 전에
    같은 검사를 한다(Studio·Center 콘솔 답은 NowView 사전 검사를 거치지 않는다).
    """
    if operation == "submit_result":
        check_submit(doc, str(args.get("task_id") or ""), args)
    elif operation == "confirm_result":
        check_confirm(doc, str(args.get("task_id") or ""), args)
    elif operation == "verify_effects":
        check_verify(doc)
    elif operation == "correct_effects":
        check_correct(doc, args)
    elif operation == "recommend":
        check_recommend(
            doc,
            {
                "items": _rec_items(args),
                "excluded_reason": args.get("excluded_reason"),
                "owners": args.get("owners"),
            },
        )
    elif operation == "freeze_report":
        check_freeze(doc)
    elif operation == "open_meeting":
        check_open_meeting(doc)
    elif operation == "draft_decision":
        check_decision_draft(doc, _decision_args(args))
    elif operation == "confirm_decision":
        check_confirm_decision(doc, args)
    elif operation == "decide":
        check_decide(doc, _decide_args(args))
    elif operation == "draft_approval":
        check_approval_draft(doc, _approval_args(args))
    elif operation == "finalize_approval":
        check_finalize(doc, args)
    elif operation == "register_actions":
        check_register(doc)
    elif operation == "accept":
        check_acceptance(doc, str(args.get("target") or ""), args)
    elif operation == "revise_assignment":
        check_revise(doc, str(args.get("target") or ""), args)
    elif operation == "complete_scene":
        check_complete(doc)


def apply(
    doc: dict, seed: Seed, operation: str, args: dict[str, Any], *, by: str, strict: bool
) -> dict[str, Any]:
    """
    기록 작업 하나의 업무 효과. 검사는 `check`가 먼저 했다. 출력은 그림의 `output` 대응이 쓴다.
    """
    if operation == "submit_result":
        return {
            "result_ref": submit_result(doc, seed, str(args["task_id"]), args, by=by, strict=strict)
        }
    if operation == "confirm_result":
        confirm_result(doc, str(args["task_id"]), args, by=by, strict=strict)
        return {}
    if operation == "verify_effects":
        return verify_effects(doc, seed, memo=_text(args, "memo"), by=by)
    if operation == "correct_effects":
        correct_effects(doc, args, by=by, strict=strict)
        return {}
    if operation == "recommend":
        ref = recommend(
            doc,
            {
                "items": _rec_items(args),
                "excluded_reason": args.get("excluded_reason"),
                "owners": args.get("owners"),
            },
            by=by,
        )
        return {"recommendation_ref": ref}
    if operation == "freeze_report":
        return {
            "report_id": freeze_report(
                doc,
                seed,
                conclusion=_text(args, "conclusion"),
                recipients=_text(args, "recipients"),
                by=by,
            )
        }
    if operation == "open_meeting":
        return {"meeting_id": open_meeting(doc, summary=_text(args, "summary"), by=by)}
    if operation == "draft_decision":
        return {"report_id": draft_decision(doc, seed, _decision_args(args), by=by)}
    if operation == "confirm_decision":
        return {"report_id": confirm_decision(doc, opinion=_text(args, "opinion"), by=by)}
    if operation == "decide":
        return {"decision_id": decide(doc, seed, _decide_args(args), by=by)}
    if operation == "draft_approval":
        return draft_approval(doc, _approval_args(args), by=by)
    if operation == "finalize_approval":
        return finalize_approval(doc, args, by=by)
    if operation == "register_actions":
        return register_actions(doc, memo=_text(args, "memo"), by=by)
    if operation == "accept":
        accept(doc, str(args["target"]), args, by=by, strict=strict)
        return {}
    if operation == "revise_assignment":
        return revise_assignment(doc, str(args["target"]), args, by=by)
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
    owner = spec.get("owner_of")
    if owner == "rework":
        rw = open_rework(doc) or (doc["rework"][-1] if doc["rework"] else None)
        if rw is not None:
            return rw["owner"]
        return CFO
    if owner:
        a = doc["assignments"].get(owner)
        if a is not None and a.get("owner"):
            return a["owner"]
    return user_for_role(spec["role"])


def _due_at(doc: dict, key: str) -> str:
    target = SCHEDULE[key]
    # 정해진 시각이 이미 지났으면(되돌아온 업무) 다음 영업일 18시다
    if parse_at(target) > parse_at(doc["clock"]):
        return target
    return due_at(parse_at(doc["clock"]), 1).isoformat()


def _due(doc: dict, node_id: str) -> str:
    due = NODE_ROLES[node_id]["due"]
    if isinstance(due, str):
        return _due_at(doc, due)
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
        _open_task(doc, p["node_id"], request_id=request_id)


def ensure_task(doc: dict, node_id: str) -> None:
    """
    결정이 기록되는데 업무가 없으면 지금 연다 — 늦게 열었다고 표시한다(Studio, 장면 1~3과 같다).
    """
    if node_id in NODE_ROLES and task_for_node(doc, node_id) is None:
        _open_task(doc, node_id, request_id=None, late=True)


def complete_task(doc: dict, node_id: str, *, actor: str) -> None:
    task = task_for_node(doc, node_id)
    if task is None:
        return
    task.update(status="COMPLETED", completed_at=doc["clock"], completed_by=actor)
    task["history"].append({"at": doc["clock"], "status": "COMPLETED", "by": actor, "note": None})
    audit(doc, actor=actor, action="task_completed", task_id=task["task_id"])


def check_actor(doc: dict, node_id: str, actor: str) -> None:
    """역할·담당 검사 — 인수·보완은 그 대상의 책임자만, 나머지는 역할표의 사람이다(403)."""
    user = USERS.get(actor)
    if user is None:
        raise DomainError(f"모르는 사용자: {actor}", 403)
    spec = NODE_ROLES[node_id]
    if "owner_of" in spec:
        owner = assignee_of(doc, node_id)
        if actor != owner:
            what = "검증 보완" if spec["owner_of"] == "rework" else f"{spec['owner_of']} 인수·반려"
            raise DomainError(f"{what}는 책임자({name_of(owner)})만 한다", 403)
        return
    if user["role"] != spec["role"]:
        raise DomainError(f"{spec['role']}만 할 수 있다 (현재 {user['role']})", 403)


def is_overdue(due: str | None, clock: str) -> bool:
    return due is not None and parse_at(clock) > parse_at(due)


def raise_overdue_alerts(doc: dict) -> list[dict]:
    """
    기한 초과 알림 — 업무(미완료)·책임 인수(미인수). 같은 대상·기한에 한 번만. 내부 알림이다(메일
    없음).
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
                    f"{a['target_id']}:accept",
                    a["accept_due"],
                    [a["owner"], FIN],
                    f"{a['target_id']} 인수 지연",
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


# ─────────────────────────── 상태 (구현명세 11장) ───────────────────────────


def statuses(doc: dict) -> dict[str, Any]:
    """
    독립 배지 — 장면 · 승인 · 조건 · 위험 · 공식 전망 · 목표. 장면 완료와 위험 해소는 다른 말이다.
    """
    r = doc["review"]
    apr = valid_approval(doc)
    cond = [
        x
        for x in doc["directives"].values()
        if x["kind"] == "CONDITION" and x["state"] != "WITHDRAWN"
    ]
    return {
        "review": r["state"],
        "approval": None if apr is None else apr["state"],
        "conditions": "OPEN"
        if any(c["fulfillment"] == "OPEN" for c in cond)
        else (None if not cond else "FULFILLED"),
        "risk": r["risk"],
        "forecast": r["forecast"],
        "target": r["target"],
        "scene": "SC04_COMPLETED"
        if r["state"] == "SC04_COMPLETED"
        else ("PENDING" if r["started_at"] is None else "ACTIVE"),
    }


#: Studio는 끝을 작업 호출로만 안다 — 이 작업이 기록되면 흐름이 끝난다.
def ends_flow(operation: str) -> bool:
    return operation == "complete_scene"


__all__ = ["CASES", "NODE_ROLES", "RECORDS", "SEED_ID", "apply", "check", "kst"]
