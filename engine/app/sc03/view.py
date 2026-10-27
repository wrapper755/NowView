"""
SC03 응답 모양 — 문서를 화면이 읽을 모양으로(장면 1·2 `view.py`와 같은 태도).

* BPM 스냅샷 원문은 내보내지 않는다. 「지금 누가 무엇을 기다리나」만 낸다.
* 부서 확인 현황·종료 요건·인수율·지연은 저장하지 않고 **파생한다** — 기록과 갈라지지 않게.
* 상태는 배지마다 따로다(검토건·결론·Risk·Forecast·Target) — 칩 하나로 뭉치지 않는다(UI31).
"""

from __future__ import annotations

from typing import Any

from chaeksas.contracts.bpmn_ext import BpmnProcess

from app.sc01.center import CenterConfig
from app.sc01.domain import USERS, executor_of, ordered
from app.sc03 import domain
from app.sc03.process import RECORDS


def _node_rank(node_id: str) -> int:
    nodes = list(domain.NODE_ROLES)
    return nodes.index(node_id) if node_id in nodes else len(nodes)


def view(doc: dict, *, historical: bool = False, center: CenterConfig | None = None) -> dict:
    bpm = doc["bpm"]
    pendings = dict(((bpm or {}).get("snapshot") or {}).get("pendings", {}))
    for w in (bpm or {}).get("waiting", []):
        pendings[w["request_id"]] = {
            "node_id": w["node_id"],
            "title": w["title"],
            "review": w["review"],
            "form": {"fields": w["fields"]},
        }
    executor = executor_of(doc)
    waiting = [
        {
            "nodeId": p["node_id"],
            "title": p["title"],
            "role": domain.NODE_ROLES.get(p["node_id"], {}).get("role"),
            "assignee": domain.assignee_of(doc, p["node_id"])
            if p["node_id"] in domain.NODE_ROLES
            else None,
            "review": p["review"],
            "fields": (p["form"] or {}).get("fields", []),
            "taskId": (domain.task_for_node(doc, p["node_id"]) or {}).get("task_id"),
        }
        for p in sorted(pendings.values(), key=lambda p: _node_rank(p["node_id"]))
    ]
    tasks = [
        {
            **t,
            "overdue": t["status"] != "COMPLETED" and domain.is_overdue(t["due_at"], doc["clock"]),
            "assignedName": USERS.get(t["assigned_to"] or "", {}).get("name"),
        }
        for t in ordered(doc["tasks"])
    ]
    run = domain.latest_run(doc)
    return {
        "scene": "SC03",
        "demoRunId": doc["demo_run_id"],
        "caseId": doc["case_id"],
        "caseLabel": domain.CASES[doc["case_id"]],
        "clock": doc["clock"],
        "step": doc["step"],
        "scriptIndex": doc.get("script_index", -1),
        "historical": historical,
        "status": domain.statuses(doc),
        "sc02": doc["sc02"],
        "review": doc["review"],
        "schedule": domain.SCHEDULE,
        "runs": ordered(doc["runs"]),
        "latestRunId": None if run is None else run["run_id"],
        "reports": ordered(doc["reports"]),
        "currentDraftId": (domain.current_draft(doc) or {}).get("report_id"),
        "frozenReportId": (domain.frozen_report(doc) or {}).get("report_id"),
        "confirmation": doc["confirmation"],
        "departments": [
            {**domain.dept_status(doc, d), "label": v["label"], "user": v["user"]}
            for d, v in domain.DEPTS.items()
        ],
        "replies": doc["replies"],
        "facts": ordered(doc["facts"]),
        "questions": ordered(doc["questions"]),
        "freezeProblems": domain.freeze_problems(doc),
        "meetings": ordered(doc["meetings"]),
        "candidates": ordered(doc["candidates"]),
        "decision": doc["decision"],
        "minutes": ordered(doc["minutes"]),
        "assignments": ordered(doc["assignments"]),
        "acceptance": domain.acceptance_rate(doc),
        "delayed": domain.delayed_tasks(doc),
        "completion": domain.completion_conditions(doc),
        "revisions": doc["revisions"],
        "handoff": doc["handoff"],
        "agentMode": doc.get("agent_mode", "mock"),
        "agentOutputs": ordered(doc["agent_outputs"]),
        "tasks": tasks,
        "alerts": doc["alerts"],
        "audit": doc["audit"],
        "executor": executor,
        "answerHere": _answer_here(executor, center),
        "bpm": None
        if bpm is None
        else {
            "executor": executor,
            "externalRunId": bpm.get("external_run_id"),
            "runId": bpm.get("run_id"),
            "state": bpm["state"],
            "waiting": waiting,
            "center": _center_view(doc, center),
            "position": (
                sorted({t["node_id"] for t in bpm["snapshot"]["tokens"]})
                if bpm.get("snapshot") is not None
                else bpm.get("position", [])
            ),
            "visited": bpm.get("visited", []),
        },
    }


def _answer_here(executor: str, center: CenterConfig | None) -> bool:
    """이 화면에서 결재에 답할 수 있나 — Center면 대리 답용 키가 있을 때, Studio는 아니다."""
    if executor == "center":
        return center is not None and center.missing(relay=True) is None
    return executor == "embedded"


def _center_view(doc: dict, center: CenterConfig | None) -> dict[str, Any] | None:
    if executor_of(doc) != "center":
        return None
    ledger = (doc["bpm"] or {}).get("center") or {}
    problem = ledger.get("problem")
    if problem is None and center is not None:
        relay = center.missing(relay=True)
        problem = f"{relay} — 화면 답(대리 답)을 할 수 없다" if relay else None
    return {"job": ledger.get("job"), "problem": problem, "package": center and center.sc03_package}


def _record_of(node: Any, process: BpmnProcess) -> str | None:
    """기록 태스크·그 오류 경계면 그 결재 — 캔버스가 결재 노드에 접는다(장면 1·2와 같다)."""
    if node.kind == "boundaryEvent":
        host = process.node(node.attached_to or "")
        return _record_of(host, process) if host is not None else None
    call = node.prop("serviceCall") if node.kind == "serviceTask" else None
    if call is None or call.operation not in RECORDS:
        return None
    return str(call.input.get("node_id", "")).strip("'") or None


def topology(process: BpmnProcess) -> dict[str, Any]:
    """캔버스가 그릴 노드·흐름 — BPMN 파일이 원천이다. 모양은 장면 1·2 토폴로지와 같다."""
    return {
        "processId": process.id,
        "name": process.name,
        "nodes": [
            {
                "id": n.id,
                "kind": n.kind,
                "name": n.name,
                "role": domain.NODE_ROLES.get(n.id, {}).get("role"),
                "recordOf": _record_of(n, process),
            }
            for n in process.all_nodes()
        ],
        "flows": [
            {
                "id": f.id,
                "source": f.source,
                "target": f.target,
                "condition": f.condition,
                "default": f.is_default,
            }
            for f in process.flows
        ],
    }
