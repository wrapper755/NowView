"""
SC05 응답 모양 — 문서를 화면이 읽을 모양으로(장면 1~4 `view.py`와 같은 태도).

* BPM 스냅샷 원문은 내보내지 않는다. 「지금 누가 무엇을 기다리나」만 낸다.
* 착수 요건·예산 사용가능액·초기 결과 미리보기·종료 요건은 저장하지 않고 **파생한다** — 기록과
  갈라지지 않게.
* 상태는 배지마다 따로다(장면·계획·경영관리 확인·CON41·SUP41·운영·공식 전망·Risk·Target).
* **문서에 있는 것만 낸다** — 배경 원천은 시각이 지나야 문서에 들어오므로(`domain.catch_up`) 미래
  기록이 브라우저에
  가지 않는다(구현명세 13장 「초기 조회에는 미래 업무 레코드 자체를 반환하지 않는다」).
"""

from __future__ import annotations

from typing import Any

from chaeksas.contracts.bpmn_ext import BpmnProcess

from app.sc01.center import CenterConfig
from app.sc01.domain import USERS, executor_of, ordered
from app.sc05 import calc, domain


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
    review = domain.review_forecast(doc)
    started = doc["scene"]["started_at"] is not None
    return {
        "scene": "SC05",
        "demoRunId": doc["demo_run_id"],
        "caseId": doc["case_id"],
        "caseLabel": domain.CASES[doc["case_id"]],
        "clock": doc["clock"],
        "step": doc["step"],
        "scriptIndex": doc.get("script_index", -1),
        "historical": historical,
        "status": domain.statuses(doc),
        "sc04": {
            k: doc["sc04"][k]
            for k in (
                "handoff",
                "approval",
                "actions",
                "directives",
                "decision_months",
                "gap_before",
            )
        },
        "sceneInfo": doc["scene"],
        "schedule": domain.SCHEDULE,
        "settings": doc["settings"],
        # 확정 차단 사유(누락·순환·승인 범위) — 화면은 같은 검사를 다시 하지 않는다
        "plans": [
            {**p, "problems": [] if p["background"] else domain.plan_problems(doc, p)}
            for p in ordered(doc["plans"])
        ],
        "planPointer": doc["plan_pointer"],
        "collaborations": doc["collaborations"],
        "conditions": ordered(doc["conditions"]),
        "requests": ordered(doc["requests"]),
        "ledger": doc["ledger"],
        "budget": domain.budget_status(doc),
        "startCheck": domain.start_requirements(doc) if started else None,
        "start": doc["start"],
        "operation": [
            {**op, "state": domain.operation_state(doc, op["task_id"])}
            for op in ordered(doc["operation"])
        ],
        "customerPlans": sorted(doc["customer_plans"].values(), key=lambda p: p["received_at"]),
        # 공유·확인 소요(분) — M503·M504와 같은 계산. 미확인은 None이다(0분 아님)
        "changes": [
            {
                **c,
                "share_minutes": _minutes(c["received_at"], c["shared_at"]),
                "ack_minutes": _minutes(c["shared_at"], c["ack_at"]),
            }
            for c in ordered(doc["changes"])
        ],
        "orders": ordered(doc["orders"]),
        "sourceIssues": [{k: v for k, v in i.items() if k != "row"} for i in doc["source_issues"]],
        "observation": doc["observation"],
        "observationPreview": None if doc["start"] is None else domain.observation(doc),
        "operatingPlans": ordered(doc["operating_plans"]),
        "runs": ordered(doc["runs"]),
        "forecasts": ordered(doc["forecasts"]),
        "official": doc["official"],
        "reviewForecastId": None if review is None else review["forecast_id"],
        "forecastBlocking": domain.forecast_blocking(doc) if review is not None else [],
        "shares": doc["shares"],
        "followups": doc["followups"],
        "directiveLog": doc["directive_log"],
        "evidence": ordered(doc["evidence"]),
        "completion": domain.completion_conditions(doc) if started else None,
        "handoff": doc["handoff"],
        "agentMode": "REPLAY" if doc.get("agent_mode", "mock") == "mock" else "LIVE",
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


def _minutes(start: str | None, end: str | None) -> str | None:
    m = calc.minutes(start, end)
    return None if m is None else str(m)


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
    running = (doc["bpm"] or {}).get("state") == "running"
    return {
        "job": ledger.get("job"),
        "problem": problem,
        "package": center and center.sc05_package,
        # 대리 답을 보냈는데 아직 기록이 오지 않은 결재 — 화면이 「Center 반영 중」을 보인다
        "inflight": list(ledger.get("inflight", [])) if running else [],
    }


def _record_of(node: Any, process: BpmnProcess) -> str | None:
    """기록 태스크·그 오류 경계면 그 결재 — 캔버스가 결재 노드에 접는다(장면 1~4와 같다)."""
    if node.kind == "boundaryEvent":
        host = process.node(node.attached_to or "")
        return _record_of(host, process) if host is not None else None
    call = node.prop("serviceCall") if node.kind == "serviceTask" else None
    if call is None or call.operation not in domain.RECORDS:
        return None
    return str(call.input.get("node_id", "")).strip("'") or None


def topology(process: BpmnProcess) -> dict[str, Any]:
    """캔버스가 그릴 노드·흐름 — BPMN 파일이 원천이다. 모양은 장면 1~4 토폴로지와 같다."""
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
