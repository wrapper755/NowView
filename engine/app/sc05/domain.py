"""
SC05 업무 기록 — 결정 실행과 계획 갱신(MR-2706-01 · ACT42 긴급구매 축소 상세 시연 · 월간 Rolling).

장면 1~4와 같은 원칙이다: **한 데모 실행 = 문서 하나**, 순수 함수, 저장·BPM은 `process.py`. 데모
실행 id는
장면 1~4와 같다. 장면 5는 **장면 4 인계(HANDOFF41)에서 시작한다** — 그 결과는 시작할 때
스냅샷(`sc04`)으로 둔다.

**상태 축은 서로 독립이다**(구현명세 10장): 장면 · 상세 계획(확정)과 경영관리 확인 · 변경 요청 ·
CON41 · SUP41 ·
품의 · ACT42 운영 · 변경 대응 · 초기 결과 · 운영계획 · 전망 · Risk(OPEN) · Target(UNCHANGED). 계획
확정은 조건
충족이 아니고, 착수는 연간 성과 달성이 아니고, 장면 완료는 과제 완료·위험 해소가 아니다.

* 확정 계획·승인된 품의·마감 자료·승인 전망은 **고치지 않는다**. 바뀌면 새 버전이다(PL51-v2, RUN52
  …).
* 업무 효과는 결재 뒤의 「… 기록」 작업이 낸다(장면 1~4 N1과 같다). `check(doc, operation, args)`가
  같은 규칙을
  화면 답의 사전 검사와 기록 작업 양쪽에서 건다 — **검사가 부수 효과보다 먼저**다.
* **시각이 지나야 보인다**(구현명세 16장 「데모 적재」). 배경 원천(ACT41·43 품의·집행, 배경 변경
  건·구매 주문,
  FC50, 근거 문서)은 가상시계가 그 시각을 지날 때 문서에 들어온다(`catch_up`) — 미래 행을 내려보낸
  뒤 화면에서
  감추지 않는다. 시각 이동은 사람의 승인·착수를 만들지 않는다 — 시연 단계(D5xx)만 사람의 업무다.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
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
from app.sc05 import agent, calc
from app.sc05.seed import SEED_ID, Seed, kst

REVIEW_ID = "MR-2706-01"
SOURCE_HANDOFF = "HANDOFF41"
HANDOFF_ID = "HANDOFF51"
TASK_ID = "ACT42"
PLAN_PREFIX = "PL51"
START_ID = "START51"
RISK_ID = "RISK51"

FIN, CFO, CEO = "u-fin", "u-fin-exec", "u-ceo"
PROD_LEAD, BUY_LEAD, BUY_STAFF = "u-prod-lead", "u-buy-lead", "u-buy"
PROD_EXEC, BUY_EXEC, SALES_EXEC, QA_LEAD = "u-prod-exec", "u-buy-exec", "u-sales-exec", "u-qa-lead"

#: 데이터의 가상 계정 → NowView 사용자. 장면 4와 같은 대응이고, USR-BUY2(구매 대행)는 장면 2의
#: 구매담당이다.
ACCOUNTS = {
    "USR-FIN": FIN,
    "USR-CFO": CFO,
    "USR-CEO": CEO,
    "USR-PROD": PROD_LEAD,
    "USR-BUY": BUY_LEAD,
    "USR-BUY2": BUY_STAFF,
    "USR-QA": QA_LEAD,
    "EX-PROD": PROD_EXEC,
    "EX-BUY": BUY_EXEC,
    "EX-SALES": SALES_EXEC,
}
#: 과제 → 책임 임원(장면 4 인수) · 운영계획 · 배경 계획
OWNERS = {"ACT41": PROD_EXEC, "ACT42": BUY_EXEC, "ACT43": BUY_EXEC}
OPERATING_PLANS = {"OPL51": "ACT42", "OPL52": "ACT41", "OPL53": "ACT43"}
BACKGROUND_PLANS = {"PL52-v1": "ACT41", "PL53-v1": "ACT43"}
#: 전망 가정 확인 부서 → 임원(구현명세 7장). 다른 부서를 대행하지 않는다.
DEPARTMENTS = {"BUY": BUY_EXEC, "PROD": PROD_EXEC, "SALES": SALES_EXEC}
#: 대표 변경 건 — 고객 원문 → 변경 건. 기본 시연은 정상 대응 한 건과 긴급 예외 한 건을 BPM 결재로
#: 돈다
#: (업무설계 V505 「상세 대표 정상 건과 긴급 예외 건」). 나머지 네 건은 배경 원천이다.
REPRESENTATIVE = {"CP51": "CH51", "CP52": "CH52"}
#: 월중 구간 — 9/1~7, 9/8~14, 9/15~21, 9/22~30(구현명세 5장)
WINDOWS = ("9/1~7", "9/8~14", "9/15~21", "9/22~30")
REQUESTS = {
    "REQ51": {"scope": "ONEOFF", "label": "일회성 검증비"},
    "OP51": {"scope": "OPERATING", "label": "9~12월 운영지원비"},
}


def _at(y: int, mo: int, d: int, h: int, mi: int = 0) -> str:
    return datetime(y, mo, d, h, mi, tzinfo=KST).isoformat()


#: 시연 일정(구현명세 17장·SC05설정) — 2027년 가상 업무 일정이다.
SCHEDULE = {
    "start_at": _at(2027, 7, 13, 10),  # 초기 시점(HANDOFF41만 보인다)
    "plan_due": _at(2027, 7, 16, 18),  # 상세 계획 제출(장면 4 승인서)
    "condition_due": _at(2027, 8, 20, 18),  # CON41·SUP41
    "apply_at": _at(2027, 9, 1, 9),  # 운영 적용(효과 개시 9월)
    "start_due": _at(2027, 9, 1, 18),
    "task_due": _at(2027, 9, 30, 18),  # ACT42 과제 완료기한
    "result_confirmed_at": _at(2027, 9, 30, 18),  # 9월 구매 결과 확인(월마감 확인시각)
    "observation_due": _at(2027, 10, 4, 18),
    "opl_due": _at(2027, 10, 4, 18),
    "forecast_due": _at(2027, 10, 5, 18),
    "approve_due": _at(2027, 10, 6, 18),
    "complete_due": _at(2027, 10, 6, 18),
    "followup_due": _at(2027, 10, 29, 18),
}
CUTOFF = date(2027, 10, 1)  # 첫 전망월 — 9월까지 마감

#: 시연 사례 — BASE와 X 사례는 **별도 데모 실행**이다(기본 집계에 섞지 않는다, T529).
#: X501·X504·X505·X509는
#: 시도·거절 확인이라 엔진 시험으로 잠근다(각본이 실패로 멈추지 않게).
CASES: dict[str, str] = {
    "BASE": "기본 시연",
    "X502": "X502 총괄 한도 초과 변경 → 시행 보류",
    "X503": "X503 CH54 구매 확인 누락 → 미확인 표시",
    "X506": "X506 승인효과 재가산 → 대사 실패·재작성",
    "X507": "X507 대표 반려 → FC50 유지·보완 재승인",
    "X508": "X508 11월 긴급 3→4건 → 새 전망",
}

#: BPMN 사람 노드 → 업무 종류·역할·기한. `due`는 SCHEDULE 키 또는 영업일 수다.
NODE_ROLES: dict[str, dict[str, Any]] = {
    "Draft_Plan": {"task": "PLAN_DRAFT", "role": "구매팀장", "due": "plan_due"},
    "Coordinate_Plan": {"task": "PLAN_COORDINATE", "role": "생산임원", "due": "plan_due"},
    "Confirm_Plan": {"task": "PLAN_CONFIRM", "role": "구매임원", "due": "plan_due"},
    "Verify_Plan": {"task": "PLAN_VERIFY", "role": "경영관리임원", "due": "plan_due"},
    "Request_Change": {"task": "CHANGE_REQUEST", "role": "구매팀장", "due": "condition_due"},
    "Coordinate_Change": {"task": "CHANGE_COORDINATE", "role": "생산임원", "due": 1},
    "Confirm_Change": {"task": "CHANGE_CONFIRM", "role": "구매임원", "due": 1},
    "Verify_Change": {"task": "CHANGE_VERIFY", "role": "경영관리임원", "due": 1},
    "Evidence_CON41": {"task": "CON41_EVIDENCE", "role": "구매팀장", "due": "condition_due"},
    "Ready_CON41": {"task": "CON41_READY", "role": "생산임원", "due": "condition_due"},
    "Confirm_CON41": {"task": "CON41_CONFIRM", "role": "구매임원", "due": "condition_due"},
    "Register_SUP41": {"task": "SUP41_REGISTER", "role": "생산임원", "due": "condition_due"},
    "Verify_SUP41": {"task": "SUP41_VERIFY", "role": "경영관리임원", "due": "condition_due"},
    "Submit_REQ51": {"task": "REQ51_SUBMIT", "role": "구매팀장", "due": "condition_due"},
    "Func_REQ51": {"task": "REQ51_FUNCTION", "role": "구매임원", "due": "condition_due"},
    "Budget_REQ51": {"task": "REQ51_BUDGET", "role": "경영관리임원", "due": "condition_due"},
    "Submit_OP51": {"task": "OP51_SUBMIT", "role": "구매팀장", "due": "condition_due"},
    "Func_OP51": {"task": "OP51_FUNCTION", "role": "구매임원", "due": "condition_due"},
    "Budget_OP51": {"task": "OP51_BUDGET", "role": "경영관리임원", "due": "condition_due"},
    "Start_Operation": {"task": "START", "role": "구매임원", "due": "start_due"},
    "Receive_Change": {"task": "CHANGE_RECEIVE", "role": "생산팀장", "due": 1},
    "Share_Change": {"task": "CHANGE_SHARE", "role": "생산팀장", "due": "share"},
    "Ack_Change": {"task": "CHANGE_ACK", "role": "구매팀장", "due": "ack"},
    "Respond_Change": {"task": "CHANGE_RESPOND", "role": "구매팀장", "due": 1},
    "Approve_Urgent": {"task": "URGENT_APPROVE", "role": "구매임원", "due": 1},
    "Execute_Order": {"task": "ORDER_EXECUTE", "role": "구매팀장", "due": 1},
    "Confirm_Observation": {"task": "OBSERVE", "role": "구매임원", "due": "observation_due"},
    "Confirm_OPL51": {"task": "OPL51_CONFIRM", "role": "구매임원", "due": "opl_due"},
    "Confirm_OPL52": {"task": "OPL52_CONFIRM", "role": "생산임원", "due": "opl_due"},
    "Confirm_OPL53": {"task": "OPL53_CONFIRM", "role": "구매임원", "due": "opl_due"},
    "Verify_OPL51": {"task": "OPL51_VERIFY", "role": "경영관리임원", "due": "opl_due"},
    "Verify_OPL52": {"task": "OPL52_VERIFY", "role": "경영관리임원", "due": "opl_due"},
    "Verify_OPL53": {"task": "OPL53_VERIFY", "role": "경영관리임원", "due": "opl_due"},
    "Draft_Forecast": {"task": "FC_DRAFT", "role": "경영관리담당", "due": "forecast_due"},
    "Confirm_FC_BUY": {"task": "FC_BUY", "role": "구매임원", "due": "forecast_due"},
    "Confirm_FC_PROD": {"task": "FC_PROD", "role": "생산임원", "due": "forecast_due"},
    "Confirm_FC_SALES": {"task": "FC_SALES", "role": "영업임원", "due": "forecast_due"},
    "Submit_Forecast": {"task": "FC_SUBMIT", "role": "경영관리임원", "due": "forecast_due"},
    "Approve_Forecast": {"task": "FC_APPROVE", "role": "대표이사", "due": "approve_due"},
    "Publish_Forecast": {"task": "FC_PUBLISH", "role": "경영관리담당", "due": "approve_due"},
    "Complete_Scene": {"task": "COMPLETE", "role": "경영관리임원", "due": "complete_due"},
}
#: 구매 확인은 지정 대행자도 한다(공동 기준 DOC51·DOC52 — USR-BUY 부재 시 USR-BUY2). 임원 권한은
#: 없다.
DELEGATES = {"Ack_Change": (BUY_STAFF,)}
#: 기한 초과 알림을 함께 받는 사람 — 변경 공유·확인 지연은 구매·생산 임원(공동 기준), 그 밖은
#: 경영관리 담당.
REVIEWER = {"CHANGE_SHARE": PROD_EXEC, "CHANGE_ACK": BUY_EXEC}


class PrerequisiteError(DomainError):
    """필수 조건 미충족 — 누락 항목을 함께 낸다(구현명세 13장의 실패 응답 `blocking_items`)."""

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


def _money(value: Any, field: str) -> Decimal | None:
    """
    금액 칸 — 비어 있으면 None(미입력)이다. 0으로 메우지 않는다(비용 0과 미입력은 다르다, T503).
    """
    if value in (None, ""):
        return None
    try:
        d = Decimal(str(value).replace(",", "").replace("원", "").strip())
    except ArithmeticError as exc:
        raise DomainError(f"{field}: 금액이 아니다 — {value!r}", 422) from exc
    if d < 0 or d != d.to_integral_value():
        raise DomainError(f"{field}: 0 이상의 원 단위 정수다 — {value!r}", 422)
    return d


def _int(value: Any, field: str) -> int:
    try:
        n = int(str(value).replace(",", "").strip())
    except ValueError as exc:
        raise DomainError(f"{field}: 정수가 아니다 — {value!r}", 422) from exc
    if n < 0:
        raise DomainError(f"{field}: 0 이상이다 — {value!r}", 422)
    return n


def _when(value: Any, field: str) -> str:
    try:
        return parse_at(str(value).strip()).isoformat()
    except ValueError as exc:
        raise DomainError(f"{field}: 시각(ISO8601)이 아니다 — {value!r}", 422) from exc


def _day(value: Any, field: str) -> str:
    try:
        return date.fromisoformat(str(value).strip()[:10]).isoformat()
    except ValueError as exc:
        raise DomainError(f"{field}: 날짜(YYYY-MM-DD)가 아니다 — {value!r}", 422) from exc


def _require(by: str, user: str | tuple[str, ...], what: str, *, strict: bool = True) -> None:
    """
    그 사람만 — 역할·담당 검사. `strict=False`면 답한 사람이 사용자 마스터 밖(콘솔 관리자)이다 —
    「담당자만」은
    바깥 Chaeksas가 결재 담당자로 이미 막았다(장면 1~4와 같다).
    """
    allowed = (user,) if isinstance(user, str) else user
    if strict and by not in allowed:
        holder = USERS.get(allowed[0], {})
        raise DomainError(f"{what}은 {holder.get('role')}({holder.get('name')})만 한다", 403)


def _past(doc: dict, at: str | None) -> bool:
    """그 시각이 지났나 — 미래 행을 문서에 넣지 않는 기준이다."""
    return at is not None and parse_at(at) <= parse_at(doc["clock"])


# ─────────────────────────── 장면 4 기준 (D500) ───────────────────────────


def baseline_from_sc04(sc04_doc: dict) -> dict[str, Any]:
    """
    장면 4 인계 → 장면 5의 출발점(CT501). 장면 4 완료·HANDOFF41·ACT41~43 현재 배정버전 인수가 있어야
    한다.
    승인서·판단본·과제·조건·지원·추가 발굴 지시와 판단본의 산정 가정을 함께 둔다 — 장면 5의 효과는
    그 가정에서
    출발하고, 장면 4 수치는 비교 기준으로 보존한다(P510).
    """
    h = sc04_doc.get("handoff") or {}
    if sc04_doc["review"].get("state") != "SC04_COMPLETED" or h.get("handoff_id") != SOURCE_HANDOFF:
        raise DomainError("개선안 검토·실행 승인이 아직 완료 전이다 — 결정 실행·계획 갱신은 "
                          "HANDOFF41에서 시작한다", 409)
    if sc04_doc.get("case_id") != "BASE":
        raise DomainError(
            f"개선안 검토·실행 승인이 기본 시연이 아니다({sc04_doc.get('case_id')}) — 결정 "
            "실행·계획 갱신 기대값은 기본 경로 "
            "기준이다",
            409,
        )
    accepted = {
        a["target_id"]: a
        for a in sc04_doc["assignments"].values()
        if a["state"] == "ACCEPTED" and a["accepted_version"] == a["assignment_version"]
    }
    missing = [t for t in (*calc.TASKS, "SUP41", "TOTAL") if t not in accepted]
    if missing:
        raise DomainError(f"개선안 검토·실행 승인 인수가 끝나지 않았다: {', '.join(missing)}", 409)
    dec = sc04_doc["decision"]
    run = sc04_doc["runs"][dec["run_id"]]
    assumptions = {
        task: copy.deepcopy(next(a for a in run["assumptions"] if a["alt_id"] == alt))
        for task, alt in calc.ALT_OF.items()
    }
    apr = next(
        a
        for a in sorted(sc04_doc["approvals"].values(), key=lambda a: a["version"])
        if a["approval_id"] == h["approval"]
    )
    actions = {
        t: {
            k: accepted[t].get(k)
            for k in (
                "target_id",
                "alt_id",
                "owner",
                "worker",
                "budget",
                "expected_effect",
                "plan_due",
                "completion_due",
                "conditions",
                "decision",
                "execution_gate",
                "assignment_version",
                "accepted_at",
            )
        }
        for t in calc.TASKS
    }
    directives = {
        x["directive_id"]: {
            k: x.get(k)
            for k in (
                "directive_id",
                "kind",
                "content",
                "owner",
                "collaborators",
                "verifier",
                "due_at",
                "fulfillment",
                "responsibility",
                "expected_effect",
                "action_ref",
            )
        }
        for x in sc04_doc["directives"].values()
        if x["state"] != "WITHDRAWN"
    }
    fs = h["financial_snapshot"]
    return {
        "demo_run_id": sc04_doc["demo_run_id"],
        # 대응 전 연간 목표 부족(Target − 장면 3 기준) — 과제의 필요성을 설명하는 기준이다(P510)
        "gap_before": str(Decimal(fs["target"]) - Decimal(fs["baseline"])),
        "handoff": {
            k: h.get(k)
            for k in (
                "handoff_id",
                "approval",
                "decision",
                "minutes",
                "overall_owner",
                "financial_snapshot",
                "budget",
                "as_of",
            )
        },
        "approval": {
            "approval_id": apr["approval_id"],
            "total_budget": apr["total_budget"],
            "delegation": apr.get("delegation"),
        },
        "actions": actions,
        "directives": directives,
        "assumptions": assumptions,
        # 판단본(DEC41-v2)의 월 손익 — 장면 4 검토안이다. 공식 전망이 아니다(소급 전환 금지)
        "decision_months": [
            {k: m[k] for k in ("period", "target", "base", "effect")}
            for m in run["result"]["months"]
        ],
        "price": sc04_doc["sc03"]["price"],
    }


def price_option(baseline: dict) -> Option:
    """장면 2 승인 단가 — 과제 전 기초 손익을 장면 2~4와 같은 원천으로 다시 내는 데만 쓴다."""
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
    D500 — 장면 4 완료, 장면 5 미착수(7/13 10:00). 계획·조건·품의·착수·관측·전망은 단계 실행 때
    생긴다. 배경
    원천도 시각이 지나야 들어온다 — 초기에는 HANDOFF41만 유효하다(구현명세 16장).
    """
    if case_id not in CASES:
        raise DomainError(f"모르는 시연 사례: {case_id} (가능: {', '.join(CASES)})", 422)
    if executor not in EXECUTORS:
        raise DomainError(f"모르는 실행 위치: {executor} (가능: {', '.join(EXECUTORS)})", 422)
    clock = max(parse_at(baseline["handoff"]["as_of"]), parse_at(SCHEDULE["start_at"]))
    actions = baseline["actions"]
    doc = {
        "demo_run_id": demo_run_id,
        "seed_id": SEED_ID,
        "case_id": case_id,
        "created_at": created_at.isoformat(),
        "clock": clock.isoformat(),
        "step": "D500",
        "sc04": baseline,
        "basis": calc.basis(seed.numbers, price_option(baseline)),
        # 공장 월 고정비 — a~e 합계에서 한 번만 뺀다(월 370백만원)
        "fixed": {m.isoformat(): str(seed.numbers.fixed[m]) for m in calc.MONTHS},
        "agent_mode": "mock",
        # 규칙·가정(SC05설정) — 화면·계산이 시드를 다시 읽지 않게 시작할 때 둔다
        "settings": {
            k: int(seed.setting(k))
            for k in (
                "share_minutes",
                "confirm_minutes",
                "urgent_approval_limit",
                "urgent_base_count",
                "urgent_unit_cost",
                "monthly_support",
            )
        },
        # Agent 고정 초안 재생(REPLAY) — 활동 재료. 협조·비용은 비어 있다(사람이 채운다)
        "replay": {
            "AG51": replay_activities(seed, "PL51-v1"),
            "AG52": replay_activities(seed, "PL51-v2"),
        },
        # 약정 거래 id — 데이터의 시연 식별자(REQ51 → TX53, OP51 → TX57)
        "txn_ids": {
            str(t["request_ref"]): str(t["txn_id"])
            for t in seed.rows("SC05예산원장")
            if t["request_ref"] in REQUESTS and t["유형"] == "COMMIT"
        },
        "scene": {
            "review_id": REVIEW_ID,
            "started_at": None,
            "started_by": None,
            "completed_at": None,
            "risk": "OPEN",
            "target": "UNCHANGED",
        },
        "plans": {},
        "plan_pointer": None,  # 유효 계획(확정 + 경영관리 확인) — 확인 뒤 한 번 교체된다
        "collaborations": [],
        "conditions": {
            cid: {
                "condition_id": cid,
                "seq": i + 1,
                "content": baseline["directives"][cid]["content"],
                "owner": baseline["directives"][cid]["owner"],
                "verifier": baseline["directives"][cid]["verifier"],
                "due_at": baseline["directives"][cid]["due_at"],
                "state": "OPEN",
                "evidence": [],
                "history": [],
            }
            for i, cid in enumerate(("CON41", "SUP41"))
        },
        "requests": {},
        "ledger": [],
        "operation": {
            t: {
                "task_id": t,
                "seq": i + 1,
                "owner": actions[t]["owner"],
                "state": "WAIT",
                "started_at": None,
                "history": [],
            }
            for i, t in enumerate(calc.TASKS)
        },
        "start": None,
        "customer_plans": {},
        "changes": {},
        "orders": {},
        "observation": None,
        "operating_plans": {},
        "runs": {},
        "forecasts": {},
        "official": None,  # 공식 전망 포인터 — 9/6 FC50 이전에는 「해당 시점 공식본 미적재」
        "shares": [],
        "followups": [],
        "directive_log": [],
        "evidence": {},
        "handoff": None,
        "background": [],
        "source_issues": [],
        "agent_outputs": {},
        "tasks": {},
        "alerts": [],
        "audit": [],
        "bpm": None if executor == "embedded" else external_bpm(executor),
    }
    catch_up(doc, seed)
    return doc


def replay_activities(seed: Seed, plan_id: str) -> list[dict[str, Any]]:
    """
    `SC05활동`의 한 계획 — Agent 재생 초안의 재료(담당·일정·선행·완료 기준). 협조·비용은 데이터에
    없다.
    """
    out = []
    for r in seed.rows("SC05활동"):
        if r["plan_id"] != plan_id:
            continue
        out.append(
            {
                "activity_id": str(r["activity_id"]),
                "name": str(r["활동"]),
                "owner": ACCOUNTS[str(r["담당"])],
                "start": r["시작일"].date().isoformat(),
                "end": r["완료계획일"].date().isoformat(),
                "predecessors": [p for p in str(r["선행활동"] or "").split(";") if p],
                "cooperation": None,
                "cost": None,
                "completion": str(r["완료기준·변경내용"]),
                "evidence": str(r["근거ID"]),
            }
        )
    return out


# ─────────────────────────── 배경 원천 (시각이 지나야 보인다) ───────────────────────────


def _account(value: Any) -> str | None:
    return None if value in (None, "") else ACCOUNTS[str(value).strip()]


def background_items(seed: Seed, case_id: str) -> list[dict[str, Any]]:
    """
    배경 이력 — 상세 시연이 없는 업무의 원천 행(구현명세 17장 「배경 이력」). 각 행은 발생 시각과
    의존(앞 기록이
    있어야 적용)을 갖는다. 시연 단계가 만드는
    기록(PL51·CON41·SUP41·REQ51·OP51·START51·CH51·CH52·PO51-001·
    PO51-010·OPL·FC51)은 여기 없다 — 그 거래·결과(집행·월말 확인)만 원천에서 이어 붙인다.
    """
    items: list[dict[str, Any]] = []
    plans = seed.by_id("SC05계획")
    for pid, task in BACKGROUND_PLANS.items():
        p = plans[pid]
        items.append({"kind": "plan_confirmed", "id": pid, "at": kst(p["확정_KST"]), "task": task})
        items.append({"kind": "plan_verified", "id": pid, "at": kst(p["확인_KST"]), "task": task})
    reqs = seed.by_id("SC05조건품의")
    for rid in ("REQ52", "REQ53"):
        r = reqs[rid]
        items.append({"kind": "request_approved", "id": rid, "at": kst(r["최종확인_KST"])})
    for t in seed.rows("SC05예산원장"):
        if t["request_ref"] in REQUESTS and t["유형"] == "COMMIT":
            continue  # 시연 품의 승인이 약정을 만든다
        items.append({"kind": "ledger", "id": str(t["txn_id"]), "at": kst(t["발생_KST"])})
    items += [
        {
            "kind": "operation",
            "id": "ACT41",
            "at": _at(2027, 8, 1, 9),
            "state": "OPERATING",
            "ref": "DOC54-P",
        },
        {
            "kind": "operation",
            "id": "ACT41",
            "at": _at(2027, 8, 31, 18),
            "state": "OPERATING_MONITORING",
            "ref": "DOC54-H",
        },
        {
            "kind": "operation",
            "id": "ACT42",
            "at": SCHEDULE["task_due"],
            "state": "OPERATING_MONITORING",
            "ref": "DOC59",
        },
        {
            "kind": "operation",
            "id": "ACT43",
            "at": _at(2027, 10, 1, 9),
            "state": "OPERATING",
            "ref": "DOC55",
        },
        {
            "kind": "directive",
            "id": "DIR41",
            "at": _at(2027, 8, 9, 10),
            "state": "FOLLOWUP_REQUIRED",
            "ref": "DOC62",
        },
        {"kind": "forecast", "id": "FC50", "at": _at(2027, 9, 6, 10)},
    ]
    for c in seed.rows("SC05변경공유"):
        if c["change_id"] in REPRESENTATIVE.values():
            # 대표 원문은 접수를 사람이 하지만, 원문 자체는 그 시각에 도착한다 — 오기 전에는
            # 접수할 수 없다(화면 직접 진행 실측: 9/2에 9/10 원문 CP52가 접수됐다)
            items.append({"kind": "original", "id": str(c["plan_ref"]), "at": kst(c["접수_KST"])})
            continue
        for stage, col in (
            ("received_at", "접수_KST"),
            ("shared_at", "공유_KST"),
            ("ack_at", "구매확인_KST"),
        ):
            at = kst(c[col])
            if case_id == "X503" and c["change_id"] == "CH54" and stage == "ack_at":
                continue  # 구매 확인 기록이 없다 — 0분으로 치환하지 않는다
            items.append({"kind": "change", "id": str(c["change_id"]), "stage": stage, "at": at})
    demo_orders = {
        str(c["대표주문"])
        for c in seed.rows("SC05변경공유")
        if c["change_id"] in REPRESENTATIVE.values()
    }
    for o in seed.rows("SC05구매표본"):
        if o["order_id"] in demo_orders:
            continue
        items.append({"kind": "order", "id": str(o["order_id"]), "at": kst(o["처리기록_KST"])})
    items.append({"kind": "results", "id": "PO51-ALL", "at": SCHEDULE["result_confirmed_at"]})
    for e in seed.rows("SC05근거"):
        items.append({"kind": "evidence", "id": str(e["evidence_id"]), "at": kst(e["작성_KST"])})
        if e["확인_KST"] is not None:
            items.append(
                {
                    "kind": "evidence_confirmed",
                    "id": str(e["evidence_id"]),
                    "at": kst(e["확인_KST"]),
                }
            )
    rank = {
        "plan_confirmed": 0,
        "plan_verified": 1,
        "request_approved": 2,
        "ledger": 3,
        "results": 9,
    }
    return sorted(items, key=lambda x: (x["at"], rank.get(x["kind"], 5)))


def catch_up(doc: dict, seed: Seed) -> list[str]:
    """
    가상시계까지의 배경 원천을 문서에 들인다. 이미 들인 것은 다시 하지 않는다. 의존(약정 → 집행,
    착수 → 운영
    인계)이 없으면 들이지 않고 기다린다 — 승인 전 약정을 집행으로 만들지 않는다(동시각은
    승인→약정→처리 순).
    """
    loaded = set(doc["background"])
    done: list[str] = []
    for item in background_items(seed, doc["case_id"]):
        key = f"{item['kind']}:{item['id']}:{item.get('stage') or item.get('state') or ''}"
        if key in loaded or not _past(doc, item["at"]):
            continue
        if _load(doc, seed, item):
            doc["background"].append(key)
            loaded.add(key)
            done.append(key)
    _change_alerts(doc)
    return done


def _load(doc: dict, seed: Seed, item: dict[str, Any]) -> bool:
    kind = item["kind"]
    if kind in ("plan_confirmed", "plan_verified"):
        p = seed.by_id("SC05계획")[item["id"]]
        plan = doc["plans"].setdefault(
            item["id"],
            {
                "plan_id": item["id"],
                "seq": _seq(doc["plans"]),
                "task_id": item["task"],
                "version": int(p["version"]),
                "background": True,
                "summary": str(p["변경사유"]),
                "budget": str(p["승인예산"]),
                "effect_start": p["효과개시"].date().isoformat(),
                "due_at": kst(p["과제기한"]),
                "activities": [],
                "state": "CONFIRMED",
                "confirmed_by": _account(p["확정자"]),
                "confirmed_at": kst(p["확정_KST"]),
                "management_check": "PENDING",
                "verified_by": None,
                "verified_at": None,
                "scope_note": str(p["상태·범위"]),
            },
        )
        if kind == "plan_verified":
            plan.update(
                management_check="VERIFIED",
                verified_by=_account(p["확인자"]),
                verified_at=kst(p["확인_KST"]),
            )
        return True
    if kind == "request_approved":
        r = seed.by_id("SC05조건품의")[item["id"]]
        doc["requests"][item["id"]] = {
            "request_id": item["id"],
            "seq": _seq(doc["requests"]),
            "task_id": str(r["task_id"]),
            "scope": "ONEOFF",
            "amount": str(r["금액"]),
            "reason": str(r["범위"]),
            "approval_ref": doc["sc04"]["approval"]["approval_id"],
            "evidence": str(r["근거·원승인"]).split(" / ")[0].split(";"),
            "state": "APPROVED",
            "background": True,
            "history": [
                {
                    "at": kst(r["상신·이행_KST"]),
                    "state": "SUBMITTED",
                    "by": _account(r["작성·이행자"]),
                },
                {
                    "at": kst(r["1차확인_KST"]),
                    "state": "FUNCTION_APPROVED",
                    "by": _account(r["1차확인자"]),
                },
                {
                    "at": kst(r["최종확인_KST"]),
                    "state": "APPROVED",
                    "by": _account(r["최종확인자"]),
                },
            ],
        }
        return True
    if kind == "ledger":
        t = next(x for x in seed.rows("SC05예산원장") if str(x["txn_id"]) == item["id"])
        req = doc["requests"].get(str(t["request_ref"]))
        if req is None or req["state"] != "APPROVED":
            return False  # 승인되지 않은 품의의 거래는 들이지 않는다
        if t["유형"] == "SETTLE":
            outstanding = sum(
                (
                    Decimal(x["commitment_delta"])
                    for x in doc["ledger"]
                    if x["request_ref"] == req["request_id"]
                ),
                Decimal(0),
            )
            if outstanding < -Decimal(t["약정증감"]):
                return False  # 약정보다 큰 정산은 없다
        doc["ledger"].append(_txn(doc, t))
        return True
    if kind == "operation":
        op = doc["operation"][item["id"]]
        if item["state"] == "OPERATING_MONITORING" and op["state"] != "OPERATING":
            return False  # 착수한 뒤에만 운영 인계가 있다 — 기다린다
        op.update(state=item["state"])
        if item["state"] == "OPERATING":
            op["started_at"] = item["at"]
        op["history"].append(
            {"at": item["at"], "state": item["state"], "ref": item["ref"], "background": True}
        )
        return True
    if kind == "directive":
        doc["directive_log"].append(
            {
                "directive_id": item["id"],
                "at": item["at"],
                "state": item["state"],
                "ref": item["ref"],
            }
        )
        return True
    if kind == "forecast":
        prior = _prior_months(doc)
        rows = seed.by_id("SC05전망버전")["FC50"]
        doc["forecasts"]["FC50"] = {
            "forecast_id": "FC50",
            "seq": _seq(doc["forecasts"]),
            "kind": "OFFICIAL",
            "run_id": "HISTORY50",
            "state": "APPROVED",
            "background": True,
            "cutoff": "2027-09-01",
            "months": prior,
            "annual": str(sum((Decimal(m["profit"]) for m in prior), Decimal(0))),
            "drafted_at": kst(rows["작성_KST"]),
            "confirmed_at": kst(rows["부서확인_KST"]),
            "approved_at": kst(rows["대표승인_KST"]),
            "approved_by": CEO,
            "evidence": "DOC60",
            "note": (
                "8월 마감 기준 가상 중간 월간 전망 — 개선안 검토·실행 승인 판단본(DEC41-v2)과 "
                "수치는 같지만 별도 "
                "승인이다"
            ),
        }
        doc["official"] = "FC50"
        return True
    if kind == "original":
        doc.setdefault("originals", {})[item["id"]] = item["at"]
        return True
    if kind == "change":
        c = next(x for x in seed.rows("SC05변경공유") if str(x["change_id"]) == item["id"])
        case = doc["changes"].setdefault(item["id"], _change_record(doc, c))
        case[item["stage"]] = item["at"]
        case["state"] = {
            "received_at": "RECEIVED",
            "shared_at": "SHARED",
            "ack_at": "ACKNOWLEDGED",
        }[item["stage"]]
        if item["stage"] == "ack_at":
            case.update(
                ack_by=_account(c["확인자"]),
                delegate=bool(c["대행여부"]),
                decision=str(c["대응"]),
                order_ref=str(c["대표주문"]),
                note=str(c["협의·판단"]),
            )
        return True
    if kind == "order":
        o = next(x for x in seed.rows("SC05구매표본") if str(x["order_id"]) == item["id"])
        if item["id"] in doc["orders"]:
            doc["source_issues"].append(
                {"kind": "DUPLICATE_ORDER", "order_id": item["id"], "row": _order_record(doc, o)}
            )
            return True
        doc["orders"][item["id"]] = _order_record(doc, o)
        return True
    if kind == "results":
        rows = {str(o["order_id"]): o for o in seed.rows("SC05구매표본")}
        for oid, order in doc["orders"].items():
            o = rows.get(oid)
            if o is None or order.get("result_status") == "CONFIRMED":
                continue
            order.update(
                late=int(o["납기이상"]),
                quality=int(o["품질이상"]),
                result_status=str(o["확인상태"]),
                result_confirmed_at=item["at"],
            )
        return True
    if kind in ("evidence", "evidence_confirmed"):
        e = seed.by_id("SC05근거")[item["id"]]
        ev = doc["evidence"].setdefault(
            item["id"],
            {
                "evidence_id": item["id"],
                "seq": _seq(doc["evidence"]),
                "type": str(e["유형"]),
                "object_refs": str(e["object_ref"]).split(";"),
                "written_at": kst(e["작성_KST"]),
                "written_by": _account(e["작성자"]),
                "body": str(e["가상 증빙 본문"]),
                "confirmed_by": None,
                "confirmed_at": None,
            },
        )
        if kind == "evidence_confirmed":
            ev.update(confirmed_by=_account(e["확인자"]), confirmed_at=kst(e["확인_KST"]))
        return True
    raise DomainError(f"모르는 배경 원천: {kind}", 500)  # pragma: no cover


def _txn(doc: dict, t: dict[str, Any]) -> dict[str, Any]:
    return {
        "txn_id": str(t["txn_id"]),
        "seq": len(doc["ledger"]) + 1,
        "task_id": str(t["task_id"]),
        "scope": str(t["budget_scope"]),
        "request_ref": str(t["request_ref"]),
        "at": kst(t["발생_KST"]),
        "type": str(t["유형"]),
        "commitment_delta": str(t["약정증감"]),
        "paid_delta": str(t["집행증감"]),
        "pnl_cost": str(t["손익비용"]),
        "evidence": str(t["근거ID"]),
    }


def _change_record(doc: dict, c: dict[str, Any] | None, *, source: str | None = None) -> dict:
    return {
        "change_id": str(c["change_id"]) if c else REPRESENTATIVE[source or ""],
        "seq": _seq(doc["changes"]),
        "plan_ref": str(c["plan_ref"]) if c else source,
        "model_id": str(c["model_id"]) if c else "A-b",
        "received_at": None,
        "shared_at": None,
        "ack_at": None,
        "shared_by": _account(c["공유자"]) if c else None,
        "ack_by": None,
        "delegate": False,
        "decision": None,
        "order_ref": None,
        "note": None,
        "response": None,
        "state": "RECEIVED",
        "background": c is not None,
        "history": [],
    }


def _order_record(doc: dict, o: dict[str, Any]) -> dict[str, Any]:
    return {
        "order_id": str(o["order_id"]),
        "seq": _seq(doc["orders"]),
        "month": "2027-09-01",
        "model_id": str(o["model_id"]),
        "part_id": str(o["part_id"]),
        "change_ref": None if o["change_ref"] in (None, "") else str(o["change_ref"]),
        "qty": int(o["수량"]),
        "urgent": bool(o["긴급여부"]),
        "transport": str(o["긴급운송비"]),
        "premium": str(o["할증"]),
        "extra": str(o["추가비합계"]),
        "ordered_at": kst(o["발주_KST"]),
        "recorded_at": kst(o["처리기록_KST"]),
        "approver": _account(o["긴급승인자"]),
        "approved_at": kst(o["긴급승인_KST"]),
        "reason": str(o["판단·사유"]),
        "evidence": str(o["근거ID"]),
        "late": None,
        "quality": None,
        "result_status": None,
        "background": True,
        "state": "EXECUTED",
    }


def _change_alerts(doc: dict) -> None:
    """
    공유 60분·구매 확인 120분 — 넘긴 순간(초과 첫 분)에 담당 임원에게 한 번 알린다. 변경
    건·규칙·상태별 한 번만이다.
    알림은 업무 승인을 대신하지 않는다(구현명세 5장).
    """
    seen = {(a["target"], a["kind"]) for a in doc["alerts"]}
    for c in ordered(doc["changes"]):
        for kind, start, end, limit, to, what in (
            (
                "SHARE_DELAY",
                c["received_at"],
                c["shared_at"],
                60,
                [PROD_EXEC, PROD_LEAD],
                "생산 공유 지연",
            ),
            ("ACK_DELAY", c["shared_at"], c["ack_at"], 120, [BUY_EXEC, BUY_LEAD], "구매 확인 지연"),
        ):
            if start is None or (c["change_id"], kind) in seen:
                continue
            at = parse_at(start) + timedelta(minutes=limit + 1)
            late = end is None or parse_at(end) > parse_at(start) + timedelta(minutes=limit)
            if not late or at > parse_at(doc["clock"]):
                continue
            doc["alerts"].append(
                {
                    "alert_id": f"ALERT-{len(doc['alerts']) + 1:03d}",
                    "kind": kind,
                    "target": c["change_id"],
                    "due_at": (parse_at(start) + timedelta(minutes=limit)).isoformat(),
                    "at": at.isoformat(),
                    "to": to,
                    "message": f"{c['change_id']} {what} — 기준 {limit}분 초과",
                }
            )
            seen.add((c["change_id"], kind))


def _prior_months(doc: dict) -> list[dict[str, Any]]:
    """장면 4 판단 가정으로 낸 월 손익 — FC50(9/6 공식)과 수치가 같다. 원인 대사의 종전 쪽이다."""
    return calc.months(
        doc["basis"], prior_effects(doc), doc["fixed"], first_forecast=date(2027, 9, 1)
    )


def prior_effects(doc: dict) -> list[dict[str, Any]]:
    return [
        calc.effect(task, calc.plan_inputs(doc["sc04"]["assumptions"][task], m))
        for task in calc.TASKS
        for m in calc.EFFECT_MONTHS
    ]


# ─────────────────────────── S01 착수 (U501 · CT501) ───────────────────────────


def start_scene(doc: dict, *, by: str) -> bool:
    """
    장면 5 착수 — 기존 MR-2706-01에 HANDOFF41·APR41-v1·ACT41~43을 잇는다(새 검토건·장면을 만들지
    않는다).
    **재착수는 기존 결과를 돌려준다**(장면 중복 생성 금지). 인수 완료를 조건 충족으로 처리하지
    않는다.
    """
    _require(by, FIN, "결정 실행·계획 갱신 착수")
    s = doc["scene"]
    if s["started_at"] is not None:
        return False
    s.update(started_at=doc["clock"], started_by=by)
    audit(
        doc,
        actor=by,
        action="scene_started",
        review_id=REVIEW_ID,
        source=SOURCE_HANDOFF,
        approval=doc["sc04"]["approval"]["approval_id"],
        event_code="EV51-01",
    )
    return True


def open_scene(doc: dict) -> dict[str, Any]:
    """BPM 첫 작업 — 착수된 장면인지 본다. 바깥 실행은 착수 뒤에 Studio·Center에서 시작한다."""
    if doc["scene"]["started_at"] is None:
        raise DomainError("아직 착수하지 않은 업무다 — 화면에서 착수를 먼저 누른다", 409)
    a = doc["sc04"]["actions"][TASK_ID]
    return {
        "review_id": REVIEW_ID,
        "task_id": TASK_ID,
        "owner_name": name_of(a["owner"]),
        "budget": str(a["budget"]),
    }


# ─────────────────────────── S02~S06 상세 계획·변경 (U502 · CT502~CT504)
# ───────────────────────────

#: 활동 한 줄 — 「번호 | 활동 | 담당 | 시작 | 종료 | 선행 | 협조 | 비용 | 완료근거 | 근거ID」. 비용
#: 빈칸은 미입력이다.
ACTIVITY_COLUMNS = (
    "activity_id",
    "name",
    "owner",
    "start",
    "end",
    "predecessors",
    "cooperation",
    "cost",
    "completion",
    "evidence",
)


def parse_activities(text: str) -> list[dict[str, Any]]:
    """
    활동 목록 글 → 활동. 형식이 틀리면 422, 빈 칸은 누락으로 남긴다(저장은 되고 확정이 막힌다).
    """
    out = []
    for n, raw in enumerate(line for line in str(text or "").splitlines() if line.strip()):
        cells = [c.strip() for c in raw.split("|")]
        if len(cells) != len(ACTIVITY_COLUMNS):
            raise DomainError(
                f"활동 {n + 1}줄: 칸이 {len(ACTIVITY_COLUMNS)}개여야 한다(받은 {len(cells)}개) — "
                "번호|활동|담당|시작|종료|선행|협조|비용|완료근거|근거ID",
                400,
            )
        row = dict(zip(ACTIVITY_COLUMNS, cells, strict=True))
        owner = _user(row["owner"]) if row["owner"] else None
        if row["owner"] and owner is None:
            raise DomainError(f"활동 {row['activity_id']}: 모르는 담당 — {row['owner']}", 422)
        for key in ("start", "end"):
            if row[key]:
                row[key] = _day(row[key], f"활동 {row['activity_id']} {key}")
        out.append(
            {
                "activity_id": row["activity_id"],
                "name": row["name"],
                "owner": owner,
                "start": row["start"] or None,
                "end": row["end"] or None,
                "predecessors": [
                    p.strip()
                    for p in re.split(r"[,;]", row["predecessors"])
                    if p.strip() and p.strip() != "-"
                ],
                "cooperation": row["cooperation"] or None,
                "cost": None
                if row["cost"] == ""
                else str(_money(row["cost"], f"활동 {row['activity_id']} 비용")),
                "completion": row["completion"] or None,
                "evidence": row["evidence"] or None,
            }
        )
    if not out:
        raise DomainError("활동이 하나도 없다", 422)
    ids = [a["activity_id"] for a in out]
    if len(set(ids)) != len(ids):
        raise DomainError("활동 번호가 겹친다", 400)
    return out


def plan_problems(doc: dict, plan: dict) -> list[str]:
    """
    확정 차단 사유(CT502·CT503) — 필수값, 시작 ≤ 종료, 선행 관계(없는 활동·순환), 승인
    범위(예산·효과 개시·최종
    기한), 활동 비용 합 ≤ 예산, 효과 확인 기준. 0원과 미입력은 다르다 — 미입력만 막는다.
    """
    problems: list[str] = []
    ids = {a["activity_id"] for a in plan["activities"]}
    for a in plan["activities"]:
        label = f"활동 {a['activity_id']}"
        for key, word in (
            ("name", "활동명"),
            ("owner", "담당"),
            ("start", "시작일"),
            ("end", "종료일"),
            ("cooperation", "협조"),
            ("cost", "비용"),
            ("completion", "완료 근거"),
        ):
            if a[key] in (None, ""):
                problems.append(f"{label} {word} 누락")
        if a["start"] and a["end"] and a["start"] > a["end"]:
            problems.append(f"{label} 시작({a['start']})이 종료({a['end']})보다 늦다")
        problems += [f"{label} 선행 {p} 없음" for p in a["predecessors"] if p not in ids]
    graph = {a["activity_id"]: a["predecessors"] for a in plan["activities"]}

    def cyclic(node: str, path: tuple[str, ...]) -> bool:
        if node in path:
            return True
        return any(cyclic(p, (*path, node)) for p in graph.get(node, []) if p in graph)

    if any(cyclic(n, ()) for n in graph):
        problems.append("선행 관계에 순환이 있다")
    if not plan.get("effect_rule"):
        problems.append("효과 확인 기준 누락")
    problems += scope_problems(doc, plan)
    costs = [Decimal(a["cost"]) for a in plan["activities"] if a["cost"] is not None]
    if sum(costs, Decimal(0)) > Decimal(plan["budget"]):
        problems.append(f"활동 비용 합 {int(sum(costs, Decimal(0))):,}원이 승인예산을 넘는다")
    return problems


def scope_problems(doc: dict, plan: dict) -> list[str]:
    """
    승인 범위(APR41) — 예산·효과 개시·최종 기한. 범위를 벗어나면 별도 승인 전 시행 보류다(CT503).
    """
    a = doc["sc04"]["actions"][TASK_ID]
    out = []
    if Decimal(plan["budget"]) > Decimal(a["budget"]):
        out.append(
            f"승인예산 {int(Decimal(plan['budget'])):,}원이 과제 한도 "
            f"{int(Decimal(a['budget'])):,}원을 넘는다"
        )
    if Decimal(plan["budget"]) > Decimal(doc["sc04"]["approval"]["total_budget"]):
        out.append("총괄 한도를 넘는다 — 대표 별도 승인 필요")
    if plan["effect_start"] != doc["sc04"]["assumptions"][TASK_ID]["start"]:
        out.append(
            f"효과 개시 {plan['effect_start']}이 "
            f"승인({doc['sc04']['assumptions'][TASK_ID]['start']})과 다르다"
        )
    if parse_at(plan["due_at"]) != parse_at(a["completion_due"]):
        out.append("과제 완료기한이 승인과 다르다")
    return out


def current_plan(doc: dict) -> dict | None:
    """ACT42의 가장 새 계획 버전(유효 여부와 무관)."""
    mine = [p for p in ordered(doc["plans"]) if p["task_id"] == TASK_ID]
    return mine[-1] if mine else None


def effective_plan(doc: dict) -> dict | None:
    """유효 계획 — 확정 + 경영관리 확인을 마친 최신 버전(포인터)."""
    return doc["plans"].get(doc["plan_pointer"] or "")


def _plan_in_review(doc: dict, phase: str) -> dict:
    plan = current_plan(doc)
    if plan is None:
        raise DomainError("상세 계획 초안이 없다", 409)
    if (phase == "change") != (plan["parent"] is not None):
        raise DomainError(
            "검토할 변경안이 없다" if phase == "change" else "최초 계획은 이미 확인을 마쳤다", 409
        )
    return plan


def _new_plan(
    doc: dict,
    *,
    activities: list[dict],
    effect_rule: str,
    by: str,
    parent: str | None,
    budget: str,
    effect_start: str,
    due_at: str,
    reason: str | None,
    impact: str | None,
) -> dict:
    mine = [p for p in ordered(doc["plans"]) if p["task_id"] == TASK_ID]
    version = len(mine) + 1
    plan_id = f"{PLAN_PREFIX}-v{version}"
    plan = doc["plans"][plan_id] = {
        "plan_id": plan_id,
        "seq": _seq(doc["plans"]),
        "task_id": TASK_ID,
        "version": version,
        "parent": parent,
        "background": False,
        "approval_ref": doc["sc04"]["approval"]["approval_id"],
        "activities": activities,
        "effect_rule": effect_rule,
        "budget": budget,
        "effect_start": effect_start,
        "due_at": due_at,
        "state": "CHANGE_REQUESTED" if parent else "DRAFT",
        "drafted_at": doc["clock"],
        "drafted_by": by,
        "change_reason": reason,
        "change_impact": impact,
        "coordinated_at": None,
        "confirmed_by": None,
        "confirmed_at": None,
        "management_check": "PENDING",
        "verified_by": None,
        "verified_at": None,
        "agent_ref": None,
        "history": [
            {"at": doc["clock"], "state": "CHANGE_REQUESTED" if parent else "DRAFT", "by": by}
        ],
    }
    plan["content_hash"] = _hash(
        {k: plan[k] for k in ("activities", "effect_rule", "budget", "effect_start", "due_at")}
    )
    return plan


def _cite_agent(doc: dict, ref: str, *, by: str, modified: bool) -> None:
    """
    사람이 Agent 초안을 근거로 썼다 — 원 초안은 그대로, 채택·수정 상태만 남긴다(자동 승인 아님).
    """
    o = doc["agent_outputs"].get(ref)
    if o is None:
        raise DomainError(f"없는 Agent 초안: {ref}", 404)
    o.update(
        review_status="MODIFIED_BY_HUMAN" if modified else "ACCEPTED_BY_HUMAN",
        reviewed_by=by,
        reviewed_at=doc["clock"],
    )


def check_draft_plan(doc: dict, args: dict[str, Any]) -> None:
    if doc["scene"]["started_at"] is None:
        raise DomainError("결정 실행·계획 갱신을 착수하지 않았다", 409)
    plan = current_plan(doc)
    if plan is not None and (
        plan["parent"] is not None or plan["state"] not in ("DRAFT", "REWORK_REQUIRED")
    ):
        raise DomainError(
            f"계획({plan['plan_id']})이 이미 {plan['state']}다 — 바꾸려면 변경 요청", 409
        )
    parse_activities(_text(args, "activities"))
    ref = _text(args, "agent_ref")
    if ref and ref not in doc["agent_outputs"]:
        raise DomainError(f"없는 Agent 초안: {ref}", 404)


def draft_plan(doc: dict, args: dict[str, Any], *, by: str, strict: bool = True) -> dict[str, Any]:
    """
    상세 계획 초안 저장(EV51-03) — 누락이 있어도 저장한다(확정에서 막는다, T503). Agent 초안을
    인용하면 원 제안과
    사람 수정본이 따로 남는다(AG51 MODIFIED_BY_HUMAN). 보완 필요(REWORK)로 돌아오면 새 버전이다.
    """
    check_draft_plan(doc, args)
    _require(by, BUY_LEAD, "상세 계획 작성", strict=strict)
    a = doc["sc04"]["actions"][TASK_ID]
    activities = parse_activities(_text(args, "activities"))
    prior = current_plan(doc)
    if prior is not None and prior["state"] == "DRAFT":
        del doc["plans"][prior["plan_id"]]  # 같은 초안을 고쳐 저장 — 확정 전이라 이력 대상이 아니다
    plan = _new_plan(
        doc,
        activities=activities,
        effect_rule=_text(args, "effect_rule"),
        by=by,
        parent=None,
        budget=str(a["budget"]),
        effect_start=doc["sc04"]["assumptions"][TASK_ID]["start"],
        due_at=a["completion_due"],
        reason=None,
        impact=None,
    )
    if prior is not None and prior["plan_id"] != plan["plan_id"]:
        plan["reworks"] = prior["plan_id"]
    ref = _text(args, "agent_ref")
    if ref:
        proposal = (doc["agent_outputs"][ref].get("draft") or {}).get("activities")
        _cite_agent(doc, ref, by=by, modified=proposal != activities)
        plan["agent_ref"] = ref
    plan["memo"] = _text(args, "memo")
    missing = plan_problems(doc, plan)
    audit(
        doc,
        actor=by,
        action="plan_drafted",
        plan_id=plan["plan_id"],
        missing=len(missing),
        event_code="EV51-03",
    )
    return {"plan_id": plan["plan_id"], "missing": len(missing)}


def check_coordinate(doc: dict, args: dict[str, Any]) -> None:
    plan = _plan_in_review(doc, _text(args, "phase") or "initial")
    if plan["state"] not in ("DRAFT", "CHANGE_REQUESTED"):
        raise DomainError(f"{plan['plan_id']}는 협조 확인 대기가 아니다 ({plan['state']})", 409)
    if args.get("decision") not in ("확인", "보완요청"):
        raise DomainError("확인 또는 보완요청을 고른다", 422)
    if not _text(args, "content"):
        raise DomainError("협의 내용을 적는다", 422)
    if args["decision"] == "확인" and _user(args.get("contact")) is None:
        raise DomainError("생산 협조 담당(창구)을 사용자 이름으로 적는다", 422)


def coordinate_plan(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    생산 협조 확인(EV51-04·11) — 생산 임원이 **현재 버전**의 실행 가능성을 확인한다. 협의는 버전별
    기록이다.
    """
    check_coordinate(doc, args)
    _require(by, PROD_EXEC, "생산 협조 확인", strict=strict)
    phase = _text(args, "phase") or "initial"
    plan = _plan_in_review(doc, phase)
    ok = args["decision"] == "확인"
    doc["collaborations"].append(
        {
            "collab_id": f"COL51-{len(doc['collaborations']) + 1:02d}",
            "plan_version": plan["plan_id"],
            "content_hash": plan["content_hash"],
            "kind": "생산 협조 확인" if ok else "보완 요청",
            "department": "생산",
            "content": _text(args, "content"),
            "contact": _user(args.get("contact")),
            "evidence": _text(args, "evidence"),
            "by": by,
            "at": doc["clock"],
        }
    )
    if ok:
        plan.update(state="COORDINATED", coordinated_at=doc["clock"])
        plan["history"].append({"at": doc["clock"], "state": "COORDINATED", "by": by})
    audit(
        doc,
        actor=by,
        action="plan_coordinated" if ok else "plan_coordination_rework",
        plan_id=plan["plan_id"],
        event_code=("EV51-04" if phase == "initial" else "EV51-11") if ok else None,
    )
    return {"plan_id": plan["plan_id"]}


def check_confirm_plan(doc: dict, args: dict[str, Any]) -> None:
    plan = _plan_in_review(doc, _text(args, "phase") or "initial")
    if args.get("decision") not in ("확정", "보완요청"):
        raise DomainError("확정 또는 보완요청을 고른다", 422)
    if plan["state"] != "COORDINATED":
        raise DomainError(f"{plan['plan_id']}는 생산 협조 확인 전이다 ({plan['state']})", 409)
    if args["decision"] == "보완요청":
        if not _text(args, "comment"):
            raise DomainError("보완 요청에는 사유가 필요하다", 422)
        return
    problems = plan_problems(doc, plan)
    if problems:
        raise PrerequisiteError(
            "계획 확정 불가: " + ", ".join(problems), problems, "PLAN_INCOMPLETE"
        )
    if not _text(args, "impact"):
        raise DomainError("승인 범위 영향 확인(예산·개시·기한)을 적는다", 422)


def confirm_plan(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    계획 확정(EV51-05·12) — **해당 과제 임원**(구매 임원)만. 확정은 조건 충족·착수가 아니다. 보완
    요청이면 같은
    버전을 다시 고친다(최초) 또는 변경 요청으로 돌아간다(변경).
    """
    check_confirm_plan(doc, args)
    _require(by, OWNERS[TASK_ID], "계획 확정", strict=strict)
    phase = _text(args, "phase") or "initial"
    plan = _plan_in_review(doc, phase)
    if args["decision"] == "보완요청":
        plan.update(state="REWORK_REQUIRED", rework_reason=_text(args, "comment"))
        plan["history"].append({"at": doc["clock"], "state": "REWORK_REQUIRED", "by": by})
        audit(doc, actor=by, action="plan_returned", plan_id=plan["plan_id"])
        return {"plan_id": plan["plan_id"]}
    plan.update(
        state="CONFIRMED",
        confirmed_by=by,
        confirmed_at=doc["clock"],
        impact_check=_text(args, "impact"),
    )
    plan["history"].append(
        {"at": doc["clock"], "state": "CONFIRMED", "by": by, "note": _text(args, "comment")}
    )
    audit(
        doc,
        actor=by,
        action="plan_confirmed",
        plan_id=plan["plan_id"],
        event_code="EV51-05" if phase == "initial" else "EV51-12",
    )
    return {"plan_id": plan["plan_id"]}


def check_verify_plan(doc: dict, args: dict[str, Any]) -> None:
    plan = _plan_in_review(doc, _text(args, "phase") or "initial")
    if plan["state"] != "CONFIRMED" or plan["management_check"] != "PENDING":
        raise DomainError(f"{plan['plan_id']}는 경영관리 확인 대기가 아니다", 409)
    if args.get("decision") not in ("확인", "보완필요"):
        raise DomainError("확인 또는 보완필요를 고른다", 422)
    if args["decision"] == "보완필요" and not _text(args, "comment"):
        raise DomainError("보완 필요에는 사유가 필요하다", 422)


def verify_plan(doc: dict, args: dict[str, Any], *, by: str, strict: bool = True) -> dict[str, Any]:
    """
    경영관리 확인(EV51-06·13) — 승인 조건·예산·손익 가정 정합성. 확인하면 **유효 계획 포인터를 한 번
    교체**한다
    (v1 → v2, 기존 활동을 합산하지 않는다 — T504). 이견은 REWORK_REQUIRED와 사유다.
    """
    check_verify_plan(doc, args)
    _require(by, CFO, "경영관리 확인", strict=strict)
    phase = _text(args, "phase") or "initial"
    plan = _plan_in_review(doc, phase)
    if args["decision"] == "보완필요":
        plan.update(
            management_check="REWORK_REQUIRED",
            rework_reason=_text(args, "comment"),
            state="REWORK_REQUIRED",
        )
        plan["history"].append(
            {
                "at": doc["clock"],
                "state": "REWORK_REQUIRED",
                "by": by,
                "note": _text(args, "comment"),
            }
        )
        audit(doc, actor=by, action="plan_rework_required", plan_id=plan["plan_id"])
        return {"plan_id": plan["plan_id"], "pointer": doc["plan_pointer"] or ""}
    plan.update(management_check="VERIFIED", verified_by=by, verified_at=doc["clock"])
    plan["history"].append(
        {"at": doc["clock"], "state": "VERIFIED", "by": by, "note": _text(args, "comment")}
    )
    previous = doc["plan_pointer"]
    doc["plan_pointer"] = plan["plan_id"]
    audit(
        doc,
        actor=by,
        action="plan_verified",
        plan_id=plan["plan_id"],
        replaces=previous,
        event_code="EV51-06" if phase == "initial" else "EV51-13",
    )
    return {"plan_id": plan["plan_id"], "pointer": plan["plan_id"]}


def check_request_change(doc: dict, args: dict[str, Any]) -> None:
    base = effective_plan(doc)
    if base is None:
        raise DomainError("유효 계획(확정·확인)이 없다 — 변경은 확정본에서 출발한다", 409)
    if args.get("decision") not in ("변경요청", "변경없음"):
        raise DomainError("변경요청 또는 변경없음을 고른다", 422)
    if args["decision"] == "변경없음":
        return
    if doc["start"] is not None:
        raise DomainError("이미 운영 적용을 시작했다 — 계획 변경은 새 영향 검토로", 409)
    if not _text(args, "reason") or not _text(args, "impact"):
        raise DomainError("변경 사유와 영향을 적는다", 422)
    parse_activities(_text(args, "activities"))
    _money(args.get("budget"), "승인예산")
    _day(args.get("effect_start"), "효과 개시")
    _when(args.get("due_at"), "과제 기한")
    ref = _text(args, "agent_ref")
    if ref and ref not in doc["agent_outputs"]:
        raise DomainError(f"없는 Agent 초안: {ref}", 404)


def request_change(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    준비 중 계획 변경 요청(EV51-10) — 확정본(v1)을 복제한 v2에 사유·영향을 둔다. **v1은 그대로
    유효**하다. 예산·
    효과 개시·최종 기한이 승인 범위를 벗어나면 NEEDS_SEPARATE_APPROVAL — 시행 보류(별도 승인 전,
    X502·T507).
    """
    check_request_change(doc, args)
    _require(by, BUY_LEAD, "계획 변경 요청", strict=strict)
    if args["decision"] == "변경없음":
        audit(doc, actor=by, action="plan_change_none")
        return {"plan_id": doc["plan_pointer"], "state": "NONE"}
    base = effective_plan(doc)
    stale = unresolved_change(doc)
    if stale is not None:
        stale.update(state="SUPERSEDED")
        stale["history"].append({"at": doc["clock"], "state": "SUPERSEDED", "by": by})
    plan = _new_plan(
        doc,
        activities=parse_activities(_text(args, "activities")),
        effect_rule=base["effect_rule"],  # type: ignore[index]
        by=by,
        parent=base["plan_id"],  # type: ignore[index]
        budget=str(_money(args.get("budget"), "승인예산")),
        effect_start=_day(args.get("effect_start"), "효과 개시"),
        due_at=_when(args.get("due_at"), "과제 기한"),
        reason=_text(args, "reason"),
        impact=_text(args, "impact"),
    )
    plan["diff"] = plan_diff(base, plan)  # type: ignore[arg-type]
    ref = _text(args, "agent_ref")
    if ref:
        _cite_agent(doc, ref, by=by, modified=True)
        plan["agent_ref"] = ref
    out = scope_problems(doc, plan)
    if out:
        plan.update(state="NEEDS_SEPARATE_APPROVAL", scope_problems=out)
        plan["history"].append(
            {"at": doc["clock"], "state": "NEEDS_SEPARATE_APPROVAL", "by": "system"}
        )
        audit(
            doc, actor=by, action="plan_change_out_of_scope", plan_id=plan["plan_id"], problems=out
        )
        return {"plan_id": plan["plan_id"], "state": "OUT_OF_SCOPE"}
    audit(
        doc, actor=by, action="plan_change_requested", plan_id=plan["plan_id"], event_code="EV51-10"
    )
    return {"plan_id": plan["plan_id"], "state": "REQUESTED"}


def plan_diff(before: dict, after: dict) -> list[dict[str, Any]]:
    """변경 전후 — 바뀐 활동만. 유지된 예산·개시·기한은 함께 비교한다(V502)."""
    old = {a["activity_id"]: a for a in before["activities"]}
    out = []
    for a in after["activities"]:
        b = old.get(a["activity_id"])
        fields = [k for k in ACTIVITY_COLUMNS[1:] if b is None or b.get(k) != a.get(k)]
        if fields:
            out.append({"activity_id": a["activity_id"], "fields": fields, "before": b, "after": a})
    for k in ("budget", "effect_start", "due_at"):
        out.append(
            {"scope": k, "before": before[k], "after": after[k], "kept": before[k] == after[k]}
        )
    return out


def unresolved_change(doc: dict) -> dict | None:
    """확정 전 변경안 — 착수를 막는다(unresolved_blocker)."""
    plan = current_plan(doc)
    if plan is None or plan["parent"] is None or plan["state"] == "SUPERSEDED":
        return None
    return None if plan["management_check"] == "VERIFIED" else plan


# ─────────────────────────── S07·S08 조건·지원 (U503 · CT505) ───────────────────────────


def check_condition_evidence(doc: dict, args: dict[str, Any]) -> None:
    target = _text(args, "target")
    c = doc["conditions"].get(target)
    if c is None:
        raise DomainError(f"없는 조건·지원: {target}", 404)
    if c["state"] in ("SATISFIED", "VERIFIED"):
        raise DomainError(f"{target}는 이미 확인을 마쳤다", 409)
    if effective_plan(doc) is None:
        raise DomainError("유효 계획이 없다 — 조건 근거는 확정·확인된 계획에 잇는다", 409)
    refs = [r for r in re.split(r"[;,\s]+", _text(args, "evidence")) if r]
    if not refs:
        raise DomainError("근거 ID를 적는다", 422)
    unknown = [r for r in refs if r not in doc["evidence"]]
    if unknown:
        raise DomainError(f"아직 없는 근거(작성 전이거나 모르는 ID): {', '.join(unknown)}", 404)
    if not _text(args, "details"):
        raise DomainError("준비 내용(창구·대행·교육)을 적는다", 422)


def condition_evidence(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    근거 등록(EV51-14) · 지원 이행 등록(SUP41) — **등록만 한다**. 첨부했다고 조건이 충족되지
    않는다(CT505).
    CON41은 구매 담당, SUP41은 생산 임원이 등록한다.
    """
    check_condition_evidence(doc, args)
    target = _text(args, "target")
    _require(by, BUY_LEAD if target == "CON41" else PROD_EXEC, f"{target} 근거 등록", strict=strict)
    c = doc["conditions"][target]
    version = len(c["evidence"]) + 1
    c["evidence"].append(
        {
            "version": version,
            "refs": [r for r in re.split(r"[;,\s]+", _text(args, "evidence")) if r],
            "details": _text(args, "details"),
            "plan_version": doc["plan_pointer"],
            "by": by,
            "at": doc["clock"],
        }
    )
    c.update(state="EVIDENCE_READY", coordinated_at=None)
    c["history"].append({"at": doc["clock"], "state": "EVIDENCE_READY", "by": by})
    audit(
        doc,
        actor=by,
        action="condition_evidence",
        target=target,
        version=version,
        event_code="EV51-14" if target == "CON41" else None,
    )
    return {"evidence_version": version}


def check_condition_coordinate(doc: dict, args: dict[str, Any]) -> None:
    c = doc["conditions"]["CON41"]
    if c["state"] != "EVIDENCE_READY":
        raise DomainError("CON41 근거 등록 전이다", 409)
    if args.get("decision") not in ("확인", "보완필요"):
        raise DomainError("확인 또는 보완필요를 고른다", 422)
    if not _text(args, "comment"):
        raise DomainError("준비 확인 의견을 적는다", 422)
    unknown = [
        r for r in re.split(r"[;,\s]+", _text(args, "evidence")) if r and r not in doc["evidence"]
    ]
    if unknown:
        raise DomainError(f"아직 없는 근거: {', '.join(unknown)}", 404)


def condition_coordinate(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """CON41 양 부서 준비 확인(EV51-15) — 생산 임원. 충족 확인(구매 임원)과 다른 기록이다."""
    check_condition_coordinate(doc, args)
    _require(by, PROD_EXEC, "CON41 준비 확인", strict=strict)
    c = doc["conditions"]["CON41"]
    ok = args["decision"] == "확인"
    refs = [r for r in re.split(r"[;,\s]+", _text(args, "evidence")) if r]
    if refs:
        c["evidence"].append(
            {
                "version": len(c["evidence"]) + 1,
                "refs": refs,
                "details": _text(args, "comment"),
                "plan_version": doc["plan_pointer"],
                "by": by,
                "at": doc["clock"],
            }
        )
    if ok:
        c.update(state="COORDINATED", coordinated_at=doc["clock"], coordinated_by=by)
    else:
        c.update(state="REWORK_REQUIRED", rework_reason=_text(args, "comment"))
    c["history"].append(
        {"at": doc["clock"], "state": c["state"], "by": by, "note": _text(args, "comment")}
    )
    audit(
        doc,
        actor=by,
        action="condition_coordinated" if ok else "condition_rework",
        target="CON41",
        event_code="EV51-15" if ok else None,
    )
    return {}


def check_condition_confirm(doc: dict, args: dict[str, Any]) -> None:
    target = _text(args, "target")
    c = doc["conditions"].get(target)
    if c is None:
        raise DomainError(f"없는 조건·지원: {target}", 404)
    need = "COORDINATED" if target == "CON41" else "EVIDENCE_READY"
    if c["state"] != need:
        what = "양 부서 준비 확인" if target == "CON41" else "이행 등록"
        raise DomainError(
            f"{target}는 {what} 전이다 — 첨부만으로 확인하지 않는다 ({c['state']})", 409
        )
    if args.get("decision") not in ("충족", "확인", "보완필요"):
        raise DomainError("충족(확인) 또는 보완필요를 고른다", 422)
    if args["decision"] == "보완필요" and not _text(args, "comment"):
        raise DomainError("보완 필요에는 사유가 필요하다", 422)


def condition_confirm(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    CON41 충족 확인(EV51-16, 구매 임원) · SUP41 이행 확인(EV51-17, 경영관리 임원) — 확인자가 근거
    버전을 보고 한다.
    CON41과 SUP41은 서로 독립 상태다.
    """
    check_condition_confirm(doc, args)
    target = _text(args, "target")
    _require(by, BUY_EXEC if target == "CON41" else CFO, f"{target} 확인", strict=strict)
    c = doc["conditions"][target]
    if args["decision"] == "보완필요":
        c.update(state="REWORK_REQUIRED", rework_reason=_text(args, "comment"))
        c["history"].append(
            {
                "at": doc["clock"],
                "state": "REWORK_REQUIRED",
                "by": by,
                "note": _text(args, "comment"),
            }
        )
        audit(doc, actor=by, action="condition_rework", target=target)
        return {"state": c["state"]}
    state = "SATISFIED" if target == "CON41" else "VERIFIED"
    c.update(
        state=state, confirmed_by=by, confirmed_at=doc["clock"], evidence_version=len(c["evidence"])
    )
    c["history"].append(
        {"at": doc["clock"], "state": state, "by": by, "note": _text(args, "comment")}
    )
    audit(
        doc,
        actor=by,
        action="condition_confirmed",
        target=target,
        state=state,
        event_code="EV51-16" if target == "CON41" else "EV51-17",
    )
    return {"state": state}


# ─────────────────────────── S09 품의·예산 (U503 · CT506) ───────────────────────────


def budget_status(doc: dict) -> dict[str, Any]:
    """M509 — 총괄·과제별 일회성 사용가능액과 별도 운영지원 원장."""
    limits = {t: Decimal(str(doc["sc04"]["actions"][t]["budget"])) for t in calc.TASKS}
    a42 = doc["sc04"]["assumptions"][TASK_ID]
    operating = Decimal(a42["monthly_support"]) * 4  # 9~12월 월 지원비 — 기존 운영예산 범위
    return calc.budget(limits, operating, doc["ledger"])


def check_submit_request(doc: dict, args: dict[str, Any]) -> None:
    rid = _text(args, "request_id")
    if rid not in REQUESTS:
        raise DomainError(f"없는 품의: {rid}", 404)
    r = doc["requests"].get(rid)
    if r is not None and r["state"] not in ("RETURNED",):
        raise DomainError(f"{rid}는 이미 {r['state']}다", 409)
    if effective_plan(doc) is None:
        raise DomainError(
            "유효 계획이 없다 — 품의는 확정·확인된 계획과 대표 승인서를 근거로 한다", 409
        )
    amount = _money(args.get("amount"), "요청액")
    if amount is None:
        raise DomainError("요청액을 적는다 — 0이라는 이유로 면제하지 않는다", 422)
    if not _text(args, "reason"):
        raise DomainError("품의 사유를 적는다", 422)
    _budget_guard(doc, rid, amount)


def _budget_guard(doc: dict, rid: str, amount: Decimal) -> None:
    status = budget_status(doc)
    if REQUESTS[rid]["scope"] == "ONEOFF":
        task = next(t for t in status["tasks"] if t["task_id"] == TASK_ID)
        avail = min(Decimal(task["available"]), Decimal(status["total"]["available"]))
        where = "과제·총괄 일회성"
    else:
        avail = Decimal(status["operating"]["available"])
        where = "운영지원"
    if amount > avail:
        raise PrerequisiteError(
            f"{where} 사용가능액 {int(avail):,}원을 넘는다 — 신규 약정·실행 보류(과제 간 전용은 "
            "경영관리 임원 승인, "
            "총괄 초과는 대표 별도 승인)",
            [f"{rid} 요청 {int(amount):,}원 > 사용가능 {int(avail):,}원"],
            "BUDGET_EXCEEDED",
        )


def submit_request(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    품의 상신(EV51-18) — 계획·대표 승인·예산 범위를 검사한다. 반려본을 고치면 새 판이고 다시
    승인받는다.
    """
    check_submit_request(doc, args)
    _require(by, BUY_LEAD, "품의 상신", strict=strict)
    rid = _text(args, "request_id")
    prior = doc["requests"].get(rid)
    version = 1 if prior is None else prior["version"] + 1
    doc["requests"][rid] = {
        "request_id": rid,
        "seq": prior["seq"] if prior else _seq(doc["requests"]),
        "version": version,
        "task_id": TASK_ID,
        "scope": REQUESTS[rid]["scope"],
        "amount": str(_money(args.get("amount"), "요청액")),
        "reason": _text(args, "reason"),
        "evidence": [r for r in re.split(r"[;,\s]+", _text(args, "evidence")) if r],
        "approval_ref": doc["sc04"]["approval"]["approval_id"],
        "plan_ref": doc["plan_pointer"],
        "state": "SUBMITTED",
        "background": False,
        "history": [
            *(prior["history"] if prior else []),
            {"at": doc["clock"], "state": "SUBMITTED", "by": by, "version": version},
        ],
    }
    audit(
        doc,
        actor=by,
        action="request_submitted",
        request_id=rid,
        version=version,
        event_code="EV51-18" if rid == "REQ51" else None,
    )
    return {"request_id": rid, "version": version}


def check_approve_request(doc: dict, args: dict[str, Any]) -> None:
    rid = _text(args, "request_id")
    r = doc["requests"].get(rid)
    if r is None and rid in REQUESTS:
        # 아는 품의인데 기록이 없다 = 상신 기록 전이다(Center 실행의 기록 작업이 늦다 — 상태 충돌)
        raise DomainError(f"{rid}는 아직 상신되지 않았다", 409)
    if r is None:
        raise DomainError(f"없는 품의: {rid}", 404)
    stage = _text(args, "stage")
    need = {"function": "SUBMITTED", "budget": "FUNCTION_APPROVED"}.get(stage)
    if need is None:
        raise DomainError(f"모르는 승인 단계: {stage}", 422)
    if r["state"] != need:
        raise DomainError(
            f"{rid}는 {'현업 승인' if stage == 'function' else '예산 승인'} 대기가 아니다 "
            f"({r['state']})",
            409,
        )
    if args.get("decision") not in ("승인", "반려"):
        raise DomainError("승인 또는 반려를 고른다", 422)
    if args["decision"] == "반려" and not _text(args, "reason"):
        raise DomainError("반려에는 사유가 필요하다", 422)
    if args["decision"] == "승인" and stage == "budget":
        _budget_guard(doc, rid, Decimal(r["amount"]))


def approve_request(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    현업 임원 → 예산 임원(EV51-19~21). **최종 승인과 약정(COMMIT)을 함께 저장한다** — 동시 품의는
    같은 예산을
    잠근 뒤 잔여액을 다시 본다(데모 실행 하나 = 문서 하나라 저장이 곧 잠금이다). 대표 재승인은
    없다(한도 안).
    """
    check_approve_request(doc, args)
    stage = _text(args, "stage")
    _require(by, BUY_EXEC if stage == "function" else CFO, "품의 승인", strict=strict)
    rid = _text(args, "request_id")
    r = doc["requests"][rid]
    if args["decision"] == "반려":
        r.update(state="RETURNED", return_reason=_text(args, "reason"))
        r["history"].append(
            {"at": doc["clock"], "state": "RETURNED", "by": by, "note": _text(args, "reason")}
        )
        audit(doc, actor=by, action="request_returned", request_id=rid)
        return {"state": "RETURNED"}
    state = "FUNCTION_APPROVED" if stage == "function" else "APPROVED"
    r["state"] = state
    r["history"].append({"at": doc["clock"], "state": state, "by": by})
    if state == "APPROVED":
        doc["ledger"].append(
            {
                "txn_id": _txn_id(doc, rid),
                "seq": len(doc["ledger"]) + 1,
                "task_id": TASK_ID,
                "scope": r["scope"],
                "request_ref": rid,
                "at": doc["clock"],
                "type": "COMMIT",
                "commitment_delta": r["amount"],
                "paid_delta": "0",
                "pnl_cost": "0",
                "evidence": ";".join(r["evidence"]) or rid,
            }
        )
    codes = {
        ("REQ51", "function"): "EV51-19",
        ("REQ51", "budget"): "EV51-20",
        ("OP51", "budget"): "EV51-21",
    }
    audit(
        doc,
        actor=by,
        action="request_approved",
        request_id=rid,
        stage=stage,
        event_code=codes.get((rid, stage)),
    )
    return {"state": state}


def _txn_id(doc: dict, rid: str) -> str:
    """약정 거래 id — 데이터의 시연 식별자를 쓴다. 이미 쓴 id(반려 뒤 재승인)면 이어 붙인다."""
    taken = {t["txn_id"] for t in doc["ledger"]}
    tid = doc["txn_ids"].get(rid)
    return tid if tid and tid not in taken else f"{rid}-C{len(doc['ledger']) + 1:02d}"


# ─────────────────────────── S10 운영 적용 착수 (U503 · CT507) ───────────────────────────


def start_requirements(doc: dict) -> dict[str, Any]:
    """
    착수 요건(M502) — 각 요건의 충족 여부를 따로 낸다. **개수 합이나 사용자가 보낸 ready로 착수를
    허용하지 않는다.**
    8/20에 모두 끝나도 적용일(9/1 09:00) 전에는 READY · 착수 불가다(CK519·CK520).
    """
    plan = effective_plan(doc)
    cond, sup = doc["conditions"]["CON41"], doc["conditions"]["SUP41"]
    req = {rid: (doc["requests"].get(rid) or {}).get("state") for rid in REQUESTS}
    pending = unresolved_change(doc)
    items = [
        (
            "plan_confirmed",
            "최신 계획 담당 임원 확정",
            plan is not None and plan["state"] == "CONFIRMED",
        ),
        (
            "plan_verified",
            "경영관리 확인",
            plan is not None and plan["management_check"] == "VERIFIED",
        ),
        ("CON41", "CON41 공동 기준 충족", cond["state"] == "SATISFIED"),
        ("SUP41", "SUP41 생산 지원 이행 확인", sup["state"] == "VERIFIED"),
        ("REQ51", "REQ51 일회성 검증비 승인", req["REQ51"] == "APPROVED"),
        ("OP51", "OP51 운영지원비 승인", req["OP51"] == "APPROVED"),
        ("no_change", "미확정 변경안 없음", pending is None),
    ]
    ready = all(ok for _k, _l, ok in items)
    arrived = _past(doc, SCHEDULE["apply_at"])
    blocking = [label for k, label, ok in items if not ok and k != "no_change"]
    if pending is not None:
        blocking.append(f"미확정 변경안 {pending['plan_id']} ({pending['state']}) — 착수 보류")
    if ready and not arrived:
        blocking.append("적용일 9/1 09:00 미도래")
    return {
        "items": [{"id": k, "label": label, "ok": ok} for k, label, ok in items],
        "ready": "READY" if ready else "WAIT",
        "start_allowed": ready and arrived,
        "apply_at": SCHEDULE["apply_at"],
        "blocking": blocking,
        "plan_version": None if plan is None else plan["plan_id"],
    }


def check_start(doc: dict, args: dict[str, Any] | None = None) -> None:
    if doc["start"] is not None:
        raise DomainError(f"이미 착수했다({START_ID}) — 한 번만 만든다", 409)
    check = start_requirements(doc)
    if not check["start_allowed"]:
        raise PrerequisiteError(
            "착수 요건 미충족: " + ", ".join(check["blocking"]), check["blocking"], "START_BLOCKED"
        )
    version = _text(args or {}, "plan_version")
    if version and version != check["plan_version"]:
        raise DomainError(f"본 계획({version})이 유효 계획({check['plan_version']})이 아니다", 409)


def start_operation(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    운영 적용 착수(EV51-22) — 구매 임원이 요건을 서버에서 다시 보고 START51을 한 번 만든다. 착수 ≠
    성과 달성.
    """
    check_start(doc, args)
    _require(by, BUY_EXEC, "운영 적용 착수", strict=strict)
    check = start_requirements(doc)
    doc["start"] = {
        "start_id": START_ID,
        "task_id": TASK_ID,
        "plan_version": check["plan_version"],
        "conditions": ["CON41", "SUP41"],
        "requests": list(REQUESTS),
        "started_at": doc["clock"],
        "started_by": by,
        "comment": _text(args, "comment"),
        "requirements": check["items"],
    }
    op = doc["operation"][TASK_ID]
    op.update(state="OPERATING", started_at=doc["clock"])
    op["history"].append({"at": doc["clock"], "state": "OPERATING", "ref": START_ID, "by": by})
    audit(
        doc,
        actor=by,
        action="operation_started",
        start_id=START_ID,
        plan=check["plan_version"],
        event_code="EV51-22",
    )
    return {"start_id": START_ID}


# ─────────────────────────── S11·S12 변경 공유·구매 대응 (U504 · CT508·CT509)
# ───────────────────────────


def customer_plan(seed: Seed, plan_ref: str) -> list[dict[str, Any]]:
    """고객 원문 a~e — 전후 네 구간. 월합계 차이는 계산한다(두 요청창을 합산하지 않는다, T510)."""
    out = []
    for r in seed.rows("SC05고객계획"):
        if r["계획공유ID"] != plan_ref:
            continue
        before = [int(r[f"전{i}구간"]) for i in range(1, 5)]
        after = [int(r[f"후{i}구간"]) for i in range(1, 5)]
        out.append(
            {
                "plan_ref": plan_ref,
                "model_id": str(r["model_id"]),
                "month_total": int(r["9월월합계"]),
                "windows": list(WINDOWS),
                "before": before,
                "after": after,
                "changed": before != after,
                "month_diff": sum(after) - sum(before),
                "note": str(r["변경내용"]),
                "evidence": str(r["근거ID"]),
            }
        )
    return out


def next_source(doc: dict) -> str:
    """BPM의 대표 변경 고리 — 아직 받지 않은 대표 원문. 없으면 빈 글(고리를 나간다)."""
    return next((src for src, ch in REPRESENTATIVE.items() if ch not in doc["changes"]), "")


def _change(doc: dict, args: dict[str, Any]) -> dict:
    """
    대상 변경 건 — 그림은 `변경ID` 변수로 싣는다. 화면 답의 사전 검사에는 그 변수가 없어 진행 중인
    대표 건을 쓴다.
    """
    cid = _text(args, "change_id") or (_open_change(doc) or {}).get("change_id", "")
    c = doc["changes"].get(cid)
    if c is None or c["background"]:
        raise DomainError(f"없는 변경 건(또는 배경 건): {cid or '없음'}", 404)
    return c


def check_receive(doc: dict, args: dict[str, Any]) -> None:
    if doc["start"] is None:
        raise DomainError("운영 적용 전이다 — 변경 공유 기준은 착수 뒤에 쓴다", 409)
    src = _text(args, "source")
    if src not in REPRESENTATIVE:
        raise DomainError(f"모르는 고객 원문: {src}", 404)
    if REPRESENTATIVE[src] in doc["changes"]:
        raise DomainError(f"{src}는 이미 접수했다({REPRESENTATIVE[src]})", 409)
    if src not in doc.get("originals", {}):
        raise DomainError(f"{src}는 아직 수신되지 않았다 — 원문이 도착한 뒤에 접수한다", 409)


def receive_change(
    doc: dict, seed: Seed, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    고객 변경 접수(EV51-23·29) — 원문 버전을 보존하고 변경 건을 연다. a~e 전체 모델을 함께 둔다.
    """
    check_receive(doc, args)
    _require(by, PROD_LEAD, "고객 변경 접수", strict=strict)
    src = _text(args, "source")
    c = _change_record(doc, None, source=src)
    c.update(received_at=doc["clock"], state="RECEIVED", received_by=by, memo=_text(args, "memo"))
    c["history"].append({"at": doc["clock"], "state": "RECEIVED", "by": by})
    doc["changes"][c["change_id"]] = c
    doc["customer_plans"][src] = {
        "plan_ref": src,
        "received_at": doc["clock"],
        "lines": customer_plan(seed, src),
    }
    audit(
        doc,
        actor=by,
        action="change_received",
        change_id=c["change_id"],
        source=src,
        event_code="EV51-23" if src == "CP51" else "EV51-29",
    )
    return {"change_id": c["change_id"]}


def check_share(doc: dict, args: dict[str, Any]) -> None:
    c = _change(doc, args)
    if c["state"] != "RECEIVED":
        raise DomainError(f"{c['change_id']}는 공유 대기가 아니다 ({c['state']})", 409)
    if not _text(args, "summary"):
        raise DomainError("공유 내용(영향 모델·구간·수량)을 적는다", 422)
    ref = _text(args, "agent_ref")
    if ref and ref not in doc["agent_outputs"]:
        raise DomainError(f"없는 Agent 초안: {ref}", 404)


def share_change(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """생산 공유(EV51-24·30) — 정해진 창구로. 공유 시각과 내부 알림을 남긴다(접수 후 60분 기준)."""
    check_share(doc, args)
    _require(by, PROD_LEAD, "생산 공유", strict=strict)
    c = _change(doc, args)
    c.update(
        shared_at=doc["clock"], shared_by=by, state="SHARED", share_summary=_text(args, "summary")
    )
    c["history"].append({"at": doc["clock"], "state": "SHARED", "by": by})
    ref = _text(args, "agent_ref")
    if ref:
        _cite_agent(doc, ref, by=by, modified=False)
        c["agent_ref"] = ref
    audit(
        doc,
        actor=by,
        action="change_shared",
        change_id=c["change_id"],
        event_code="EV51-24" if c["change_id"] == "CH51" else "EV51-30",
    )
    return {}


def check_ack(doc: dict, args: dict[str, Any]) -> None:
    c = _change(doc, args)
    if c["state"] != "SHARED":
        raise DomainError(f"{c['change_id']}는 공유 전이거나 이미 확인했다 ({c['state']})", 409)


def ack_change(doc: dict, args: dict[str, Any], *, by: str, strict: bool = True) -> dict[str, Any]:
    """
    구매 확인(EV51-25·31) — 구매 담당 또는 **유효한 지정 대행**(USR-BUY2 — CON41 충족 뒤, 공동 기준
    DOC51).
    대행 범위 밖이면 403이다.
    """
    check_ack(doc, args)
    delegate = by in DELEGATES["Ack_Change"]
    if delegate and doc["conditions"]["CON41"]["state"] != "SATISFIED":
        raise DomainError("대행 지정(공동 기준 CON41)이 아직 유효하지 않다", 403)
    _require(by, (BUY_LEAD, *DELEGATES["Ack_Change"]), "구매 확인", strict=strict)
    c = _change(doc, args)
    c.update(
        ack_at=doc["clock"],
        ack_by=by,
        delegate=delegate,
        state="ACKNOWLEDGED",
        ack_note=_text(args, "comment"),
    )
    c["history"].append({"at": doc["clock"], "state": "ACKNOWLEDGED", "by": by})
    audit(
        doc,
        actor=by,
        action="change_acknowledged",
        change_id=c["change_id"],
        delegate=delegate,
        event_code="EV51-25" if c["change_id"] == "CH51" else "EV51-31",
    )
    return {}


def check_respond(doc: dict, args: dict[str, Any]) -> None:
    c = _change(doc, args)
    if c["state"] != "ACKNOWLEDGED":
        raise DomainError(f"{c['change_id']}는 구매 확인 전이다 ({c['state']})", 409)
    decision = args.get("decision")
    if decision not in ("정상대응", "긴급기안"):
        raise DomainError("정상대응 또는 긴급기안을 고른다", 422)
    for key, word in (("inventory", "재고"), ("open_orders", "기발주"), ("qty", "주문수량")):
        _int(args.get(key), word)
    _day(args.get("need_date"), "필요일")
    if decision == "긴급기안" or _text(args, "normal_date"):
        _day(args.get("normal_date"), "정상조달일")  # 정상 대응은 재고·기발주로 충당하면 비워 둔다
    if not _text(args, "order_id"):
        raise DomainError("주문번호를 적는다", 422)
    if _text(args, "order_id") in doc["orders"]:
        raise DomainError(f"이미 있는 주문: {_text(args, 'order_id')}", 409)
    if not _text(args, "rationale"):
        raise DomainError("판단 근거를 적는다", 422)
    if decision == "긴급기안":
        if _day(args.get("normal_date"), "정상조달일") <= _day(args.get("need_date"), "필요일"):
            raise DomainError("정상조달이 필요일에 맞으면 긴급구매가 아니다 — 정상 대응으로", 422)
        if (
            _money(args.get("transport"), "긴급운송비") is None
            or _money(args.get("premium"), "할증") is None
        ):
            raise DomainError(
                "긴급 추가비(운송·할증)를 적는다 — 미확인 비용을 0으로 두지 않는다", 422
            )


def respond_change(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    구매 대응(EV51-26·32) — 재고·기발주·필요일·정상조달일로 판단한다. 정상 대응이면 추가비 0으로
    주문을 준비하고,
    정상조달이 불가하면 사유·추가비·납기 영향으로 **긴급 기안**한다(기존 구매 전결로 승인받는다).
    긴급구매를 무조건
    금지하지 않는다.
    """
    check_respond(doc, args)
    _require(by, BUY_LEAD, "구매 대응", strict=strict)
    c = _change(doc, args)
    urgent = args["decision"] == "긴급기안"
    transport = _money(args.get("transport"), "긴급운송비") if urgent else Decimal(0)
    premium = _money(args.get("premium"), "할증") if urgent else Decimal(0)
    response = {
        "inventory": _int(args["inventory"], "재고"),
        "open_orders": _int(args["open_orders"], "기발주"),
        "need_date": _day(args["need_date"], "필요일"),
        "normal_date": _day(args["normal_date"], "정상조달일")
        if _text(args, "normal_date")
        else None,
        "rationale": _text(args, "rationale"),
        "decided_at": doc["clock"],
        "decided_by": by,
    }
    oid = _text(args, "order_id")
    doc["orders"][oid] = {
        "order_id": oid,
        "seq": _seq(doc["orders"]),
        "month": "2027-09-01",
        "model_id": c["model_id"],
        "part_id": "P-COM01",
        "change_ref": c["change_id"],
        "qty": _int(args["qty"], "주문수량"),
        "urgent": urgent,
        "transport": str(transport),
        "premium": str(premium),
        "extra": str(transport + premium),  # type: ignore[operator]
        "ordered_at": None,
        "recorded_at": None,
        "approver": None,
        "approved_at": None,
        "reason": _text(args, "rationale"),
        "evidence": None,
        "late": None,
        "quality": None,
        "result_status": None,
        "background": False,
        "state": "URGENT_SUBMITTED" if urgent else "NORMAL_DECIDED",
    }
    state = "URGENT_SUBMITTED" if urgent else "NORMAL_DECIDED"
    c.update(
        state=state, decision="URGENT" if urgent else "NORMAL", order_ref=oid, response=response
    )
    c["history"].append({"at": doc["clock"], "state": state, "by": by})
    audit(
        doc,
        actor=by,
        action="change_responded",
        change_id=c["change_id"],
        decision=c["decision"],
        order=oid,
        event_code="EV51-26" if not urgent else "EV51-32",
    )
    return {"order_id": oid, "decision": c["decision"]}


def urgent_limit(doc: dict) -> Decimal:
    """가상 기존 구매 전결 — 긴급 추가비 이 금액 이하는 구매 임원(SC05설정)."""
    return Decimal(doc["settings"]["urgent_approval_limit"])


def check_approve_urgent(doc: dict, args: dict[str, Any]) -> None:
    c = _change(doc, args)
    if c["state"] != "URGENT_SUBMITTED":
        raise DomainError(f"{c['change_id']}는 긴급 승인 대기가 아니다 ({c['state']})", 409)
    if args.get("decision") not in ("승인", "반려"):
        raise DomainError("승인 또는 반려를 고른다", 422)
    if args["decision"] == "반려":
        if not _text(args, "reason"):
            raise DomainError("반려에는 사유가 필요하다", 422)
        return
    cost = _money(args.get("additional_cost"), "추가비")
    order = doc["orders"][c["order_ref"]]
    if cost is None or cost != Decimal(order["extra"]):
        raise DomainError(f"승인 추가비가 기안({int(Decimal(order['extra'])):,}원)과 다르다", 409)
    if cost > urgent_limit(doc):
        raise PrerequisiteError(
            f"추가비 {int(cost):,}원이 구매 임원 전결 {int(urgent_limit(doc)):,}원을 넘는다 — 상위 "
            "전결 확인 전 실행 차단",
            [f"{c['order_ref']} 상위 전결 필요"],
            "BUDGET_EXCEEDED",
        )
    if not _text(args, "impacts"):
        raise DomainError("납기·품질 영향을 적는다", 422)


def approve_urgent(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    긴급 예외 승인(EV51-33) — 기존 구매 전결(추가비 200만원 이하 구매 임원). 계획 변경 승인과
    다르다.
    """
    check_approve_urgent(doc, args)
    _require(by, BUY_EXEC, "긴급 예외 승인", strict=strict)
    c = _change(doc, args)
    order = doc["orders"][c["order_ref"]]
    if args["decision"] == "반려":
        c.update(state="ACKNOWLEDGED", return_reason=_text(args, "reason"))
        del doc["orders"][c["order_ref"]]
        c["history"].append({"at": doc["clock"], "state": "URGENT_RETURNED", "by": by})
        audit(doc, actor=by, action="urgent_returned", change_id=c["change_id"])
        return {"state": "RETURNED"}
    order.update(
        approver=by, approved_at=doc["clock"], state="APPROVED", impacts=_text(args, "impacts")
    )
    c.update(state="APPROVED")
    c["history"].append({"at": doc["clock"], "state": "APPROVED", "by": by})
    audit(
        doc,
        actor=by,
        action="urgent_approved",
        change_id=c["change_id"],
        order=order["order_id"],
        event_code="EV51-33",
    )
    return {"state": "APPROVED"}


def check_execute(doc: dict, args: dict[str, Any]) -> None:
    c = _change(doc, args)
    order = doc["orders"].get(c["order_ref"] or "")
    if order is None:
        raise DomainError(f"{c['change_id']}에 준비된 주문이 없다", 409)
    if order["urgent"] and order["state"] != "APPROVED":
        raise PrerequisiteError(
            "긴급 예외가 승인되지 않았다 — 실행 완료·실적 반영 불가(X504)",
            [f"{order['order_id']} 긴급 예외 승인 대기"],
            "URGENT_NOT_APPROVED",
        )
    if order["state"] == "EXECUTED":
        raise DomainError("이미 실행 기록이 있다", 409)
    ordered_at = _when(args.get("ordered_at"), "발주 시각")
    if parse_at(ordered_at) > parse_at(doc["clock"]):
        raise DomainError("발주 시각이 지금보다 늦다", 400)
    if order["approved_at"] and parse_at(ordered_at) < parse_at(order["approved_at"]):
        raise DomainError("발주가 긴급 승인보다 앞선다", 400)


def execute_order(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    발주·처리 기록(EV51-27·34) — 발주 시각(주문 실행)과 처리기록 시각(시스템 등록, 지금)을 따로
    남긴다. 실제 비용·
    납기·품질은 결과 원천에서 확인한다 — 승인액에서 실적을 만들지 않는다.
    """
    check_execute(doc, args)
    _require(by, BUY_LEAD, "발주 기록", strict=strict)
    c = _change(doc, args)
    order = doc["orders"][c["order_ref"]]
    order.update(
        ordered_at=_when(args.get("ordered_at"), "발주 시각"),
        recorded_at=doc["clock"],
        evidence=_text(args, "evidence") or None,
        state="EXECUTED",
    )
    c.update(state="EXECUTED")
    c["history"].append({"at": doc["clock"], "state": "EXECUTED", "by": by})
    audit(
        doc,
        actor=by,
        action="order_executed",
        change_id=c["change_id"],
        order=order["order_id"],
        event_code="EV51-27" if c["change_id"] == "CH51" else "EV51-34",
    )
    return {"next_source": next_source(doc)}


# ─────────────────────────── S13 초기 실행 결과 (U505 · CT509·CT510) ───────────────────────────


def observation(doc: dict) -> dict[str, Any]:
    """
    지금 시각까지 들어온 원천으로 9월 A-b·P-COM01 결과를 집계한다(확정 전 미리보기). 기본 60건·6건은
    상수가 아니라
    집계 결과다. 확정하면 그 순간의 결과를 버전으로 고정한다.
    """
    a42 = doc["sc04"]["assumptions"][TASK_ID]
    orders = [
        o
        for o in ordered(doc["orders"])
        if o["month"] == "2027-09-01"
        and o["model_id"] == "A-b"
        and o["part_id"] == "P-COM01"
        and o["state"] == "EXECUTED"
    ]
    support_txn = [
        t
        for t in doc["ledger"]
        if t["request_ref"] == "OP51" and t["type"] == "SETTLE" and t["at"][:7] == "2027-09"
    ]
    support = (
        None if not support_txn else sum((Decimal(t["pnl_cost"]) for t in support_txn), Decimal(0))
    )
    obs = calc.observation(
        # 원천의 중복 행은 주문 사전에서 사라지지 않게 따로 둔 것을 다시 붙인다(은폐 금지, X509)
        orders + [i["row"] for i in doc["source_issues"] if i["kind"] == "DUPLICATE_ORDER"],
        [
            c
            for c in ordered(doc["changes"])
            if c["received_at"] and c["received_at"][:7] == "2027-09"
        ],
        base_count=a42["emergency_before"],
        unit_cost=Decimal(a42["per_event_cost"]),
        support=support,
        share_limit=doc["settings"]["share_minutes"],
        ack_limit=doc["settings"]["confirm_minutes"],
    )
    obs["period"] = "2027-09"
    obs["scope"] = "A-b · P-COM01 · 주문 ID 단위(취소 제외)"
    obs["comparison_basis"] = (
        f"개선안 검토·실행 승인 판단 가정 — 동일 물량 정규화 월 {a42['emergency_before']}건 × 건당 "
        f"{int(Decimal(a42['per_event_cost'])):,}원. "
        "과거 실제 비용이나 인과적으로 입증된 절감이 아니다"
    )
    obs["one_off_august"] = str(
        sum(
            (
                Decimal(t["pnl_cost"])
                for t in doc["ledger"]
                if t["request_ref"] == "REQ51" and t["type"] == "SETTLE"
            ),
            Decimal(0),
        )
    )
    return obs


def check_confirm_observation(doc: dict, args: dict[str, Any]) -> None:
    if doc["observation"] is not None:
        raise DomainError("초기 결과는 이미 확인했다 — 확인본은 고치지 않는다", 409)
    if doc["start"] is None:
        raise DomainError("운영 적용 전이다", 409)
    if not _past(doc, SCHEDULE["result_confirmed_at"]):
        raise PrerequisiteError(
            "9월 마감 전이다 — 결과 확인시각(9/30 18:00) 뒤에 확인한다",
            ["9월 결과 확인시각 미도래"],
            "RESULT_INCOMPLETE",
        )
    if args.get("decision") not in ("확인",):
        raise DomainError("확인을 고른다", 422)
    obs = observation(doc)
    if not obs["complete"]:
        raise PrerequisiteError(
            "초기 결과 확정 불가: " + ", ".join(obs["blocking"]),
            obs["blocking"],
            "RESULT_INCOMPLETE",
        )


def confirm_observation(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    초기 결과 확인(EV51-37) — 구매 임원이 비교 범위·비용·납기·품질을 확인한다. 초기 결과를 연간
    달성으로 확대하지
    않는다. 8월 일회성비는 9월 순개선에서 다시 빼지 않는다(T517).
    """
    check_confirm_observation(doc, args)
    _require(by, BUY_EXEC, "초기 결과 확인", strict=strict)
    obs = observation(doc)
    doc["observation"] = {
        **obs,
        "observation_id": "OBS51",
        "result_version": 1,
        "source_hash": _hash(
            [obs["orders"], obs["qty"], obs["extra_cost"], obs["support"], obs["duplicates"]]
        ),
        "confirmed_by": by,
        "confirmed_at": doc["clock"],
        "comment": _text(args, "comment"),
        "evidence": "DOC58",
    }
    audit(doc, actor=by, action="observation_confirmed", observation="OBS51", event_code="EV51-37")
    return {"observation_id": "OBS51", "urgent": obs["urgent"], "net": obs["net"]}


# ─────────────────────────── S14·S15 운영계획 (U506 · CT510·CT511) ───────────────────────────


def check_confirm_opl(doc: dict, args: dict[str, Any]) -> None:
    pid = _text(args, "plan_id")
    if pid not in OPERATING_PLANS:
        raise DomainError(f"없는 운영계획: {pid}", 404)
    p = doc["operating_plans"].get(pid)
    if p is not None and p["state"] not in ("REWORK_REQUIRED",):
        raise DomainError(f"{pid}는 이미 {p['state']}다 — 확정본은 새 버전으로", 409)
    if doc["observation"] is None:
        raise DomainError("9월 초기 결과 확인 전이다 — 마감 실적을 잠근 뒤 잔여 계획을 고친다", 409)
    if args.get("decision") != "확정":
        raise DomainError("확정을 고른다", 422)
    if not _text(args, "remaining_plan"):
        raise DomainError("잔여 운영계획을 적는다", 422)
    task = OPERATING_PLANS[pid]
    if task == "ACT42":
        for m in ("oct", "nov", "dec"):
            _int(args.get(m), f"{m} 긴급건수")
        if not _text(args, "assumption"):
            raise DomainError("개선 가정의 근거를 적는다 — 9월 실적에서 자동 외삽하지 않는다", 422)
    else:
        _int(args.get("qty"), "월 적용량")
    if task == "ACT41":
        saving = _money(args.get("fixed_saving"), "고정비 절감")
        if saving is None or saving != 0:
            raise PrerequisiteError(
                "외주 조정으로 공장 고정비를 줄이지 않는다 — 절감 0, 월 370백만원 유지(T522)",
                ["고정비 절감 입력 차단"],
                "FORECAST_INVALID",
            )
    if task == "ACT43":
        _when(args.get("stabilize_due"), "안정화 확인일")


def confirm_opl(doc: dict, args: dict[str, Any], *, by: str, strict: bool = True) -> dict[str, Any]:
    """
    운영계획 확정(EV51-38~40) — 담당 임원이 잔여 10~12월 가정만 고친다. 마감월(1~9월)은 잠겨 있다.
    11~12월 개선은
    담당 임원의 판단 가정이고 9월 실적에서 자동 외삽하지 않는다.
    """
    check_confirm_opl(doc, args)
    pid = _text(args, "plan_id")
    task = OPERATING_PLANS[pid]
    _require(by, OWNERS[task], f"{pid} 확정", strict=strict)
    a = doc["sc04"]["assumptions"][task]
    if task == "ACT42":
        months = {
            "2027-10-01": _int(args["oct"], "10월"),
            "2027-11-01": _int(args["nov"], "11월"),
            "2027-12-01": _int(args["dec"], "12월"),
        }
        assumptions = {"urgent": months, "support": a["monthly_support"]}
    else:
        assumptions = {"qty": _int(args["qty"], "월 적용량"), "fixed_saving": "0"}
        if task == "ACT43":
            assumptions["stabilize_due"] = _when(args.get("stabilize_due"), "안정화 확인일")
    prior = doc["operating_plans"].get(pid)
    doc["operating_plans"][pid] = {
        "plan_id": pid,
        "seq": prior["seq"] if prior else _seq(doc["operating_plans"]),
        "version": 1 if prior is None else prior["version"] + 1,
        "task_id": task,
        "period_from": "2027-10-01",
        "period_to": "2027-12-31",
        "remaining_plan": _text(args, "remaining_plan"),
        "assumption_note": _text(args, "assumption"),
        "assumptions": assumptions,
        "source_actuals": "OBS51",
        "state": "CONFIRMED",
        "owner_confirm": {"by": by, "at": doc["clock"]},
        "management_verify": None,
        "progress": _text(args, "progress"),
        "agent_ref": _text(args, "agent_ref") or None,
    }
    if _text(args, "agent_ref"):
        _cite_agent(doc, _text(args, "agent_ref"), by=by, modified=True)
    codes = {"OPL51": "EV51-38", "OPL52": "EV51-39", "OPL53": "EV51-40"}
    audit(doc, actor=by, action="opl_confirmed", plan_id=pid, event_code=codes[pid])
    _stale_forecasts(doc, f"{pid} 운영계획이 바뀌었다")
    return {"plan_id": pid}


def check_verify_opl(doc: dict, args: dict[str, Any]) -> None:
    pid = _text(args, "plan_id")
    p = doc["operating_plans"].get(pid)
    if p is None or p["state"] != "CONFIRMED":
        raise DomainError(f"{pid}는 경영관리 확인 대기가 아니다", 409)
    if args.get("decision") not in ("확인", "보완필요"):
        raise DomainError("확인 또는 보완필요를 고른다", 422)
    if args["decision"] == "보완필요" and not _text(args, "comment"):
        raise DomainError("보완 필요에는 사유가 필요하다", 422)


def verify_opl(doc: dict, args: dict[str, Any], *, by: str, strict: bool = True) -> dict[str, Any]:
    """경영관리 확인(EV51-41) — 부서 가정의 정합성. 셋 다 확인돼야 전망 작성 자료가 된다."""
    check_verify_opl(doc, args)
    _require(by, CFO, "운영계획 확인", strict=strict)
    pid = _text(args, "plan_id")
    p = doc["operating_plans"][pid]
    if args["decision"] == "보완필요":
        p.update(state="REWORK_REQUIRED", rework_reason=_text(args, "comment"))
        audit(doc, actor=by, action="opl_rework", plan_id=pid)
        return {"state": p["state"]}
    p.update(
        state="VERIFIED",
        management_verify={"by": by, "at": doc["clock"], "comment": _text(args, "comment")},
    )
    all_done = all(
        (doc["operating_plans"].get(x) or {}).get("state") == "VERIFIED" for x in OPERATING_PLANS
    )
    audit(
        doc,
        actor=by,
        action="opl_verified",
        plan_id=pid,
        event_code="EV51-41" if all_done else None,
    )
    return {"state": "VERIFIED"}


# ─────────────────────────── S16·S17 공식 전망 (U507 · CT510~CT512) ───────────────────────────

METHODS = {
    "마감 실적+잔여 전망": "CLOSE_PLUS_REMAINING",
    "종전 공식본+승인효과": "PRIOR_PLUS_APPROVED",
}


def run_effects(doc: dict) -> tuple[list[dict[str, Any]], list[str]]:
    """
    RUN의 과제 효과 — 장면 4 판단 가정에서 출발해 마감월은 관측·집행 실적으로, 잔여월은 확인된
    운영계획으로 덮는다.
    덮을 근거가 없는 입력은 문제 목록으로 낸다(미확인 가정은 확정 반영 금지, CT510).
    """
    problems: list[str] = []
    obs = doc["observation"]
    out = []
    for task in calc.TASKS:
        a = doc["sc04"]["assumptions"][task]
        opl_id = next(k for k, v in OPERATING_PLANS.items() if v == task)
        opl = doc["operating_plans"].get(opl_id)
        if opl is None or opl["state"] != "VERIFIED":
            problems.append(f"{opl_id} 확정·경영관리 확인 누락")
        for m in calc.EFFECT_MONTHS:
            key = m.isoformat()
            inputs = calc.plan_inputs(a, m)
            if m < CUTOFF:
                # 마감 — 일회성·운영지원은 집행된 손익비용, ACT42 긴급비용은 확인된 관측값
                spent = [
                    t
                    for t in doc["ledger"]
                    if t["task_id"] == task and t["type"] == "SETTLE" and t["at"][:7] == key[:7]
                ]
                inputs["one_off"] = str(
                    sum(
                        (Decimal(t["pnl_cost"]) for t in spent if t["scope"] == "ONEOFF"),
                        Decimal(0),
                    )
                )
                inputs["support"] = str(
                    sum(
                        (Decimal(t["pnl_cost"]) for t in spent if t["scope"] == "OPERATING"),
                        Decimal(0),
                    )
                )
                if task == TASK_ID and inputs["applied"]:
                    if obs is None:
                        problems.append("9월 초기 결과 확인 누락")
                    else:
                        inputs.update(count=obs["urgent"], extra_cost=obs["extra_cost"])
                inputs["source"] = "CLOSE51"
            elif opl is not None:
                if task == TASK_ID:
                    inputs["count"] = opl["assumptions"]["urgent"][key] if inputs["applied"] else 0
                elif inputs["applied"]:
                    inputs["qty"] = opl["assumptions"]["qty"]
                inputs["fixed_saving"] = opl["assumptions"].get("fixed_saving", "0")
                inputs["source"] = opl_id
            out.append(calc.effect(task, inputs))
    if any(Decimal(e["fixed_saving"]) for e in out):
        problems.append("고정비 절감 입력 — 잔존 고정비는 줄지 않는다")
    return out, problems


def _stale_forecasts(doc: dict, reason: str) -> None:
    """
    계산 입력이 바뀌면 그 RUN을 본 확인·제출을 STALE로(구현명세 10장). 승인·게시된 과거 버전은
    그대로다.
    """
    for f in doc["forecasts"].values():
        if f["kind"] == "REVIEW" and f["state"] in ("DRAFT", "REVIEWED", "SUBMITTED"):
            f.update(state="STALE", stale_reason=reason)


def compute_forecast(
    doc: dict, method: str = "CLOSE_PLUS_REMAINING"
) -> tuple[list, list, dict, list[str], Decimal | None]:
    """
    산정 한 번 — 효과·월 손익·종전 공식본 대비 대사·오류. 저장하지 않는다(작성 전 AG57 설명도 같은
    계산이다).
    `PRIOR_PLUS_APPROVED`는 종전 공식본에 장면 4 승인효과를 다시 더한 연간을 낸다(X506 — 대사가
    막는다).
    """
    prior = doc["forecasts"][doc["official"]]
    effects, problems = run_effects(doc)
    rows = calc.months(doc["basis"], effects, doc["fixed"], first_forecast=CUTOFF)
    reported = None
    if method == "PRIOR_PLUS_APPROVED":
        reported = Decimal(prior["annual"]) + Decimal(
            doc["sc04"]["handoff"]["financial_snapshot"]["effect"]
        )
    recon = calc.reconcile(
        rows, effects, prior["months"], prior_effects(doc), reported_total=reported
    )
    errors = list(problems)
    keys = [(m["period"], r["model_id"]) for m in rows for r in m["models"]]
    models = {b["model_id"] for b in doc["basis"]}
    if len(keys) != len(set(keys)) or len(keys) != 12 * len(models):
        errors.append("월·모델 키 중복 또는 대상 모델 누락")
    if not recon["ok"]:
        errors.append(
            f"변경 원인으로 설명되지 않는 차이 {int(Decimal(recon['residual'])):,}원 — 이미 반영된 "
            "효과를 다시 더했는지 본다"
        )
    return effects, rows, recon, errors, reported


def check_draft_forecast(doc: dict, args: dict[str, Any]) -> None:
    if args.get("method") not in METHODS:
        raise DomainError(f"산정 방식을 고른다 ({' · '.join(METHODS)})", 422)
    if doc["observation"] is None:
        raise DomainError("9월 초기 결과 확인 전이다 — 마감 경계를 먼저 잠근다", 409)
    missing = [
        p
        for p in OPERATING_PLANS
        if (doc["operating_plans"].get(p) or {}).get("state") != "VERIFIED"
    ]
    if missing:
        raise PrerequisiteError(
            "부서 운영계획 확정·확인이 끝나지 않았다: " + ", ".join(missing),
            missing,
            "FORECAST_INVALID",
        )
    if doc["official"] is None:
        raise DomainError("종전 공식본(FC50)이 아직 없다 — 변경 대사의 기준이 없다", 409)
    if not _text(args, "reasons"):
        raise DomainError("변경 사유 설명을 적는다", 422)
    cur = review_forecast(doc)
    if cur is not None and cur["state"] == "SUBMITTED":
        raise DomainError(
            f"{cur['forecast_id']}가 대표 승인 대기 중이다 — 새 산정은 승인·반려 뒤에", 409
        )
    if cur is not None and cur["state"] == "APPROVED":
        raise DomainError(f"{cur['forecast_id']}가 승인됐고 게시 대기다 — 게시 뒤 새 RUN으로", 409)


def draft_forecast(
    doc: dict, seed: Seed, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    전망 작성·대사(EV51-42) — 새 RUN(9월 마감 + 10~12월 전망)과 검토안 FC51-D를 만든다. 공식본을
    덮어쓰지 않는다.
    대사가 맞지 않으면(X506 — 승인효과 재가산) 검토안은 남고 대사 실패로 돌아간다.
    """
    check_draft_forecast(doc, args)
    _require(by, FIN, "전망 작성", strict=strict)
    prior = doc["forecasts"][doc["official"]]
    method = METHODS[args["method"]]
    effects, rows, recon, errors, reported = compute_forecast(doc, method)
    run_id = f"RUN{51 + len(doc['runs'])}"
    periods = calc.periods(rows)
    annual = Decimal(periods["year"]["profit"]) if reported is None else reported
    run = doc["runs"][run_id] = {
        "run_id": run_id,
        "seq": _seq(doc["runs"]),
        "method": method,
        "cutoff": "2027-09-30",
        "basis_includes_action_effects": False,
        "close_batch": "CLOSE51",
        "baseline_ref": doc["sc04"]["handoff"]["decision"],
        "prior_official": prior["forecast_id"],
        "operating_plans": {p: doc["operating_plans"][p]["version"] for p in OPERATING_PLANS},
        "observation": doc["observation"]["observation_id"],
        "effects": effects,
        "months": rows,
        "periods": periods,
        "annual": str(annual),
        "target": periods["year"]["target"],
        "gap": str(Decimal(periods["year"]["target"]) - annual),
        "reconciliation": recon,
        "errors": errors,
        "valid": not errors,
        "calculated_at": doc["clock"],
        "created_by": by,
    }
    run["run_hash"] = _hash(
        [run["annual"], [m["profit"] for m in rows], run["operating_plans"], run["method"]]
    )
    _stale_forecasts(doc, f"새 산정본 {run_id}")
    target = next_official_id(doc)
    n = sum(
        1 for f in doc["forecasts"].values() if f["kind"] == "REVIEW" and f["target_id"] == target
    )
    fid = f"{target}-D" if n == 0 else f"{target}-D{n + 1}"
    doc["forecasts"][fid] = {
        "forecast_id": fid,
        "seq": _seq(doc["forecasts"]),
        "kind": "REVIEW",
        "target_id": target,
        "run_id": run_id,
        "run_hash": run["run_hash"],
        "parent_official": prior["forecast_id"],
        "state": "DRAFT",
        "background": False,
        "change_reasons": _text(args, "reasons"),
        "confirmations": {},
        "drafted_at": doc["clock"],
        "drafted_by": by,
        "submitted_at": None,
        "approved_at": None,
        "approved_by": None,
        "approved_id": None,
        "published_at": None,
        "history": [{"at": doc["clock"], "state": "DRAFT", "by": by}],
    }
    if _text(args, "agent_ref"):
        _cite_agent(doc, _text(args, "agent_ref"), by=by, modified=False)
    audit(
        doc,
        actor=by,
        action="forecast_drafted",
        forecast_id=fid,
        run_id=run_id,
        valid=run["valid"],
        event_code="EV51-42" if run["valid"] else None,
    )
    return {"forecast_id": fid, "run_id": run_id, "valid": run["valid"]}


def next_official_id(doc: dict) -> str:
    """
    다음 공식본 id — FC50 다음은 FC51. 게시 뒤 입력이 바뀌면 FC52로 간다(기존 공식본 불변, T526).
    """
    published = [
        f for f in doc["forecasts"].values() if f["kind"] == "OFFICIAL" and not f.get("background")
    ]
    return f"FC{51 + len(published)}"


def review_forecast(doc: dict) -> dict | None:
    """지금 검토 중인 전망 — 가장 새 검토안."""
    mine = [f for f in ordered(doc["forecasts"]) if f["kind"] == "REVIEW"]
    return mine[-1] if mine else None


def check_confirm_forecast(doc: dict, args: dict[str, Any]) -> None:
    f = review_forecast(doc)
    if f is None or f["state"] not in ("DRAFT", "REVIEWED"):
        raise DomainError("확인할 검토안이 없다", 409)
    run = doc["runs"][f["run_id"]]
    if not run["valid"]:
        raise PrerequisiteError(
            "대사 실패 검토안은 확인하지 않는다", run["errors"], "FORECAST_INVALID"
        )
    dept = _text(args, "department")
    if dept not in DEPARTMENTS:
        raise DomainError(f"모르는 부서: {dept}", 404)
    ref = _text(args, "run_ref")
    if ref and ref != f["run_id"]:
        raise DomainError(f"본 산정본({ref})이 최신({f['run_id']})이 아니다 — 다시 확인한다", 409)
    if args.get("decision") not in ("확인", "이견"):
        raise DomainError("확인 또는 이견을 고른다", 422)
    if not _text(args, "comment"):
        raise DomainError("확인 의견(가정)을 적는다", 422)


def confirm_forecast(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    부서 가정 확인(EV51-43~45) — 구매·생산·영업 임원이 **자기 부서만** 확인한다(대행 불가). 확인
    대상 해시가 남는다.
    """
    check_confirm_forecast(doc, args)
    dept = _text(args, "department")
    _require(by, DEPARTMENTS[dept], f"{dept} 가정 확인", strict=strict)
    f = review_forecast(doc)
    f["confirmations"][dept] = {  # type: ignore[index]
        "decision": args["decision"],
        "by": by,
        "at": doc["clock"],
        "run_hash": f["run_hash"],  # type: ignore[index]
        "comment": _text(args, "comment"),
    }
    done = all((f["confirmations"].get(d) or {}).get("decision") == "확인" for d in DEPARTMENTS)  # type: ignore[index]
    if done:
        f.update(state="REVIEWED")  # type: ignore[union-attr]
        f["history"].append({"at": doc["clock"], "state": "REVIEWED", "by": "system"})  # type: ignore[index]
    codes = {"BUY": "EV51-43", "PROD": "EV51-44", "SALES": "EV51-45"}
    audit(
        doc,
        actor=by,
        action="forecast_confirmed",
        department=dept,
        decision=args["decision"],
        event_code=codes[dept] if args["decision"] == "확인" else None,
    )
    return {}


def forecast_blocking(doc: dict) -> list[str]:
    """제출 차단 사유 — 마감·대사·최신 확인(CT511·CT512)."""
    f = review_forecast(doc)
    if f is None:
        return ["검토안 없음"]
    run = doc["runs"][f["run_id"]]
    out = list(run["errors"])
    if f["state"] == "STALE":
        out.append(f"입력이 바뀌어 검토안이 낡았다 — {f.get('stale_reason')}")
    for d in DEPARTMENTS:
        c = f["confirmations"].get(d)
        if c is None or c["decision"] != "확인":
            out.append(f"{d} 담당 임원 가정 확인 누락")
        elif c["run_hash"] != run["run_hash"]:
            out.append(f"{d} 확인이 이전 산정본 기준이다")
    return out


def check_submit_forecast(doc: dict, args: dict[str, Any] | None = None) -> None:
    f = review_forecast(doc)
    if f is not None and f["state"] in ("SUBMITTED", "APPROVED"):
        raise DomainError(f"{f['forecast_id']}는 이미 {f['state']}다", 409)
    blocking = forecast_blocking(doc)
    if blocking:
        raise PrerequisiteError(
            "대표 승인 요청 불가: " + ", ".join(blocking), blocking, "FORECAST_INVALID"
        )


def submit_forecast(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    대표 승인 요청(EV51-46) — 경영관리 임원이 대사와 확인 버전을 검증해 제출한다. 아직 검토안이다.
    """
    check_submit_forecast(doc, args)
    _require(by, CFO, "전망 제출", strict=strict)
    f = review_forecast(doc)
    f.update(state="SUBMITTED", submitted_at=doc["clock"], submitted_by=by)  # type: ignore[union-attr]
    f["history"].append({"at": doc["clock"], "state": "SUBMITTED", "by": by})  # type: ignore[index]
    audit(
        doc,
        actor=by,
        action="forecast_submitted",
        forecast_id=f["forecast_id"],
        event_code="EV51-46",
    )  # type: ignore[index]
    return {"forecast_id": f["forecast_id"]}  # type: ignore[index]


def check_approve_forecast(doc: dict, args: dict[str, Any]) -> None:
    f = review_forecast(doc)
    if f is None or f["state"] != "SUBMITTED":
        raise DomainError("승인 요청된 검토안이 없다", 409)
    if args.get("decision") not in ("승인", "반려"):
        raise DomainError("승인 또는 반려를 고른다", 422)
    if args["decision"] == "반려" and not _text(args, "reason"):
        raise DomainError("반려에는 사유가 필요하다", 422)
    ref = _text(args, "run_hash")
    if ref and ref != f["run_hash"]:
        raise DomainError("본 산정본 해시가 제출본과 다르다 — 다시 본다", 409)


def approve_forecast(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    공식 Forecast 승인(EV51-47) — 대표이사만. 이 승인은 **공식 전망 갱신**이다 — 범위 안에서 확정된
    실행계획을 다시
    승인하는 절차가 아니다. 반려면 RETURNED이고 FC50이 공식본으로 남는다(Target 불변).
    """
    check_approve_forecast(doc, args)
    _require(by, CEO, "공식 전망 승인", strict=strict)
    f = review_forecast(doc)
    if args["decision"] == "반려":
        f.update(state="RETURNED", return_reason=_text(args, "reason"))  # type: ignore[union-attr]
        f["history"].append(
            {"at": doc["clock"], "state": "RETURNED", "by": by, "note": _text(args, "reason")}
        )  # type: ignore[index]
        audit(doc, actor=by, action="forecast_returned", forecast_id=f["forecast_id"])  # type: ignore[index]
        return {"state": "RETURNED"}
    approved_id = f["target_id"]  # type: ignore[index]
    f.update(
        state="APPROVED",
        approved_at=doc["clock"],
        approved_by=by,
        approved_id=approved_id,
        approval_ref="APR51",
    )  # type: ignore[union-attr]
    f["history"].append({"at": doc["clock"], "state": "APPROVED", "by": by})  # type: ignore[index]
    audit(
        doc,
        actor=by,
        action="forecast_approved",
        forecast_id=f["forecast_id"],
        approved_id=approved_id,  # type: ignore[index]
        event_code="EV51-47",
    )
    return {"state": "APPROVED", "approved_id": approved_id}


def check_publish(doc: dict, args: dict[str, Any]) -> None:
    f = review_forecast(doc)
    if f is None or f["state"] != "APPROVED":
        raise DomainError("승인된 검토안이 없다 — 승인 전에는 공식 포인터를 바꾸지 않는다", 409)
    if f["published_at"]:
        raise DomainError("이미 게시했다", 409)
    if not _text(args, "recipients"):
        raise DomainError("공유 대상을 적는다", 422)


def publish_forecast(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    공식본 게시·공유(EV51-48) — 승인본과 공식 포인터·내부 공유 기록을 **함께** 바꾼다. FC51-D와
    FC51은 같은 RUN의
    승인 전후 참조다(월손익을 더하지 않는다). 종전 공식본은 이력으로 남는다.
    """
    check_publish(doc, args)
    _require(by, FIN, "공식본 게시", strict=strict)
    f = review_forecast(doc)
    run = doc["runs"][f["run_id"]]  # type: ignore[index]
    official = {
        "forecast_id": f["approved_id"],  # type: ignore[index]
        "seq": _seq(doc["forecasts"]),
        "kind": "OFFICIAL",
        "run_id": run["run_id"],
        "run_hash": run["run_hash"],
        "review_ref": f["forecast_id"],  # type: ignore[index]
        "parent_official": doc["official"],
        "state": "PUBLISHED",
        "background": False,
        "cutoff": "2027-10-01",
        "months": run["months"],
        "annual": run["annual"],
        "approved_at": f["approved_at"],  # type: ignore[index]
        "approved_by": f["approved_by"],  # type: ignore[index]
        "approval_ref": "APR51",
        "published_at": doc["clock"],
        "published_by": by,
        "evidence": "DOC61",
    }
    doc["forecasts"][official["forecast_id"]] = official
    f.update(published_at=doc["clock"], state="PUBLISHED")  # type: ignore[union-attr]
    f["history"].append({"at": doc["clock"], "state": "PUBLISHED", "by": by})  # type: ignore[index]
    previous = doc["official"]
    doc["official"] = official["forecast_id"]
    doc["shares"].append(
        {
            "share_id": f"SH51-{len(doc['shares']) + 1:02d}",
            "object": official["forecast_id"],
            "recipients": _text(args, "recipients"),
            "at": doc["clock"],
            "by": by,
            "dedupe_key": f"publish:{official['forecast_id']}",
        }
    )
    audit(
        doc,
        actor=by,
        action="forecast_published",
        forecast_id=official["forecast_id"],
        replaces=previous,
        event_code="EV51-48",
    )
    return {"official": official["forecast_id"]}


# ─────────────────────────── S18 후속 관리·장면 인계 (U508 · CT513) ───────────────────────────

FOLLOWUP_COLUMNS = ("followup_id", "target", "owner", "due_at", "content")


def parse_followups(text: str) -> list[dict[str, Any]]:
    """
    후속 목록 — 「id | 대상 | 담당 | 기한 | 내용」. 담당·기한 빈칸은 누락으로 남긴다(완료가 막힌다,
    T531).
    """
    out = []
    for raw in (line for line in str(text or "").splitlines() if line.strip()):
        cells = [c.strip() for c in raw.split("|")]
        if len(cells) != len(FOLLOWUP_COLUMNS):
            raise DomainError("후속 줄은 「id | 대상 | 담당 | 기한 | 내용」이다", 400)
        row = dict(zip(FOLLOWUP_COLUMNS, cells, strict=True))
        owner = _user(row["owner"]) if row["owner"] else None
        if row["owner"] and owner is None:
            raise DomainError(f"{row['followup_id']}: 모르는 담당 — {row['owner']}", 422)
        out.append(
            {
                **row,
                "owner": owner,
                "due_at": _when(row["due_at"], f"{row['followup_id']} 기한")
                if row["due_at"]
                else None,
                "content": row["content"] or None,
            }
        )
    return out


def completion_conditions(
    doc: dict, followups: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """
    종료 요건(CT513) — 확정 계획·경영관리 확인, 범위 내 변경 근거, CON41·SUP41, 품의, 착수, 초기
    결과, 운영계획,
    **게시된 공식 전망**, 후속 책임·기한. Risk OPEN·과제 운영 중은 차단이 아니다 — 끝내도 그대로다.
    """
    plan = effective_plan(doc)
    official = doc["forecasts"].get(doc["official"] or "") or {}
    fups = followups if followups is not None else doc["followups"]
    needed = {"FUP51", "FUP52", "FUP53", "DIR41", RISK_ID}
    given = {f["followup_id"] for f in fups}
    items = [
        (
            "plan",
            "확정 계획 · 경영관리 확인",
            plan is not None and plan["management_check"] == "VERIFIED",
        ),
        (
            "change",
            "범위 내 변경 근거(전후·사유·확인) 또는 변경 없음 기록",
            (plan is not None and plan.get("parent") is not None)
            or any(a["action"] == "plan_change_none" for a in doc["audit"]),
        ),
        ("CON41", "CON41 충족 확인", doc["conditions"]["CON41"]["state"] == "SATISFIED"),
        ("SUP41", "SUP41 이행 확인", doc["conditions"]["SUP41"]["state"] == "VERIFIED"),
        (
            "requests",
            "REQ51·OP51 승인",
            all((doc["requests"].get(r) or {}).get("state") == "APPROVED" for r in REQUESTS),
        ),
        ("start", "START51 운영 착수", doc["start"] is not None),
        ("observation", "9월 초기 결과 확인", doc["observation"] is not None),
        (
            "opl",
            "OPL51~53 확정·확인",
            all(
                (doc["operating_plans"].get(p) or {}).get("state") == "VERIFIED"
                for p in OPERATING_PLANS
            ),
        ),
        ("forecast", "공식 전망 게시(FC51)", official.get("state") == "PUBLISHED"),
        (
            "followups",
            "후속 책임·기한(FUP51~53·DIR41·RISK51)",
            needed <= given and all(f["owner"] and f["due_at"] for f in fups),
        ),
    ]
    blocking = [label for _k, label, ok in items if not ok]
    blocking += [
        f"{f['followup_id']} 담당·기한 누락" for f in fups if not (f["owner"] and f["due_at"])
    ]
    blocking += [f"{x} 후속 항목 없음" for x in sorted(needed - given)]
    return {
        "items": [{"id": k, "label": label, "ok": ok} for k, label, ok in items],
        "met": all(ok for _k, _l, ok in items),
        "blocking": list(dict.fromkeys(blocking)),
    }


def check_complete(doc: dict, args: dict[str, Any] | None = None) -> None:
    if doc["handoff"] is not None:
        raise DomainError("이미 완료된 업무다 — 완료본은 바꾸지 않는다", 409)
    fups = (
        parse_followups(_text(args or {}, "followups")) if args and args.get("followups") else None
    )
    check = completion_conditions(doc, fups if fups is not None else [])
    if not check["met"]:
        raise PrerequisiteError(
            "종료 요건 미충족: " + ", ".join(check["blocking"]),
            check["blocking"],
            "COMPLETION_BLOCKED",
        )


def complete_scene(
    doc: dict, args: dict[str, Any], *, by: str, strict: bool = True
) -> dict[str, Any]:
    """
    장면 5 완료(EV51-49) — 요건을 서버가 다시 보고 HANDOFF51과 SC05_COMPLETED를 **함께** 저장한다.
    ACT42는 운영
    추적 중이고 Risk는 OPEN, Target은 그대로다. 장면 6의 범위를 여기서 정의하지 않는다.
    """
    check_complete(doc, args)
    _require(by, CFO, "업무 인계", strict=strict)
    fups = parse_followups(_text(args, "followups"))
    for f in fups:
        f.update(
            state="FOLLOWUP_REQUIRED" if f["followup_id"] == "DIR41" else "OPEN",
            confirmed_at=doc["clock"],
        )
    doc["followups"] = fups
    official = doc["forecasts"][doc["official"]]
    run = doc["runs"][official["run_id"]]
    plan = effective_plan(doc)
    doc["handoff"] = {
        "handoff_id": HANDOFF_ID,
        "review_id": REVIEW_ID,
        "source_handoff": SOURCE_HANDOFF,
        "approval": doc["sc04"]["approval"]["approval_id"],
        "decision": doc["sc04"]["handoff"]["decision"],
        "execution": {
            "actions": list(calc.TASKS),
            "latest_plan": plan["plan_id"],  # type: ignore[index]
            "management_check": plan["management_check"],  # type: ignore[index]
            "conditions": {c: doc["conditions"][c]["state"] for c in ("CON41", "SUP41")},
            "requests": {r: doc["requests"][r]["state"] for r in REQUESTS},
            "start": START_ID,
        },
        "results": {
            "observation": doc["observation"]["observation_id"],
            "close_batch": run["close_batch"],
            "operating_plans": {p: doc["operating_plans"][p]["version"] for p in OPERATING_PLANS},
            "run": run["run_id"],
        },
        "forecast": {
            "parent": official["parent_official"],
            "official": official["forecast_id"],
            "approved_at": official["approved_at"],
            "published_at": official["published_at"],
            "run_hash": official["run_hash"],
        },
        "financial_snapshot": {
            "target": run["target"],
            "forecast": run["annual"],
            "gap": run["gap"],
            "effect": run["periods"]["year"]["effect"],
            "effect_closed": run["periods"]["closed"]["effect"],
            "effect_remaining": run["periods"]["forecast"]["effect"],
        },
        "followups": fups,
        "operation": {t: doc["operation"][t]["state"] for t in calc.TASKS},
        "state_snapshot": {
            "scene": "SC05_COMPLETED",
            "forecast": "PUBLISHED",
            "target": "UNCHANGED",
            "risk": "OPEN",
        },
        "completed_by": by,
        "completed_at": doc["clock"],
        "memo": _text(args, "memo"),
    }
    doc["scene"]["completed_at"] = doc["clock"]
    audit(doc, actor=by, action="SC05_COMPLETED", handoff=HANDOFF_ID, event_code="EV51-49")
    return {"handoff_id": HANDOFF_ID}


# ─────────────────────────── Agent (구현명세 16장) ───────────────────────────


def agent_draft(doc: dict, *, kind: str) -> str:
    """
    AG51~AG58 초안 하나 — 같은 입력이면 이전 성공 초안을 다시 쓴다. 실패해도 업무는 계속된다(수동
    작성, T530).
    초안에는 agent_run·source_hash·prompt_version·generated_at·status가 있다. 승인 권한이 없다.
    """
    if kind not in agent.KINDS:
        raise DomainError(f"모르는 Agent 지원: {kind}", 422)
    record: dict[str, Any] = {
        "output_id": f"{kind}-{len(doc['agent_outputs']) + 1:03d}",
        "seq": _seq(doc["agent_outputs"]),
        "kind": kind,
        "prompt_version": agent.PROMPT_VERSION,
        "model_version": "mock-1",
        "mode": "REPLAY" if doc.get("agent_mode", "mock") == "mock" else "LIVE",
        "created_at": doc["clock"],
        "status": "FAILED",
        "draft": None,
        "errors": [],
        "source_hash": None,
        "review_status": "UNREVIEWED",
        "reviewed_by": None,
        "reviewed_at": None,
    }
    try:
        payload = agent.build_input(doc, kind)
    except agent.AgentFailure as exc:
        record["errors"].append(str(exc))
        payload = None
    if payload is not None:
        digest = agent.input_hash(payload)
        record["source_hash"] = digest
        for o in ordered(doc["agent_outputs"]):
            if o["kind"] == kind and o["source_hash"] == digest and o["status"] == "SUCCEEDED":
                return o["output_id"]
        try:
            out = agent.run(payload, doc.get("agent_mode", "mock"))
            problems = agent.validate(out, payload)
            if problems:
                record["errors"].append("검증 실패: " + "; ".join(problems))
            else:
                record.update(status="SUCCEEDED", draft=out)
        except agent.AgentFailure as exc:
            record["errors"].append(str(exc))
    doc["agent_outputs"][record["output_id"]] = record
    audit(
        doc,
        actor="system",
        action="agent_draft",
        output_id=record["output_id"],
        status=record["status"],
    )
    return record["output_id"]


def review_agent(doc: dict, output_id: str, *, actor: str, note: str = "") -> None:
    """제안 검토 기록(REVIEWED) — 원 초안은 그대로. 업무 확인·승인을 대신하지 않는다."""
    o = doc["agent_outputs"].get(output_id)
    if o is None or o["status"] != "SUCCEEDED":
        raise DomainError("검토할 초안이 없다", 404)
    if actor not in USERS or actor == "u-demo":
        raise DomainError("업무 역할이 검토한다", 403)
    if o["review_status"] == "UNREVIEWED":
        o["review_status"] = "REVIEWED"
    o.update(reviewed_by=actor, reviewed_at=doc["clock"], review_note=note)
    audit(doc, actor=actor, action="agent_reviewed", output_id=output_id)


# ─────────────────────────── 작업 → 업무 효과 (기록 작업의 몸통) ───────────────────────────

RECORDS = (
    "draft_plan",
    "coordinate_plan",
    "confirm_plan",
    "verify_plan",
    "request_change",
    "condition_evidence",
    "condition_coordinate",
    "condition_confirm",
    "submit_request",
    "approve_request",
    "start_operation",
    "receive_change",
    "share_change",
    "ack_change",
    "respond_change",
    "approve_urgent",
    "execute_order",
    "confirm_observation",
    "confirm_opl",
    "verify_opl",
    "draft_forecast",
    "confirm_forecast",
    "submit_forecast",
    "approve_forecast",
    "publish_forecast",
    "complete_scene",
)

_CHECKS = {
    "draft_plan": check_draft_plan,
    "coordinate_plan": check_coordinate,
    "confirm_plan": check_confirm_plan,
    "verify_plan": check_verify_plan,
    "request_change": check_request_change,
    "condition_evidence": check_condition_evidence,
    "condition_coordinate": check_condition_coordinate,
    "condition_confirm": check_condition_confirm,
    "submit_request": check_submit_request,
    "approve_request": check_approve_request,
    "start_operation": check_start,
    "receive_change": check_receive,
    "share_change": check_share,
    "ack_change": check_ack,
    "respond_change": check_respond,
    "approve_urgent": check_approve_urgent,
    "execute_order": check_execute,
    "confirm_observation": check_confirm_observation,
    "confirm_opl": check_confirm_opl,
    "verify_opl": check_verify_opl,
    "draft_forecast": check_draft_forecast,
    "confirm_forecast": check_confirm_forecast,
    "submit_forecast": check_submit_forecast,
    "approve_forecast": check_approve_forecast,
    "publish_forecast": check_publish,
    "complete_scene": check_complete,
}


def check(doc: dict, operation: str, args: dict[str, Any]) -> None:
    """
    기록 작업의 사전 검사 — **부수 효과가 없다**. 화면 답(내장·대리 답)은 답을 넣기 전에, 기록
    작업은 적기 전에
    같은 검사를 한다(Studio·Center 콘솔 답은 NowView 사전 검사를 거치지 않는다).
    """
    fn = _CHECKS.get(operation)
    if fn is None:
        raise DomainError(f"모르는 작업: {operation}", 404)
    fn(doc, args)


def apply(
    doc: dict, seed: Seed, operation: str, args: dict[str, Any], *, by: str, strict: bool
) -> dict[str, Any]:
    """
    기록 작업 하나의 업무 효과. 검사는 `check`가 먼저 했다. 출력은 그림의 `output` 대응이 쓴다.
    """
    simple = {
        "draft_plan": draft_plan,
        "coordinate_plan": coordinate_plan,
        "confirm_plan": confirm_plan,
        "verify_plan": verify_plan,
        "request_change": request_change,
        "condition_evidence": condition_evidence,
        "condition_coordinate": condition_coordinate,
        "condition_confirm": condition_confirm,
        "submit_request": submit_request,
        "approve_request": approve_request,
        "start_operation": start_operation,
        "share_change": share_change,
        "ack_change": ack_change,
        "respond_change": respond_change,
        "approve_urgent": approve_urgent,
        "execute_order": execute_order,
        "confirm_observation": confirm_observation,
        "confirm_opl": confirm_opl,
        "verify_opl": verify_opl,
        "confirm_forecast": confirm_forecast,
        "submit_forecast": submit_forecast,
        "approve_forecast": approve_forecast,
        "publish_forecast": publish_forecast,
        "complete_scene": complete_scene,
    }
    if operation in simple:
        return simple[operation](doc, args, by=by, strict=strict)
    if operation == "receive_change":
        return receive_change(doc, seed, args, by=by, strict=strict)
    if operation == "draft_forecast":
        return draft_forecast(doc, seed, args, by=by, strict=strict)
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
    return user_for_role(NODE_ROLES[node_id]["role"])


def _open_change(doc: dict) -> dict | None:
    live = [c for c in ordered(doc["changes"]) if not c["background"] and c["state"] != "EXECUTED"]
    return live[-1] if live else None


def _due(doc: dict, node_id: str) -> str:
    due = NODE_ROLES[node_id]["due"]
    if due in ("share", "ack"):
        c = _open_change(doc)
        start = None if c is None else (c["received_at"] if due == "share" else c["shared_at"])
        if start is not None:
            return (parse_at(start) + timedelta(minutes=60 if due == "share" else 120)).isoformat()
        return due_at(parse_at(doc["clock"]), 1).isoformat()
    if isinstance(due, str):
        target = SCHEDULE[due]
        if parse_at(target) > parse_at(doc["clock"]):
            return target
        return due_at(parse_at(doc["clock"]), 1).isoformat()
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
            task["request_id"] = request_id
            continue
        _open_task(doc, p["node_id"], request_id=request_id)


def ensure_task(doc: dict, node_id: str) -> None:
    """
    결정이 기록되는데 업무가 없으면 지금 연다 — 늦게 열었다고 표시한다(Studio, 장면 1~4와 같다).
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
    """역할 검사 — 역할표의 사람, 구매 확인은 지정 대행자도(403)."""
    user = USERS.get(actor)
    if user is None:
        raise DomainError(f"모르는 사용자: {actor}", 403)
    spec = NODE_ROLES[node_id]
    if actor in DELEGATES.get(node_id, ()):
        return
    if user["role"] != spec["role"]:
        raise DomainError(f"{spec['role']}만 할 수 있다 (현재 {user['role']})", 403)


def is_overdue(due: str | None, clock: str) -> bool:
    return due is not None and parse_at(clock) > parse_at(due)


def raise_overdue_alerts(doc: dict) -> list[dict]:
    """기한 초과 알림 — 미완료 업무. 같은 대상·기한에 한 번만. 내부 알림이다(메일 없음)."""
    alerts = doc["alerts"]
    seen = {(a["target"], a["due_at"]) for a in alerts}
    created = []
    for t in ordered(doc["tasks"]):
        if t["status"] == "COMPLETED" or not is_overdue(t["due_at"], doc["clock"]):
            continue
        if (t["task_id"], t["due_at"]) in seen:
            continue
        alert = {
            "alert_id": f"ALERT-{len(alerts) + 1:03d}",
            "kind": "OVERDUE",
            "target": t["task_id"],
            "due_at": t["due_at"],
            "at": doc["clock"],
            "to": [u for u in dict.fromkeys([t["assigned_to"], REVIEWER.get(t["type"], FIN)]) if u],
            "message": f"업무 미완료 — 기한 {t['due_at'][5:16].replace('T', ' ')} 초과",
        }
        alerts.append(alert)
        created.append(alert)
        audit(doc, actor="system", action="overdue_alert", target=t["task_id"], to=alert["to"])
    return created


# ─────────────────────────── 상태 (구현명세 10장) ───────────────────────────


def operation_state(doc: dict, task: str) -> str:
    """
    ACT42 운영 — START_ALLOWED는 계산 상태다(저장하지 않는다). 착수 명령 전에는 OPERATING이 아니다.
    """
    state = doc["operation"][task]["state"]
    if task == TASK_ID and state == "WAIT" and start_requirements(doc)["start_allowed"]:
        return "START_ALLOWED"
    return state


def statuses(doc: dict) -> dict[str, Any]:
    """
    독립 배지 — 장면 · 계획 · 경영관리 확인 · CON41 · SUP41 · ACT42 운영 · 공식 전망 · Risk ·
    Target. 상위(장면)
    상태는 증거에서 산출한다 — 하위 상태를 일괄 바꾸지 않는다.
    """
    s = doc["scene"]
    plan = effective_plan(doc) or current_plan(doc)
    official = doc["forecasts"].get(doc["official"] or "")
    if doc["handoff"] is not None:
        scene = "SC05_COMPLETED"
    elif (
        official is not None
        and official["kind"] == "OFFICIAL"
        and official.get("state") == "PUBLISHED"
    ):
        scene = "FORECAST_PUBLISHED"
    elif doc["observation"] is not None:
        scene = "ROLLING_REVIEW"
    elif doc["start"] is not None:
        scene = "OPERATING"
    elif effective_plan(doc) is not None:
        scene = "PREPARING"
    elif s["started_at"] is not None:
        scene = "PLAN_PENDING"
    else:
        scene = "PENDING"
    review = review_forecast(doc)
    return {
        "scene": scene,
        "plan": None if plan is None else plan["state"],
        "planVersion": None if plan is None else plan["plan_id"],
        "managementCheck": None if plan is None else plan["management_check"],
        "con41": doc["conditions"]["CON41"]["state"],
        "sup41": doc["conditions"]["SUP41"]["state"],
        "operation": operation_state(doc, TASK_ID),
        "official": doc["official"],
        "review": None if review is None else review["state"],
        "risk": s["risk"],
        "target": s["target"],
    }


#: Studio는 끝을 작업 호출로만 안다 — 이 작업이 기록되면 흐름이 끝난다.
def ends_flow(operation: str) -> bool:
    return operation == "complete_scene"


__all__ = ["CASES", "NODE_ROLES", "RECORDS", "SEED_ID", "apply", "catch_up", "check", "kst"]
