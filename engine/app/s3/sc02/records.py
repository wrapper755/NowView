"""
시나리오 3 장면 2의 경영 기록 — 분석 실행·계산 결과·첨부 Excel·항목 검토·보고 건·인계·체크리스트
집계(`docs/s3/sc02.md`, 스키마 `docs/records/s3/sc02/`).

회사 사이트의 분석 지시·실행 및 첨부·계산 근거 검토·보고 및 상신 화면과 NowView 대시보드가 이 기록만
읽는다 — 둘 다 계산하지 않는다. 장면 1과 같은 회차에 적으므로 장면 1 기록(체크리스트 `dashboard`
S3-CLOSE-01·`close_item`·`handoff` HAND-S3-01)과 id가 겹치지 않게 짓는다(기간계 키는
kind/record_id).
"""

from __future__ import annotations

from typing import Any

from app.records import record
from app.s3.sc02.process import (
    CLOSE_ID,
    ENTRY_HANDOFF,
    HANDOFF_ID,
    REVIEW_ORDER,
    STATE_LABEL,
    attachment_of,
    item_state,
    latest_result,
    latest_run,
    review_of,
)

TITLE = "결산조정 계산 및 담당자 검토"
BOARD_ID = f"{CLOSE_ID}:SC02"
KINDS = {
    "scene": (
        "장면 머리 — 시연 시각·실행 위치·BPM 실행(지나온 노드·대기)·분석 지시(지시문·버전·"
        "연결 자료)·"
        "장면 1 인계·낡은 결과·흐름 01~07·회사와 오간 것"
    ),
    "analysis_run": (
        "분석 실행(M22) — 결산 건·두 업무·실행자·입력·정책·프롬프트·서식 버전·실행 방식(모의/실제)·"
        "작업 단계와 응답 시각·대사·분류 건수·보완 대상"
    ),
    "close_result": (
        "계산 결과(결과 버전) — 두 항목의 계산·대사·승인 요약 행·Agent 문안(수치마다 결과 칸 참조)"
    ),
    "attachment": "첨부 Excel — 파일 id·버전·실행·결과 버전·지문·전송 시도·열기 확인·승인요약 칸",
    "item_review": "항목 검토 — 검토자·검토 시각·결과 버전·첨부·검토 동선·승계 여부",
    "close_report": (
        "보고 건(REP-S3-01) — 두 항목 요청액·변동 사유·주석 발췌·첨부·실행·검토자·수신 회계팀장"
    ),
    "handoff": (
        "장면 3 인계(HAND-S3-02) — 보고 ID·버전·두 항목 요청액·요약·첨부 참조·팀장 수신 업무"
    ),
    "dashboard": "결산 체크리스트(장면 2) — 항목별 단계·요청액·검토·승인 대기·상신 보고·승인",
}

NEXT_ACTION = {
    "WAITING_RUN": "분석 지시 보기",
    "RUNNING": "처리 이력 보기",
    "ATTACH_WAIT": "첨부 재시도",
    "NEEDS_FIX": "보완 근거 보기",
    "REVIEW_WAIT": "첨부 열고 검토",
    "REVIEWED": "보고 초안 보기",
    "STALE": "다시 분석 실행",
    "SUBMITTED": "팀장 승인 대기",
}


def dashboard(doc: dict) -> dict[str, Any]:
    """
    체크리스트(장면 2) — 항목별 단계와 요청액. 상신은 고유 보고 건 수, 승인·전표·주석은 장면 3 뒤라
    0이다(구현명세 §3 「두 업무가 승인 대기이고 상신 보고 1건·승인 완료 0건」).
    """
    run, res = latest_run(doc), latest_result(doc)
    att = attachment_of(doc, res["result_version"]) if res else None
    summary = (
        {s["item"]: s for s in res["calc"]["summary"]} if res and res["state"] == "DONE" else {}
    )
    rows = []
    for item in doc["items"].values():
        state = item_state(doc, item["item_id"])
        rev = review_of(doc, item["item_id"], res["result_version"]) if res else None
        s = summary.get(item["item_id"]) or {}
        rows.append(
            {
                "item_id": item["item_id"],
                "work_id": item["work_id"],
                "name": item["name"],
                "owner_name": item["owner_name"],
                "owner_id": item["owner_id"],
                "state": state,
                "state_label": STATE_LABEL[state],
                "next_action": NEXT_ACTION[state]
                if not (state == "WAITING_RUN" and item["item_id"] != "ALW")
                else "같은 실행 범위(충당금 행에서 실행)",
                "prior": s.get("prior"),
                "current": s.get("current"),
                "change": s.get("change"),
                "book": s.get("book"),
                "request": s.get("request"),
                "request_label": s.get("request_label"),
                "result_version": res["result_version"] if res else None,
                "review_id": rev["review_id"] if rev else None,
                "reviewed_at": rev["reviewed_at"] if rev else None,
                "report_id": doc["report"]["report_id"] if doc["report"] else None,
                "approval": "WAITING" if doc["report"] else "NOT_SUBMITTED",
                "follow_up": [{"task": t, "state": "WAITING_APPROVAL"} for t in item["follow_up"]],
            }
        )
    count = len(rows)
    reviewed = sum(1 for r in rows if r["review_id"])
    return {
        "close_id": CLOSE_ID,
        "title": doc["close"]["title"],
        "period_end": doc["close"]["period_end"],
        "comparative_end": doc["close"]["comparative_end"],
        "as_of": doc["clock"],
        "scope": {"label": "시연 대상 2항목", "items": count},
        "input_version": run["input_version"] if run else doc["entry"]["input_version"],
        "run": None
        if run is None
        else {
            k: run[k]
            for k in (
                "run_id",
                "state",
                "last_success",
                "last_response_at",
                "execution_mode",
            )
        },
        "result_version": res["result_version"] if res else None,
        "file": None
        if att is None
        else {k: att[k] for k in ("file_id", "file_version", "filename", "state")},
        "max_diff_won": res["calc"]["max_diff_won"] if res else None,
        "reviewed": {"done": reviewed, "of": count},
        "waiting_approval": sum(1 for r in rows if r["approval"] == "WAITING"),
        "reports": 1 if doc["report"] else 0,
        "approved": {"done": 0, "of": count},
        "posting": {"done": 0, "of": count},
        "notes": {"done": 0, "of": count},
        "stale": doc["stale"],
        "rows": rows,
        "note": (
            "승인 요청액(조정 전 장부 대비)과 전기 대비 증감은 다른 숫자다 — 승인·전표 반영·주석 "
            "취합은 장면 3 뒤"
        ),
    }


def _flow(doc: dict) -> list[dict[str, Any]]:
    """업무설계표 01~07의 진행 — 지시 열람(01)은 기록을 만들지 않는 조회다."""
    run, res = latest_run(doc), latest_result(doc)
    run_state = run["state"] if run else None
    steps = {s["step"]: s["state"] for s in run["steps"]} if run else {}

    def done(cond: bool, running: bool = False) -> str:
        return "done" if cond else ("running" if running else "waiting")

    reviewed = {i: bool(res and review_of(doc, i, res["result_version"])) for i in REVIEW_ORDER}
    return [
        {"step": "01", "name": "분석 지시 열기", "role": "회계담당", "state": "view"},
        {"step": "02", "name": "실행 요청", "role": "회계담당", "state": done(run is not None)},
        {
            "step": "03",
            "name": "대손충당금 산출",
            "role": "계산 기능",
            "state": "blocked"
            if run_state == "NEEDS_FIX"
            else done(steps.get("CALCULATED") == "done", run_state == "PENDING"),
        },
        {
            "step": "04",
            "name": "감가상각비 산출",
            "role": "계산 기능",
            "state": done(steps.get("CALCULATED") == "done", run_state == "PENDING"),
        },
        {
            "step": "05",
            "name": "변동 설명과 첨부 생성",
            "role": "Agent · 연계 PC(모의)",
            "state": "blocked"
            if run_state == "ATTACH_WAIT"
            else done(steps.get("REVIEW_READY") == "done", steps.get("FILE_CREATED") == "done"),
        },
        {
            "step": "06",
            "name": "계산 근거 검토",
            "role": "회계담당",
            "state": done(all(reviewed.values()), any(reviewed.values())),
        },
        {
            "step": "07",
            "name": "한 건 상신",
            "role": "회계담당",
            "state": done(doc["report"] is not None),
        },
    ]


def _scene_state(doc: dict) -> str:
    if doc["report"] is not None:
        return "SUBMITTED"
    if doc["stale"]:
        return "STALE"
    run = latest_run(doc)
    if run is None:
        return "WAITING_RUN"
    return "REVIEWING" if run["state"] == "REVIEW_READY" else "RUNNING"


def records_of(doc: dict) -> list[dict]:
    """지금 문서의 장면 2 기록 전부(판 번호 없이)."""
    bpm = doc["bpm"]
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
        "entry": {**doc["entry"], "handoff_id": ENTRY_HANDOFF},
        "instruction": doc["instruction"],
        "stale": doc["stale"],
        "flow": _flow(doc),
        "runs": [r["run_id"] for r in doc["runs"]],
        "companyLog": doc["company_log"],
        "report": doc["report"]["report_id"] if doc["report"] else None,
        "handoff": HANDOFF_ID if doc["handoff"] else None,
    }
    state = _scene_state(doc)
    out = [record("scene", "S3:SC02", state, TITLE, head)]
    for run in doc["runs"]:
        out.append(
            record("analysis_run", run["run_id"], run["state"], f"분석 실행 {run['run_id']}", run)
        )
    for res in doc["results"]:
        out.append(
            record(
                "close_result",
                res["result_version"],
                res["state"],
                f"계산 결과 {res['result_version']} — 입력 {res['input_version']}",
                res,
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
                f"{name} 검토 {rev['result_version']}",
                rev,
            )
        )
    if doc["report"] is not None:
        r = doc["report"]
        out.append(record("close_report", r["report_id"], r["state"], r["title"], r))
    if doc["handoff"] is not None:
        out.append(record("handoff", HANDOFF_ID, "SUBMITTED", "장면 3 인계", doc["handoff"]))
    out.append(record("dashboard", BOARD_ID, state, "결산 체크리스트 — 장면 2", dashboard(doc)))
    return out


__all__ = ["BOARD_ID", "KINDS", "TITLE", "dashboard", "records_of"]
