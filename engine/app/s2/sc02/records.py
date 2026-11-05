"""
시나리오 2 장면 2의 경영 기록 — 공통 기록 종류(`docs/platform.md` §3, 스키마
`docs/records/s2/sc02/`).

회사 사이트의 화면(UI-B03 수행계획 · UI-B04 변경안 확인 · UI-B02 주문별 결과)과 NowView
대시보드(UI-D01)가
이 기록만 읽는다 — 둘 다 계산하지 않는다. Case 기록(`case` CASE-S2-01)은 장면 1 문서의 것이라 이
장면은
고치지 않는다(기간계 키가 kind/record_id라 두 문서가 같은 기록의 판을 따로 세면 엇갈린다) — 장면 2의
사건
진행은 `case_plan`·`scene`의 흐름 단계가 싣는다.
"""

from __future__ import annotations

from typing import Any

from app.platform import catalog
from app.records import record
from app.s2.sc01 import calc as sc01_calc
from app.s2.sc02 import calc
from app.s2.sc02.process import ASSESSMENT_ID, CASE_ID, HANDOFF_ID, PLAN_ID

TITLE = "정형통제 실행과 주문별 분기"
BOARD_ID = "company1:ULS:A:SC02"
KINDS = {
    "scene": "장면 머리 — 시연 시각·사례·실행 위치·BPM 실행·장면 1 인계 사본·회사와 오간 것",
    "case_plan": (
        "사건 수행계획(M06·M07) — A03 제안 항목(U01~U05)·Y01 검사·적용 상태·"
        "흐름 단계 N03A~N08·역할 목록"
    ),
    "production_change": (
        "생산계획 변경안(M20) — 판·기준 원계획·대상 약정 행(전후 시각·배정·라인·준비)·"
        "점검표·배경 주문"
    ),
    "confirmation": (
        "확인(M12 production_plan_apply) — H03 확인 한 건·대상 판·내용 식별값·두 약정"
    ),
    "production_plan": (
        "반영본 재조회(M21) — 저장소에서 다시 읽은 행·주문별 대조·실행키·시도 이력"
    ),
    "assessment": (
        "주문별 납기 재평가 — 출하 준비·이용 정기차·예상 도착·약정·여유·후속 경로·보류 사유"
    ),
    "handoff": "장면 인계(HAND-02) — 운송 확인 주문·근거 버전·하지 않은 일",
    "dashboard": (
        "납기 상황판(UI-D01) 장면 2 몫 — 마감 OTD·최초 영향·대조 일치·관찰·잔여 위험·보류·확인"
    ),
}

#: 이 장면의 역할과 하는 일(상세화면구성 01·02). 사람 결재는 H03의 확인 한 번이다.
PARTICIPANTS = [
    ("A03", "수행 업무 제안", ["N03A"]),
    ("Y01", "위임·필수 통제 검사 · 반영·재조회 · 재평가", ["N03A", "N06", "N07", "N08"]),
    ("A02", "생산계획 변경안 작성", ["N04"]),
    ("H03", "생산계획 변경 확인 (한 번)", ["N05"]),
]


def _state(doc: dict, node: str) -> str:
    """흐름 단계 상태 — 기록에서 파생한다(BPM 토큰을 저장하지 않는다)."""
    plan, drafts, confs = doc["plan"], doc["drafts"], doc["confirmations"]
    last_conf = confs[-1] if confs else None
    if node == "N03A":
        if plan is None:
            return "waiting"
        return {"APPLIED": "done", "BLOCKED": "blocked"}.get(plan["state"], "running")
    if node == "N04":
        return (
            "done"
            if drafts
            else ("running" if (plan or {}).get("state") == "APPLIED" else "waiting")
        )
    if node == "N05":
        if last_conf and last_conf["draft_id"] == drafts[-1]["draft_id"]:
            return "rework" if last_conf["decision"] == "보완요청" else "done"
        return "awaiting" if drafts else "waiting"
    if node == "N06":
        rb = doc["readback"]
        if rb is None:
            return "running" if doc["apply"] else "waiting"
        matched = all(r["match"] == calc.MATCHED for r in rb["rows"].values())
        return "done" if matched else "partial"
    if node == "N07":
        return "done" if doc["assessments"] else "waiting"
    if node == "N08":
        if doc["handoff"]:
            return "done"
        if doc["assessments"] and not any(
            r["route"] == calc.TRANSPORT for r in doc["assessments"][-1]["rows"]
        ):
            return "skipped"
        return "waiting"
    raise KeyError(node)


FLOW = [
    ("N03A", "수행계획 구성", "A03"),
    ("N04", "생산계획 변경안 작성", "A02"),
    ("N05", "생산계획 변경 확인", "H03"),
    ("N06", "반영·재조회 대조", "Y01"),
    ("N07", "주문별 납기 재평가", "Y01"),
    ("N08", "운송 확인 인계 (장면 3)", "Y01"),
]


def flow(doc: dict) -> list[dict[str, Any]]:
    return [
        {"node": n, "name": name, "role": role, "state": _state(doc, n)} for n, name, role in FLOW
    ]


def _plan_body(doc: dict) -> dict[str, Any]:
    p = doc["plan"]
    roles = [
        {**catalog.role(rid), "duty": duty, "steps": steps} for rid, duty, steps in PARTICIPANTS
    ]
    return {
        **p,
        "items": [{**i, "state": _item_state(doc, i["unit"])} for i in p["items"]],
        "roles": roles,
        "flow": flow(doc),
        "source": {
            k: doc["source"][k] for k in ("case_id", "alert_id", "revision_id", "commitments")
        }
        | {"handoff_id": doc["source"]["handoff"]["handoff_id"]},
        "case_state": "진행 중",
    }


#: 업무 단위 → 흐름 단계(그 단위가 끝났는지는 그 단계로 본다)
UNIT_NODE = {"U01": "N03A", "U02": "N04", "U03": "N05", "U04": "N06", "U05": "N07"}
ITEM_STATE = {
    "done": "완료",
    "running": "진행 중",
    "waiting": "대기",
    "awaiting": "확인 대기",
    "blocked": "차단",
    "rework": "보완 요청",
    "partial": "재조회 필요",
    "skipped": "해당 없음",
}


def _item_state(doc: dict, unit: str) -> str:
    return ITEM_STATE[_state(doc, UNIT_NODE[unit])]


def _scene_head(doc: dict) -> dict[str, Any]:
    bpm = doc["bpm"]
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
            "handoff_id": doc["source"]["handoff"]["handoff_id"],
            "case_id": doc["source"]["case_id"],
            "analysis": {
                k: doc["source"]["analysis"][k] for k in ("analysis_id", "version", "data_as_of")
            },
            "commitments": doc["source"]["commitments"],
        },
        "flow": flow(doc),
        "companyLog": doc["company_log"],
        "handoff": doc["handoff"]["next_node"] if doc["handoff"] else None,
    }


def _scene_state(doc: dict) -> str:
    if doc["handoff"]:
        return "HANDED_OFF"
    if doc["bpm"].get("state") == "failed":
        # 일감 전에 실행이 실패했다(공통 BPM 사본 없음 등) — 사유는 머리 `bpm.problem`
        return "RUN_FAILED"
    if (doc["plan"] or {}).get("state") == "BLOCKED":
        return "PLAN_BLOCKED"
    if doc["confirmations"] and doc["confirmations"][-1]["decision"] == "보완요청":
        return "REWORK"
    if doc["assessments"]:
        return "ASSESSED"
    if doc["drafts"]:
        return "AWAITING_CONFIRM" if not doc["confirmations"] else "CONTROL"
    return "PLANNING"


def dashboard(doc: dict, master: dict) -> dict[str, Any]:
    """
    UI-D01 장면 2 몫 — 최초 영향 2건과 현재 잔여 위험을 나눈다. 마감 OTD는 인수 실적이라
    그대로다.
    """
    a = doc["assessments"][-1]["rows"] if doc["assessments"] else []
    s = calc.summary(
        doc["source"]["commitments"],
        (doc["readback"] or {}).get("rows"),
        a,
        sum(1 for c in doc["confirmations"] if c["decision"] == "확정"),
    )
    return {
        "as_of": doc["clock"],
        "scope": {"company": "company1", "plant": "울산", "product": "A"},
        "dataset_version": master["dataset_version"],
        "kpi": sc01_calc.otd(master, doc["clock"]),
        "summary": s,
        "orders": [
            {
                "commitment_id": r["commitment_id"],
                "route": r["route"],
                "route_label": r["route_label"],
                "margin_min": r["margin_min"],
            }
            for r in a
        ],
        "case_id": CASE_ID,
        "notice": (
            "예상 도착은 계획 기준 전망이다 — 실제 인수 전이라 마감 OTD에 합산하지 않는다. "
            "통제 실행 완료와 위험 상태는 따로 본다"
        ),
    }


def records_of(doc: dict, master: dict) -> list[dict[str, Any]]:
    """지금 문서의 장면 2 기록 전부(판 번호 없이)."""
    out = [record("scene", "S2:SC02", _scene_state(doc), TITLE, _scene_head(doc))]
    if doc["plan"] is not None:
        p = doc["plan"]
        out.append(record("case_plan", PLAN_ID, p["state"], "사건 수행계획", _plan_body(doc)))
    for d in doc["drafts"]:
        out.append(record("production_change", d["draft_id"], d["state"], "생산계획 변경안", d))
    for c in doc["confirmations"]:
        out.append(record("confirmation", c["approval_id"], c["state"], "생산계획 변경 확인", c))
    if doc["readback"] is not None or doc["apply"] is not None:
        body = {
            "target_version": calc.TARGET_VERSION,
            "apply": doc["apply"],
            "readback": doc["readback"],
        }
        state = None
        if doc["readback"] is not None:
            matched = all(r["match"] == calc.MATCHED for r in doc["readback"]["rows"].values())
            state = "MATCHED" if matched else "PARTIAL"
        out.append(record("production_plan", calc.TARGET_VERSION, state, "반영본 재조회", body))
    if doc["assessments"]:
        a = doc["assessments"][-1]
        out.append(
            record("assessment", ASSESSMENT_ID, None, f"주문별 납기 재평가 v{a['version']}", a)
        )
    if doc["handoff"] is not None:
        out.append(record("handoff", HANDOFF_ID, "N09", "장면 3 인계", doc["handoff"]))
    out.append(record("dashboard", BOARD_ID, None, "납기 상황판 — 장면 2", dashboard(doc, master)))
    return out


__all__ = ["BOARD_ID", "KINDS", "TITLE", "dashboard", "flow", "records_of"]
