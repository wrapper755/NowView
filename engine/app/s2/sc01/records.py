"""
시나리오 2 장면 1의 경영 기록 — 공통 기록 종류(`docs/platform.md` §3, 스키마 `docs/records/s2/`).

회사 사이트의 Case 화면(UI-B02)과 NowView 대시보드(UI-D01)가 이 기록만 읽는다 — 둘 다 계산하지
않는다. 시나리오 2
회차에는 시나리오 2 기록만 있으므로 record_id에 장면 접두를 붙이지 않는다.
"""

from __future__ import annotations

from typing import Any

from app.platform import catalog
from app.records import record
from app.s2.sc01 import calc
from app.s2.sc01.process import ALERT_ID, ANALYSIS_ID, CASE_ID, HANDOFF_ID, LABEL

TITLE = "납기 위험 조기 감지"
KINDS = {
    "scene": "장면 머리 — 시연 시각·사례·실행 위치·개정마다 BPM 실행·회사와 오간 것",
    "event": (
        "원천 Event(M02) — 구매 입고예정 개정 한 건과 Y01 판정(최초·기록·경보·평가 보류·"
        "중복·늦게 옴)"
    ),
    "alert": "경보(M16) — KRI·규칙 버전·사유·위험 수준·연결 Event·Case",
    "case": "Case(M03) — 유형·목표·책임 역할·상태·Event·영향 약정·역할 목록·흐름 단계",
    "analysis": "분석 결과(M13) — 판·기준시각·실행 방식·약정별 근거 행·근거 스냅샷(M14)·누락",
    "handoff": "장면 인계(HAND-01) — 다음 노드 N03A·약정·분석 판·누락·원계획 유지",
    "dashboard": "납기 상황판(UI-D01) — 마감 OTD·목표·고유 경보·영향 약정·사건·개정 이력·11월 약정",
}

#: Case 화면 왼쪽 — 이 장면에 참여하는 역할과 하는 일(상세화면구성 02). 정상 조회는 사람 할 일이
#: 아니다.
PARTICIPANTS = [
    ("Y01", "경보 판정·사건 연결", ["N01", "N02"]),
    ("A01", "주문 연결·영향 분석", ["N03"]),
    ("H03", "예외 확인 (Case 책임 — 조회만, 승인 없음)", ["N03"]),
    ("H01", "원천 보완 (누락·오류만)", ["N01"]),
]


def _flow(doc: dict) -> list[dict[str, Any]]:
    """N01~N03A 단계 상태 — 장면 1의 끝은 분석 완료·수행계획 구성 대기다."""
    events = list(doc["events"].values())
    alerted = any(e["judgment"] == calc.ALERT for e in events)
    case = doc["case"]
    analyzed = bool(doc["analyses"])
    failed = bool(case and case.get("analysis_failed_at") and not analyzed)
    return [
        {
            "node": "N01",
            "name": "변경 수신·경보 판정",
            "role": "Y01",
            "state": "done" if events else "waiting",
        },
        {
            "node": "N02",
            "name": "경보·사건 연결",
            "role": "Y01",
            "state": "done" if case else ("waiting" if not alerted else "running"),
        },
        {
            "node": "N03",
            "name": "영향 분석",
            "role": "A01",
            "state": "done"
            if analyzed
            else ("failed" if failed else ("running" if case else "waiting")),
        },
        {
            "node": "N03A",
            "name": "수행계획 구성 (장면 2)",
            "role": "A03",
            "state": "next" if doc["handoff"] else "waiting",
        },
    ]


def _case_body(doc: dict) -> dict[str, Any]:
    case = doc["case"]
    roles = [
        {**catalog.role(rid), "duty": duty, "steps": steps} for rid, duty, steps in PARTICIPANTS
    ]
    analysis = doc["analyses"][-1] if doc["analyses"] else None
    return {
        **case,
        "state_label": catalog.CASE_STATES[case["state"]],
        "owner": catalog.role(case["owner_role"]),
        "roles": roles,
        "flow": _flow(doc),
        "analysis_version": analysis["version"] if analysis else None,
        "attempts": [a for a in doc["attempts"]],
        "production_plan": "원본 유지",
        "approvals": 0,
    }


def _event_body(e: dict) -> dict[str, Any]:
    return {
        "event_id": e["event_id"],
        "source_system": e["source_system"],
        "source_key": e["po_line"],
        "revision_id": e["revision_id"],
        "revision_no": e["revision_no"],
        "registered_at": e["registered_at"],
        "evaluated_at": e["evaluated_at"],
        "lots": e["lots"],
        "total_qty": e["total_qty"],
        "window": e["window"],
        "change_count": e["change_count"],
        "min_slack_min": e["min_slack_min"],
        "shortage": e["shortage"],
        "judgment": e["judgment"],
        "judgment_label": LABEL[e["judgment"]],
        "reasons": e["reasons"],
        "missing": e["missing"],
        "affected": e["affected"],
        "rule_version": e["rule_version"],
        "execution_mode": e["execution_mode"],
        "case_id": e.get("case_id"),
        "redeliveries": e.get("redeliveries", []),
    }


def _latest_lots(doc: dict) -> list[dict[str, Any]]:
    """지금 알려진 P 입고 예정 — 가장 최신 개정(늦게 온 개정은 최신값을 되돌리지 않는다)."""
    fresh = [e for e in doc["events"].values() if e["judgment"] != "LATE"]
    if not fresh:
        return []
    return max(fresh, key=lambda e: e["revision_no"])["lots"]


def dashboard(doc: dict, master: dict) -> dict[str, Any]:
    """
    UI-D01 — 실적(KPI)·위험(KRI)·통제(Case 처리) 카드를 서로 다른 단위로. 경보 선택으로
    실적이 바뀌지 않는다.
    """
    as_of = doc["clock"]
    case, alert = doc["case"], doc["alert"]
    events = sorted(doc["events"].values(), key=lambda e: (e["po_line"], e["revision_no"]))
    analysis = doc["analyses"][-1] if doc["analyses"] else None
    cases = []
    if case is not None:
        cases.append(
            {
                "case_id": case["case_id"],
                "opened_at": case["opened_at"],
                "part_id": ", ".join(alert["part_id"]) if alert else None,
                "reason": " · ".join(alert["reasons"]) if alert else None,
                "commitments": case["commitments"],
                "state": case["state"],
                "state_label": catalog.CASE_STATES[case["state"]],
            }
        )
    return {
        "as_of": as_of,
        "scope": {
            "company": "company1",
            "plant": "울산",
            "product": "A",
            "label": "울산공장 / 기존사업 A제품",
        },
        "dataset_version": master["dataset_version"],
        "kpi": calc.otd(master, as_of),
        "kri": {
            "alerts": 1 if alert else 0,
            "affected_commitments": len(case["commitments"]) if case else 0,
            "alert_id": alert["alert_id"] if alert else None,
            "risk_label": alert["risk_label"] if alert else None,
        },
        "control": {
            "case_state": case["state"] if case else None,
            "label": (
                f"{catalog.CASE_STATES[case['state']]} / 생산계획 변경 전"
                if case
                else "열린 사건 없음"
            ),
            "analysis_version": analysis["version"] if analysis else None,
        },
        "cases": cases,
        "revisions": [
            {
                "revision_id": e["revision_id"],
                "registered_at": e["registered_at"],
                "lots": [{"qty": lot["qty"], "planned_at": lot["planned_at"]} for lot in e["lots"]],
                "judgment": e["judgment"],
                "judgment_label": LABEL[e["judgment"]],
            }
            for e in events
        ],
        "open_commitments": calc.open_commitments(master, _latest_lots(doc), as_of),
        "notice": (
            "가상 시연 자료 — 실적은 이미 납기가 도래한 약정의 인수실적이고, 이 통지로 "
            "바뀌지 않는다"
        ),
    }


def records_of(doc: dict, master: dict) -> list[dict[str, Any]]:
    """지금 문서의 장면 1 기록 전부(판 번호 없이)."""
    head = {
        "demoRunId": doc["demo_run_id"],
        "scenario": doc["scenario"],
        "scene": doc["scene"],
        "title": TITLE,
        "caseId": doc["case_id"],
        "clock": doc["clock"],
        "executor": doc["executor"],
        "runs": [
            {
                "doc_id": r["doc_id"],
                "revision_id": r["revision_id"],
                "received_at": r["received_at"],
                "outcome": r["outcome"],
                "outcome_label": LABEL.get(r["outcome"] or "", None),
                **{
                    k: r["run"][k]
                    for k in ("job_id", "external_run_id", "state", "visited", "problem")
                },
            }
            for r in sorted(doc["receipts"].values(), key=lambda r: r["doc_id"])
        ],
        "companyLog": doc["company_log"],
        "handoff": doc["handoff"]["next_node"] if doc["handoff"] else None,
    }
    state = (
        "HANDED_OFF" if doc["handoff"] else (doc["case"]["state"] if doc["case"] else "MONITORING")
    )
    out = [record("scene", "S2:SC01", state, TITLE, head)]
    for e in sorted(doc["events"].values(), key=lambda e: (e["po_line"], e["revision_no"])):
        out.append(
            record(
                "event",
                e["event_id"],
                e["judgment"],
                f"{e['revision_id']} {LABEL[e['judgment']]}",
                _event_body(e),
            )
        )
    if doc["alert"] is not None:
        out.append(
            record("alert", ALERT_ID, doc["alert"]["risk_level"], doc["alert"]["kri"], doc["alert"])
        )
    if doc["case"] is not None:
        out.append(
            record("case", CASE_ID, doc["case"]["state"], doc["case"]["title"], _case_body(doc))
        )
    if doc["analyses"]:
        a = doc["analyses"][-1]
        out.append(record("analysis", ANALYSIS_ID, "SUCCEEDED", f"영향 분석 v{a['version']}", a))
    if doc["handoff"] is not None:
        out.append(record("handoff", HANDOFF_ID, "N03A", "장면 2 인계", doc["handoff"]))
    out.append(record("dashboard", "company1:ULS:A", None, "납기 상황판", dashboard(doc, master)))
    return out


__all__ = ["KINDS", "TITLE", "dashboard", "records_of"]
