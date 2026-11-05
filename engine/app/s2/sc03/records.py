"""
시나리오 2 장면 3의 경영 기록 — 공통 기록 종류(`docs/platform.md` §3, 스키마
`docs/records/s2/sc03/`).

회사 사이트의 화면(UI-B03 수행계획 변경 · UI-B04 → B02 운송 회신·재보고 · UI-B05 경영검토·과제
인수)과 NowView 대시보드(UI-D01)가 이 기록만 읽는다 — 둘 다 계산하지 않는다. Case 기록은 장면 1
문서의 것이라 쓰지 않는다(장면 2와 같다) — 사건 진행은 `case_plan`·`scene`의 흐름 단계가 싣는다.
"""

from __future__ import annotations

from typing import Any

from app.platform import catalog
from app.records import record
from app.s2.sc01 import calc as sc01_calc
from app.s2.sc03 import calc
from app.s2.sc03.process import CASE_ID, REFRESH

TITLE = "잔여 납기 위험의 경영검토와 대응 합의"
BOARD_ID = "company1:ULS:A:SC03"
KINDS = {
    "scene": "장면 머리 — 시연 시각·사례·실행 위치·BPM 실행·장면 2 인계 사본·회사와 오간 것",
    "case_plan": (
        "사건 수행계획 v2(M06·M07) — v1 완료 항목 보존·U06 원업무 참조·조건부 U07·Y01 검사·"
        "흐름 단계"
    ),
    "work_link": (
        "원업무 참조(M11 references) — 출하팀 운송 문의·담당·받은 회신·관측 이력·새 문의 0건"
    ),
    "comparison": (
        "전량 대안 비교(M13) — 판·근거(회신·고객 확인·전결 기준)·두 대안의 수량·도착·여유·"
        "추가비·초과액·판정"
    ),
    "escalation": "팀장 권고·재보고(M12) — 권고안·사유·전결 한도·초과액·U07 활성·갱신 요청",
    "decision": "경영검토 결정(M23) — 선택·사유·한도·책임·기한·재보고 조건·결정 당시 근거 사본",
    "action": "실행과제(M24) — 담당·기한·한도·인수·결정 이후 재보고",
    "handoff": "장면 인계(HAND-03) — 결정·과제·근거 버전·후속 확인·실제값 미확정",
    "dashboard": (
        "납기 상황판(UI-D01) 장면 3 몫 — 두 안의 여유·긴급 추가비(견적)·한도 초과·결정·과제·"
        "마감 OTD"
    ),
}

#: 이 장면의 역할과 하는 일(상세화면구성 01 「역할과 권한」). 사람은 셋 — 팀장 권고, 임원 결정, 과제
#: 인수
PARTICIPANTS = [
    ("A03", "수행계획 변경 제안 (U06 참조 · 조건부 U07)", ["N03A"]),
    ("Y01", "위임·필수 조건 검사 · 원업무 연결 · 전결 한도 대조", ["N03A", "N09"]),
    ("A01", "운송 대안 비교 (전량 두 안)", ["N09"]),
    ("H04", "기존 운송 문의 담당 · 실행과제 인수", ["N09", "N10"]),
    ("H03", "담당 팀장 — 권고·재보고", ["N09"]),
    ("H05", "경영검토 결정 (조건부)", ["N10"]),
]

FLOW = [
    ("N03A", "수행계획 변경 (v2)", "A03"),
    ("U06", "기존 운송 문의 연결", "Y01"),
    ("N09", "운송 대안 비교", "A01"),
    ("ESC", "팀장 권고·재보고", "H03"),
    ("N10", "경영검토 결정", "H05"),
    ("ACT", "실행과제 인수", "H04"),
]


def _last_rec(doc: dict) -> dict | None:
    return doc["recommendations"][-1] if doc["recommendations"] else None


def _state(doc: dict, node: str) -> str:
    """흐름 단계 상태 — 기록에서 파생한다(BPM 토큰을 저장하지 않는다)."""
    plan, link, rec = doc["plan"], doc["link"], _last_rec(doc)
    if node == "N03A":
        if plan is None:
            return "waiting"
        return {"APPLIED": "done", "BLOCKED": "blocked"}.get(plan["state"], "running")
    if node == "U06":
        if link is None:
            return "waiting"
        return "done" if link["ready"] or doc["comparisons"] else "awaiting"
    if node == "N09":
        if not doc["comparisons"]:
            return "waiting"
        return "stale" if doc["comparisons"][-1]["state"] == "STALE" else "done"
    if node == "ESC":
        if rec is None:
            return "awaiting" if doc["comparisons"] else "waiting"
        return {
            "ESCALATED": "done",
            "WITHIN_AUTHORITY": "within",
            "REFRESH": "refresh",
        }[rec["result"]]
    if node == "N10":
        if doc["decisions"]:
            return "done"
        if rec is not None and rec["result"] == "WITHIN_AUTHORITY":
            return "skipped"
        if rec is not None and rec["result"] == "ESCALATED":
            return "stale" if rec["state"] == "STALE" else "awaiting"
        return "waiting"
    if node == "ACT":
        a = doc["action"]
        if a is None:
            return "skipped" if (rec or {}).get("result") == "WITHIN_AUTHORITY" else "waiting"
        return "done" if a["state"] == "ACCEPTED" else "awaiting"
    raise KeyError(node)


def flow(doc: dict) -> list[dict[str, Any]]:
    return [
        {"node": n, "name": name, "role": role, "state": _state(doc, n)} for n, name, role in FLOW
    ]


#: 업무 단위 → 흐름 단계 — v1 항목(U01~U05)은 장면 2에서 끝났다
UNIT_NODE = {"U06": "U06", "U07": "N10"}
ITEM_STATE = {
    "done": "완료",
    "running": "진행 중",
    "waiting": "대기",
    "awaiting": "진행 중",
    "blocked": "차단",
    "skipped": "비활성 — 재보고 없음",
    "stale": "근거 변경 — 다시 비교",
}


def _item_state(doc: dict, item: dict) -> str:
    if item.get("carried_from"):
        return item.get("carried_state") or "완료"
    if item["unit"] == "U07" and not doc["plan"]["u07_active"]:
        return "조건부 — 재보고 시 활성"
    return ITEM_STATE[_state(doc, UNIT_NODE[item["unit"]])]


def _plan_body(doc: dict) -> dict[str, Any]:
    p = doc["plan"]
    roles = [
        {**catalog.role(rid), "duty": duty, "steps": steps} for rid, duty, steps in PARTICIPANTS
    ]
    s = doc["source"]
    return {
        **p,
        "items": [{**i, "state": _item_state(doc, i)} for i in p["items"]],
        "roles": roles,
        "flow": flow(doc),
        "source": {
            "case_id": s["case_id"],
            "handoff_id": s["handoff"]["handoff_id"],
            "commitments": s["commitments"],
            "observed": s["observed"],
            "production_plan_version": s["production_plan_version"],
            "approval_id": s["approval_id"],
            "regular": s["regular"],
        },
        "kept": [
            f"{', '.join(s['observed'])} 인수 관찰",
            f"생산계획 {s['production_plan_version']}",
            f"확인 {s['approval_id']}",
        ],
        "case_state": "경영검토" if p["u07_active"] else "진행 중",
    }


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
            "handoff_id": s["handoff"]["handoff_id"],
            "case_id": s["case_id"],
            "commitments": s["commitments"],
            "observed": s["observed"],
            "production_plan_version": s["production_plan_version"],
            "approval_id": s["approval_id"],
        },
        "flow": flow(doc),
        "companyLog": doc["company_log"],
        "handoff": None if doc["handoff"] is None else doc["handoff"]["handoff_id"],
        "reReports": len(doc["re_reports"]),
    }


def _scene_state(doc: dict) -> str:
    rec = _last_rec(doc)
    if doc["handoff"]:
        return "HANDED_OFF"
    if doc["bpm"].get("state") == "failed":
        return "RUN_FAILED"
    if (doc["plan"] or {}).get("state") == "BLOCKED":
        return "PLAN_BLOCKED"
    if doc["decisions"]:
        return "DECIDED"
    if rec is not None and rec["result"] == "WITHIN_AUTHORITY":
        return "WITHIN_AUTHORITY"
    if rec is not None and rec["result"] == "ESCALATED" and rec["state"] == "AWAITING_DECISION":
        return "ESCALATED"
    if doc["comparisons"] and doc["comparisons"][-1]["state"] == "CURRENT":
        return "COMPARED"
    if doc["link"] is not None:
        return "WAITING_SOURCES"
    return "PLANNING"


def dashboard(doc: dict, master: dict) -> dict[str, Any]:
    """UI-D01 장면 3 몫 — 견적·전망은 실적이 아니다. 마감 OTD는 10월 인수 실적 그대로다."""
    current = next((c for c in reversed(doc["comparisons"]) if c["state"] != "SUPERSEDED"), None)
    decision = doc["decisions"][-1] if doc["decisions"] else None
    if decision is not None:
        current = next(c for c in doc["comparisons"] if c["label"] == decision["comparison"])
    return {
        "as_of": doc["clock"],
        "scope": {"company": "company1", "plant": "울산", "product": "A"},
        "dataset_version": master["dataset_version"],
        "kpi": sc01_calc.otd(master, doc["clock"]),
        "summary": calc.summary(current, decision, doc["action"]),
        "comparison": None if current is None else current["label"],
        "case_id": CASE_ID,
        "re_reports": len(doc["re_reports"]),
        "notice": (
            "추가비는 견적이고 도착은 전망이다 — 예약·실제 인수·집행비는 장면 4에서 연결한다. "
            "R 인수 전이라 마감 OTD는 그대로다"
        ),
    }


def records_of(doc: dict, master: dict) -> list[dict[str, Any]]:
    """지금 문서의 장면 3 기록 전부(판 번호 없이)."""
    out = [record("scene", "S2:SC03", _scene_state(doc), TITLE, _scene_head(doc))]
    if doc["plan"] is not None:
        p = doc["plan"]
        out.append(
            record("case_plan", calc.PLAN_ID, p["state"], "사건 수행계획 v2", _plan_body(doc))
        )
    if doc["link"] is not None:
        link = doc["link"]
        out.append(record("work_link", calc.LINK_ID, link["reply_state"], "원업무 참조", link))
    if doc["comparisons"]:
        c = doc["comparisons"][-1]
        body = {
            **c,
            "history": [
                {k: x[k] for k in ("label", "version", "basis", "compared_at", "state")}
                for x in doc["comparisons"]
            ],
        }
        out.append(record("comparison", calc.COMPARISON_ID, c["state"], "운송 대안 비교", body))
    rec = _last_rec(doc)
    if rec is not None:
        body = {
            **rec,
            "history": [
                {k: x.get(k) for k in ("version", "comparison", "choice", "result", "state")}
                for x in doc["recommendations"]
            ],
        }
        title = "운송 대안 갱신 요청" if rec["choice"] == REFRESH else "팀장 권고·재보고"
        out.append(record("escalation", calc.ESCALATION_ID, rec["state"], title, body))
    if doc["decisions"]:
        d = doc["decisions"][-1]
        out.append(record("decision", calc.DECISION_ID, d["state"], "경영검토 결정", d))
    if doc["action"] is not None:
        a = doc["action"]
        body = {
            **a,
            "re_reports": [r for r in doc["re_reports"] if r["action_id"] == a["action_id"]],
        }
        out.append(record("action", calc.ACTION_ID, a["state"], "실행과제", body))
    if doc["handoff"] is not None:
        h = doc["handoff"]
        out.append(record("handoff", calc.HANDOFF_ID, h["state"], "장면 4 인계", h))
    out.append(record("dashboard", BOARD_ID, None, "납기 상황판 — 장면 3", dashboard(doc, master)))
    return out


__all__ = ["BOARD_ID", "KINDS", "TITLE", "dashboard", "flow", "records_of"]
