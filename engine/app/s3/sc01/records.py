"""
시나리오 3 장면 1의 경영 기록 — 결산 건·조정항목(체크리스트 행)·점검·보완 요청·인계·체크리스트
집계(`docs/s3/common.md` §3, 스키마 `docs/records/s3/sc01/`).

회사 사이트의 결산 체크리스트·입력자료 점검·준비 결과 화면과 NowView 대시보드가 이 기록만 읽는다 —
둘 다 판정하지 않는다. 시나리오 3 회차에는 시나리오 3 기록만 있으므로 record_id에 장면 접두를 붙이지
않는다.
"""

from __future__ import annotations

from typing import Any

from app.records import record
from app.s3.sc01 import calc
from app.s3.sc01.process import CLOSE_ID, HANDOFF_ID, STATE_LABEL, next_action

TITLE = "결산조정 업무 착수"
KINDS = {
    "scene": (
        "장면 머리 — 시연 시각·실행 위치·BPM 실행(지나온 노드·대기)·재점검 실행 이력·회사와 오간 것"
    ),
    "close_case": "결산 건 — 기간·비교기간·결산 일정·검토자·입력 허용목록·연결된 입력 버전 이력",
    "close_item": (
        "조정항목(체크리스트 한 행) — 원업무·담당·기한·잔여일·단계·보완·재점검 사유·다음 조치·"
        "승인·상신·후속 업무 상태"
    ),
    "input_check": (
        "입력자료 점검 — 항목·입력 버전·점검자·검사별 판정(기대값·확인값·근거)·근거 요약"
    ),
    "fix_request": "보완 요청 — 대상 시트·행·기대값·확인값·보완 담당·기한·해소 버전",
    "handoff": "장면 2 인계(HAND-S3-01) — 입력 버전·허용 시트·항목별 준비·점검 근거·다음 조치",
    "dashboard": "결산 체크리스트 집계 — 조회 범위·준비·보완·승인·상신·전표 반영·주석 취합",
}


def _row(doc: dict, item: dict) -> dict[str, Any]:
    clock = doc["clock"]
    fix = next((f for f in doc["fixes"] if f["fix_id"] == item["fix"]), None)
    remaining = calc.remaining_days(clock, item["due"]) if clock else None
    return {
        "close_id": CLOSE_ID,
        "item_id": item["item_id"],
        "work_id": item["work_id"],
        "name": item["name"],
        "owner_role": item["owner_role"],
        "owner_name": item["owner_name"],
        "owner_id": item["owner_id"],
        "sheets": item["sheets"],
        "due": item["due"],
        "remaining_days": remaining,
        #: 기한 경과와 자료 보완은 따로 표시한다(화면 01)
        "overdue": remaining is not None and remaining < 0 and item["state"] != "READY",
        "state": item["state"],
        "state_label": STATE_LABEL[item["state"]],
        "started_at": item["started_at"],
        "checked_version": item["checked_version"],
        "last_check": item["last_check"],
        "fix": None
        if fix is None
        else {
            "fix_id": fix["fix_id"],
            "state": fix["state"],
            "owners": fix["owners"],
            "due": fix["due"],
            "reasons": [f["reason"] for f in fix["findings"]],
        },
        "recheck_reason": item["recheck_reason"],
        "next_action": next_action(item),
        "approval": "NOT_SUBMITTED",
        "report_id": None,
        "follow_up": [{"task": t, "state": "WAITING_APPROVAL"} for t in item["follow_up"]],
        "checks": item["checks"],
    }


def dashboard(doc: dict) -> dict[str, Any]:
    """
    체크리스트 집계 — 분모는 조회 범위(시연 두 항목)다. 준비 완료는 전체 결산마감 완료가 아니다.
    승인·상신·전표 반영·주석 취합은 장면 3 뒤의 일이라 0이다.
    """
    items = list(doc["items"].values())
    rows = [_row(doc, i) for i in items]
    count = len(items)
    states = [i["state"] for i in items]
    return {
        "close_id": CLOSE_ID,
        "title": doc["close"]["title"],
        "period_end": doc["close"]["period_end"],
        "comparative_end": doc["close"]["comparative_end"],
        "as_of": doc["clock"],
        "scope": {"label": "시연 대상 2항목", "items": count},
        "input_version": doc["current_version"],
        "ready": {"done": states.count("READY"), "of": count},
        "needs_fix": states.count("NEEDS_FIX"),
        "recheck": states.count("RECHECK"),
        "overdue": sum(1 for r in rows if r["overdue"]),
        "approved": {"done": 0, "of": count},
        "reports": 0,
        "posting": {"done": 0, "of": count},
        "notes": {"done": 0, "of": count},
        "rows": [
            {
                k: r[k]
                for k in (
                    "item_id",
                    "work_id",
                    "name",
                    "owner_name",
                    "owner_id",
                    "due",
                    "remaining_days",
                    "overdue",
                    "state",
                    "state_label",
                    "next_action",
                )
            }
            | {"fix_reason": "; ".join(r["fix"]["reasons"]) if r["fix"] else None}
            for r in rows
        ],
        "note": "준비 완료는 결산마감 완료가 아니다 — 전표 반영·주석 취합은 승인 후 인계 예정",
    }


def _flow(doc: dict) -> list[dict[str, Any]]:
    """업무설계표 01~06의 진행 — 조회(01·02)는 사람의 기록을 만들지 않는다."""
    started = any(i["started_at"] for i in doc["items"].values())
    states = {i["item_id"]: i["state"] for i in doc["items"].values()}

    def item_state(it: str) -> str:
        s = states[it]
        return {"READY": "done", "NEEDS_FIX": "blocked", "RECHECK": "running"}.get(
            s, "running" if doc["bpm"]["waiting"] else "waiting"
        )

    return [
        {"step": "01", "name": "진행상황 조회", "role": "회계팀장", "state": "view"},
        {"step": "02", "name": "내 업무 열기", "role": "회계담당", "state": "view"},
        {
            "step": "03",
            "name": "자료 연결 확인",
            "role": "BPM",
            "state": "done" if "Task_Link" in doc["bpm"]["visited"] else "waiting",
        },
        {
            "step": "04",
            "name": "감가상각비 준비 점검",
            "role": "회계담당",
            "state": item_state("DEP"),
        },
        {
            "step": "05",
            "name": "대손충당금 준비 점검",
            "role": "회계담당",
            "state": item_state("ALW"),
        },
        {
            "step": "06",
            "name": "장면 2 인계",
            "role": "BPM",
            "state": "done"
            if doc["handoff"] and doc["handoff"]["valid"]
            else ("waiting" if not started else "pending"),
        },
    ]


def records_of(doc: dict) -> list[dict]:
    """지금 문서의 장면 1 기록 전부(판 번호 없이)."""
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
            for k in (
                "state",
                "job_id",
                "external_run_id",
                "visited",
                "waiting",
                "problem",
                "reason",
            )
        },
        "bpmHistory": [
            {k: b[k] for k in ("state", "job_id", "external_run_id", "problem", "reason")}
            for b in doc["bpm_history"]
        ],
        "flow": _flow(doc),
        "companyLog": doc["company_log"],
        "handoff": HANDOFF_ID if doc["handoff"] and doc["handoff"]["valid"] else None,
    }
    # 「준비 2/2 · 인계 전」도 점검 중이다 — READY는 시나리오 1 장면 머리의 「사건 전」과 겹친다
    state = "HANDED_OFF" if head["handoff"] else "CHECKING"
    out = [record("scene", "S3:SC01", state, TITLE, head)]
    close = {
        **doc["close"],
        "input_version": doc["current_version"],
        "inputs": doc["inputs"],
        "items": [i["item_id"] for i in doc["items"].values()],
    }
    out.append(record("close_case", CLOSE_ID, state, doc["close"]["title"], close))
    for item in doc["items"].values():
        out.append(
            record(
                "close_item",
                item["work_id"],
                item["state"],
                f"{item['name']} — {STATE_LABEL[item['state']]}",
                _row(doc, item),
            )
        )
    for c in doc["checks"]:
        name = doc["items"][c["item"]]["name"]
        out.append(
            record("input_check", c["check_id"], c["result"], f"{name} 점검 {c['version']}", c)
        )
    for f in doc["fixes"]:
        name = doc["items"][f["item"]]["name"]
        out.append(record("fix_request", f["fix_id"], f["state"], f"{name} 보완 요청", f))
    if doc["handoff"] is not None:
        h = doc["handoff"]
        out.append(
            record("handoff", HANDOFF_ID, "VALID" if h["valid"] else "STALE", "장면 2 인계", h)
        )
    out.append(record("dashboard", CLOSE_ID, None, "결산 체크리스트", dashboard(doc)))
    return out


__all__ = ["KINDS", "TITLE", "dashboard", "records_of"]
