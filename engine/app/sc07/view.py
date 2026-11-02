"""
SC07 문서 머리 — 화면이 장면 7이 열렸는지·확인·적용 절차가 어디까지 왔는지를 안다. 개선
전후·검증·적용
내용은 조회 서비스(`domain.improvement` …)로 받는다(장면 1~6 `view.py`와 같은 태도 — BPM 스냅샷
원문은
내보내지 않는다).

* 결재 폼 칸은 그림(`chk:approval.fields`)에서 온다. **기본값은 데이터의 확인·적용 기록이다** —
  각본과 같은
  글을 미리 채운다. 사람은 고쳐서 낼 수 있다.
"""

from __future__ import annotations

from typing import Any

from chaeksas.contracts.bpmn_ext import BpmnProcess

from app.sc01.center import CenterConfig
from app.sc01.domain import USERS, executor_of
from app.sc07 import confirm, demo, domain


def _node_rank(node_id: str) -> int:
    nodes = list(confirm.NODE_ROLES)
    return nodes.index(node_id) if node_id in nodes else len(nodes)


def _defaults(node_id: str, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    step = next((s for s in demo.steps_for() if s.node_id == node_id), None)
    if step is None:
        return fields
    return [
        {**f, "default": step.answer[f["key"]]} if step.answer.get(f["key"]) else f for f in fields
    ]


def view(doc: dict, *, historical: bool = False, center: CenterConfig | None = None) -> dict:
    status = confirm.status(doc)
    head = {
        "scene": "SC07",
        "demoRunId": doc["demo_run_id"],
        "caseId": doc["case_id"],
        "clock": doc["clock"],
        "step": doc.get("step"),
        # 상태로 본 각본 위치 — 화면·회사 사이트에서 직접 답해도 플레이어가 따라간다
        "scriptIndex": max(doc.get("script_index", -1), demo.done_index(doc)),
        "historical": historical,
        "improvementId": domain.IMPROVEMENT_ID,
        "applicationId": domain.APPLICATION_ID,
        "datasetVersion": doc["batch"]["dataset_version"],
        "versionBundle": doc["bundle"],
        "sc06": {k: doc["sc06"][k] for k in ("report_version", "report_state")},
        "batch": doc["batch"],
        "status": status,
        "companyLog": doc.get("company_log", []),
    }
    bpm = doc.get("bpm")
    pendings = dict(((bpm or {}).get("snapshot") or {}).get("pendings", {}))
    for w in (bpm or {}).get("waiting", []):
        pendings[w["request_id"]] = {
            "node_id": w["node_id"],
            "title": w["title"],
            "review": w["review"],
            "form": {"fields": w["fields"]},
        }
    waiting = [
        {
            "nodeId": p["node_id"],
            "title": p["title"],
            "role": confirm.NODE_ROLES.get(p["node_id"], {}).get("role"),
            "assignee": confirm.NODE_ROLES.get(p["node_id"], {}).get("user"),
            "review": p["review"],
            "fields": _defaults(p["node_id"], (p["form"] or {}).get("fields", [])),
            "taskId": (confirm.task_for_node(doc, p["node_id"]) or {}).get("task_id"),
        }
        for p in sorted(pendings.values(), key=lambda p: _node_rank(p["node_id"]))
    ]
    executor = executor_of(doc)
    plan = doc["plan"]
    steps = [
        {
            "nodeId": node,
            "recordId": spec["record"],
            "role": spec["role"],
            "assignee": spec["user"],
            "assigneeName": USERS[spec["user"]]["name"],
            "plannedAt": confirm.planned_at(doc, spec["record"]),
            "record": _record(confirm.record_of(doc, node), spec["record"], doc),
        }
        for node, spec in confirm.NODE_ROLES.items()
    ]
    rejected = [a for a in doc["audit"] if a["action"] == "answer_rejected"]
    run = doc["verification"]
    return {
        **head,
        "executor": executor,
        "answerHere": _answer_here(executor, center),
        "procedure": {
            "startedAt": doc["scene_info"]["started_at"],
            "verification": None
            if run is None
            else {
                **{k: run[k] for k in ("run_id", "executed_at", "agent_version", "set", "passed")},
                "failed": [r["check"] for r in run["results"] if r["status"] != "PASS"],
                "total": len(run["results"]),
            },
            "steps": steps,
            "setting": doc["setting"],
            "followUp": doc["follow_up"],
            "plan": {k: plan[k] for k in ("target_version", "scope", "snapshot_id", "next_run_at")},
            "history": doc["record_history"],
            "lastRejection": rejected[-1]["detail"] if rejected else None,
        },
        "tasks": [
            {**t, "assignedName": USERS.get(t["assigned_to"] or "", {}).get("name")}
            for t in sorted(doc["tasks"].values(), key=lambda t: t["seq"])
        ],
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


def _record(record: dict | None, record_id: str, doc: dict) -> dict[str, Any] | None:
    if record is None:
        return None
    return {**record, "record_id": record_id, "actor": domain.who(record["actor"])}


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
    return {"job": ledger.get("job"), "problem": problem, "package": center and center.sc07_package}


def _record_of(node: Any, process: BpmnProcess) -> str | None:
    """기록 태스크·그 오류 경계면 그 결재 — 캔버스가 결재 노드에 접는다(장면 1~6과 같다)."""
    if node.kind == "boundaryEvent":
        host = process.node(node.attached_to or "")
        return _record_of(host, process) if host is not None else None
    call = node.prop("serviceCall") if node.kind == "serviceTask" else None
    if call is None or call.operation not in confirm.RECORDS:
        return None
    return str(call.input.get("node_id", "")).strip("'") or None


def topology(process: BpmnProcess) -> dict[str, Any]:
    """캔버스가 그릴 노드·흐름 — BPMN 파일이 원천이다. 모양은 장면 1~6 토폴로지와 같다."""
    return {
        "processId": process.id,
        "name": process.name,
        "nodes": [
            {
                "id": n.id,
                "kind": n.kind,
                "name": n.name,
                "role": confirm.NODE_ROLES.get(n.id, {}).get("role"),
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
