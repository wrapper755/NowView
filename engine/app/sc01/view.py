"""
SC01 응답 모양 — 문서를 화면이 읽을 모양으로 바꾼다.

* BPM 스냅샷 원문은 내보내지 않는다. 화면이 알아야 하는 것은 "지금 누가 무엇을 기다리나"다.
* UI01 대시보드 집계는 매번 시드 + 이 실행의 전망에서 계산한다 — 값을 문서에 적어 두면
  원천이 바뀔 때 조용히 어긋난다.
* **F02는 계산이 성공하기 전에는 보이지 않는다**(AT01·UI01-01). 승인 전망 기본값은 F01이다.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from chaeksas.contracts.bpmn_ext import BpmnProcess

from app.sc01 import domain
from app.sc01.calc import PERIODS, Pnl, monthly_pnl, period_pnl
from app.sc01.seed import Seed


def _pnl(p: Pnl) -> dict[str, str]:
    return {
        "revenue": str(p.revenue),
        "cm": str(p.cm),
        "fixed": str(p.fixed),
        "mgmtProfit": str(p.mgmt_profit),
    }


def view(doc: dict, *, historical: bool = False) -> dict[str, Any]:
    pendings = (doc["bpm"] or {}).get("snapshot", {}).get("pendings", {})
    waiting = [
        {
            "nodeId": p["node_id"],
            "title": p["title"],
            "role": domain.NODE_ROLES.get(p["node_id"], {}).get("role"),
            "review": p["review"],
            "fields": (p["form"] or {}).get("fields", []),
            "taskId": (domain.task_for_node(doc, p["node_id"]) or {}).get("task_id"),
        }
        for p in pendings.values()
    ]
    tasks = [
        {
            **t,
            "overdue": domain.overdue(t, doc["clock"]),
            "assignedName": domain.USERS.get(t["assigned_to"] or "", {}).get("name"),
        }
        for t in doc["tasks"].values()
    ]
    latest_run = next(
        (r for r in reversed(doc["calc_runs"].values()) if r["status"] == "SUCCEEDED"), None
    )
    return {
        "demoRunId": doc["demo_run_id"],
        "caseId": doc["case_id"],
        "clock": doc["clock"],
        "step": doc["step"],
        "scriptIndex": doc.get("script_index", -1),
        "scene": doc["scene"],
        "historical": historical,
        "bpm": None
        if doc["bpm"] is None
        else {
            "runId": doc["bpm"]["run_id"],
            "state": doc["bpm"]["state"],
            "waiting": waiting,
            "position": sorted({t["node_id"] for t in doc["bpm"]["snapshot"]["tokens"]}),
            "visited": doc["bpm"].get("visited", []),
        },
        "sources": list(doc["sources"].values()),
        "forecasts": [
            {k: v for k, v in f.items() if k != "quantities"} for f in doc["forecasts"].values()
        ],
        "calcRuns": list(doc["calc_runs"].values()),
        "latestRunId": latest_run["run_id"] if latest_run else None,
        "issues": list(doc["issues"].values()),
        "tasks": tasks,
        "reviews": list(doc["reviews"].values()),
        "handoff": doc["handoff"],
        "handoffCheck": (
            domain.handoff_conditions(doc, latest_run["run_id"])
            if latest_run and latest_run["run_id"] != "RUN-F01-001"
            else None
        ),
        "audit": doc["audit"],
    }


def dashboard(doc: dict, seed: Seed, *, period: str = "연간", month: int = 7) -> dict[str, Any]:
    """UI01 — Target·승인 F01·(계산 후) 검토 F02의 손익과 모델별 표."""
    if period not in PERIODS:
        raise domain.DomainError(f"모르는 기간: {period}", 422)
    start, end = PERIODS[period]
    plans: dict[str, Any] = {"T01": seed.plans["T01"], "F01": seed.plans["F01"]}
    review = next(
        (
            f
            for f in reversed(doc["forecasts"].values())
            if doc["calc_runs"].get(f"RUN-{f['version_id']}-001")
        ),
        None,
    )
    if review is not None:
        plans[review["version_id"]] = domain._plan_from(review["quantities"])
    months = {name: monthly_pnl(plan, seed) for name, plan in plans.items()}
    totals = {name: _pnl(period_pnl(m, start, end)) for name, m in months.items()}
    trend = [
        {
            "month": m.isoformat(),
            "basis": "ACTUAL"
            if m.month <= 5
            else ("ACTUAL_PLUS_FORECAST" if m.month == 6 else "FORECAST"),
            **{name: str(series[m].mgmt_profit) for name, series in months.items()},
        }
        for m in sorted(months["T01"])
    ]
    target_month = date(2027, month, 1)
    latest_plan = plans[review["version_id"]] if review else plans["F01"]
    run = (
        doc["calc_runs"].get(f"RUN-{review['version_id']}-001")
        if review
        else doc["calc_runs"]["RUN-F01-001"]
    )
    results = {(r["model_id"], r["period"]): r for r in run["results"]}
    models = []
    for m in seed.models:
        key = ("CUS-HK", "ULS", m, target_month)
        r = results.get((m, target_month.isoformat()))
        models.append(
            {
                "modelId": m,
                "target": seed.plans["T01"][key],
                "prior": seed.plans["F01"][key],
                "latest": latest_plan[key],
                "actual": seed.actuals.get(key),
                "risk": r["risk"] if r else None,  # 평가 대상 월(7~9월) 밖이면 판정 없음
                "achievement": r["metrics"]["KPI01"]["value"] if r else None,
            }
        )
    return {
        "scope": {
            "customer": "CUS-HK",
            "plant": "ULS",
            "product": "A",
            "year": 2027,
            # 공장관리손익은 전사 영업이익이 아니다(UI01 근거 정보) — 상시 표기한다.
            "note": "공장관리손익 = 모델별 공헌이익 합계 − 공장고정비. 전사 영업이익과 다르다.",
        },
        "asOf": {"actualCutoff": "2027-06-15", "forecast": doc["clock"]},
        "period": period,
        "versions": list(plans),
        "approved": "F01",
        "review": review["version_id"] if review else None,
        "totals": totals,
        "trend": trend,
        "month": target_month.isoformat(),
        "models": models,
        "openIssues": sum(1 for i in doc["issues"].values() if i["status"] == "OPEN"),
    }


def topology(process: BpmnProcess) -> dict[str, Any]:
    """캔버스가 그릴 노드·흐름. **BPMN 파일이 원천**이다 — 화면은 토폴로지를 따로 적지 않는다."""
    return {
        "processId": process.id,
        "name": process.name,
        "nodes": [
            {
                "id": n.id,
                "kind": n.kind,
                "name": n.name,
                "role": domain.NODE_ROLES.get(n.id, {}).get("role"),
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
