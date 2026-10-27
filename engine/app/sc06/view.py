"""
SC06 문서 머리 — 화면이 장면 6이 열렸는지·어느 보고본인지·확인 절차가 어디까지 왔는지를 안다. 숫자는
조회 서비스(`domain.summary` …)로 받는다(장면 1~5 `view.py`와 같은 태도 — BPM 스냅샷 원문은 내보내지
않는다).

* 결재 폼 칸은 그림(`chk:approval.fields`)에서 온다. **기본값은 데이터의 확인 기록(SC06보고)이다** —
  각본과 같은 글을 미리 채운다. 사람은 고쳐서 낼 수 있다(기록이 그 글을 남긴다).
* 확인 기록은 끝난 것만 낸다 — 일정(`schedule`)은 시각·단계만 낸다(아직 쓰지 않은 글을 내려보내지
  않는다).
"""

from __future__ import annotations

from typing import Any

from chaeksas.contracts.bpmn_ext import BpmnProcess

from app.sc01.center import CenterConfig
from app.sc01.domain import USERS, executor_of
from app.sc06 import confirm, demo, domain


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
    report = doc["report"]
    head = {
        "scene": "SC06",
        "demoRunId": doc["demo_run_id"],
        "caseId": doc["case_id"],
        "clock": doc["clock"],
        "step": doc.get("step"),
        # 상태로 본 각본 위치 — 화면에서 직접 답해도 플레이어가 따라간다
        "scriptIndex": max(doc.get("script_index", -1), demo.done_index(doc))
        if confirm.is_bpm(doc)
        else -1,
        "historical": historical,
        "reviewId": domain.REVIEW_ID,
        "reportVersion": report["report_version"],
        "calculationVersion": report["calculation_version"],
        "reportState": report["state"],
        "sc05": {k: doc["sc05"][k] for k in ("handoff_id", "official", "annual", "target", "gap")},
        "batch": doc["batch"],
        "status": confirm.status(doc),
    }
    if not confirm.is_bpm(doc):
        return {**head, "executor": None, "answerHere": False, "bpm": None, "procedure": None}
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
    steps = [
        {
            "nodeId": node,
            "recordId": spec["record"],
            "role": spec["role"],
            "assignee": spec["user"],
            "assigneeName": USERS[spec["user"]]["name"],
            "step": doc["schedule"].get(spec["record"], {}).get("step"),
            "plannedAt": doc["schedule"].get(spec["record"], {}).get("at"),
            "record": _record(doc["report_records"].get(spec["record"])),
        }
        for node, spec in confirm.NODE_ROLES.items()
    ]
    rejected = [a for a in doc["audit"] if a["action"] == "answer_rejected"]
    return {
        **head,
        "executor": executor,
        "answerHere": _answer_here(executor, center),
        "procedure": {
            "startedAt": doc["scene_info"]["started_at"],
            "steps": steps,
            "note": _record(doc["report_records"].get("NOTE61")),
            "history": [_record(r) for r in doc["record_history"]],
            "finalizeBlocking": confirm.finalize_blocking(doc)
            if report["state"] == "DRAFT" and doc["scene_info"]["started_at"]
            else [],
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


def _record(record: dict | None) -> dict[str, Any] | None:
    return None if record is None else {**record, "actor": domain.who(record["actor"])}


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
    return {"job": ledger.get("job"), "problem": problem, "package": center and center.sc06_package}


def _record_of(node: Any, process: BpmnProcess) -> str | None:
    """기록 태스크·그 오류 경계면 그 결재 — 캔버스가 결재 노드에 접는다(장면 1~5와 같다)."""
    if node.kind == "boundaryEvent":
        host = process.node(node.attached_to or "")
        return _record_of(host, process) if host is not None else None
    call = node.prop("serviceCall") if node.kind == "serviceTask" else None
    if call is None or call.operation not in confirm.RECORDS:
        return None
    return str(call.input.get("node_id", "")).strip("'") or None


def topology(process: BpmnProcess) -> dict[str, Any]:
    """캔버스가 그릴 노드·흐름 — BPMN 파일이 원천이다. 모양은 장면 1~5 토폴로지와 같다."""
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
