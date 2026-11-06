"""
시나리오 3 장면 3의 경영 기록 — 보고 버전·결정·보완 요청·(보완 재계산의 실행·결과·첨부·검토)·후속
업무·인계·체크리스트 집계(`docs/s3/sc03.md`, 스키마 `docs/records/s3/sc03/`).

회사 사이트의 승인 요약·근거와 결정·승인 후 체크리스트 화면과 NowView 대시보드가 이 기록만 읽는다 —
둘 다 계산하지 않는다. 장면 1·2와 같은 회차에 적으므로 id가 겹치지 않게 짓는다(기간계 키는
kind/record_id) — 보고 버전은 `REP-S3-01:v{n}`, 보완 재계산의 실행·결과·파일·검토 번호는 장면 2에
이어진다.
"""

from __future__ import annotations

from typing import Any

from app.records import record
from app.s3.sc03.process import (
    APPROVAL_SCOPE,
    CLOSE_ID,
    ENTRY_HANDOFF,
    HANDOFF_ID,
    REPORT_ID,
    STATE_LABEL,
    VERSION_LABEL,
    approved,
    current,
    item_state,
    latest_result,
    open_revision,
)

TITLE = "팀장 보고 및 승인"
BOARD_ID = f"{CLOSE_ID}:SC03"
KINDS = {
    "scene": (
        "장면 머리 — 시연 시각·실행 위치·BPM 실행(지나온 노드·대기)·장면 2 인계·현재 보고 버전·"
        "결정 보류·입력 변경 알림·흐름 01~06·회사와 오간 것"
    ),
    "report_version": (
        "제출본(보고 버전) — 두 항목 요청액·변동 사유·주석·근거(A사 개별평가·회수 회차·영업/회계 "
        "확인·충당금비교·상각비 귀속)·첨부·검토·변경 내역·이전 보완 사유·상태"
    ),
    "approval_decision": "결정 — 승인/보완 요청·결정자·시각·보고 버전·결과·첨부·대상·사유",
    "report_revision": (
        "보완 요청 — 대상 항목·사유·담당·원 제출본·처리(참조 보강/재계산/재상신)·새 버전"
    ),
    "analysis_run": "보완 재계산의 실행 — 장면 2 실행과 같은 모양(번호는 장면 2에 이어진다)",
    "close_result": "보완 재계산의 결과 — 두 항목의 계산·대사·승인 요약 행·Agent 문안",
    "attachment": "보완 재계산의 첨부 Excel — 파일 id·버전·지문·열기 확인·승인요약 칸",
    "item_review": "보완 재검토 — 참조 보강 재검토·재계산 뒤 영향 항목 검토·승계",
    "followup": "후속 업무 — 전표 반영·주석 취합 담당에게 등록한 항목별 업무(반영·취합 대기)",
    "handoff": "후속 인계(HAND-S3-03) — 승인 보고 ID·버전·두 경로의 담당·후속 업무 ID",
    "dashboard": (
        "결산 체크리스트(장면 3) — 항목별 승인 단계·보완 사유·후속 업무 상태, 승인·보고·전표·"
        "주석 집계"
    ),
}

NEXT_ACTION = {
    "WAITING": "승인 요약 열기",
    "NEEDS_REVISION": "보완 근거 보기",
    "REVIEWED_WAIT": "공통 보고 보완 대기",
    "APPROVED": "후속 업무 보기",
}
FOLLOW_LABEL = {
    "WAITING_APPROVAL": "승인 후 인계",
    "REQUESTED": "인계 요청",
    "HANDOFF_WAIT": "인계 대기",
}


def _follow(doc: dict, path: str, item_id: str) -> dict[str, Any]:
    """한 행의 후속 경로 상태 — 등록 전이면 경로 상태, 등록됐으면 그 항목의 후속 업무."""
    p = doc["followups"][path]
    task = next((t for t in p["tasks"] if t["item_id"] == item_id), None)
    if task is None:
        state, label = p["state"], FOLLOW_LABEL.get(p["state"], p["state"])
    else:
        state, label = task["state"], p["waiting"]
    return {
        "path": path,
        "label": p["label"],
        "state": state,
        "state_label": label,
        "assignee": p["assignee"],
        "task_id": task["task_id"] if task else None,
        "note_sheet": task.get("note_sheet") if task else None,
        "reason": p["reason"] if task is None else None,
        "done": False,
    }


def dashboard(doc: dict) -> dict[str, Any]:
    """
    체크리스트(장면 3) — 승인 항목 수는 원업무 id, 승인 보고 수는 보고 id, 후속 처리 수는 항목별
    실제 완료 이력으로 센다(구현명세 §3 — 승인 2/2 · 보고 1건 · 전표 0/2 · 주석 0/2가 함께 성립).
    """
    ver = current(doc)
    rev = open_revision(doc)
    dec = approved(doc)
    items = {i["item_id"]: i for i in ver["items"]}
    rows = []
    for item in doc["items"].values():
        it = items[item["item_id"]]
        state = item_state(doc, item["item_id"])
        rows.append(
            {
                "item_id": item["item_id"],
                "work_id": item["work_id"],
                "name": item["name"],
                "owner_name": item["owner_name"],
                "owner_id": item["owner_id"],
                "state": state,
                "state_label": STATE_LABEL[state],
                "next_action": NEXT_ACTION[state],
                "report_id": REPORT_ID,
                "report_version": ver["version"],
                **{k: it[k] for k in ("prior", "current", "change", "book", "request")},
                "request_label": it["request_label"],
                "revision": None
                if rev is None or item["item_id"] not in rev["targets"]
                else {
                    "revision_id": rev["revision_id"],
                    "reason": rev["reason"],
                    "owner": rev["owner"]["owner_name"],
                },
                "approved_by": dec["decided_by"] if dec else None,
                "approved_at": dec["decided_at"] if dec else None,
                "posting": _follow(doc, "POSTING", item["item_id"]),
                "notes": _follow(doc, "NOTES", item["item_id"]),
            }
        )
    count = len(rows)

    def done(key: str) -> int:
        return sum(1 for r in rows if r[key]["done"])

    return {
        "close_id": CLOSE_ID,
        "title": doc["close"]["title"],
        "period_end": doc["close"]["period_end"],
        "comparative_end": doc["close"]["comparative_end"],
        "as_of": doc["clock"],
        "scope": {"label": "시연 대상 2항목", "items": count},
        "report": {
            "report_id": REPORT_ID,
            "version": ver["version"],
            "state": ver["state"],
            "state_label": VERSION_LABEL[ver["state"]],
            "result_version": ver["result_version"],
            "file_id": ver["attachment"]["file_id"],
            "versions": len(doc["versions"]),
        },
        "waiting_approval": sum(1 for r in rows if r["state"] == "WAITING"),
        "approved": {"done": sum(1 for r in rows if r["state"] == "APPROVED"), "of": count},
        "reports": 1,
        "reports_approved": 1 if dec else 0,
        "revisions": len(doc["revisions"]),
        "posting": {"done": done("posting"), "of": count},
        "notes": {"done": done("notes"), "of": count},
        "handed": {
            "done": sum(1 for p in doc["followups"].values() if p["state"] == "REGISTERED"),
            "of": len(doc["followups"]),
        },
        "hold": doc["hold"],
        "rows": rows,
        "note": (
            "승인 항목 수는 원업무, 승인 보고 수는 보고 ID, 전표 반영·주석 취합은 항목별 실제 "
            "완료로 센다 — 승인 직후에는 0/2다. 전체 회사 마감 상태는 별도"
        ),
    }


def _flow(doc: dict) -> list[dict[str, Any]]:
    """업무설계표 01~06의 진행 — 열람(01~03)은 결재 기록을 만들지 않는 조회다."""
    ver = current(doc)
    dec = approved(doc)

    def done(cond: bool, running: bool = False) -> str:
        return "done" if cond else ("running" if running else "waiting")

    returned = bool(doc["revisions"])
    handed = [p["state"] for p in doc["followups"].values()]
    return [
        {"step": "01", "name": "보고 열람", "role": "회계팀장", "state": "view"},
        {"step": "02", "name": "승인 요청액 검토", "role": "회계팀장", "state": "view"},
        {"step": "03", "name": "대표 판단 근거 확인", "role": "회계팀장", "state": "view"},
        {
            "step": "04A",
            "name": "승인",
            "role": "회계팀장",
            "state": done(dec is not None),
        },
        {
            "step": "04B",
            "name": "보완 요청",
            "role": "회계팀장",
            "state": "done" if returned else "skipped",
        },
        {
            "step": "05",
            "name": "수정본 재상신",
            "role": "회계담당",
            "state": "skipped"
            if not returned
            else done(open_revision(doc) is None, ver["state"] == "RETURNED"),
        },
        {
            "step": "06",
            "name": "후속 인계 확인",
            "role": "BPM · 회계팀장",
            "state": "blocked"
            if "HANDOFF_WAIT" in handed
            else done(doc["handoff"] is not None, dec is not None),
        },
    ]


def _scene_state(doc: dict) -> str:
    ver = current(doc)
    if doc["handoff"] is not None:
        return "DONE"
    if ver["state"] == "APPROVED":
        return "HANDING_OFF"
    if ver["state"] == "RETURNED":
        return "RETURNED"
    return "WAITING"


def records_of(doc: dict) -> list[dict]:
    """지금 문서의 장면 3 기록 전부(판 번호 없이)."""
    bpm = doc["bpm"]
    ver = current(doc)
    res = latest_result(doc)
    head = {
        "demoRunId": doc["demo_run_id"],
        "scenario": doc["scenario"],
        "scene": doc["scene"],
        "title": TITLE,
        "caseId": doc["case_id"],
        "clock": doc["clock"],
        "executor": doc["executor"],
        "bpm": {
            k: bpm[k]
            for k in ("state", "job_id", "external_run_id", "visited", "waiting", "problem")
        },
        "close": doc["close"],
        "approver": doc["approver"],
        "entry": {**doc["entry"], "handoff_id": ENTRY_HANDOFF},
        "report": {
            "report_id": REPORT_ID,
            "version": ver["version"],
            "record_id": f"{REPORT_ID}:v{ver['version']}",
            "state": ver["state"],
            "result_version": ver["result_version"],
            "file_id": ver["attachment"]["file_id"],
            "approval_scope": APPROVAL_SCOPE,
        },
        "latest_result": res["result_version"],
        "hold": doc["hold"],
        "holds": doc["holds"],
        "input_notice": doc["input_notice"],
        "flow": _flow(doc),
        "decisions": [d["decision_id"] for d in doc["decisions"]],
        "companyLog": doc["company_log"],
        "handoff": HANDOFF_ID if doc["handoff"] else None,
    }
    out = [record("scene", "S3:SC03", _scene_state(doc), TITLE, head)]
    for v in doc["versions"]:
        out.append(
            record(
                "report_version",
                f"{REPORT_ID}:v{v['version']}",
                v["state"],
                f"{v['title']} v{v['version']}",
                v,
            )
        )
    for d in doc["decisions"]:
        out.append(
            record(
                "approval_decision",
                d["decision_id"],
                d["decision"],
                f"{d['label']} — {REPORT_ID} v{d['report_version']}",
                d,
            )
        )
    for r in doc["revisions"]:
        out.append(
            record(
                "report_revision",
                r["revision_id"],
                r["state"],
                f"보완 요청 — {REPORT_ID} v{r['base_version']}",
                r,
            )
        )
    for run in doc["runs"]:
        out.append(
            record("analysis_run", run["run_id"], run["state"], f"분석 실행 {run['run_id']}", run)
        )
    for r in doc["results"]:
        out.append(
            record(
                "close_result",
                r["result_version"],
                r["state"],
                f"계산 결과 {r['result_version']} — 입력 {r['input_version']}",
                r,
            )
        )
    for att in doc["attachments"]:
        out.append(record("attachment", att["file_id"], att["state"], att["filename"], att))
    for rev in doc["reviews"]:
        name = doc["items"][rev["item"]]["name"]
        out.append(
            record(
                "item_review",
                rev["review_id"],
                rev["state"] if rev["valid"] else "INVALID",
                f"{name} 재검토 {rev['result_version']}",
                rev,
            )
        )
    for p in doc["followups"].values():
        for t in p["tasks"]:
            body = {
                **t,
                "path": p["path"],
                "label": p["label"],
                "assignee": p["assignee"],
                "waiting": p["waiting"],
                "report_id": REPORT_ID,
                "report_version": doc["handoff"]["report_version"]
                if doc["handoff"]
                else ver["version"],
                "registered_at": p["registered_at"],
                "recovered": p["recovered"],
            }
            out.append(
                record("followup", t["task_id"], t["state"], f"{p['label']} — {t['name']}", body)
            )
    if doc["handoff"] is not None:
        out.append(record("handoff", HANDOFF_ID, "DONE", "후속 업무 인계", doc["handoff"]))
    out.append(
        record("dashboard", BOARD_ID, _scene_state(doc), "결산 체크리스트 — 장면 3", dashboard(doc))
    )
    return out


__all__ = ["BOARD_ID", "KINDS", "TITLE", "dashboard", "records_of"]
