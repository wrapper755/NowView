"""
시나리오 2 장면 4 실행 — 실행 결과 확인과 관리기준 개선(D09~D11, `docs/s2/sc04.md`).

* **장면 3 인계(HAND-03)에서 시작한다** — 같은 데모 실행·같은 사건(CASE-S2-01). 사이트의 「장면
  열기」(기간계 명령 `open`)가 이 문서를 만들고 Center에 `company1.s2.sc04`를 기동한다(입력
  `데모실행ID`·`사건ID`). 장면 3의 결정·과제·인계와 장면 2의 분석 사본·반영본 재평가는 그 시점
  사본이다 — 다시 결정하지 않는다.
* **그림**(`processes/s2-sc04.bpmn`): 결정·실적 대조(N11 — 회사 시스템의 예약·인수·정산 증빙을 다시
  읽는다, 모자라면 **메시지 「실행증빙」을 기다린다**) → **H06 개선 착수 결재**(N12·N13 — A01의
  KRI·Control 개정 초안) → 당시 자료 재현(SNAP-0900 초기선별·요청 초안) → **H04 요청 확인·송신
  결재** → 모의 운송사 접수증·회신 → **H04 타 고객 영향 확인 결재** → 인수시험(N14 — 8개 회신
  분기·시험 01~09) → **H07 시험 판정 결재** → **H06 적용 확인 결재**(N15 — APP-04 범위·효력시점) →
  **H07 위임 설정 결재**(N16 — CFG-04, 다음 신규 사건부터).
* **재현은 모의 전송이다** — 실제 운송사에 보내지 않는다(외부 송신 0건). 재현 시각(09:00·09:03·
  09:05·09:08)은 자료의 시각이고 기록 시각(세계 시계)과 따로 둔다. 재현 전망은 실적에 더하지 않는다.
* **개선은 별도 개선 건이다**(전체업무연결 U09 「별도 개선 건으로 Case 참조」) — 사건 수행계획을
  바꾸지 않으므로 공통 BPM `platform.case-plan`을 부르지 않는다. 사람 결재 여섯은 모두 이 그림에
  있다(서버 실행기가 호출 활동 안의 결재를 올리지 않는다 — `docs/s2/sc03.md`).
* **기존 사건은 소급하지 않는다** — CASE-S2-01은 당시 버전·결정·실적 그대로이고, 개선 버전은 효력
  시점 이후 신규 사건(CASE-NEXT-01 예시)에만 적용된다.
"""

from __future__ import annotations

import copy
import logging
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from chaeksas.contracts.bpmn_ext import read_process

from app import records
from app.company import CompanyClient
from app.platform import catalog
from app.s2.sc03 import calc as sc03_calc
from app.s2.sc04 import calc
from app.sc01.center import CenterClient, CenterConfig, CenterError
from app.sc01.domain import DomainError, parse_at
from app.sc01.store import Sc01Store, StaleWrite

PROCESS_PATH = Path(__file__).resolve().parents[3] / "processes" / "s2-sc04.bpmn"
SCENARIO = "s2"
SCENE = 4
#: NowView 업무 번호 — 시나리오 2 장면 N은 20 + N(`docs/platform.md` §7)
WORK = 24
OPERATIONS = (
    "link_execution_results",
    "start_standard_improvement",
    "replay_route_screening",
    "send_route_request",
    "receive_route_reply",
    "confirm_route_impact",
    "run_standard_verification",
    "record_verification_verdict",
    "confirm_standard_application",
    "apply_standard_config",
)
CASES = ("BASE",)
CASE_ID = calc.CASE_ID
WAIT_NODE = "Wait_Evidence"
MESSAGE = "실행증빙"
START_NODE, REQUEST_NODE, IMPACT_NODE = "Approve_Start", "Approve_Request", "Approve_Impact"
TEST_NODE, APPLY_NODE, CONFIG_NODE = "Approve_Test", "Approve_Apply", "Approve_Config"
ON_BEHALF = "시스템 자동처리"
START, NOT_NEEDED = "착수", "개선 불필요"
SEND = "송신"
PASS, REWORK = "통과", "보완·재시험"
CONFIRM, HOLD = "확인", "보류"
SET = "반영"
#: 타 고객 기존 약정 차질 확인의 답 → 값(구현명세 §3 — 0 · 1 · 공란)
IMPACT_OF = {"차질 없음": 0, "차질 예상": 1, "미확인": None}
#: 모의 회신의 분기 — 기본 시연은 SC04회신재현 「기본 수락」이다(나머지는 시험 분기)
BASE_BRANCH = "기본 수락"
#: 장면 3의 원업무(출하팀 기존 운송 문의) — 재현 시각에 열려 있었는지 본다
WORK_ID = "W-TRAN-R"

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def audit(doc: dict, *, actor: str, action: str, **detail: Any) -> None:
    doc["audit"].append({"at": doc["clock"], "actor": actor, "action": action, **detail})


def new_doc(
    demo_run_id: str,
    source: dict[str, Any],
    *,
    case_id: str,
    executor: str,
    world_generation: int | None,
) -> dict[str, Any]:
    if case_id not in CASES:
        raise DomainError(f"모르는 사례: {case_id} (가능: {', '.join(CASES)})", 422)
    if executor not in ("center", "studio"):
        raise DomainError("실행 위치는 center·studio다 — 내장 실행은 쓰지 않는다", 422)
    return {
        "demo_run_id": demo_run_id,
        "scenario": SCENARIO,
        "scene": SCENE,
        "case_id": case_id,
        "executor": executor,
        "step": "S0",
        "script_index": None,
        "clock": "",
        "created_at": _now(),
        "world_generation": world_generation,
        "center_epoch": uuid.uuid4().hex[:8],
        "source": source,
        "outcome": None,
        "outcome_history": [],
        "improvement": None,
        "replay": None,
        "verification": None,
        "approval": None,
        "config": None,
        "evidence_seen": [],
        "wait": {"message_pending": False, "attempts": 0},
        "bpm": {
            "executor": executor,
            "state": "idle",
            "job_id": None,
            "external_run_id": None,
            "visited": [],
            "waiting": [],
            "problem": None,
        },
        "audit": [],
        "company_log": [],
        "company_records": {},
    }


def source_of(sc03_doc: dict[str, Any], sc02_doc: dict[str, Any]) -> dict[str, Any]:
    """
    장면 3 인계와 장면 2 재현 근거의 사본 — 결정(DEC-03)·과제(ACT-03)·인계(HAND-03), S의 인수 관찰,
    장면 2의 분석 사본(09:00 자료)·생산 확인(APP-01)·반영본 재조회·재평가(R). 앞 장면을 초기화해도
    장면 4의 근거는 그 시점 것이다.
    """
    handoff = sc03_doc.get("handoff")
    if not handoff or not sc03_doc.get("decisions"):
        raise DomainError("장면 3 인계(HAND-03)가 아직 없다 — 과제 인수 뒤에 연다", 409)
    decision = sc03_doc["decisions"][-1]
    assessment = (sc02_doc.get("assessments") or [None])[-1]
    readback = sc02_doc.get("readback")
    if assessment is None or readback is None or not sc02_doc.get("handoff"):
        raise DomainError("장면 2 반영본 재평가·인계가 없다 — 재현 근거가 없다", 409)
    [r] = [x for x in assessment["rows"] if x["commitment_id"] == calc.TARGET]
    [confirm] = [c for c in sc02_doc["confirmations"] if c["state"] == "CONFIRMED"][-1:] or [None]
    return {
        "case_id": handoff["case_id"],
        "handoff": copy.deepcopy(handoff),
        "decision": {
            k: copy.deepcopy(decision.get(k))
            for k in (
                "decision_id",
                "selected",
                "selected_label",
                "limit",
                "terms",
                "reservation_due",
                "decided_at",
                "decided_by",
                "comparison",
            )
        },
        "action": {
            k: (sc03_doc.get("action") or {}).get(k)
            for k in ("action_id", "owner_role", "owner_name", "due", "limit", "accepted_at")
        },
        "observed": list(handoff.get("observed") or []),
        "analysis": copy.deepcopy(sc02_doc["source"]["analysis"]),
        "existing": {
            "handoff_id": sc02_doc["handoff"]["handoff_id"],
            "judged_at": sc02_doc["handoff"]["handed_at"],
            "margin_min": r["margin_min"],
            "approval_id": None if confirm is None else confirm["approval_id"],
            "approved_at": None if confirm is None else confirm["confirmed_at"],
            "readback_version": readback["version"],
            "readback_at": readback["read_at"],
        },
        "reflect": {"match": r["match"], "ready_at": r["ready_at"], "arrival": r["arrival"]},
    }


# ─────────────────────────── 작업 (일꾼·시험이 같은 함수) ───────────────────────────


def _holder(by: str, role: str, what: str) -> None:
    if by not in catalog.HOLDERS[role]:
        label = catalog.ROLES[role]["label"]
        raise DomainError(f"{what}은 {label}({role})만 한다 — {by or '이름 없음'}", 403)


def _links(doc: dict) -> dict[str, dict[str, Any]]:
    """약정 → 원결정 연결 — S는 장면 2의 인수 관찰, R은 장면 3의 결정·과제·인계."""
    s = doc["source"]
    d = s["decision"]
    out: dict[str, dict[str, Any]] = {
        cid: {"label": "인수 관찰", "ids": [], "needs_booking": False} for cid in s["observed"]
    }
    out[calc.TARGET] = {
        "label": " / ".join(
            [d["decision_id"], s["action"]["action_id"], s["handoff"]["handoff_id"]]
        ),
        "ids": [d["decision_id"], s["action"]["action_id"], s["handoff"]["handoff_id"]],
        "needs_booking": d["selected"] == sc03_calc.ALT_EXP,
        "terms": {
            "limit": d["limit"],
            "reservation_due": d["reservation_due"],
            "expected_arrival": (d.get("terms") or {}).get("arrival"),
        },
    }
    return out


def _set_outcome(doc: dict, master: dict, evidence: list[dict]) -> dict[str, Any]:
    found = calc.outcome(master, evidence, _links(doc))
    prev = doc["outcome"]
    if prev is None or prev["rows"] != found["rows"]:
        if prev is not None:
            doc["outcome_history"].append(
                {k: prev[k] for k in ("version", "reconciled_at", "on_time_full", "evidence")}
            )
        version = 1 if prev is None else prev["version"] + 1
        doc["outcome"] = {
            "outcome_id": calc.OUTCOME_ID,
            "version": version,
            "case_id": CASE_ID,
            **found,
            "evidence": sorted({e["source_id"] for e in evidence}),
            "reconciled_at": doc["clock"],
            "reconciled_by": "Y01",
            "summary_by": "A01",
            "execution_mode": "rule",
            "october_kept": True,
            "note": (
                "증빙 기준 실적이다 — 장면 3 결정 당시의 공란은 그 기록에 그대로 둔다. 11월 대표 "
                "주문 2건은 사건 실적이고 월 OTD를 산출하지 않는다"
            ),
        }
        audit(doc, actor="Y01", action="results_reconciled", version=version)
    return doc["outcome"]


def link_results(doc: dict, master: dict, evidence: list[dict]) -> dict[str, Any]:
    """
    N11 — 결정과 후속 증빙을 약정별로 잇는다. 증빙이 다 오지 않았으면 그림이 메시지 「실행증빙」을
    기다린다(누락은 미확인 — 전망으로 메우지 않는다).
    """
    o = _set_outcome(doc, master, evidence)
    missing = [f"{r['commitment_id']} {m}" for r in o["rows"] for m in r["missing"]]
    bpm = doc["bpm"]
    if o["ready"]:
        bpm["waiting"] = [{"node_id": START_NODE, "title": "관리기준 개선 착수 — H06"}]
    else:
        bpm["waiting"] = [{"node_id": WAIT_NODE, "title": "예약·인수·정산 증빙 대기"}]
        doc["wait"]["message_pending"] = False
    return {
        "outcome_id": calc.OUTCOME_ID,
        "ready": o["ready"],
        "on_time_full": o["on_time_full"],
        "reason": "증빙 대기: " + ", ".join(missing)
        if missing
        else f"정시 전량 {o['on_time_full']}건 · 증빙 연결 완료",
    }


def _improvement_draft(doc: dict) -> dict[str, Any]:
    """A01 개정 초안(N13) — 주문별 운송납기 여유 KRI + 마감 전 구체 배차 조정 요청 Control."""
    o = doc["outcome"]
    r = next(x for x in o["rows"] if x["commitment_id"] == calc.TARGET)
    ex = doc["source"]["existing"]
    return {
        "reason": (
            f"{calc.TARGET} 정시 전량 인수({r['accepted_at'][11:16]})였지만 "
            f"{r['transport']}·추가비 {r['extra_cost']:,}원이 들었다. 기존 판정 "
            f"{ex['judged_at'][11:16]}(여유 {calc.signed_min(ex['margin_min'])})에는 정규노선 변경 "
            "접수 마감이 지났다 — 생산계획 승인을 기다리지 않고 조정을 요청할 수 있었는가"
            if r["extra_cost"] is not None and r["accepted_at"]
            else "증빙 미확인 — 개선 사유를 확정하지 않는다"
        ),
        "kri": {
            "name": "주문별 운송납기 여유",
            "formula": "고객 약정 − 지금 확정된 정기차의 예상 도착(분)",
            "trigger": "음수이고 조정 접수 가능 시간이 남아 있으면 조정 요청 후보",
            "recheck": "생산계획 반영 뒤 반드시 다시 평가",
        },
        "control": {
            "name": "마감 전 구체 배차 조정 요청",
            "cutoff_rule": (
                "정규 순회노선 기점 출발 24시간 전까지 변경 접수(울산 상차·고객 약정 기준 아님)"
            ),
            "steps": [
                "A01 요청 초안",
                "H04 확인·요청",
                "운송사 접수증",
                "별도 수락 회신",
                "승인본 반영 뒤 재평가",
            ],
            "duplicate_rule": "같은 주문의 문의가 열려 있으면 갱신, 없으면 한 건만 시작",
        },
        "kept": ["고객 약정", "성과 KPI(OTD)", "전결 기준(AUTH-T1)"],
        "unit": "U09",
        "unit_name": catalog.UNITS["U09"]["name"],
        "version": calc.KRI_VERSION,
        "previous": calc.PREVIOUS_LABEL,
        "previous_rules": list(calc.PREVIOUS_RULES),
        "proposed_by": "A01",
        "execution_mode": "rule",
    }


def start_improvement(doc: dict, args: dict[str, Any]) -> dict[str, Any]:
    """N12 — H06이 개선 착수 여부를 판단한다(모든 사건을 개선으로 강제하지 않는다)."""
    by = str(args.get("answered_by") or "")
    _holder(by, "H06", "관리기준 개선 착수")
    choice = str(args.get("decision") or "")
    if choice not in (START, NOT_NEEDED):
        raise DomainError(f"착수 판단은 {START}·{NOT_NEEDED}다: {choice}", 422)
    reason = str(args.get("reason") or "").strip()
    if not reason:
        raise DomainError("판단 사유가 없다", 422)
    o = doc["outcome"]
    if o is None or not o["ready"]:
        raise DomainError("결과 대조가 끝나지 않았다 — 증빙을 다 연결한 뒤 판단한다", 409)
    imp = doc["improvement"]
    if imp is not None:
        if imp["decision"] != choice:
            raise DomainError(f"이미 「{imp['decision']}」로 판단했다", 409)
        return _start_out(imp)
    doc["improvement"] = imp = {
        "improvement_id": calc.IMPROVEMENT_ID,
        "case_refs": [CASE_ID],
        "outcome": f"{o['outcome_id']} v{o['version']}",
        **_improvement_draft(doc),
        "decision": choice,
        "decision_reason": reason,
        "decided_by": by,
        "decided_role": "H06",
        "via": args.get("answered_via"),
        "decided_at": doc["clock"],
        "state": "STARTED" if choice == START else "NOT_NEEDED",
        "note": "개선은 별도 개선 건이다 — 사건 수행계획을 바꾸지 않는다(U09)",
    }
    doc["bpm"]["waiting"] = []
    audit(doc, actor=by, action="improvement_decided", decision=choice)
    return _start_out(imp)


def _start_out(imp: dict) -> dict[str, Any]:
    return {
        "result": "STARTED" if imp["decision"] == START else "NOT_NEEDED",
        "improvement_id": imp["improvement_id"],
        "error_message": None,
    }


def _improvement(doc: dict) -> dict:
    imp = doc["improvement"]
    if imp is None or imp["state"] == "NOT_NEEDED":
        raise DomainError("개선 착수 전이다", 409)
    return imp


def _event(master: dict, record_id: str) -> dict:
    found = next((e for e in master["replay_events"] if e["record_id"] == record_id), None)
    if found is None:
        raise DomainError(f"재현 시각이 회사 자료에 없다: {record_id}", 404)
    return found


def _branch(master: dict, name: str) -> dict:
    return next(b for b in master["replay_branches"] if b["branch"] == name)


def _evaluate(doc: dict, master: dict, branch: dict, *, reflect: Any = "source") -> dict:
    s = doc["source"]
    snap = doc["replay"]["snapshot"]
    r = next(x for x in snap["rows"] if x["commitment_id"] == calc.TARGET)
    c = next(x for x in master["commitments"] if x["commitment_id"] == calc.TARGET)
    actual = (doc["outcome"] or {}).get("actual_extra_cost", {}).get(calc.TARGET)
    return calc.evaluate_branch(
        branch,
        cutoff=doc["replay"]["cutoff"]["cutoff_at"],
        need_qty=c["qty"],
        snapshot_ready=r["ready_at"],
        promised_at=c["promised_at"],
        reflect=s["reflect"] if reflect == "source" else reflect,
        actual_cost=actual,
    )


def replay_screening(doc: dict, master: dict, inquiry: dict | None) -> dict[str, Any]:
    """
    D10 재현 — SNAP-0900 자료로 8건을 선별하고, 마감(기점 출발 − 24시간)과 남은 시간을 내고,
    R에 요청 초안을 만든다(A01). 그 시각에 같은 주문의 운송 문의가 열려 있었으면 갱신, 없었으면 재현
    업무 한 건(원업무 계보 연결). 실제 운송사에는 보내지 않는다.
    """
    _improvement(doc)
    if doc["replay"] is None:
        snap_at = _event(master, calc.SNAPSHOT_ID)["at"]
        screening = calc.screen(master, doc["source"]["analysis"]["rows"], snap_at)
        cutoff = calc.route_cutoff(master["route_contract"])
        ex = doc["source"]["existing"]
        open_then = inquiry is not None and parse_at(inquiry["started_at"]) <= parse_at(snap_at)
        work_id = None if inquiry is None else inquiry["work_id"]
        doc["replay"] = {
            "replay_id": calc.REPLAY_ID,
            "case_id": CASE_ID,
            "mode": "replay",
            "banner": f"재현 모드 — 자료 기준 {snap_at[5:10].replace('-', '/')} "
            f"{snap_at[11:16]} · 실제 운송사에 보내지 않는다",
            "data_as_of": snap_at,
            "snapshot": screening,
            "cutoff": {
                "route": master["route_contract"],
                "cutoff_at": cutoff,
                "minutes_left": calc.round_min(parse_at(cutoff) - parse_at(snap_at)),
                "note": "기점 출발 기준 — 울산 상차(16:15)·고객 약정(18:30) 기준이 아니다",
            },
            "existing": {
                "inquiry_id": work_id,
                "inquiry_started_at": None if inquiry is None else inquiry["started_at"],
                "inquiry_note": "일반 운송 문의 — 노선 변경 요청 접수가 아니다",
                "judged_by": ex["handoff_id"],
                "judged_at": ex["judged_at"],
                "margin_min": ex["margin_min"],
                "past_cutoff": parse_at(ex["judged_at"]) > parse_at(cutoff),
            },
            "early_min": calc.round_min(parse_at(ex["judged_at"]) - parse_at(snap_at)),
            "request": None,
            "receipt": None,
            "reply": None,
            "impact": None,
            "adoption_at_reply": None,
            "adoption": None,
            "external_sends": 0,
            "recorded_at": doc["clock"],
        }
        if calc.TARGET in screening["candidates"]:
            d = doc["replay"]
            d["request"] = {
                "request_id": calc.REQUEST_ID,
                "commitment_id": calc.TARGET,
                "qty": next(
                    c["qty"] for c in master["commitments"] if c["commitment_id"] == calc.TARGET
                ),
                "content": "정규 순회노선 울산 경유 · 240세트 전량 적재 조정 요청",
                "route_id": master["route_contract"]["route_id"],
                "cutoff_at": cutoff,
                "drafted_at": snap_at,
                "drafted_by": "A01",
                "draft_mode": "rule",
                "work_mode": "update" if open_then else "replay_work",
                "work_id": work_id if open_then else f"{calc.REQUEST_ID} (재현 업무)",
                "lineage": work_id,
                "state": "DRAFTED",
                "sent_at": None,
                "sent_by": None,
                "mode": "mock",
            }
        audit(doc, actor="A01", action="replay_screened", candidates=screening["candidates"])
    d = doc["replay"]
    doc["bpm"]["waiting"] = (
        [{"node_id": REQUEST_NODE, "title": f"조정 요청 확인 — {calc.REQUEST_ID} (재현)"}]
        if d["request"]
        else []
    )
    return {
        "replay_id": calc.REPLAY_ID,
        "candidates": len(d["snapshot"]["candidates"]),
        "requested": d["request"] is not None,
        "request_id": None if d["request"] is None else calc.REQUEST_ID,
        "minutes_left": d["cutoff"]["minutes_left"],
    }


def _replay(doc: dict) -> dict:
    if doc["replay"] is None or doc["replay"]["request"] is None:
        raise DomainError("재현 요청 초안이 없다", 409)
    return doc["replay"]


def send_request(doc: dict, args: dict[str, Any], master: dict) -> dict[str, Any]:
    """D10 — H04가 초안을 확인해 (모의) 송신한다. 초안·송신·접수는 다른 상태다."""
    by = str(args.get("answered_by") or "")
    _holder(by, "H04", "조정 요청 확인·송신")
    if str(args.get("decision") or "") != SEND:
        raise DomainError(f"요청 확인은 「{SEND}」다", 422)
    req = _replay(doc)["request"]
    if req["state"] == "DRAFTED":
        req.update(
            state="SENT",
            sent_at=_event(master, calc.REQUEST_ID)["at"],
            sent_by=by,
            sent_role="H04",
            via=args.get("answered_via"),
            comment=str(args.get("comment") or ""),
            recorded_at=doc["clock"],
        )
        audit(doc, actor=by, action="route_request_sent", request_id=calc.REQUEST_ID)
    doc["bpm"]["waiting"] = []
    return {"request_id": calc.REQUEST_ID, "state": req["state"], "error_message": None}


def receive_reply(doc: dict, master: dict) -> dict[str, Any]:
    """
    모의 운송사 — 접수증(ACK-R-04)과 수락 회신(REP-R-04)을 별도 사건으로 남긴다. 같은 메시지 id는 한
    번만. 수락 시점(09:08)에는 생산 반영 전이라 채택하지 않는다.
    """
    d = _replay(doc)
    if d["request"]["state"] != "SENT":
        raise DomainError("송신 전에는 접수·회신이 없다", 409)
    branch = _branch(master, BASE_BRANCH)
    if d["receipt"] is None:
        d["receipt"] = {
            "ack_id": calc.ACK_ID,
            "request_id": calc.REQUEST_ID,
            "received_at": branch["received_at"],
            "deadline_margin_min": None
            if branch["received_at"] is None
            else calc.round_min(
                parse_at(d["cutoff"]["cutoff_at"]) - parse_at(branch["received_at"])
            ),
            "mode": "mock",
        }
    if d["reply"] is None:
        rep = _event(master, calc.REPLY_ID)
        d["reply"] = {
            "reply_id": calc.REPLY_ID,
            "ack_id": calc.ACK_ID,
            "version": 1,
            "replied_at": rep["at"],
            "branch": branch["branch"],
            "reply": branch["reply"],
            "capacity": branch["capacity"],
            "extra_fare": branch["extra_fare"],
            "departure": branch["departure"],
            "run_min": branch["run_min"],
            "mode": "mock",
            "note": rep["note"],
        }
        d["adoption_at_reply"] = _evaluate(
            doc, master, {**branch, "other_customer_impact": None}, reflect=None
        )
        audit(doc, actor="운송사(모의)", action="route_reply_received", reply_id=calc.REPLY_ID)
    doc["bpm"]["waiting"] = [{"node_id": IMPACT_NODE, "title": "타 고객 기존 약정 영향 확인 — H04"}]
    return {
        "ack_id": calc.ACK_ID,
        "reply_id": calc.REPLY_ID,
        "reply": d["reply"]["reply"],
        "deadline_margin_min": d["receipt"]["deadline_margin_min"],
    }


def confirm_impact(doc: dict, args: dict[str, Any], master: dict) -> dict[str, Any]:
    """
    구현명세 §3 — H04가 조정 노선의 도착·수용량을 당사 타 고객 약정과 대조해 0·1·미확인을 남긴다.
    회신 이후 최종 판정(채택·기존 운송 검토·보류)을 낸다.
    """
    by = str(args.get("answered_by") or "")
    _holder(by, "H04", "타 고객 기존 약정 영향 확인")
    answer = str(args.get("impact") or "")
    if answer not in IMPACT_OF:
        raise DomainError(f"영향은 {'·'.join(IMPACT_OF)}다: {answer}", 422)
    evidence = str(args.get("evidence") or "").strip()
    if not evidence:
        raise DomainError("영향 근거가 없다", 422)
    d = _replay(doc)
    if d["reply"] is None:
        raise DomainError("운송사 회신 전에는 영향을 확인하지 않는다", 409)
    value = IMPACT_OF[answer]
    branch = {**_branch(master, BASE_BRANCH), "other_customer_impact": value}
    d["impact"] = {
        "value": value,
        "label": calc.IMPACT_LABEL[value],
        "evidence": evidence,
        "candidates_by": "A01",
        "confirmed_by": by,
        "confirmed_role": "H04",
        "via": args.get("answered_via"),
        "confirmed_at": doc["clock"],
        "sample_note": "자료의 영향 1 행은 특정 고객이 없는 예외 시험값이다",
    }
    d["adoption_at_reply"] = _evaluate(doc, master, branch, reflect=None)
    d["adoption"] = {
        **_evaluate(doc, master, branch),
        "reflect": copy.deepcopy(doc["source"]["reflect"]),
        "readback_at": doc["source"]["existing"]["readback_at"],
        "decided_at": doc["clock"],
        "note": "조건부 회피 가능액은 재현 효과다 — 실제 절감으로 집계하지 않는다",
    }
    doc["bpm"]["waiting"] = []
    audit(doc, actor=by, action="route_impact_confirmed", impact=value)
    a = d["adoption"]
    return {"result": a["state"], "path": a["path"], "error_message": None}


def run_verification(doc: dict, master: dict, evidence: list[dict]) -> dict[str, Any]:
    """N14 — H07 시험 운영: 8개 회신 분기·시험 01~09를 같은 당시 자료로 돌린다(외부 송신 0건)."""
    d = _replay(doc)
    if d["adoption"] is None:
        raise DomainError("재현 회신 판정 전에는 시험하지 않는다", 409)
    if doc["verification"] is None:
        branches = [_evaluate(doc, master, b) for b in master["replay_branches"]]
        base = _branch(master, BASE_BRANCH)

        def variant(change: dict, reflect: Any = "source") -> dict:
            return _evaluate(doc, master, {**base, **change}, reflect=reflect)

        no_pod = [
            e
            for e in evidence
            if not (e["kind"] == "delivery_receipt" and e["commitment_id"] == calc.TARGET)
        ]
        found = calc.verify(
            master=master,
            screening=d["snapshot"],
            branch_results=branches,
            evaluate=variant,
            outcome_now=doc["outcome"],
            outcome_missing_pod=calc.outcome(master, no_pod, _links(doc)),
            sends=d["external_sends"],
        )
        doc["verification"] = {
            **found,
            "branches": branches,
            "run_at": doc["clock"],
            "run_by": "Y01",
            "operator_role": "H07",
            "execution_mode": "rule",
            "verdict": None,
            "verdict_by": None,
            "verdict_at": None,
            "state": "RUN",
        }
        audit(doc, actor="Y01", action="verification_run", passed=found["passed"])
    v = doc["verification"]
    doc["bpm"]["waiting"] = [{"node_id": TEST_NODE, "title": f"시험 판정 기록 — {calc.TEST_ID}"}]
    return {"test_id": calc.TEST_ID, "passed": v["passed"], "sample": v["sample_verdict"]}


def record_verdict(doc: dict, args: dict[str, Any]) -> dict[str, Any]:
    """N14 — H07이 실제 출력·기대값 차이·판정을 남긴다. 미통과를 통과로 적을 수 없다."""
    by = str(args.get("answered_by") or "")
    _holder(by, "H07", "시험 판정 기록")
    verdict = str(args.get("verdict") or "")
    if verdict not in (PASS, REWORK):
        raise DomainError(f"시험 판정은 {PASS}·{REWORK}다: {verdict}", 422)
    v = doc["verification"]
    if v is None:
        raise DomainError("시험을 돌리기 전이다", 409)
    if verdict == PASS and not v["passed"]:
        failed = [r["test_id"] for r in v["rows"] if r["verdict"] != "PASS"]
        raise DomainError(
            f"미통과 시험이 있다({', '.join(failed) or v['sample_verdict']}) — "
            "통과로 기록하지 않는다",
            422,
        )
    if v["verdict"] is None:
        v.update(
            verdict=verdict,
            verdict_by=by,
            verdict_role="H07",
            via=args.get("answered_via"),
            comment=str(args.get("comment") or ""),
            verdict_at=doc["clock"],
            state="PASSED" if verdict == PASS else "REWORK",
        )
        audit(doc, actor=by, action="verification_recorded", verdict=verdict)
    elif v["verdict"] != verdict:
        raise DomainError(f"이미 「{v['verdict']}」로 기록했다", 409)
    doc["bpm"]["waiting"] = (
        [{"node_id": APPLY_NODE, "title": f"적용안 확인 — {calc.APPROVAL_ID} (H06)"}]
        if v["state"] == "PASSED"
        else []
    )
    return {"result": v["state"], "error_message": None}


def confirm_application(doc: dict, args: dict[str, Any]) -> dict[str, Any]:
    """N15 — H06이 검증된 기준의 적용 범위·효력시점을 확인한다(APP-04). 소급 적용은 없다."""
    by = str(args.get("answered_by") or "")
    _holder(by, "H06", "적용안 확인")
    decision = str(args.get("decision") or "")
    if decision not in (CONFIRM, HOLD):
        raise DomainError(f"적용 확인은 {CONFIRM}·{HOLD}다: {decision}", 422)
    v = doc["verification"]
    if v is None or v["state"] != "PASSED":
        raise DomainError("시험 통과 기록이 없다 — 적용을 확인하지 않는다", 409)
    scope = str(args.get("scope") or "").strip()
    effective = str(args.get("effective_at") or "").strip()
    if decision == CONFIRM:
        if not scope:
            raise DomainError("적용 범위가 없다", 422)
        when = calc.at(effective)
        if when is None:
            raise DomainError(f"효력시점은 시간대 있는 ISO 시각이다: {effective!r}", 422)
        if when <= parse_at(doc["clock"]):
            raise DomainError("효력시점이 지금보다 앞이다 — 과거 사건에 소급하지 않는다", 422)
    a = doc["approval"]
    if a is not None:
        if a["decision"] != decision:
            raise DomainError(f"이미 「{a['decision']}」로 확인했다", 409)
        return _apply_out(a)
    doc["approval"] = a = {
        "approval_id": calc.APPROVAL_ID,
        "kind": "standard_apply",  # 생산계획 확인(production_plan_apply)과 다른 승인이다
        "version": calc.KRI_VERSION,
        "test_id": calc.TEST_ID,
        "decision": decision,
        "state": "CONFIRMED" if decision == CONFIRM else "HELD",
        "scope": scope or None,
        "effective_at": calc.iso(calc.at(effective)) if decision == CONFIRM else None,
        "delegate_role": "H07",
        "delegate_name": catalog.HOLDERS["H07"][0],
        "actor": by,
        "actor_role": "H06",
        "via": args.get("answered_via"),
        "comment": str(args.get("comment") or ""),
        "confirmed_at": doc["clock"],
        "note": "기준 확인과 Agent 설정 권한을 나눈다 — 설정은 H07이 위임 범위 안에서 한다",
    }
    doc["bpm"]["waiting"] = (
        [{"node_id": CONFIG_NODE, "title": f"위임 설정 반영 — {calc.CONFIG_ID} (H07)"}]
        if decision == CONFIRM
        else []
    )
    audit(doc, actor=by, action="standard_confirmed", decision=decision)
    return _apply_out(a)


def _apply_out(a: dict) -> dict[str, Any]:
    return {"result": a["state"], "approval_id": a["approval_id"], "error_message": None}


def apply_config(doc: dict, args: dict[str, Any], master: dict) -> dict[str, Any]:
    """
    N16 — H07이 H06이 확인한 범위·효력시점 그대로 설정을 반영한다(CFG-04). 신규 사건만 개선 버전,
    기존 사건(CASE-S2-01)은 당시 버전이다.
    """
    by = str(args.get("answered_by") or "")
    _holder(by, "H07", "위임 설정 반영")
    if str(args.get("decision") or "") != SET:
        raise DomainError(f"설정 반영은 「{SET}」이다", 422)
    a = doc["approval"]
    if a is None or a["state"] != "CONFIRMED":
        raise DomainError("H06 적용 확인(APP-04)이 없다 — 설정하지 않는다", 409)
    version = str(args.get("version") or "").strip()
    if version != a["version"]:
        raise DomainError(
            f"설정 버전 {version or '없음'}이 확인한 버전 {a['version']}이 아니다", 422
        )
    if doc["config"] is None:
        state = calc.application_state(doc["verification"]["sample_verdict"], True)
        case_at = _event(master, calc.SNAPSHOT_ID)["at"]
        doc["config"] = {
            "config_id": calc.CONFIG_ID,
            "version": a["version"],
            "approval_id": a["approval_id"],
            "test_id": calc.TEST_ID,
            "scope": a["scope"],
            "effective_at": a["effective_at"],
            "set_by": by,
            "set_role": "H07",
            "via": args.get("answered_via"),
            "comment": str(args.get("comment") or ""),
            "set_at": doc["clock"],
            "state": state,
            "cases": [
                {
                    "case_id": calc.NEXT_CASE,
                    "at": calc.NEXT_CASE_AT,
                    "version": calc.version_for(calc.NEXT_CASE_AT, a["effective_at"]),
                    "flow": "주문 여유 산출 → H04 조정 요청",
                    "roles": ["A01", "H04"],
                    "example": True,
                    "watch": ["요청 적시성", "운송사 수락", "실제 운임"],
                },
                {
                    "case_id": CASE_ID,
                    "at": case_at,
                    "version": calc.version_for(case_at, a["effective_at"]),
                    "flow": "조회 기준 · 원결정 및 실적 이력",
                    "roles": [],
                    "example": False,
                    "watch": [],
                },
            ],
            "note": "한 사건으로 전사 절감률을 추정하지 않는다 — 다음 사건부터 관찰한다",
        }
        audit(doc, actor=by, action="standard_config_set", config_id=calc.CONFIG_ID)
    doc["bpm"]["waiting"] = []
    return {"config_id": calc.CONFIG_ID, "state": doc["config"]["state"], "error_message": None}


def run_operation(
    doc: dict, operation: str, args: dict[str, Any], master: dict, company: Any
) -> dict[str, Any]:
    """일감 하나 — 증빙·원업무를 읽는 작업은 회사 시스템에서 지금 값을 다시 읽는다."""
    case = args.get("case_id")
    if case is not None and case != CASE_ID:
        raise DomainError(f"이 데모 실행의 사건은 {CASE_ID}다: {case}", 404)
    if operation == "link_execution_results":
        return link_results(doc, master, company.execution_evidence(doc["demo_run_id"]))
    if operation == "start_standard_improvement":
        return start_improvement(doc, args)
    if operation == "replay_route_screening":
        return replay_screening(doc, master, _inquiry(company, doc["demo_run_id"]))
    if operation == "send_route_request":
        return send_request(doc, args, master)
    if operation == "receive_route_reply":
        return receive_reply(doc, master)
    if operation == "confirm_route_impact":
        return confirm_impact(doc, args, master)
    if operation == "run_standard_verification":
        return run_verification(doc, master, company.execution_evidence(doc["demo_run_id"]))
    if operation == "record_verification_verdict":
        return record_verdict(doc, args)
    if operation == "confirm_standard_application":
        return confirm_application(doc, args)
    if operation == "apply_standard_config":
        return apply_config(doc, args, master)
    raise DomainError(f"모르는 작업: {operation} (가능: {', '.join(OPERATIONS)})", 404)


def _inquiry(company: Any, world_id: str) -> dict | None:
    try:
        return company.shipping_inquiry(world_id, WORK_ID)
    except DomainError as exc:
        if exc.status == 404:
            return None
        raise


NODE_OF = {
    "link_execution_results": "Task_Results",
    "start_standard_improvement": "Record_Start",
    "replay_route_screening": "Task_Replay",
    "send_route_request": "Record_Request",
    "receive_route_reply": "Task_Reply",
    "confirm_route_impact": "Record_Impact",
    "run_standard_verification": "Task_Verify",
    "record_verification_verdict": "Record_Test",
    "confirm_standard_application": "Record_Apply",
    "apply_standard_config": "Record_Config",
}
#: 기록 작업의 결재 — 결재 노드는 일감이 없다. 그 기록이 오면 지나온 것이다
APPROVAL_OF = {
    "start_standard_improvement": START_NODE,
    "send_route_request": REQUEST_NODE,
    "confirm_route_impact": IMPACT_NODE,
    "record_verification_verdict": TEST_NODE,
    "confirm_standard_application": APPLY_NODE,
    "apply_standard_config": CONFIG_NODE,
}


def ends_flow(operation: str, out: dict[str, Any]) -> str | None:
    """그 작업 뒤에 흐름이 끝나는가 — 끝 노드 id."""
    if operation == "start_standard_improvement" and out.get("result") == "NOT_NEEDED":
        return "End_NoImprovement"
    if operation == "replay_route_screening" and not out.get("requested"):
        return "End_NoCandidate"
    if operation == "record_verification_verdict" and out.get("result") == "REWORK":
        return "End_TestFailed"
    if operation == "confirm_standard_application" and out.get("result") == "HELD":
        return "End_ApplyHeld"
    if operation == "apply_standard_config":
        return "End"
    return None


def _failure_of(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        data = event.get("data") or {}
        if event.get("kind") == "node_state" and data.get("state") == "failed":
            return f"{data.get('error_code') or 'failed'}: {data.get('message') or '-'}"
    for event in reversed(events):
        if event.get("kind") == "run_finished":
            data = event.get("data") or {}
            code = data.get("error_code") or data.get("status")
            return f"{code}: {data.get('error_message') or '-'}"
    return None


# ─────────────────────────── 프로세스 ───────────────────────────


class S2Sc04Process:
    def __init__(
        self,
        store: Sc01Store,
        *,
        company: CompanyClient,
        sc03: Any,
        center: CenterClient | None = None,
        publish: Callable[[str], None] = lambda _id: None,
    ) -> None:
        self.store = store
        self.company = company
        self.sc03 = sc03
        self.center = center or CenterClient(CenterConfig())
        self.publish = publish
        self.process = read_process(PROCESS_PATH.read_bytes())
        self.processes: dict[str, Any] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock(self, demo_run_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(demo_run_id, threading.Lock())

    def _load(self, demo_run_id: str) -> tuple[dict, int]:
        found = self.store.load(demo_run_id)
        if found is None:
            raise DomainError(f"시나리오 2 장면 4를 열지 않은 데모 실행: {demo_run_id}", 404)
        return found

    def get(self, demo_run_id: str) -> dict:
        return self._load(demo_run_id)[0]

    def master(self) -> dict:
        return self.company.s2_master()

    def _write_records(self, doc: dict) -> None:
        from app.s2.sc04.records import records_of

        records.write(self.company, doc, SCENE, records_of(doc, self.master()))

    def _commit(self, doc: dict, version: int, event: str) -> dict:
        self._write_records(doc)
        try:
            self.store.save(doc["demo_run_id"], doc, version, event)
        except StaleWrite as exc:
            raise DomainError("다른 요청이 먼저 바꿨다 — 다시 하라", 409) from exc
        self.publish(f"s2sc04:{doc['demo_run_id']}")
        return doc

    # ───────────── 열기·초기화·거두기 ─────────────

    def _new(self, demo_run_id: str, *, case_id: str, executor: str, world_generation: int | None):
        sc03_doc = self.sc03.get(demo_run_id)
        sc02_doc = self.sc03.sc02.get(demo_run_id)
        doc = new_doc(
            demo_run_id,
            source_of(sc03_doc, sc02_doc),
            case_id=case_id,
            executor=executor,
            world_generation=world_generation
            if world_generation is not None
            else sc03_doc.get("world_generation"),
        )
        doc["clock"] = self.company.world(demo_run_id)["clock"]
        got = self.company.execution_evidence(demo_run_id)
        doc["company_log"].append(
            {
                "at": doc["clock"],
                "direction": "in",
                "what": f"실행 증빙 읽기 — {len(got)}건"
                + (f" ({', '.join(e['source_id'] for e in got)})" if got else ""),
            }
        )
        records.restart(self.company, doc, SCENE)
        return doc

    def create(
        self,
        demo_run_id: str,
        *,
        case_id: str = "BASE",
        executor: str = "center",
        world_generation: int | None = None,
        actor: str = "system",
    ) -> dict:
        """장면 4 열기 — 장면 3 인계 사본을 들고 문서를 만들고, Center 실행이면 기동한다."""
        with self._lock(demo_run_id):
            found = self.store.load(demo_run_id)
            if found is not None:
                return found[0]
            doc = self._new(
                demo_run_id, case_id=case_id, executor=executor, world_generation=world_generation
            )
            audit(doc, actor=actor, action="scene_opened", case_id=case_id)
            if executor == "center":
                self._start_job(doc)
            self._write_records(doc)
            self.store.insert(demo_run_id, doc)
        self.publish(f"s2sc04:{demo_run_id}")
        return doc

    def reset(
        self,
        demo_run_id: str,
        *,
        actor: str = "u-demo",
        case_id: str | None = None,
        executor: str | None = None,
    ) -> dict:
        """장면 4만 처음으로 — Center 작업을 거두고 다시 연다."""
        self.discard(demo_run_id)
        return self.create(
            demo_run_id, case_id=case_id or "BASE", executor=executor or "center", actor=actor
        )

    def discard(self, demo_run_id: str) -> None:
        found = self.store.load(demo_run_id)
        if found is not None:
            self._cancel_job(found[0])
        self.store.delete(demo_run_id)

    def follow_clock(self, demo_run_id: str, at: str) -> dict:
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if doc["clock"] and parse_at(at) <= parse_at(doc["clock"]):
                return doc
            doc["clock"] = at
            return self._commit(doc, version, "clock")

    # ───────────── 실행 증빙 ─────────────

    def receive_evidence(self, demo_run_id: str, doc_id: str) -> dict | None:
        """
        세계 따라가기가 기간계의 새 실행 증빙을 넘긴다. 실행이 증빙을 기다리면 Center에 메시지를
        보내 깨운다. 대조가 끝난 뒤의 정정 증빙은 결과를 새 판으로 다시 대조한다(이전 판 보존).
        """
        if self.store.load(demo_run_id) is None:
            return None
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if doc_id in doc["evidence_seen"]:
                return doc
            evidence = self.company.execution_evidence(demo_run_id)
            src = next((e for e in evidence if e["doc_id"] == doc_id), None)
            if src is None:
                raise DomainError(f"없는 실행 증빙: {doc_id}", 404)
            doc["evidence_seen"].append(doc_id)
            doc["company_log"].append(
                {
                    "at": doc["clock"],
                    "direction": "in",
                    "what": f"증빙 받기 {src['source_id']} ({src['kind']}) — 등록 "
                    f"{src['registered_at'][11:16]}",
                }
            )
            waiting = any(w["node_id"] == WAIT_NODE for w in doc["bpm"]["waiting"])
            if doc["outcome"] is not None and not waiting:
                _set_outcome(doc, self.master(), evidence)
            if waiting:
                doc["wait"]["message_pending"] = True
                self._send_message(doc, src["source_id"])
            self._commit(doc, version, "evidence")
            return doc

    def _send_message(self, doc: dict, source_id: str) -> None:
        if doc["executor"] != "center" or self.center.config.missing(integration=True):
            return
        doc["wait"]["attempts"] += 1
        try:
            self.center.send_message(
                MESSAGE,
                correlation=doc["demo_run_id"],
                payload={"증빙ID": source_id},
                idempotency_key=(
                    f"s2sc04:{doc['demo_run_id']}:e{doc['center_epoch']}:{source_id}:"
                    f"{doc['wait']['attempts']}"
                ),
                on_behalf=ON_BEHALF,
            )
        except CenterError as exc:
            log.info(
                "증빙 메시지를 넣지 못했다(%s) — 다시 보낸다: %s", doc["demo_run_id"], exc.message
            )
            return
        doc["wait"]["message_pending"] = False
        audit(doc, actor="system", action="center_message_sent", source_id=source_id)

    # ───────────── Center ─────────────

    def _center_key(self, doc: dict) -> str:
        return f"s2sc04:{doc['demo_run_id']}:e{doc['center_epoch']}"

    def _start_job(self, doc: dict) -> None:
        bpm = doc["bpm"]
        problem = self.center.config.missing(integration=True)
        if problem:
            bpm["problem"] = f"{problem} — 장면 4를 기동하지 않았다. Center에서 직접 기동하라"
            return
        try:
            job = self.center.start_job(
                {"데모실행ID": doc["demo_run_id"], "사건ID": CASE_ID},
                idempotency_key=self._center_key(doc),
                on_behalf=ON_BEHALF,
                package=self.center.config.s2_sc04_package,
                note="NowView S2 SC04 — 실행 결과 확인과 관리기준 개선",
            )
        except CenterError as exc:
            bpm["problem"] = f"Center가 기동을 거절했다 — {exc.code}: {exc.message}"
            return
        bpm.update(job_id=job["job_id"], state="running", problem=None)
        audit(doc, actor="system", action="center_job_started", job_id=job["job_id"])

    def _cancel_job(self, doc: dict) -> None:
        bpm = doc.get("bpm") or {}
        if bpm.get("job_id") and bpm.get("state") == "running":
            try:
                self.center.cancel_job(bpm["job_id"])
            except CenterError as exc:
                log.info("Center 작업을 거두지 못했다 %s: %s", bpm["job_id"], exc.message)

    def poll_center(self) -> int:
        """도는 Center 실행 — 못 넣은 증빙 메시지를 다시 보내고, 실패한 실행의 사유를 남긴다."""
        if self.center.config.missing(integration=True):
            return 0
        changed = 0
        for demo_run_id in self.store.running_external("center"):
            try:
                changed += self._resend(demo_run_id)
                changed += self.sync_center(demo_run_id)
            except (CenterError, DomainError) as exc:
                log.warning("Center 진행을 읽지 못했다 (%s): %s", demo_run_id, exc)
        return changed

    def _resend(self, demo_run_id: str) -> int:
        doc = self.get(demo_run_id)
        waiting = any(w["node_id"] == WAIT_NODE for w in doc["bpm"]["waiting"])
        if not (waiting and doc["wait"]["message_pending"]):
            return 0
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            seen = doc["evidence_seen"][-1] if doc["evidence_seen"] else None
            if not doc["wait"]["message_pending"] or seen is None:
                return 0
            got = {e["doc_id"]: e for e in self.company.execution_evidence(demo_run_id)}
            self._send_message(doc, got[seen]["source_id"])
            self._commit(doc, version, "message")
        return 1

    def sync_center(self, demo_run_id: str) -> int:
        doc = self.get(demo_run_id)
        bpm = doc["bpm"]
        if bpm.get("state") != "running" or not bpm.get("job_id"):
            return 0
        info = self.center.job(bpm["job_id"])
        state, status = info.get("state"), info.get("run_status")
        if state in ("rejected", "expired", "cancelled"):
            ended = ("failed", f"작업 {state}: {info.get('state_reason') or '-'}")
        elif status in ("failed", "cancelled"):
            ext = bpm.get("external_run_id") or info.get("run_id")
            reason = _failure_of(self.center.run_events(ext)) if ext else None
            ended = ("failed", f"실행 {status} — {reason or '사유 없음'}")
        elif status == "success":
            ended = ("done", None)
        else:
            return 0
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if doc["bpm"].get("state") != "running":
                return 0
            doc["bpm"].update(state=ended[0], problem=ended[1])
            if ended[1]:
                audit(doc, actor="system", action="center_run_failed", reason=ended[1])
            self._commit(doc, version, "center")
        return 1

    # ───────────── 일감 ─────────────

    def operate(
        self,
        demo_run_id: str,
        operation: str,
        args: dict[str, Any],
        *,
        external_run_id: str | None,
        node_id: str | None = None,
        via: str | None = None,
    ) -> dict[str, Any]:
        if operation not in OPERATIONS:
            raise DomainError(f"모르는 작업: {operation} (가능: {', '.join(OPERATIONS)})", 404)
        master = self.master()
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            self._link(doc, external_run_id, via)
            out = run_operation(doc, operation, args, master, self.company)
            bpm = doc["bpm"]
            end = ends_flow(operation, out)
            before = (APPROVAL_OF[operation],) if operation in APPROVAL_OF else ()
            after = (
                (WAIT_NODE,) if operation == "link_execution_results" and not out["ready"] else ()
            )
            for nid in (*before, node_id or NODE_OF[operation], *after, end):
                if nid and nid not in bpm["visited"]:
                    bpm["visited"].append(nid)
            if end:
                bpm.update(state="done", waiting=[])
            self._commit(doc, version, operation)
        return out

    def _link(self, doc: dict, external_run_id: str | None, via: str | None) -> None:
        if via is not None and via != doc["executor"]:
            raise DomainError(
                f"일감이 {via}에서 왔는데 이 데모 실행은 {doc['executor']}용이다 — "
                "실행 위치를 맞춰라",
                409,
            )
        if not external_run_id:
            raise DomainError("바깥 실행 id가 없다 — 일감의 멱등 칸에 run_id가 있어야 한다", 422)
        bpm = doc["bpm"]
        if bpm["external_run_id"] is None:
            bpm.update(external_run_id=external_run_id, state="running")
        elif bpm["external_run_id"] != external_run_id:
            raise DomainError(f"이 장면은 이미 다른 실행({bpm['external_run_id']})이 처리한다", 409)


__all__ = ["CASES", "OPERATIONS", "S2Sc04Process", "WORK", "run_operation"]
