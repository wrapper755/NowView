"""
장면 1의 경영 기록 — 회사 시스템(기간계)에 적는 판(`docs/role-split.md` §3,
스키마 `docs/records/sc01/`).

경영 기록의 원본은 회사 시스템이다(2026-11-03 사용자 결정). 일꾼이 규칙 계산 결과를
**저장 직전에** 적고(`Sc01Process._commit` — 원천 확인 상태 쓰기와 같은 길), 회사가 받지
못하면 그 조작은 저장되지 않는다(503). 회사 사이트는 이 기록만 읽어 업무 화면을 그린다 —
계산하지 않고 NowView를 부르지 않는다.

* **본문은 NowView 화면이 읽는 모양 그대로다**(사용자 결정) — `view.view`의 같은 칸. 두
  화면을 나란히 대조할 수 있고, 장면을 넓힐 때 같은 방식을 쓴다.
* **바뀐 기록만 새 판으로 적는다.** 문서의 `company_records`에 기록마다 (판, 본문 해시)를
  두고, 본문이 바뀌면 판을 올린다. ref = 데모실행:종류:id:판 — 재시도는 회사가 다시 적지
  않는다.
* 시각에 따라 저절로 바뀌는 칸(Agent 초안의 실제 시간 `delayed`)은 싣지 않는다 — 판이
  까닭 없이 오른다.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.sc01.seed import Seed

SCENE = 1


def _record(kind: str, record_id: str, state: str | None, title: str, body: Any) -> dict:
    return {"kind": kind, "record_id": record_id, "state": state, "title": title, "body": body}


def records_of(doc: dict, seed: Seed) -> list[dict[str, Any]]:
    """지금 문서의 장면 1 기록 전부(판 번호 없이) — 화면 다섯이 읽는 것."""
    from app.sc01 import view  # view가 process를 읽는다 — 순환을 피해 늦게 읽는다

    v = view.view(doc)
    out = [
        _record(
            "scene",
            "SC01",
            doc["scene"],
            "고객 생산계획 변경 대응",
            {
                "demoRunId": v["demoRunId"],
                "caseId": v["caseId"],
                "clock": v["clock"],
                "scene": v["scene"],
                "executor": v["executor"],
                "bpm": None
                if v["bpm"] is None
                else {
                    k: v["bpm"][k] for k in ("executor", "externalRunId", "state", "visited")
                },
                "latestRunId": v["latestRunId"],
                "rules": {k: str(x) for k, x in seed.rules.items()},
                "alerts": v["alerts"],
                "companyLog": v["companyLog"],
            },
        )
    ]
    for s in v["sources"]:
        out.append(_record("source", s["source_id"], s["status"], s["customer_plan_id"], s))
    for f in v["forecasts"]:
        out.append(_record("forecast", f["version_id"], f["approval"], f["version_id"], f))
    for r in v["calcRuns"]:
        out.append(_record("calc_run", r["run_id"], r["status"], r["run_id"], r))
    for i in v["issues"]:
        title = f"{i['model_id']} {i['period'][:7]}"
        out.append(_record("issue", i["issue_id"], i["status"], title, i))
    for t in v["tasks"]:
        out.append(_record("task", t["task_id"], t["status"], t["type"], t))
    for r in v["reviews"]:
        out.append(_record("review", r["run_id"], None, r["run_id"], r))
    for o in v["agentOutputs"]:
        body = {k: x for k, x in o.items() if k != "delayed"}
        out.append(_record("agent_draft", o["output_id"], o["status"], o["run_id"], body))
    out.append(
        _record(
            "handoff",
            "SC01",
            "HANDED_OFF" if v["handoff"] else "PENDING",
            "후속 업무 인계",
            {
                "handoff": v["handoff"],
                "handoffCheck": v["handoffCheck"],
                "handoffHistory": v["handoffHistory"],
                "bpmHistory": v["bpmHistory"],
                "audit": v["audit"],
            },
        )
    )
    out.append(_record("dashboard", "UI01", None, "경영 현황", view.dashboard_all(doc, seed)))
    return out


def _digest(body: Any) -> str:
    text = json.dumps(body, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def pending_writes(doc: dict, seed: Seed) -> list[dict[str, Any]]:
    """
    바뀐 기록을 새 판으로 — 회사에 보낼 봉투 목록. 문서의 `company_records`(판·해시)를 함께 고친다 —
    회사가 받지 못하면 문서가 저장되지 않으므로 고친 판도 버려진다(다음 조작이 같은 판을 다시 낸다).
    """
    known = doc.setdefault("company_records", {})
    writes = []
    for r in records_of(doc, seed):
        key = f"{r['kind']}/{r['record_id']}"
        digest = _digest([r["state"], r["title"], r["body"]])
        prior = known.get(key)
        if prior is not None and prior["hash"] == digest:
            continue
        version = (prior["version"] if prior else 0) + 1
        known[key] = {"version": version, "hash": digest}
        writes.append(
            {
                **r,
                "version": version,
                "scene": SCENE,
                "at": doc["clock"],
                "by": None,
                "ref": f"{doc['demo_run_id']}:{key}:v{version}",
            }
        )
    return writes


__all__ = ["SCENE", "pending_writes", "records_of"]
