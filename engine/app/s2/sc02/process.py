"""
시나리오 2 장면 2 실행 — 정형통제 실행과 주문별 분기(N03A~N08, `docs/s2/sc02.md`).

* **장면 1 인계(HAND-01)에서 시작한다** — 같은 데모 실행·같은 Case(CASE-S2-01)를 잇고 새 사건을
  만들지 않는다. 사이트의 「장면 열기」(기간계 명령 `open`)가 이 장면 문서를 만들고 Center에
  `company1.s2.sc02`를 기동한다(입력 `데모실행ID`·`사건ID`). 장면 1의 분석·인계는 그 시점 사본이다.
* **그림**(`processes/s2-sc02.bpmn`): 공통 BPM `platform.case-plan` 호출(A03 제안 → Y01 검사 → 적용
—
  위임 범위 안이면 구성 승인 없음) → 변경안 작성(A02) → **H03 확인 결재 한 번** → 확인 기록 → 반영 →
  재조회 대조(미반영 확인분만 같은 실행키로 다시) → 주문별 재평가 → 잔여 위험이 있으면 장면 3 인계.
* **생산계획의 원본은 회사 시스템이다**(M20·M21) — 반영은 기간계 생산계획 저장소에 주문 한 행씩
  실행키(run·확인 ID·약정)로 적고, 대조는 거기서 **다시 읽은** 값으로 한다. 화면 초안 복사는 대조가
  아니다(구현명세 §2).
* **결재는 회사 사이트가 한다**(Center 대리 답 — 사이트의 직원 결재 화면). NowView는 대리 답하지
않는다.
  결재가 열려 있는지는 변경안 작성 일감이 알려 준다(다음 노드가 그 결재다).
* 사례(`case_id`) — 기본 시연 외의 변형은 시험·시연용이다(구현명세 §5 「오류 시험은 별도 실행」):
  `PLAN-NO-U03`(A03 제안이 필수 확인을 빠뜨림 — T01), `LINE-CONFLICT`(배경 주문 COM-D2가 R의 라인을
  쓴다
  — T05), `R-LOST`(R 반영 응답 유실 — T07), `NO-TRUCK`(R 정기차 자료 누락 — T08).
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
from app.s2.sc02 import calc
from app.sc01.center import CenterClient, CenterConfig, CenterError
from app.sc01.domain import DomainError, parse_at
from app.sc01.store import Sc01Store, StaleWrite

PROCESS_PATH = Path(__file__).resolve().parents[3] / "processes" / "s2-sc02.bpmn"
#: 그림이 호출하는 공통 BPM(`docs/platform.md` §5) — 패키지 `libs/`에 받아 둔 사본과 같은 그림
CALLED_PATHS = (Path(__file__).resolve().parents[3] / "processes" / "case-plan.bpmn",)
SCENARIO = "s2"
SCENE = 2
#: NowView 업무 번호 — 시나리오 2 장면 N은 20 + N(`docs/platform.md` §7)
WORK = 22
OPERATIONS = (
    # 공통 BPM `platform.case-plan`의 작업 — 이름은 공통이고 내용은 이 업무의 것이다
    "propose_case_plan",
    "check_case_plan",
    "apply_case_plan",
    "draft_production_change",
    "confirm_production_change",
    "apply_production_change",
    "requery_production_plan",
    "reassess_delivery_risk",
    "hand_off_residual_risk",
)
CASES = ("BASE", "PLAN-NO-U03", "LINE-CONFLICT", "R-LOST", "NO-TRUCK")
CASE_ID = "CASE-S2-01"
PLAN_ID = f"{calc.PLAN_PREFIX}1"
#: 주문별 판정 기록 id — 자료는 「판정 버전 + 약정」이라고만 한다(구현용 보완)
ASSESSMENT_ID = "JDG-S2-01"
HANDOFF_ID = "HAND-02"
APPROVAL_NODE = "Approve_Change"
ON_BEHALF = "시스템 자동처리"
#: 확인 결정 — 결재 폼의 선택지
CONFIRM, REWORK = "확정", "보완요청"

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
        "plan": None,
        "drafts": [],
        "confirmations": [],
        "apply": None,
        "readback": None,
        "assessments": [],
        "handoff": None,
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


def source_of(sc01_doc: dict[str, Any]) -> dict[str, Any]:
    """
    장면 1 인계의 사본 — Case·약정·분석 판·근거 시각. 장면 1을 초기화해도 장면 2의 근거는 그 시점
    것이다(시나리오 1 장면 2의 `doc.sc01`과 같은 원칙).
    """
    handoff = sc01_doc.get("handoff")
    if not handoff or not sc01_doc.get("analyses"):
        raise DomainError("장면 1 인계(HAND-01)가 아직 없다 — 영향 분석·인계 뒤에 연다", 409)
    analysis = sc01_doc["analyses"][-1]
    if analysis["version"] != handoff["analysis"]["version"]:
        raise DomainError("인계한 분석 판과 최신 분석 판이 다르다 — 장면 1을 다시 인계한다", 409)
    return {
        "handoff": copy.deepcopy(handoff),
        "case_id": handoff["case_id"],
        "alert_id": handoff["alert_id"],
        "revision_id": handoff["revision_id"],
        "commitments": list(handoff["commitments"]),
        "analysis": {
            "analysis_id": analysis["analysis_id"],
            "version": analysis["version"],
            "data_as_of": analysis["data_as_of"],
            "rows": copy.deepcopy(analysis["rows"]),
        },
        "case_state": (sc01_doc.get("case") or {}).get("state"),
    }


# ─────────────────────────── 사례 변형 ───────────────────────────


def master_of(doc: dict, master: dict) -> dict:
    """사례의 회사 자료 — `NO-TRUCK`은 R의 정기차 자료가 없다(T08). 원본은 바꾸지 않는다."""
    if doc["case_id"] != "NO-TRUCK":
        return master
    found = copy.deepcopy(master)
    found["trucks"] = [t for t in found["trucks"] if t["commitment_id"] != "COM-R"]
    return found


def plan_of(doc: dict, plan: dict) -> dict:
    """
    사례의 생산계획 — `LINE-CONFLICT`는 배경 주문 COM-D2가 R의 라인(b)을 13:00~15:00 쓰고 있다(T05,
    구현용 보완 — 자료의 배경 주문은 제 모델 라인에 있어 겹치지 않는다).
    """
    if doc["case_id"] != "LINE-CONFLICT":
        return plan
    found = copy.deepcopy(plan)
    for r in found["rows"]:
        if r["commitment_id"] == "COM-D2":
            r.update(
                line_id="ULS-A-b",
                start="2026-11-05T13:00:00+09:00",
                end="2026-11-05T15:00:00+09:00",
            )
    return found


# ─────────────────────────── 작업 (일꾼·시험이 같은 함수) ───────────────────────────


def _plan(doc: dict) -> dict:
    if doc["plan"] is None:
        raise DomainError("수행계획이 아직 없다 — A03 제안 뒤에", 409)
    return doc["plan"]


def propose_plan(doc: dict) -> dict[str, Any]:
    """N03A — A03이 업무 조합을 제안한다. 같은 사건에 두 번 오면 같은 제안을 돌려준다."""
    if doc["plan"] is None:
        omit = ("U03",) if doc["case_id"] == "PLAN-NO-U03" else ()
        doc["plan"] = {
            "plan_id": PLAN_ID,
            "version": 1,
            "case_id": CASE_ID,
            "items": calc.propose(doc["source"]["handoff"], omit=omit),
            "proposed_at": doc["clock"],
            "proposed_by": "A03",
            # 고정 규칙으로 고른다 — 실제 Agent 호출로 표시하지 않는다(F05)
            "execution_mode": "rule",
            "check": None,
            "state": "PROPOSED",
            "applied_at": None,
            "production_plan_version": None,
        }
        audit(doc, actor="A03", action="plan_proposed", plan_id=PLAN_ID)
    p = doc["plan"]
    return {"plan_id": p["plan_id"], "version": p["version"], "items": len(p["items"])}


def check_plan(doc: dict) -> dict[str, Any]:
    """N03A — Y01이 위임 범위·필수 확인을 검사한다. 차단이면 생산계획을 건드리지 않고 끝난다."""
    p = _plan(doc)
    if p["check"] is None:
        p["check"] = {
            **calc.check(p["items"], doc["source"]["handoff"]["handoff_id"]),
            "checked_at": doc["clock"],
        }
        p["state"] = "BLOCKED" if p["check"]["result"] == calc.BLOCKED else "CHECKED"
        audit(doc, actor="Y01", action="plan_checked", result=p["check"]["result"])
    c = p["check"]
    reason = " · ".join(i["message"] for i in c["issues"]) or "허용 업무 조합 · 필수 확인 포함"
    return {"result": c["result"], "issues": len(c["issues"]), "reason": reason}


def apply_plan(doc: dict, plan_now: dict) -> dict[str, Any]:
    """N03A — 위임 범위 안 조합을 사건에 적용한다. **실제 생산계획은 그대로다**(T01)."""
    p = _plan(doc)
    if (p.get("check") or {}).get("result") != calc.PASS:
        raise DomainError("Y01 검사를 통과하지 않은 수행계획은 적용하지 않는다", 409)
    if p["state"] != "APPLIED":
        p.update(
            state="APPLIED", applied_at=doc["clock"], production_plan_version=plan_now["version"]
        )
        audit(doc, actor="Y01", action="plan_applied", plan_id=p["plan_id"])
    return {
        "plan_id": p["plan_id"],
        "state": p["state"],
        "production_plan": p["production_plan_version"],
    }


def _draft(doc: dict) -> dict:
    if not doc["drafts"]:
        raise DomainError("변경안이 아직 없다", 409)
    return doc["drafts"][-1]


def draft_change(doc: dict, master: dict, plan_now: dict) -> dict[str, Any]:
    """
    N04 — A02 변경안. 입력이 같으면 같은 판을 돌려준다(재시도). 확인 뒤 전제가 바뀌어(반영 차단)
    다시 오면 새 판이다 — 이전 판과 확인 이력은 보존한다(T04).
    """
    if (doc["plan"] or {}).get("state") != "APPLIED":
        raise DomainError("수행계획이 적용되지 않았다 — 변경안을 쓰지 않는다", 409)
    found = calc.draft(doc["source"]["analysis"]["rows"], master, plan_of(doc, plan_now))
    digest = calc.content_hash(found)
    last = doc["drafts"][-1] if doc["drafts"] else None
    if last is not None and last["content_hash"] == digest and last["state"] != "STALE":
        return _draft_out(last)
    n = len(doc["drafts"]) + 1
    entry = {
        "draft_id": f"{calc.DRAFT_PREFIX}{n}",
        "version": n,
        "case_id": CASE_ID,
        "plan_id": PLAN_ID,
        "content_hash": digest,
        **found,
        "inputs": {
            "analysis": doc["source"]["analysis"]["analysis_id"],
            "analysis_version": doc["source"]["analysis"]["version"],
            "revision_id": doc["source"]["revision_id"],
            "data_as_of": doc["source"]["analysis"]["data_as_of"],
        },
        "drafted_at": doc["clock"],
        "drafted_by": "A02",
        "execution_mode": "rule",
        "state": "AWAITING_CONFIRM",
        "supersedes": last["draft_id"] if last else None,
    }
    doc["drafts"].append(entry)
    doc["bpm"]["waiting"] = [
        {"node_id": APPROVAL_NODE, "title": f"생산계획 변경안 확인 — {entry['draft_id']}"}
    ]
    audit(doc, actor="A02", action="change_drafted", draft_id=entry["draft_id"])
    return _draft_out(entry)


def _draft_out(d: dict) -> dict[str, Any]:
    issues = [f"{r['commitment_id']}: {i}" for r in d["rows"] for i in r["issues"]]
    return {
        "draft_id": d["draft_id"],
        "content_hash": d["content_hash"],
        "check": "OK" if d["confirmable"] else "CONFLICT",
        "issues": len(issues),
        "reason": " · ".join(issues) or "자재·라인·품질 조건 충족 · 배경 주문 일정 유지",
    }


def confirm_change(doc: dict, args: dict[str, Any]) -> dict[str, Any]:
    """
    N05 — H03의 확인 한 번(두 주문을 포함한 변경안 한 버전). 권한·최신성은 서버가 검사한다(T03·T04).
    같은 판의 같은 결정이 다시 오면 기존 결과를 돌려준다(중복 클릭). 보완 요청이면 원계획 유지.
    """
    by = str(args.get("answered_by") or "")
    if by not in catalog.HOLDERS["H03"]:
        raise DomainError(
            f"생산계획 변경 확인은 생산관리 책임자(H03)만 한다 — {by or '이름 없음'}", 403
        )
    decision = str(args.get("decision") or "")
    if decision not in (CONFIRM, REWORK):
        raise DomainError(f"결정은 {CONFIRM}·{REWORK}다: {decision or '빈 값'}", 422)
    d = _draft(doc)
    version = str(args.get("version") or "")
    if version != d["draft_id"]:
        raise DomainError(f"본 변경안({version or '없음'})이 최신({d['draft_id']})이 아니다", 409)
    if str(args.get("content_hash") or "") != d["content_hash"]:
        raise DomainError("변경안 내용 식별값이 다르다 — 화면을 다시 열어 확인한다", 409)
    done = next(
        (
            c
            for c in doc["confirmations"]
            if c["draft_id"] == d["draft_id"] and c["decision"] == decision
        ),
        None,
    )
    if done is not None:
        return {"approval_id": done["approval_id"], "state": done["state"], "error_message": None}
    if decision == CONFIRM and not d["confirmable"]:
        issues = " · ".join(f"{r['commitment_id']}: {i}" for r in d["rows"] for i in r["issues"])
        raise DomainError(f"확정할 수 없는 변경안이다 — 보완 요청만 할 수 있다: {issues}", 422)
    n = len(doc["confirmations"]) + 1
    entry = {
        "approval_id": f"APP-{n:02d}",
        "kind": "production_plan_apply",  # 수행계획 적용(plan_apply)과 다른 승인이다(F24)
        "draft_id": d["draft_id"],
        "content_hash": d["content_hash"],
        "base_version": d["base_version"],
        "case_id": CASE_ID,
        "decision": decision,
        "state": "CONFIRMED" if decision == CONFIRM else "REWORK_REQUESTED",
        "actor": by,
        "actor_role": "H03",
        "via": args.get("answered_via"),
        "comment": str(args.get("comment") or ""),
        "confirmed_at": doc["clock"],
        "targets": [r["commitment_id"] for r in d["rows"]],
        "target_version": calc.TARGET_VERSION if decision == CONFIRM else None,
        "note": "생산 가능시간의 확정 — 운송 승인·고객 약정 변경이 아니다",
    }
    doc["confirmations"].append(entry)
    d["state"] = "CONFIRMED" if decision == CONFIRM else "REWORK_REQUESTED"
    doc["bpm"]["waiting"] = []
    audit(
        doc,
        actor=by,
        action="change_confirmed",
        decision=decision,
        approval_id=entry["approval_id"],
    )
    return {"approval_id": entry["approval_id"], "state": entry["state"], "error_message": None}


#: 반영해도 되는 확인의 상태 — 확인 완료 → 반영 중 → 반영·대조 완료(만료·보완 요청은 아니다)
VALID = ("CONFIRMED", "APPLYING", "APPLIED")


def _confirmed(doc: dict) -> tuple[dict, dict]:
    d = _draft(doc)
    c = doc["confirmations"][-1] if doc["confirmations"] else None
    if c is None or c["draft_id"] != d["draft_id"] or c["state"] not in VALID:
        raise DomainError("유효한 H03 확인이 없다 — 확인 전 반영 금지", 409)
    return d, c


def _key(doc: dict, approval_id: str, cid: str) -> str:
    return f"{doc['demo_run_id']}:{approval_id}:{cid}"


def apply_change(doc: dict, company: Any, plan_now: dict) -> dict[str, Any]:
    """
    N06 반영 — 반영 직전에 확인 유효성과 지금 원계획 버전을 다시 검사한다. 확인된 범위만, 주문 한
    행씩
    실행키로 적는다. 이미 일치로 재조회된 행은 다시 적지 않는다. 원계획이 바뀌었으면 반영하지 않고
    그 확인을 만료한다(새 판·재확인, T04).
    """
    d, c = _confirmed(doc)
    ours = plan_now["version"] == calc.TARGET_VERSION and any(
        r.get("approval_id") == c["approval_id"] for r in plan_now["rows"]
    )
    if plan_now["version"] != c["base_version"] and not ours:
        c.update(
            state="EXPIRED", expired_reason=f"원계획 {c['base_version']} → {plan_now['version']}"
        )
        d["state"] = "STALE"
        audit(doc, actor="Y01", action="apply_blocked", reason=c["expired_reason"])
        return {"result": "STALE", "applied": 0, "unknown": 0}
    c["state"] = "APPLYING"
    a = doc["apply"]
    if a is None or a["approval_id"] != c["approval_id"]:
        a = doc["apply"] = {
            "approval_id": c["approval_id"],
            "draft_id": d["draft_id"],
            "target_version": calc.TARGET_VERSION,
            "rows": {
                r["commitment_id"]: {
                    "state": "PENDING",
                    "execution_key": _key(doc, c["approval_id"], r["commitment_id"]),
                    "attempts": [],
                }
                for r in d["rows"]
            },
        }
    for r in d["rows"]:
        cid = r["commitment_id"]
        row = a["rows"][cid]
        if row["state"] in ("ACKNOWLEDGED", "MATCHED", "MISMATCH"):
            continue  # 이미 반영됐거나 대조가 끝났다 — 다시 적지 않는다
        if row["state"] == "UNKNOWN":
            continue  # 응답 유실 — 재조회로 미반영을 확인하기 전에는 다시 보내지 않는다
        if doc["case_id"] == "R-LOST" and cid == "COM-R" and not row["attempts"]:
            # 시연 모사 — 요청이 저장소에 닿기 전에 끊겼다. 실패로 확정하지 않는다(결과 미확인).
            row["attempts"].append({"at": doc["clock"], "outcome": "LOST", "mode": "mock"})
            row["state"] = "UNKNOWN"
            continue
        body = {
            "execution_key": row["execution_key"],
            "approval_id": c["approval_id"],
            "base_version": c["base_version"],
            "target_version": calc.TARGET_VERSION,
            "row": {k: r[k] for k in ("commitment_id", "qty", "start", "end", "line_id")},
        }
        try:
            got = company.apply_plan_row(doc["demo_run_id"], body)
        except DomainError as exc:
            if exc.status != 409:
                raise
            c.update(state="EXPIRED", expired_reason=str(exc))
            d["state"] = "STALE"
            audit(doc, actor="Y01", action="apply_blocked", reason=str(exc))
            return {"result": "STALE", "applied": 0, "unknown": 0}
        row["attempts"].append(
            {"at": doc["clock"], "outcome": "ACK", "created": got.get("created"), "mode": "company"}
        )
        row["state"] = "ACKNOWLEDGED"
        doc["company_log"].append(
            {
                "at": doc["clock"],
                "direction": "out",
                "what": f"생산계획 반영 {cid} → {calc.TARGET_VERSION} ({row['execution_key']})",
            }
        )
    states = [x["state"] for x in a["rows"].values()]
    unknown = states.count("UNKNOWN")
    audit(doc, actor="Y01", action="change_applied", unknown=unknown)
    return {
        "result": "PARTIAL" if unknown else "APPLIED",
        "applied": sum(1 for s in states if s in ("ACKNOWLEDGED", "MATCHED")),
        "unknown": unknown,
    }


def requery(doc: dict, plan_now: dict) -> dict[str, Any]:
    """
    N06 재조회 — 저장소에서 다시 읽은 값으로 대조한다. 원천 조회로 **미반영이 확인된** 결과 미확인
    행만
    같은 실행키로 다시 보낸다(`retry`). 불일치 행과 증적은 보존하고 다시 반영하지 않는다.
    """
    d, c = _confirmed(doc)
    a = doc["apply"]
    found = calc.compare(d["rows"], plan_now, c["approval_id"])
    retry = False
    for cid, r in found.items():
        row = a["rows"][cid]
        if r["match"] == calc.MATCHED:
            row["state"] = "MATCHED"
        elif r["match"] == calc.MISMATCH:
            row["state"] = "MISMATCH"
        elif row["state"] == "UNKNOWN" and len(row["attempts"]) < 2:
            row["state"] = "PENDING"
            row["attempts"][-1]["requery"] = "미반영 확인 — 같은 실행키로 다시"
            retry = True
    doc["readback"] = {
        "version": plan_now["version"],
        "read_at": doc["clock"],
        "approval_id": c["approval_id"],
        "rows": {
            cid: {
                "match": r["match"],
                "match_label": calc.MATCH_LABEL[r["match"]],
                "diffs": r["diffs"],
                "stored": r["stored"],
            }
            for cid, r in found.items()
        },
        "background": [
            {k: x.get(k) for k in ("commitment_id", "line_id", "qty", "start", "end", "version")}
            for x in plan_now["rows"]
            if x["commitment_id"] not in found
        ],
    }
    matched = sum(1 for r in found.values() if r["match"] == calc.MATCHED)
    if matched == len(found):
        c["state"] = "APPLIED"  # 반영·대조 완료
    audit(doc, actor="Y01", action="plan_requeried", matched=matched, retry=retry)
    return {
        "result": "MATCHED" if matched == len(found) else "PARTIAL",
        "matched": matched,
        "retry": retry,
    }


def reassess(doc: dict, master: dict) -> dict[str, Any]:
    """N07 — 재조회 일치 행만으로 주문별 납기를 다시 판정한다. 같은 결과면 새 판을 만들지 않는다."""
    if doc["readback"] is None:
        raise DomainError("재조회 전에는 재평가하지 않는다 — 승인 초안으로 판정하지 않는다", 409)
    d = _draft(doc)
    rows = calc.reassess(d["rows"], doc["readback"]["rows"], master)
    last = doc["assessments"][-1] if doc["assessments"] else None
    if last is None or last["rows"] != rows:
        n = len(doc["assessments"]) + 1
        last = {
            "assessment_id": ASSESSMENT_ID,
            "version": n,
            "case_id": CASE_ID,
            "draft_id": d["draft_id"],
            "approval_id": doc["readback"]["approval_id"],
            "production_plan_version": doc["readback"]["version"],
            "assessed_at": doc["clock"],
            "execution_mode": "rule",
            "rows": rows,
            "note": "예상 도착은 계획 기준 전망이다 — 실제 인수 지연 실적이 아니다",
        }
        doc["assessments"].append(last)
        audit(doc, actor="Y01", action="risk_reassessed", version=n)
    routes = [r["route"] for r in rows]
    return {
        "assessment_id": ASSESSMENT_ID,
        "version": last["version"],
        "residual": calc.TRANSPORT in routes,
        "observe": routes.count(calc.OBSERVE),
        "transport": routes.count(calc.TRANSPORT),
        "hold": routes.count(calc.HOLD),
    }


def hand_off(doc: dict) -> dict[str, Any]:
    """
    N08 — 남은 위험(운송 확인) 주문만 장면 3으로. 같은 판정 판의 재조회는 새 인계를 만들지
    않는다(T09).
    긴급차 확보·비용 전결·경영검토 상신은 아직 하지 않는다.
    """
    if not doc["assessments"]:
        raise DomainError("재평가 전에는 인계하지 않는다", 409)
    a = doc["assessments"][-1]
    risky = [r for r in a["rows"] if r["route"] == calc.TRANSPORT]
    if not risky:
        raise DomainError("운송 확인 대상이 없다 — 인계하지 않는다", 409)
    h = doc["handoff"]
    if h is not None and h["assessment"] == {
        "assessment_id": a["assessment_id"],
        "version": a["version"],
    }:
        return {"handoff_id": h["handoff_id"], "next_node": h["next_node"]}
    d = _draft(doc)
    rb = doc["readback"]
    items = []
    for r in risky:
        items.append(
            {
                "commitment_id": r["commitment_id"],
                "qty": r["qty"],
                "ready_at": r["ready_at"],
                "promised_at": r["promised_at"],
                "truck_id": r["truck_id"],
                "arrival": r["arrival"],
                "shortfall_min": -r["margin_min"],
                "missed": r["missed"],
                "stored": rb["rows"][r["commitment_id"]]["stored"],
            }
        )
    doc["handoff"] = {
        "handoff_id": HANDOFF_ID,
        "case_id": CASE_ID,
        "demo_run_id": doc["demo_run_id"],
        "items": items,
        "draft_id": d["draft_id"],
        "approval_id": rb["approval_id"],
        "production_plan_version": rb["version"],
        "assessment": {"assessment_id": a["assessment_id"], "version": a["version"]},
        "evidence_at": a["assessed_at"],
        "observed": [r["commitment_id"] for r in a["rows"] if r["route"] == calc.OBSERVE],
        "held": [r["commitment_id"] for r in a["rows"] if r["route"] == calc.HOLD],
        "next_node": "N09",
        "next_label": "운송 대안 사실 확인 (장면 3 · U06) — 기존 운송 확인 업무 참조 여부 확인",
        "not_done": ["긴급차 확보", "추가 운송비 전결 판단", "경영검토 상신"],
        "handed_at": doc["clock"],
    }
    audit(doc, actor="Y01", action="residual_handed_off", handoff_id=HANDOFF_ID)
    return {"handoff_id": HANDOFF_ID, "next_node": "N09"}


def run_operation(
    doc: dict, operation: str, args: dict[str, Any], master: dict, company: Any
) -> dict[str, Any]:
    """일감 하나 — 생산계획을 읽는 작업은 회사 시스템에서 지금 값을 읽는다(원천 재조회)."""
    case = args.get("case_id")
    if case is not None and case != CASE_ID:
        raise DomainError(f"이 데모 실행의 사건은 {CASE_ID}다: {case}", 404)
    m = master_of(doc, master)
    if operation == "propose_case_plan":
        return propose_plan(doc)
    if operation == "check_case_plan":
        return check_plan(doc)
    if operation == "confirm_production_change":
        return confirm_change(doc, args)
    if operation == "reassess_delivery_risk":
        return reassess(doc, m)
    if operation == "hand_off_residual_risk":
        return hand_off(doc)
    plan_now = company.production_plan(doc["demo_run_id"])
    if operation == "apply_case_plan":
        return apply_plan(doc, plan_now)
    if operation == "draft_production_change":
        return draft_change(doc, m, plan_now)
    if operation == "apply_production_change":
        return apply_change(doc, company, plan_now)
    if operation == "requery_production_plan":
        return requery(doc, plan_now)
    raise DomainError(f"모르는 작업: {operation} (가능: {', '.join(OPERATIONS)})", 404)


#: 일감의 노드 — 앞 셋은 공통 BPM 안의 노드다(호출 활동 `Call_CasePlan` 안쪽)
NODE_OF = {
    "propose_case_plan": "Task_Propose",
    "check_case_plan": "Task_Check",
    "apply_case_plan": "Task_ApplyPlan",
    "draft_production_change": "Task_Draft",
    "confirm_production_change": "Record_Approve_Change",
    "apply_production_change": "Task_Apply",
    "requery_production_plan": "Task_Requery",
    "reassess_delivery_risk": "Task_Reassess",
    "hand_off_residual_risk": "Task_Handoff",
}


def ends_flow(operation: str, out: dict[str, Any]) -> str | None:
    """그 작업 뒤에 흐름이 끝나는가 — 끝 노드 id."""
    if operation == "check_case_plan" and out.get("result") == calc.BLOCKED:
        return "End_PlanBlocked"
    if operation == "confirm_production_change" and out.get("state") == "REWORK_REQUESTED":
        return "End_Rework"
    if operation == "reassess_delivery_risk" and not out.get("residual"):
        return "End_Observe"
    if operation == "hand_off_residual_risk":
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


class S2Sc02Process:
    def __init__(
        self,
        store: Sc01Store,
        *,
        company: CompanyClient,
        sc01: Any,
        center: CenterClient | None = None,
        publish: Callable[[str], None] = lambda _id: None,
    ) -> None:
        self.store = store
        self.company = company
        self.sc01 = sc01
        self.center = center or CenterClient(CenterConfig())
        self.publish = publish
        self.process = read_process(PROCESS_PATH.read_bytes())
        self.processes = {
            found.id: found for found in (read_process(p.read_bytes()) for p in CALLED_PATHS)
        }
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock(self, demo_run_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(demo_run_id, threading.Lock())

    def _load(self, demo_run_id: str) -> tuple[dict, int]:
        found = self.store.load(demo_run_id)
        if found is None:
            raise DomainError(f"시나리오 2 장면 2를 열지 않은 데모 실행: {demo_run_id}", 404)
        return found

    def get(self, demo_run_id: str) -> dict:
        return self._load(demo_run_id)[0]

    def master(self) -> dict:
        return self.company.s2_master()

    def _write_records(self, doc: dict) -> None:
        from app.s2.sc02.records import records_of

        records.write(self.company, doc, SCENE, records_of(doc, self.master()))

    def _commit(self, doc: dict, version: int, event: str) -> dict:
        self._write_records(doc)
        try:
            self.store.save(doc["demo_run_id"], doc, version, event)
        except StaleWrite as exc:
            raise DomainError("다른 요청이 먼저 바꿨다 — 다시 하라", 409) from exc
        self.publish(f"s2sc02:{doc['demo_run_id']}")
        return doc

    # ───────────── 열기·초기화·거두기 ─────────────

    def _new(self, demo_run_id: str, *, case_id: str, executor: str, world_generation: int | None):
        sc01_doc = self.sc01.get(demo_run_id)
        doc = new_doc(
            demo_run_id,
            source_of(sc01_doc),
            case_id=case_id,
            executor=executor,
            world_generation=world_generation
            if world_generation is not None
            else sc01_doc.get("world_generation"),
        )
        doc["clock"] = self.company.world(demo_run_id)["clock"]
        self.master()
        doc["company_log"].append(
            {
                "at": doc["clock"],
                "direction": "in",
                "what": "생산계획 원계획 읽기 "
                + self.company.production_plan(demo_run_id)["version"],
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
        """
        장면 2 열기 — 장면 1 인계 사본을 들고 문서를 만들고, Center 실행이면 기동한다. 이미 있으면
        그대로 돌려준다(사이트 자동 모드가 「장면 열기」를 다시 남겨도 두 번 기동하지 않는다).
        """
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
        self.publish(f"s2sc02:{demo_run_id}")
        return doc

    def reset(
        self,
        demo_run_id: str,
        *,
        actor: str = "u-demo",
        case_id: str | None = None,
        executor: str | None = None,
    ) -> dict:
        """장면 2만 처음으로 — Center 작업을 거두고 다시 연다(장면 1 인계 사본도 다시 든다)."""
        self.discard(demo_run_id)
        return self.create(
            demo_run_id, case_id=case_id or "BASE", executor=executor or "center", actor=actor
        )

    def discard(self, demo_run_id: str) -> None:
        """세계가 지워졌거나 장면 2부터 다시 — 기동한 Center 작업을 거두고 문서를 지운다."""
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

    # ───────────── Center ─────────────

    def _center_key(self, doc: dict) -> str:
        return f"s2sc02:{doc['demo_run_id']}:e{doc['center_epoch']}"

    def _start_job(self, doc: dict) -> None:
        bpm = doc["bpm"]
        problem = self.center.config.missing(integration=True)
        if problem:
            bpm["problem"] = f"{problem} — 장면 2를 기동하지 않았다. Center에서 직접 기동하라"
            return
        try:
            job = self.center.start_job(
                {"데모실행ID": doc["demo_run_id"], "사건ID": CASE_ID},
                idempotency_key=self._center_key(doc),
                on_behalf=ON_BEHALF,
                package=self.center.config.s2_sc02_package,
                note="NowView S2 SC02 — 정형통제 실행과 주문별 분기",
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
        """
        결재 답·진행은 일감이 알려 준다. 일감 전에 실행이 실패하면(공통 BPM 사본이 패키지에 없다 등)
        알려 줄 일감이 없으므로 도는 작업의 상태를 읽어 실패와 사유를 남긴다(장면 1과 같다).
        """
        if self.center.config.missing(integration=True):
            return 0
        changed = 0
        for demo_run_id in self.store.running_external("center"):
            try:
                changed += self.sync_center(demo_run_id)
            except (CenterError, DomainError) as exc:
                log.warning("Center 진행을 읽지 못했다 (%s): %s", demo_run_id, exc)
        return changed

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
            # 결재 노드는 일감이 없다 — 그 기록 작업이 오면 지나온 것이다
            before = (APPROVAL_NODE,) if operation == "confirm_production_change" else ()
            for nid in (*before, node_id or NODE_OF[operation], end):
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


__all__ = ["CASES", "OPERATIONS", "S2Sc02Process", "WORK", "run_operation"]
