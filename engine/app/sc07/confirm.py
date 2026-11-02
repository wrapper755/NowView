"""
SC07 확인 절차 — 개선건 열기 → 검증 실행(TS71-v1) → 구매 임원 확인(CF71) → 경영관리 임원 확인(CF72)
→ 운영
담당 설정 반영(CFG71) → 경영관리 담당 설정 확인 → 후속 점검 연결(업무설계표 SC07-S05~S09)을 BPM
(`processes/sc07.bpmn`)으로 받는다. 결재 뒤의 기록 작업(기본 확장 `external`)이 이 모듈의 `check` →
`apply`를
부른다 — 내장·Studio·Center 어디서 닫았든 같은 길이다(장면 1~6 N1).

* **결재는 데이터에 시각·담당이 있는 넷뿐이다**(2026-11-02 사용자 결정). 개선 요청·변경 기준·Agent
  개선
  확정(S01~S04)은 적재된 개선건이고, 검증 수행(S05)은 서비스 태스크가 규칙으로 다시
  계산한다(`calc.verify`).
* **데이터의 확인·적용 기록은 일정이자 기대값이다**(`schedule`·`plan`) — 기록 시각은 그 일정이다.
  가상시계가
  일정보다 앞이면 일정으로 옮긴다(시각 이동은 확인을 만들지 않는다 — 장면 6과 같다). 각본은 데이터의
  글을
  답으로 넣는다.
* **확인은 대상 버전이 맞아야 한다**(CT704) — 다른 버전의 확인을 적용 근거로 쓰지 않는다(UI705).
  보완 요청이면
  흐름이 「보완 필요」(ST703)로 끝난다 — 새 버전의 개선은 새 실행이다.
* **설정 확인의 「일치」는 연결된 레코드로 본다**(구현명세 5장 다섯 조건) — 예약만 된 설정·다른
  버전·다른
  범위면 「일치」를 거절한다(422 SETTING_MISMATCH). 「불일치」면 설정 반영으로 돌아간다.
* 설정 반영 확인 ≠ 운영 실행 확인 — 운영 실행 id는 없고 실행 상태는 NOT_CONFIRMED다(UI707).
"""

from __future__ import annotations

from typing import Any

from app.sc01.domain import USERS, DomainError, parse_at, user_id_of
from app.sc07 import domain
from app.sc07.domain import IMPROVEMENT_ID, account_of

#: 결재 → 담당·남길 기록. 결재 담당은 사람 하나다(`chk:approval.assignees`와 같다 — 시험이 맞춰
#: 본다).
NODE_ROLES: dict[str, dict[str, str]] = {
    "Confirm_Buy": {"user": "u-buy-exec", "record": "CF71", "task": "CONFIRM_BUY"},
    "Confirm_Finance": {"user": "u-fin-exec", "record": "CF72", "task": "CONFIRM_FINANCE"},
    "Apply_Setting": {"user": "u-ops", "record": "CFG71", "task": "APPLY_SETTING"},
    "Check_Setting": {"user": "u-fin", "record": "CFG71-R", "task": "CHECK_SETTING"},
}
for _spec in NODE_ROLES.values():
    _spec["role"] = USERS[_spec["user"]]["role"]

RECORDS = ("confirm_improvement_version", "apply_agent_setting", "check_agent_setting")
SERVICES = ("open_improvement", "verify_improvement_version", "schedule_follow_up_check")
#: 확인 결재 → 그 기록
OWNER_RECORDS = {"Confirm_Buy": "CF71", "Confirm_Finance": "CF72"}
#: 확인 착수 시각 — 데이터는 IMP71 발의일(2028-01-17)만 준다(SC07버전). 시각은 구현용 보완이다.
START_AT = "2028-01-17T09:00:00+09:00"
#: 확인을 착수하는 사람 — 개선 요청을 취합하는 경영관리 담당(SC07-S01)
STARTER = "u-fin"
EVIDENCE_TYPES = ("SETTINGS_SNAPSHOT", "RESERVED")


class PrerequisiteError(DomainError):
    """필수 조건 미충족 — 남은 항목을 함께 낸다(장면 3~6의 `blocking_items`와 같다)."""

    def __init__(self, message: str, items: list[str], code: str) -> None:
        super().__init__(message, 422)
        self.items = items
        self.code = code


# ─────────────────────────── 문서 ───────────────────────────


def pending_state(doc: dict, *, executor: str) -> None:
    """적재된 개선 문서를 **확인 전**으로 둔다. 바깥 실행이면 그 자리를 만든다(첫 작업 호출이
    묶는다)."""
    from app.sc01.domain import external_bpm

    doc.update(
        clock=START_AT,
        step="D700",
        verification=None,
        confirmations={},
        setting=None,
        follow_up=None,
        record_history=[],
        tasks={},
    )
    doc["scene_info"] = {"started_at": None, "started_by": None}
    doc["bpm"] = None if executor == "embedded" else external_bpm(executor)


def start(doc: dict, *, by: str) -> bool:
    """확인 착수 — 경영관리 담당. **재착수는 기존 결과를 돌려준다**(두 번째 절차를 만들지
    않는다)."""
    if by not in (STARTER, "u-demo"):
        holder = USERS[STARTER]
        raise DomainError(f"확인 착수는 {holder['role']}({holder['name']})가 한다", 403)
    if doc["scene_info"]["started_at"] is not None:
        return False
    doc["scene_info"].update(started_at=doc["clock"], started_by=by)
    domain.audit(doc, actor=by, action="improvement_started", improvement_id=IMPROVEMENT_ID)
    return True


def _started(doc: dict) -> None:
    if doc["scene_info"]["started_at"] is None:
        raise DomainError("아직 확인을 착수하지 않았다 — 화면에서 착수를 먼저 누른다", 409)


def open_improvement(doc: dict) -> dict[str, Any]:
    """BPM 첫 작업 — 착수된 개선건인지 본다. 바깥 실행은 착수 뒤에 Studio·Center에서 시작한다."""
    _started(doc)
    b = doc["bundle"]
    return {
        "improvement_id": IMPROVEMENT_ID,
        "agent_version": b["agent"],
        "verification_set": b["verification_set"],
    }


def verify_version(doc: dict, *, preserved: bool) -> dict[str, Any]:
    """
    SC07-S05 검증 수행 — TS71-v1을 개선 버전 규칙으로 실행해 기대값과 대조한다(`calc.verify`).
    데이터의 PASS를
    옮기지 않는다. 실행 일시는 가상시계, 실행 id는 이 문서의 순번이다 — Agent 실행 id가
    아니다(구현명세 2장).
    """
    _started(doc)
    if doc["confirmations"]:
        raise DomainError("업무 확인이 시작된 뒤에는 같은 버전을 다시 검증하지 않는다", 409)
    old = doc["verification"]
    if old is not None:
        doc["record_history"].append({**old, "retired": "재검증"})
    results = domain.run_verification(doc, preserved=preserved)
    passed = all(r["status"] == "PASS" for r in results)
    runs = 1 + sum(1 for h in doc["record_history"] if h.get("run_id"))
    doc["verification"] = {
        "run_id": f"VR71-{runs}",
        "executed_at": doc["clock"],
        "executed_by": "system",
        "agent_version": doc["bundle"]["agent"],
        "set": doc["bundle"]["verification_set"],
        "results": results,
        "passed": passed,
    }
    domain.audit(
        doc,
        actor="system",
        action="verification_run",
        run_id=doc["verification"]["run_id"],
        passed=passed,
        failed=[r["check"] for r in results if r["status"] != "PASS"],
    )
    return {
        "result": "PASS" if passed else "FAIL",
        "passed": sum(1 for r in results if r["status"] == "PASS"),
        "total": len(results),
    }


def schedule_follow_up(doc: dict) -> dict[str, Any]:
    """SC07-S09 후속 점검 연결 — 설정 반영이 확인된 뒤에만. 점검 담당·예정일은 데이터(AP71 사후
    점검)다."""
    _started(doc)
    state = domain.application_state(doc)
    if state["state"] != "ST707":
        raise DomainError(f"운영 설정 반영이 확인되지 않았다({state['label']})", 409)
    plan = doc["plan"]
    doc["follow_up"] = {
        "owner": plan["follow_up_by"],
        "planned_at": plan["follow_up_at"],
        "items": plan["follow_up_items"],
        "state": "PLANNED",
        "linked_at": doc["clock"],
        # 장기 효과는 미측정 — 시간 절감·정확도·재무 효과 수치를 만들지 않는다(구현명세 5장)
        "measured": False,
    }
    domain.audit(doc, actor="system", action="follow_up_linked", planned_at=plan["follow_up_at"])
    return {"state": state["state"], "planned_at": plan["follow_up_at"]}


# ─────────────────────────── 검사 (부수 효과 없음) ───────────────────────────


def _text(args: dict[str, Any], key: str) -> str:
    return str(args.get(key) or "").strip()


def _confirmed(doc: dict, record_id: str) -> bool:
    r = doc["confirmations"].get(record_id)
    return (
        r is not None
        and r["state"] == "CONFIRMED"
        and r["version"] == doc["plan"]["target_version"]
    )


def setting_blocking(doc: dict) -> list[str]:
    """설정 확인 「일치」의 남은 항목 — 반영 기록이 대상 버전·범위·스냅샷 증적인가(구현명세 5장
    ③④)."""
    s = doc["setting"]
    plan = doc["plan"]
    if s is None:
        return ["설정 반영 기록이 없다"]
    items = []
    if s["active_version"] != plan["target_version"]:
        items.append(
            f"active_version이 {s['active_version']}이다 — 대상 버전 {plan['target_version']}"
        )
    if s["scope"] != plan["scope"]:
        items.append(f"적용 범위가 다르다 — {s['scope']}")
    if s["evidence_type"] != "SETTINGS_SNAPSHOT":
        items.append(f"증적이 {s['evidence_type']}다 — 예약만으로 반영을 확인하지 않는다")
    return items


def check(doc: dict, operation: str, args: dict[str, Any]) -> None:
    """기록 작업과 화면 답의 사전 검사가 같이 쓴다 — 409(순서·상태) · 422(입력·요건)."""
    _started(doc)
    if doc["follow_up"] is not None:
        raise DomainError("이미 설정 반영 확인과 후속 점검 연결까지 끝났다", 409)
    node = str(args.get("node_id") or "")
    target = doc["plan"]["target_version"]
    if operation == "confirm_improvement_version":
        if OWNER_RECORDS.get(node) != args.get("record_id"):
            raise DomainError(f"{node}의 기록은 {OWNER_RECORDS.get(node)}이다", 422)
        run = doc["verification"]
        if run is None or not run["passed"]:
            raise DomainError("검증을 통과한 버전만 업무 확인을 한다(ST703)", 409)
        if args["record_id"] == "CF72" and not _confirmed(doc, "CF71"):
            raise DomainError("구매 임원 확인(CF71) 뒤에 경영관리 임원이 확인한다", 409)
        if doc["setting"] is not None:
            raise DomainError("설정 반영 뒤에는 확인을 바꾸지 않는다", 409)
        if args.get("decision") not in ("확인", "보완요청"):
            raise DomainError("확인은 확인·보완요청 중 하나다", 422)
        if _text(args, "version") != target:
            raise DomainError(
                f"확인 대상 버전은 {target}이다 — 다른 버전의 확인을 적용 근거로 쓰지 않는다", 422
            )
        if not _text(args, "content"):
            raise DomainError("확인 내용(보완 요청이면 사유)을 적는다", 422)
        return
    if operation == "apply_agent_setting":
        if not (_confirmed(doc, "CF71") and _confirmed(doc, "CF72")):
            raise DomainError("구매 임원·경영관리 임원 확인 뒤에 설정에 반영한다(CT704)", 409)
        for key, label in (
            ("snapshot_id", "설정 스냅샷"),
            ("active_version", "적용 버전"),
            ("scope", "적용 범위"),
            ("content", "반영 내용"),
        ):
            if not _text(args, key):
                raise DomainError(f"{label}을 적는다", 422)
        if args.get("evidence_type") not in EVIDENCE_TYPES:
            raise DomainError(f"증적 유형은 {'·'.join(EVIDENCE_TYPES)} 중 하나다", 422)
        return
    if operation == "check_agent_setting":
        if doc["setting"] is None:
            raise DomainError("설정 반영 기록이 없다 — 반영 뒤에 확인한다", 409)
        if args.get("result") not in ("일치", "불일치"):
            raise DomainError("설정 확인은 일치·불일치 중 하나다", 422)
        if not _text(args, "content"):
            raise DomainError("확인 내용을 적는다", 422)
        if args["result"] == "일치" and (items := setting_blocking(doc)):
            raise PrerequisiteError(
                "설정 반영을 확인할 수 없다 — 불일치로 답한다", items, "SETTING_MISMATCH"
            )
        return
    raise DomainError(f"모르는 작업: {operation}", 404)


def check_actor(node_id: str, actor: str) -> None:
    """역할 검사 — 그 결재의 담당만(403). 화면의 역할 선택은 신뢰 경계가 아니다(5.4)."""
    spec = NODE_ROLES[node_id]
    if actor != spec["user"]:
        holder = USERS[spec["user"]]
        raise DomainError(f"{holder['role']}({holder['name']})만 한다", 403)


# ─────────────────────────── 효과 ───────────────────────────


def planned_at(doc: dict, record_id: str) -> str | None:
    if record_id in doc["schedule"]:
        return doc["schedule"][record_id]["at"]
    return {"CFG71": doc["plan"]["applied_at"], "CFG71-R": doc["plan"]["checked_at"]}.get(record_id)


def _at(doc: dict, record_id: str) -> str:
    """기록 시각 = 일정. 가상시계가 일정보다 앞이면 일정으로 옮긴다(뒤로 가지 않는다)."""
    planned = planned_at(doc, record_id)
    if planned and parse_at(planned) > parse_at(doc["clock"]):
        doc["clock"] = parse_at(planned).isoformat()
        doc["_company_clock"] = True  # 회사 세계 시각도 함께(저장 때)
    return doc["clock"]


def apply(doc: dict, operation: str, args: dict[str, Any], *, by: str) -> dict[str, Any]:
    """기록 작업의 몸통 — `check`를 통과한 뒤 부른다."""
    actor = account_of(by)
    if operation == "confirm_improvement_version":
        rid = args["record_id"]
        old = doc["confirmations"].get(rid)
        if old is not None:
            doc["record_history"].append({**old, "retired": "다시 확인"})
        rework = args["decision"] == "보완요청"
        record = doc["confirmations"][rid] = {
            "record_id": rid,
            "improvement_id": IMPROVEMENT_ID,
            "actor": actor,
            "version": _text(args, "version"),
            "state": "REWORK_REQUESTED" if rework else "CONFIRMED",
            "at": _at(doc, rid),
            "content": _text(args, "content"),
        }
        domain.audit(
            doc, actor=by, action="improvement_rework" if rework else "improvement_confirmed",
            record_id=rid, version=record["version"],
        )  # fmt: skip
        return {"state": record["state"]}
    if operation == "apply_agent_setting":
        old = doc["setting"]
        if old is not None:
            doc["record_history"].append({**old, "record_id": "CFG71", "retired": "다시 반영"})
        doc["setting"] = {
            "snapshot_id": _text(args, "snapshot_id"),
            "previous_version": doc["plan"]["previous_version"],
            "active_version": _text(args, "active_version"),
            "scope": _text(args, "scope"),
            "evidence_type": args["evidence_type"],
            "applied_at": _at(doc, "CFG71"),
            "applied_by": actor,
            "content": _text(args, "content"),
            "checked_at": None,
            "checked_by": None,
            "check_result": None,
            "check_note": None,
        }
        domain.audit(
            doc, actor=by, action="setting_applied", snapshot=doc["setting"]["snapshot_id"],
            version=doc["setting"]["active_version"], evidence=args["evidence_type"],
        )  # fmt: skip
        return {"state": domain.application_state(doc)["state"]}
    if operation == "check_agent_setting":
        match = args["result"] == "일치"
        doc["setting"].update(
            checked_at=_at(doc, "CFG71-R"),
            checked_by=actor,
            check_result="MATCH" if match else "MISMATCH",
            check_note=_text(args, "content"),
        )
        domain.audit(doc, actor=by, action="setting_checked", result=doc["setting"]["check_result"])
        return {"state": domain.application_state(doc)["state"]}
    raise DomainError(f"모르는 작업: {operation}", 404)


def record_of(doc: dict, node_id: str) -> dict | None:
    """그 결재가 남긴 지금 기록(업무 완료 시각·각본 위치가 쓴다)."""
    rid = NODE_ROLES[node_id]["record"]
    if rid in doc["confirmations"]:
        return doc["confirmations"][rid]
    s = doc["setting"]
    if s is None:
        return None
    if rid == "CFG71":
        evidence = s["evidence_type"]
        return {"actor": s["applied_by"], "at": s["applied_at"], "evidence_type": evidence}
    if rid == "CFG71-R" and s["checked_at"]:
        return {"actor": s["checked_by"], "at": s["checked_at"], "result": s["check_result"]}
    return None


#: Studio는 끝을 작업 호출로만 안다 — 후속 점검 연결이나 보완 요청 기록이면 흐름이 끝난다.
def ends_flow(operation: str, out: dict[str, Any]) -> bool:
    return (
        operation == "schedule_follow_up_check"
        or (operation == "confirm_improvement_version" and out.get("state") == "REWORK_REQUESTED")
        or (operation == "verify_improvement_version" and out.get("result") == "FAIL")
    )


# ─────────────────────────── 업무 ───────────────────────────


def _open_task(doc: dict, node_id: str, *, request_id: str | None, late: bool) -> dict:
    spec = NODE_ROLES[node_id]
    previous = [t for t in doc["tasks"].values() if t["type"] == spec["task"]]
    task_id = f"TASK-{spec['task']}" + (f"-{len(previous) + 1}" if previous else "")
    due = planned_at(doc, spec["record"])
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
    """
    BPM의 사람 대기 → 업무. 같은 대기면 새로 만들지 않는다. 끝나지 않은 같은 결재의 업무가 있으면 새
    결재
    id를 거기 잇는다 — 기록 거절로 Center가 같은 결재를 새 id로 다시 열 때(장면 3·5 실측).
    """
    order = list(NODE_ROLES)
    for request_id, p in sorted(
        pendings.items(),
        key=lambda kv: order.index(kv[1]["node_id"]) if kv[1]["node_id"] in order else 99,
    ):
        if p["node_id"] not in NODE_ROLES:
            continue
        task = task_for_node(doc, p["node_id"])
        if task is not None:
            task["request_id"] = request_id
            continue
        _open_task(doc, p["node_id"], request_id=request_id, late=False)


def ensure_task(doc: dict, node_id: str) -> None:
    """결정이 기록되는데 업무가 없으면 지금 연다 — 늦게 열었다고 표시한다(Studio, 장면 1~6과
    같다)."""
    if node_id in NODE_ROLES and task_for_node(doc, node_id) is None:
        _open_task(doc, node_id, request_id=None, late=True)


def complete_task(doc: dict, node_id: str, *, actor: str) -> None:
    """업무 완료 시각은 그 결재가 남긴 기록의 시각이다(장면 6 Center 실측과 같은 이유)."""
    task = task_for_node(doc, node_id)
    if task is None:
        return
    record = record_of(doc, node_id)
    at = (
        record["at"]
        if record is not None and record["actor"] == account_of(actor)
        else doc["clock"]
    )
    task.update(status="COMPLETED", completed_at=at, completed_by=actor)
    domain.audit(doc, actor=actor, action="task_completed", task_id=task["task_id"])


def by_of(args: dict[str, Any], actor: str | None) -> tuple[str, bool]:
    """답한 사람 → (id 또는 이름, 마스터 안인가). 마스터 밖의 이름(콘솔 관리자)은 거절하지
    않는다."""
    given = args.get("answered_by") or actor
    if not given:
        raise DomainError("답한 사람(answered_by)이 없다", 422)
    try:
        return user_id_of(str(given)), True
    except DomainError:
        return str(given), False


def status(doc: dict) -> dict[str, Any]:
    """독립 배지 — 확인 절차 · 검증 · 적용 상태 · 운영 실행. 설정 반영 확인 ≠ 운영 실행 ≠ 장기
    효과."""
    state = domain.application_state(doc)
    rework = any(c["state"] == "REWORK_REQUESTED" for c in doc["confirmations"].values())
    if doc["scene_info"]["started_at"] is None:
        procedure = "PENDING"
    elif doc["follow_up"] is not None:
        procedure = "APPLIED"
    elif rework or (doc["verification"] is not None and not doc["verification"]["passed"]):
        procedure = "NEEDS_WORK"
    else:
        procedure = "CONFIRMING"
    run = doc["verification"]
    return {
        "procedure": procedure,
        "verification": "NOT_RUN" if run is None else ("PASSED" if run["passed"] else "FAILED"),
        "application": state["state"],
        "applicationLabel": state["label"],
        "execution": state["execution_status"],
        "confirmed": [rid for rid in ("CF71", "CF72") if _confirmed(doc, rid)],
        "followUp": None if doc["follow_up"] is None else doc["follow_up"]["state"],
    }


__all__ = [
    "NODE_ROLES",
    "RECORDS",
    "SERVICES",
    "PrerequisiteError",
    "apply",
    "check",
    "check_actor",
    "open_improvement",
    "start",
]
