"""
SC06 확인 절차 — 담당 임원 확인 → 경영관리 종합 확인 → 보고 결론 → 보고본 확정 → 대표
보고(업무설계표 SC06-S11~S13)를 BPM(`processes/sc06.bpmn`)의 결재로 받는다. 결재 뒤의 기록 작업(외부
확장 `nowview-sc06`)이 이 모듈의 `check` → `apply`를 부른다 — 내장·Studio·Center 어디서 닫았든 같은
길이다(장면 1~5 N1).

* **적재는 그대로다.** 기준·실적·거래·판단·후속·근거·Agent는 적재 때 들어오고 숫자는 그때 규칙
  계산이 만든다(`domain.new_review`). 이 절차는 숫자를 만들지 않는다 — 그 숫자를 사람이 확인하고
  보고본에 묶는다.
* **데이터의 확인 기록(SC06보고)은 일정이자 기대값이다**(`doc["schedule"]`). 기록 시각은 그 일정이다
  — 가상시계가 일정보다 앞이면 일정으로 옮긴다(시각 이동은 확인을 만들지 않는다 — 확인은 결재만
  만든다). 각본은 일정의 글을 답으로 넣고, 끝난 문서가 SC06보고 시트와 같아야 한다(시험).
* **확정은 막힐 수 있다**(CT611) — 확인 세 단계가 같은 보고 버전이고, 결론 문장의 「…백만원」이 묶일
  산정의 숫자와 같아야 한다. 아니면 422 REPORT_INVALID와 남은 항목이다(기록 거절 → 같은 결재).
  확정이 지금 산정을 보고본에 묶는다.
* **재확인·보완은 이력을 지우지 않는다.** 종합 확인의 재확인 요청은 두 담당 임원 확인을, 확정의 보완
  요청은 결론을 `record_history`로 옮기고 다시 받는다.
* 보고 확정·대표 보고는 과제 실행·예산 승인이 아니다 — RISK61 OPEN · PROP61 PROPOSED · FC51·Target
  그대로다(CT612).
"""

from __future__ import annotations

import re
from typing import Any

from app.sc01.domain import USERS, DomainError, parse_at, user_id_of
from app.sc06 import domain
from app.sc06.domain import ACCOUNTS, FOCUS_TASK, REVIEW_ID

#: 결재 → 담당·남길 기록. 결재 담당은 사람 하나다(`chk:approval.assignees`와 같다 — 시험이 맞춰
#: 본다).
NODE_ROLES: dict[str, dict[str, str]] = {
    "Confirm_Prod": {"user": "u-prod-exec", "record": "CF61-P", "task": "CONFIRM_PROD"},
    "Confirm_Buy": {"user": "u-buy-exec", "record": "CF61-B", "task": "CONFIRM_BUY"},
    "Review_Finance": {"user": "u-fin-exec", "record": "CF61-F", "task": "REVIEW_FINANCE"},
    "Draft_Conclusion": {"user": "u-fin", "record": "TXT61", "task": "DRAFT_CONCLUSION"},
    "Finalize_Report": {"user": "u-fin-exec", "record": "CF61-R", "task": "FINALIZE_REPORT"},
    "Report_CEO": {"user": "u-ceo", "record": "CF61-M", "task": "REPORT_CEO"},
}
for _spec in NODE_ROLES.values():
    _spec["role"] = USERS[_spec["user"]]["role"]

RECORDS = ("confirm_owner", "review_finance", "draft_conclusion", "finalize_report", "report_ceo")
#: 담당 임원 확인 — 결재마다 그 기록 하나
OWNER_RECORDS = {"Confirm_Prod": "CF61-P", "Confirm_Buy": "CF61-B"}
#: 확인 착수 시각 — 데이터에 착수 행이 없다(구현용 보완). 후속 등록(1/10)과 첫 확인(1/11 14:00)
#: 사이다.
START_AT = "2028-01-11T09:00:00+09:00"
#: 확인을 착수하는 사람 — 검토건을 꾸린 경영관리 담당
STARTER = "u-fin"

_ACCOUNT_OF = {uid: account for account, uid in ACCOUNTS.items()}


class PrerequisiteError(DomainError):
    """필수 조건 미충족 — 남은 항목을 함께 낸다(장면 3~5의 `blocking_items`와 같다)."""

    def __init__(self, message: str, items: list[str], code: str) -> None:
        super().__init__(message, 422)
        self.items = items
        self.code = code


# ─────────────────────────── 문서 ───────────────────────────


def pending_state(doc: dict, *, executor: str) -> None:
    """
    적재된 검토 문서를 **확인 전**으로 둔다 — 데이터의 확인 기록은 일정(`schedule`)으로 옮기고
    보고본은 DRAFT다. 바깥 실행이면 그 자리를 만든다(첫 작업 호출이 묶는다).
    """
    from app.sc01.domain import external_bpm

    doc["schedule"] = doc.pop("report_records")
    doc["report_records"] = {}
    doc["record_history"] = []
    doc["report"].update(state="DRAFT", finalized_at=None, problems=[])
    doc["clock"] = START_AT
    doc["step"] = "D600"
    doc["scene_info"] = {"started_at": None, "started_by": None}
    doc["tasks"] = {}
    doc["bpm"] = None if executor == "embedded" else external_bpm(executor)


def is_bpm(doc: dict) -> bool:
    """확인 절차를 BPM으로 도는 문서인가 — 확인 기록을 끝난 것으로 적재한 예전 문서는 아니다."""
    return "schedule" in doc


def start(doc: dict, *, by: str) -> bool:
    """
    확인 착수 — 경영관리 담당. **재착수는 기존 결과를 돌려준다**(같은 검토건에 두 번째 절차를 만들지
    않는다).
    """
    if by not in (STARTER, "u-demo"):
        holder = USERS[STARTER]
        raise DomainError(f"확인 착수는 {holder['role']}({holder['name']})가 한다", 403)
    if doc["scene_info"]["started_at"] is not None:
        return False
    doc["scene_info"].update(started_at=doc["clock"], started_by=by)
    domain.audit(doc, actor=by, action="confirmation_started", review_id=REVIEW_ID)
    return True


def open_review(doc: dict) -> dict[str, Any]:
    """BPM 첫 작업 — 착수된 검토건인지 본다. 바깥 실행은 착수 뒤에 Studio·Center에서 시작한다."""
    if not is_bpm(doc):
        raise DomainError(
            "이 검토건은 확인 기록을 끝난 것으로 적재했다 — 확인 절차를 돌지 않는다", 409
        )
    if doc["scene_info"]["started_at"] is None:
        raise DomainError("아직 확인을 착수하지 않았다 — 화면에서 착수를 먼저 누른다", 409)
    return {
        "review_id": REVIEW_ID,
        "report_version": doc["report"]["report_version"],
        "calculation_version": doc["current_calculation"],
    }


# ─────────────────────────── 검사 (부수 효과 없음) ───────────────────────────


def _text(args: dict[str, Any], key: str) -> str:
    return str(args.get(key) or "").strip()


def _done(doc: dict, record_id: str) -> bool:
    r = doc["report_records"].get(record_id)
    return r is not None and r["version"] == doc["report"]["report_version"]


def finalize_blocking(doc: dict) -> list[str]:
    """
    확정 전 남은 항목(CT611) — 담당 임원 두 확인 · 종합 확인 · 결론, 그리고 결론 숫자가 지금 산정과
    같은가. LLM·사람이 쓴 문장의 숫자를 집계 원천으로 쓰지 않고, 거꾸로 산정과 대조한다.
    """
    items = [
        f"{label}이 없다"
        for record_id, label in (
            ("CF61-P", "생산 임원 성과 근거 확인"),
            ("CF61-B", "구매 임원 성과 근거 확인"),
            ("CF61-F", "경영관리 종합 확인"),
            ("TXT61", "보고 결론"),
        )
        if not _done(doc, record_id)
    ]
    current = doc["calculations"][doc["current_calculation"]]
    if current["totals"]["calculation_status"] != "CONFIRMED":
        items.append("산정 보류인 과제가 있다 — 확인된 합계로 보고본을 확정할 수 없다")
    text = (doc["report_records"].get("TXT61") or {}).get("content") or ""
    said = {round(float(v) * 1_000_000) for v in domain._MILLION.findall(text)}
    tasks = {t["task_id"]: t for t in current["tasks"]}
    wanted = {
        current["totals"]["expected_krw"],
        current["totals"]["actual_krw"],
        tasks[FOCUS_TASK]["expected_krw"],
        tasks[FOCUS_TASK]["actual_krw"],
    }
    if text and not said <= wanted:
        odd = ", ".join(f"{v / 1_000_000:.1f}" for v in sorted(said - wanted))
        items.append(
            f"보고 결론의 숫자가 산정 {current['calculation_version']}과 다르다(백만원: {odd})"
        )
    return items


def check(doc: dict, operation: str, args: dict[str, Any]) -> None:
    """기록 작업과 화면 답의 사전 검사가 같이 쓴다 — 409(순서·상태) · 422(입력·요건)."""
    if not is_bpm(doc) or doc["scene_info"]["started_at"] is None:
        raise DomainError("아직 확인을 착수하지 않았다", 409)
    if doc["report"]["state"] == "REPORTED":
        raise DomainError(
            "이미 대표 보고까지 끝난 보고본이다 — 새 보고 버전에서 다시 확인한다", 409
        )
    node = str(args.get("node_id") or "")
    if operation == "confirm_owner":
        if OWNER_RECORDS.get(node) != args.get("record_id"):
            raise DomainError(f"{node}의 기록은 {OWNER_RECORDS.get(node)}이다", 422)
        if not _text(args, "content") or not _text(args, "refs"):
            raise DomainError("확인 내용과 근거 ID를 적는다", 422)
        return
    if operation == "review_finance":
        if not (_done(doc, "CF61-P") and _done(doc, "CF61-B")):
            raise DomainError("두 담당 임원 확인이 끝나야 종합 확인을 한다", 409)
        if args.get("decision") not in ("확인", "재확인요청"):
            raise DomainError("종합 확인은 확인·재확인요청 중 하나다", 422)
        if not _text(args, "content"):
            raise DomainError("확인 내용(재확인 요청이면 사유)을 적는다", 422)
        return
    if operation == "draft_conclusion":
        if not _done(doc, "CF61-F"):
            raise DomainError("경영관리 종합 확인 뒤에 보고 결론을 쓴다", 409)
        if not _text(args, "content"):
            raise DomainError("보고 결론을 적는다", 422)
        return
    if operation == "finalize_report":
        if args.get("decision") not in ("확정", "보완요청"):
            raise DomainError("확정은 확정·보완요청 중 하나다", 422)
        if not _text(args, "content"):
            raise DomainError("확정 내용(보완 요청이면 사유)을 적는다", 422)
        if args.get("decision") == "보완요청":
            if not _done(doc, "TXT61"):
                raise DomainError("보완할 보고 결론이 없다", 409)
            return
        if not _text(args, "note"):
            raise DomainError("남는 사항(보완 기한·다음 보고·미산정)을 적는다", 422)
        items = finalize_blocking(doc)
        if items:
            raise PrerequisiteError("보고본을 확정할 수 없다", items, "REPORT_INVALID")
        return
    if operation == "report_ceo":
        if doc["report"]["state"] != "FINALIZED":
            raise DomainError("확정된 보고본만 대표에게 보고한다", 409)
        if not _text(args, "content"):
            raise DomainError("보고 내용을 적는다", 422)
        return
    raise DomainError(f"모르는 작업: {operation}", 404)


def check_actor(node_id: str, actor: str) -> None:
    """역할 검사 — 그 결재의 담당만(403). 화면의 역할 선택은 신뢰 경계가 아니다(5.4)."""
    spec = NODE_ROLES[node_id]
    if actor != spec["user"]:
        holder = USERS[spec["user"]]
        raise DomainError(f"{holder['role']}({holder['name']})만 한다", 403)


# ─────────────────────────── 효과 ───────────────────────────


def _at(doc: dict, record_id: str) -> str:
    """기록 시각 = 일정. 가상시계가 일정보다 앞이면 일정으로 옮긴다(뒤로 가지 않는다)."""
    planned = doc["schedule"].get(record_id, {}).get("at")
    if planned and parse_at(planned) > parse_at(doc["clock"]):
        doc["clock"] = parse_at(planned).isoformat()
    return doc["clock"]


def _record(doc: dict, record_id: str, *, by: str, state: str, content: str, refs: Any) -> dict:
    plan = doc["schedule"].get(record_id, {})
    old = doc["report_records"].get(record_id)
    if old is not None:
        doc["record_history"].append(old)
    text = content.strip()
    record = {
        "record_id": record_id,
        "seq": plan.get("seq", len(doc["schedule"])),
        "version": doc["report"]["report_version"],
        "step": plan.get("step", record_id),
        # 데이터 계정으로 적는다(화면이 `who`로 이름을 낸다). 마스터 밖의 이름(콘솔 관리자)은 그대로
        "actor": _ACCOUNT_OF.get(by, by),
        "at": _at(doc, record_id),
        "state": state,
        "content": text,
        "refs": domain._ids(refs) if not isinstance(refs, list) else refs,
        "tasks": sorted(set(re.findall(r"ACT4\d", text.replace("ACT42·43", "ACT42 ACT43")))),
    }
    doc["report_records"][record_id] = record
    return record


def _retire(doc: dict, *record_ids: str, reason: str) -> None:
    for rid in record_ids:
        old = doc["report_records"].pop(rid, None)
        if old is not None:
            doc["record_history"].append({**old, "retired": reason, "retired_at": doc["clock"]})


def apply(doc: dict, operation: str, args: dict[str, Any], *, by: str) -> dict[str, Any]:
    """기록 작업의 몸통 — `check`를 통과한 뒤 부른다."""
    report = doc["report"]
    if operation == "confirm_owner":
        rec = _record(
            doc, args["record_id"], by=by, state="CONFIRMED", content=args["content"],
            refs=args["refs"],
        )  # fmt: skip
        domain.audit(doc, actor=by, action="owner_confirmed", record_id=rec["record_id"])
        return {}
    if operation == "review_finance":
        if args["decision"] == "재확인요청":
            _at(doc, "CF61-F")
            doc["record_history"].append(
                {
                    "record_id": "CF61-F",
                    "version": report["report_version"],
                    "actor": _ACCOUNT_OF.get(by, by),
                    "at": doc["clock"],
                    "state": "RECONFIRM_REQUESTED",
                    "content": _text(args, "content"),
                }
            )
            _retire(doc, "CF61-P", "CF61-B", reason="종합 확인 재확인 요청")
            domain.audit(doc, actor=by, action="reconfirm_requested", reason=_text(args, "content"))
            return {}
        _record(
            doc, "CF61-F", by=by, state="CONFIRMED", content=args["content"],
            refs=args.get("refs") or "",
        )  # fmt: skip
        domain.audit(doc, actor=by, action="finance_confirmed")
        return {}
    if operation == "draft_conclusion":
        _record(
            doc, "TXT61", by=by, state="DRAFT", content=args["content"],
            refs=args.get("refs") or "",
        )  # fmt: skip
        domain.audit(doc, actor=by, action="conclusion_drafted")
        return {}
    if operation == "finalize_report":
        if args["decision"] == "보완요청":
            _retire(doc, "TXT61", reason=f"확정 보완 요청 — {_text(args, 'content')}")
            domain.audit(doc, actor=by, action="report_rework", reason=_text(args, "content"))
            return {"state": report["state"]}
        rec = _record(
            doc, "CF61-R", by=by, state="FINALIZED", content=args["content"],
            refs="CF61-P;CF61-B;CF61-F",
        )  # fmt: skip
        doc["report_records"]["TXT61"]["state"] = "FINALIZED"
        _record(
            doc, "NOTE61", by=by, state="OPEN", content=args["note"],
            refs=doc["schedule"].get("NOTE61", {}).get("refs", []),
        )  # fmt: skip
        # 확정이 지금 산정을 보고본에 묶는다 — 그 뒤의 재적재는 새 산정 버전이고 이 보고본 숫자는
        # 그대로다
        current = doc["calculations"][doc["current_calculation"]]
        report.update(
            state="FINALIZED",
            finalized_at=rec["at"],
            calculation_version=current["calculation_version"],
            calculation_hash=current["calculation_hash"],
        )
        domain.audit(
            doc, actor=by, action="report_finalized", calculation=current["calculation_version"]
        )
        return {"state": "FINALIZED"}
    if operation == "report_ceo":
        content = _text(args, "content")
        directive = _text(args, "directive")
        _record(
            doc, "CF61-M", by=by, state="REPORTED",
            content=content + (f" — 대표 지시: {directive}" if directive else ""), refs="CF61-R",
        )  # fmt: skip
        report["state"] = "REPORTED"
        bound = doc["calculations"][report["calculation_version"]]
        report["problems"] = domain.report_problems(report, bound, doc["report_records"])
        # 보고 완료 후 조회 시점(데이터의 as_of) — 시연은 여기서 두 화면을 본다
        as_of = doc["settings"]["as_of"]
        if parse_at(as_of) > parse_at(doc["clock"]):
            doc["clock"] = as_of
        domain.audit(doc, actor=by, action="report_reported", directive=directive or None)
        return {"state": "REPORTED"}
    raise DomainError(f"모르는 작업: {operation}", 404)


#: Studio는 끝을 작업 호출로만 안다 — 대표 보고가 기록되면 흐름이 끝난다.
def ends_flow(operation: str) -> bool:
    return operation == "report_ceo"


# ─────────────────────────── 업무 ───────────────────────────


def _open_task(doc: dict, node_id: str, *, request_id: str | None, late: bool) -> dict:
    spec = NODE_ROLES[node_id]
    previous = [t for t in doc["tasks"].values() if t["type"] == spec["task"]]
    task_id = f"TASK-{spec['task']}" + (f"-{len(previous) + 1}" if previous else "")
    due = doc["schedule"].get(spec["record"], {}).get("at")
    if due is None or parse_at(due) < parse_at(doc["clock"]):
        due = None
    task = doc["tasks"][task_id] = {
        "task_id": task_id,
        "seq": len(doc["tasks"]),
        "type": spec["task"],
        "node_id": node_id,
        "request_id": request_id,
        "assigned_to": spec["user"],
        "assigned_at": doc["clock"],
        # 기한 = 데이터 일정의 그 기록 시각(지났으면 없음 — 지어내지 않는다)
        "due_at": due,
        "status": "ASSIGNED",
        "completed_at": None,
        "completed_by": None,
        "reopens": previous[-1]["task_id"] if previous else None,
        "opened_late": late,
    }
    domain.audit(doc, actor="system", action="task_assigned", task_id=task_id)
    return task


def task_for_node(doc: dict, node_id: str) -> dict | None:
    spec = NODE_ROLES.get(node_id)
    if spec is None:
        return None
    live = [
        t for t in doc["tasks"].values() if t["type"] == spec["task"] and t["status"] != "COMPLETED"
    ]
    return max(live, key=lambda t: t["seq"]) if live else None


def sync_tasks(doc: dict, pendings: dict[str, dict[str, Any]]) -> None:
    """BPM의 사람 대기 → 업무. 같은 대기면 새로 만들지 않는다. 끝난 업무는 다시 쓰지 않는다."""
    order = list(NODE_ROLES)
    for request_id, p in sorted(
        pendings.items(),
        key=lambda kv: order.index(kv[1]["node_id"]) if kv[1]["node_id"] in order else 99,
    ):
        if p["node_id"] not in NODE_ROLES:
            continue
        task = task_for_node(doc, p["node_id"])
        if task is not None and task["request_id"] in (request_id, None):
            task["request_id"] = request_id
            continue
        _open_task(doc, p["node_id"], request_id=request_id, late=False)


def ensure_task(doc: dict, node_id: str) -> None:
    """
    결정이 기록되는데 업무가 없으면 지금 연다 — 늦게 열었다고 표시한다(Studio, 장면 1~5와 같다).
    """
    if node_id in NODE_ROLES and task_for_node(doc, node_id) is None:
        _open_task(doc, node_id, request_id=None, late=True)


def complete_task(doc: dict, node_id: str, *, actor: str) -> None:
    task = task_for_node(doc, node_id)
    if task is None:
        return
    task.update(status="COMPLETED", completed_at=doc["clock"], completed_by=actor)
    domain.audit(doc, actor=actor, action="task_completed", task_id=task["task_id"])


def by_of(args: dict[str, Any], actor: str | None) -> tuple[str, bool]:
    """
    답한 사람 → (id 또는 이름, 마스터 안인가). 마스터 밖의 이름(콘솔 관리자)은 거절하지 않는다.
    """
    given = args.get("answered_by") or actor
    if not given:
        raise DomainError("답한 사람(answered_by)이 없다", 422)
    try:
        return user_id_of(str(given)), True
    except DomainError:
        return str(given), False


def status(doc: dict) -> dict[str, Any]:
    """독립 배지 — 확인 절차 · 보고본 · Risk. 보고 확정 ≠ 과제 실행 승인 ≠ 위험 종결."""
    if not is_bpm(doc):
        procedure = "LOADED"
    elif doc["report"]["state"] == "REPORTED":
        procedure = "REPORTED"
    elif doc["scene_info"]["started_at"] is None:
        procedure = "PENDING"
    else:
        procedure = "CONFIRMING"
    done = [r for r in ("CF61-P", "CF61-B", "CF61-F", "CF61-R", "CF61-M") if _done(doc, r)]
    return {
        "procedure": procedure,
        "report": doc["report"]["state"],
        "confirmed": done,
        "risk": doc["risk"]["state"],
    }


__all__ = [
    "NODE_ROLES",
    "RECORDS",
    "PrerequisiteError",
    "apply",
    "check",
    "check_actor",
    "finalize_blocking",
    "open_review",
    "start",
]
