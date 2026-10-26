"""
SC02 응답 모양 — 문서를 화면이 읽을 모양으로 바꾼다(SC01 `view.py`와 같은 태도).

* BPM 스냅샷 원문은 내보내지 않는다. 화면이 알아야 하는 것은 「지금 누가 무엇을 기다리나」다.
* 원가 상태(적용 예정 → 적용)는 저장하지 않고 가상시계에서 파생한다 — 적용일 도래는 이벤트가 아니다.
* **통합 영향(U27)은 한 안만 고른다**(HAND-03). 승인안이 있으면 그것, 없으면 가장 최근의 안을
  **잠정**으로 보인다 — 요청·협상·승인안을 동시에 합산하지 않는다.
"""

from __future__ import annotations

from typing import Any

from chaeksas.contracts.bpmn_ext import BpmnProcess

from app.sc01.domain import USERS, ordered, overdue
from app.sc02 import domain
from app.sc02.process import RECORDS


def _node_rank(node_id: str) -> int:
    nodes = list(domain.NODE_ROLES)
    return nodes.index(node_id) if node_id in nodes else len(nodes)


def selected_run(doc: dict) -> dict | None:
    """U27이 보일 안 하나. 승인안이 아니면 잠정이다."""
    runs = [r for r in ordered(doc["runs"]) if not r["is_stale"] and r["kind"] != "OFFER"]
    if not runs:
        return None
    app = next((r for r in reversed(runs) if r["kind"] == "APPROVED"), None)
    return app or runs[-1]


def view(doc: dict, *, historical: bool = False) -> dict[str, Any]:
    bpm = doc["bpm"]
    pendings = ((bpm or {}).get("snapshot") or {}).get("pendings", {})
    waiting = [
        {
            "nodeId": p["node_id"],
            "title": p["title"],
            "role": domain.NODE_ROLES.get(p["node_id"], {}).get("role"),
            "review": p["review"],
            "fields": (p["form"] or {}).get("fields", []),
            "taskId": (domain.task_for_node(doc, p["node_id"]) or {}).get("task_id"),
        }
        for p in sorted(pendings.values(), key=lambda p: _node_rank(p["node_id"]))
    ]
    tasks = [
        {
            **t,
            "overdue": overdue(t, doc["clock"]),
            "assignedName": USERS.get(t["assigned_to"] or "", {}).get("name"),
        }
        for t in ordered(doc["tasks"])
    ]
    cost_versions = [
        {**cv, "status": domain.cost_status(cv, doc["clock"])}
        for cv in ordered(doc["cost_versions"])
    ]
    picked = selected_run(doc)
    return {
        "scene": "SC02",
        "demoRunId": doc["demo_run_id"],
        "caseId": doc["case_id"],
        "caseLabel": domain.CASES[doc["case_id"]],
        "clock": doc["clock"],
        "step": doc["step"],
        "scriptIndex": doc.get("script_index", -1),
        "historical": historical,
        "status": domain.statuses(doc),
        "sc01": doc["sc01"],
        "request": doc["request"],
        "report": doc["report"],
        "priceVersions": ordered(doc["price_versions"]),
        "runs": ordered(doc["runs"]),
        "negotiations": ordered(doc["negotiations"]),
        "proposals": ordered(doc["proposals"]),
        "decisions": doc["decisions"],
        "instruction": doc["instruction"],
        "costVersions": cost_versions,
        "issue": doc["issue"],
        "review": doc["review"],
        "selectedRunId": None if picked is None else picked["run_id"],
        "selectedProvisional": picked is None or picked["kind"] != "APPROVED",
        "handoff": doc["handoff"],
        "handoffHistory": doc["handoff_history"],
        "handoffCheck": domain.handoff_conditions(doc),
        "evidence": doc["evidence_ids"],
        "agentMode": doc.get("agent_mode", "mock"),
        "agentOutputs": ordered(doc["agent_outputs"]),
        "tasks": tasks,
        "alerts": doc["alerts"],
        "audit": doc["audit"],
        "bpm": None
        if bpm is None
        else {
            "executor": "embedded",
            "runId": bpm["run_id"],
            "state": bpm["state"],
            "waiting": waiting,
            "position": sorted({t["node_id"] for t in bpm["snapshot"]["tokens"]}),
            "visited": bpm.get("visited", []),
        },
    }


def _record_of(node: Any) -> str | None:
    call = node.prop("serviceCall") if node.kind == "serviceTask" else None
    if call is None or call.operation not in RECORDS:
        return None
    return str(call.input.get("node_id", "")).strip("'") or None


def topology(process: BpmnProcess) -> dict[str, Any]:
    """캔버스가 그릴 노드·흐름 — BPMN 파일이 원천이다. 모양은 SC01 토폴로지와 같다."""
    return {
        "processId": process.id,
        "name": process.name,
        "nodes": [
            {
                "id": n.id,
                "kind": n.kind,
                "name": n.name,
                "role": domain.NODE_ROLES.get(n.id, {}).get("role"),
                "recordOf": _record_of(n),
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
