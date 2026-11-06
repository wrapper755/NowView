"""
시나리오 2 장면 4의 경영 기록 — 공통 기록 종류(`docs/platform.md` §3, 스키마
`docs/records/s2/sc04/`).

회사 사이트의 화면(UI-B05 실행 결과 · UI-A03/A04 개선안 재현 · UI-A04 → A02 검증과 적용)과 NowView
대시보드(UI-D01)가 이 기록만 읽는다 — 둘 다 계산하지 않는다. Case 기록은 장면 1 문서의 것이라 쓰지
않는다. 개선은 별도 개선 건(IMP-04)이 사건을 참조한다(사건 수행계획을 바꾸지 않는다).
"""

from __future__ import annotations

from typing import Any

from app.platform import catalog
from app.records import record
from app.s2.sc01 import calc as sc01_calc
from app.s2.sc04 import calc
from app.s2.sc04.process import CASE_ID

TITLE = "실행 결과 확인과 관리기준 개선"
BOARD_ID = "company1:ULS:A:SC04"
KINDS = {
    "scene": "장면 머리 — 시연 시각·실행 위치·BPM 실행·장면 3 인계 사본·회사와 오간 것·흐름",
    "outcome": (
        "결정과 실적 대조(M05·M10, N11) — 약정별 원결정·예약·인수·정산 증빙·여유·정시 전량·"
        "실제 추가비·결정 조건 대비"
    ),
    "improvement": (
        "관리기준 개선 건(M25, N12·N13) — 개선 사유·KRI·Control 개정 초안·유지 기준·H06 착수 판단"
    ),
    "replay": (
        "당시 자료 재현(M14·M26, N14) — SNAP-0900 초기선별·변경 접수 마감·요청 초안·송신·접수증·"
        "회신·타 고객 영향·채택 판정·기존 사건 대비"
    ),
    "verification": (
        "인수시험(M26, N14) — 8개 회신 분기·시험 01~09의 기대·실제·판정·표본 대조·H07 판정"
    ),
    "confirmation": "기준 적용 확인(M12, N15) — APP-04 적용 범위·효력시점·H06 확인",
    "config": ("위임 설정(M18·M19, N16) — CFG-04 운영 버전·효력시점·H07 반영·사건별 적용 버전"),
    "dashboard": (
        "납기 상황판(UI-D01) 장면 4 몫 — 정시 전량·실제 추가비·재현 여유·앞당김·접수 여유·조건부 "
        "회피·10월 OTD·적용 상태"
    ),
}

#: 이 장면의 역할과 하는 일(업무설계표 D09~D11, 상세화면구성 05 「사람과 Agent」)
PARTICIPANTS = [
    ("Y01", "증빙 연결·결과 대조 · 마감 계산 · 시험 대조", ["N11", "N14"]),
    ("A01", "결과 요약 · 개정 초안 · 위험 선별 · 요청 초안 · 영향 후보", ["N11", "N13", "N14"]),
    ("H04", "조정 요청 확인·송신 · 타 고객 영향 확인", ["N14"]),
    ("H06", "개선 착수 · 적용 범위·효력시점 확인", ["N12", "N15"]),
    ("H07", "시험 판정 기록 · 위임 설정 반영", ["N14", "N16"]),
]

FLOW = [
    ("N11", "결정과 실적 대조", "Y01"),
    ("N12", "개선 착수", "H06"),
    ("N14R", "당시 자료 재현·요청", "H04"),
    ("N14T", "인수시험", "H07"),
    ("N15", "기준 적용 확인", "H06"),
    ("N16", "위임 설정·다음 사건", "H07"),
]


def _state(doc: dict, node: str) -> str:
    """흐름 단계 상태 — 기록에서 파생한다(BPM 토큰을 저장하지 않는다)."""
    o, imp, rp, v, a, cfg = (
        doc["outcome"],
        doc["improvement"],
        doc["replay"],
        doc["verification"],
        doc["approval"],
        doc["config"],
    )
    stopped = (imp or {}).get("state") == "NOT_NEEDED"
    if node == "N11":
        if o is None:
            return "waiting"
        return "done" if o["ready"] else "awaiting"
    if node == "N12":
        if imp is None:
            return "awaiting" if o is not None and o["ready"] else "waiting"
        return "skipped" if stopped else "done"
    if node == "N14R":
        if stopped:
            return "skipped"
        if rp is None:
            return "waiting"
        return "done" if rp.get("adoption") is not None else "awaiting"
    if node == "N14T":
        if stopped:
            return "skipped"
        if v is None:
            return "waiting"
        return {"RUN": "awaiting", "PASSED": "done", "REWORK": "blocked"}[v["state"]]
    if node == "N15":
        if stopped or (v or {}).get("state") == "REWORK":
            return "skipped"
        if a is None:
            return "awaiting" if (v or {}).get("state") == "PASSED" else "waiting"
        return "done" if a["state"] == "CONFIRMED" else "blocked"
    if node == "N16":
        if stopped or (a or {}).get("state") == "HELD" or (v or {}).get("state") == "REWORK":
            return "skipped"
        if cfg is None:
            return "awaiting" if (a or {}).get("state") == "CONFIRMED" else "waiting"
        return "done"
    raise KeyError(node)


def flow(doc: dict) -> list[dict[str, Any]]:
    return [
        {"node": n, "name": name, "role": role, "state": _state(doc, n)} for n, name, role in FLOW
    ]


def _scene_head(doc: dict) -> dict[str, Any]:
    bpm = doc["bpm"]
    s = doc["source"]
    return {
        "demoRunId": doc["demo_run_id"],
        "scenario": doc["scenario"],
        "scene": doc["scene"],
        "title": TITLE,
        "caseId": doc["case_id"],
        "clock": doc["clock"],
        "executor": doc["executor"],
        "bpm": {
            k: bpm.get(k)
            for k in ("job_id", "external_run_id", "state", "visited", "waiting", "problem")
        },
        "source": {
            "case_id": s["case_id"],
            "handoff_id": s["handoff"]["handoff_id"],
            "decision_id": s["decision"]["decision_id"],
            "action_id": s["action"]["action_id"],
            "observed": s["observed"],
            "existing": s["existing"],
        },
        "roles": [
            {**catalog.role(rid), "duty": duty, "steps": steps} for rid, duty, steps in PARTICIPANTS
        ],
        "flow": flow(doc),
        "companyLog": doc["company_log"],
        "evidenceSeen": len(doc["evidence_seen"]),
    }


def _scene_state(doc: dict) -> str:
    if doc["config"] is not None:
        return "APPLIED"
    if doc["bpm"].get("state") == "failed":
        return "RUN_FAILED"
    imp, v, a = doc["improvement"], doc["verification"], doc["approval"]
    if (imp or {}).get("state") == "NOT_NEEDED":
        return "NO_IMPROVEMENT"
    if (v or {}).get("state") == "REWORK":
        return "TEST_FAILED"
    if (a or {}).get("state") == "HELD":
        return "APPLY_HELD"
    if a is not None:
        return "CONFIRMED"
    if v is not None:
        return "VERIFYING"
    if doc["replay"] is not None:
        return "REPLAYING"
    if imp is not None:
        return "IMPROVING"
    if doc["outcome"] is not None and doc["outcome"]["ready"]:
        return "RESULTS_LINKED"
    return "WAITING_EVIDENCE"


def dashboard(doc: dict, master: dict) -> dict[str, Any]:
    """UI-D01 장면 4 몫 — 실적과 재현 전망을 섞지 않는다. 10월 마감 OTD는 그대로다."""
    rp = doc["replay"] or {}
    october = sc01_calc.otd(master, doc["clock"])
    return {
        "as_of": doc["clock"],
        "scope": {"company": "company1", "plant": "울산", "product": "A"},
        "dataset_version": master["dataset_version"],
        "kpi": october,
        "summary": calc.summary(
            doc["outcome"],
            rp.get("snapshot"),
            rp.get("early_min"),
            rp.get("receipt"),
            rp.get("adoption"),
            october,
            None if doc["config"] is None else doc["config"]["state"],
        ),
        "case_id": CASE_ID,
        "notice": (
            "실적(증빙)과 재현 전망을 합산하지 않는다 — 조건부 회피 가능액은 절감 실적이 아니다. "
            "11월 대표 주문 2건으로 월 OTD를 산출하지 않는다"
        ),
    }


def records_of(doc: dict, master: dict) -> list[dict[str, Any]]:
    """지금 문서의 장면 4 기록 전부(판 번호 없이)."""
    out = [record("scene", "S2:SC04", _scene_state(doc), TITLE, _scene_head(doc))]
    o = doc["outcome"]
    if o is not None:
        body = {**o, "history": doc["outcome_history"]}
        state = "LINKED" if o["ready"] else "AWAITING_EVIDENCE"
        out.append(record("outcome", calc.OUTCOME_ID, state, "결정과 실적 대조", body))
    imp = doc["improvement"]
    if imp is not None:
        out.append(
            record("improvement", calc.IMPROVEMENT_ID, imp["state"], "관리기준 개선 건", imp)
        )
    rp = doc["replay"]
    if rp is not None:
        state = (rp.get("adoption") or {}).get("state") or (
            "REQUEST_SENT" if (rp.get("request") or {}).get("state") == "SENT" else "SCREENED"
        )
        out.append(record("replay", calc.REPLAY_ID, state, "당시 자료 재현", rp))
    v = doc["verification"]
    if v is not None:
        out.append(record("verification", calc.TEST_ID, v["state"], "인수시험", v))
    a = doc["approval"]
    if a is not None:
        out.append(record("confirmation", calc.APPROVAL_ID, a["state"], "기준 적용 확인", a))
    cfg = doc["config"]
    if cfg is not None:
        out.append(record("config", calc.CONFIG_ID, cfg["state"], "위임 설정", cfg))
    out.append(record("dashboard", BOARD_ID, None, "납기 상황판 — 장면 4", dashboard(doc, master)))
    return out


__all__ = ["BOARD_ID", "KINDS", "TITLE", "dashboard", "flow", "records_of"]
