"""
시나리오 2 장면 3 실행 — 잔여 납기 위험의 경영검토와 대응 합의(D06~D08, `docs/s2/sc03.md`).

* **장면 2 인계(HAND-02)에서 시작한다** — 같은 데모 실행·같은 사건(CASE-S2-01)이고 COM-R만 잇는다.
  사이트의 「장면 열기」(기간계 명령 `open`)가 이 문서를 만들고 Center에 `company1.s2.sc03`을
  기동한다(입력 `데모실행ID`·`사건ID`). S의 인수 관찰·생산계획 PROD-V2·확인 APP-01은 다시 승인하지
  않는다 — 장면 2의 인계·수행계획은 그 시점 사본이다.
* **그림**(`processes/s2-sc03.bpmn`): 공통 BPM `platform.case-plan` 호출(A03이 U06 참조·조건부 U07
  제안 → Y01 검사 → v2 적용) → 원업무 연결(LINK-03 — 출하팀의 기존 운송 문의를 참조, 새 문의 0건) →
  회신·고객 확인이 없으면 **메시지 「사건근거」를 기다린다** → 전량 대안 비교(CMP-03) → **팀장 권고
  결재**(H03) → 권고 기록(한도 초과면 ESC-03·U07 활성) → **H05 결정 결재** → 결정
  기록(DEC-03·ACT-03, 근거가 바뀌었으면 다시 연결·비교) → **H04 과제 인수 결재** → 인수
  기록(HAND-03).
* **원업무는 회사 시스템의 것이다** — 운송 문의 W-TRAN-R과 회신, 고객 소요 확인은 기간계에 있고
  NowView는 읽기만 한다(소유권·담당·이력을 바꾸지 않는다). 연결·비교·결정은 그때 **다시 읽은**
  값으로 한다.
* **근거가 오면 기다리는 실행을 깨운다** — 세계 따라가기가 기간계의 새 근거를 보면
  `receive_source`가 Center에 메시지를 보낸다(상관 키 = 데모실행ID). 실행이 아직 기다리는 자리에
  닿지 않아 Center가 `no_receiver`로 거절하면 폴러가 다시 보낸다.
* **결재는 회사 사이트가 한다**(Center 대리 답). 서버 실행기는 호출 활동 안의 결재를 Center에 올리지
  않으므로 세 결재는 모두 이 장면 그림에 있다(공통 BPM으로 뽑지 않았다 — `docs/s2/sc03.md`).
* 사례(`case_id`): `BASE`, `PLAN-DUP-INQUIRY`(A03이 진행 중인 문의를 두고 새 문의를 제안 → Y01
  차단). 미회신·기한 경과·2대·운임 변경·한도 동일은 기간계 근거 변형으로 낸다(구현명세 §4 「조건
  변경 시험은 별도 run」).
"""

from __future__ import annotations

import copy
import logging
import re
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
from app.s2.sc03 import calc
from app.sc01.center import CenterClient, CenterConfig, CenterError
from app.sc01.domain import DomainError, parse_at
from app.sc01.store import Sc01Store, StaleWrite

PROCESS_PATH = Path(__file__).resolve().parents[3] / "processes" / "s2-sc03.bpmn"
#: 그림이 호출하는 공통 BPM — 장면 2와 같은 `platform.case-plan`(수행계획 구성)을 다시 부른다
CALLED_PATHS = (Path(__file__).resolve().parents[3] / "processes" / "case-plan.bpmn",)
SCENARIO = "s2"
SCENE = 3
#: NowView 업무 번호 — 시나리오 2 장면 N은 20 + N(`docs/platform.md` §7)
WORK = 23
OPERATIONS = (
    # 공통 BPM `platform.case-plan`의 작업 — 이름은 공통이고 내용은 이 업무(수행계획 v2)의 것이다
    "propose_case_plan",
    "check_case_plan",
    "apply_case_plan",
    "link_transport_work",
    "compare_transport_options",
    "recommend_transport_option",
    "record_transport_decision",
    "accept_transport_action",
)
CASES = ("BASE", "PLAN-DUP-INQUIRY")
CASE_ID = "CASE-S2-01"
COMMITMENT = "COM-R"
#: 기존 운송 문의(원업무) — 장면 2 인계가 가리키는 「기존 운송 확인 업무」
WORK_ID = "W-TRAN-R"
WAIT_NODE = "Wait_Sources"
MESSAGE = "사건근거"
RECOMMEND_NODE, DECIDE_NODE, ACCEPT_NODE = "Approve_Recommend", "Approve_Decision", "Approve_Accept"
ON_BEHALF = "시스템 자동처리"
REFRESH = "갱신요청"
ACCEPT = "인수"
#: 결정 이후 재보고 기록 id — 자료에 없다(구현용 보완)
RE_REPORT_PREFIX = "RR-03-"

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
        "link": None,
        "comparisons": [],
        "recommendations": [],
        "decisions": [],
        "action": None,
        "handoff": None,
        "re_reports": [],
        "refresh_basis": None,
        "sources_seen": [],
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


def source_of(sc02_doc: dict[str, Any], master: dict[str, Any]) -> dict[str, Any]:
    """
    장면 2 인계의 사본 — R의 반영 근거·정기차·부족, S의 관찰, 수행계획 v1. 장면 2를 초기화해도
    장면 3의 근거는 그 시점 것이다(장면 2의 장면 1 사본과 같은 원칙).
    """
    handoff = sc02_doc.get("handoff")
    if not handoff or not sc02_doc.get("plan"):
        raise DomainError("장면 2 인계(HAND-02)가 아직 없다 — 재평가·인계 뒤에 연다", 409)
    items = [i for i in handoff["items"] if i["commitment_id"] == COMMITMENT]
    if not items:
        raise DomainError(f"HAND-02에 {COMMITMENT}가 없다 — 장면 3 대상이 아니다", 409)
    [item] = items
    truck = next((t for t in master.get("trucks") or [] if t["truck_id"] == item["truck_id"]), {})
    return {
        "handoff": copy.deepcopy({**handoff, "items": items}),
        "case_id": handoff["case_id"],
        "commitments": [COMMITMENT],
        "observed": list(handoff["observed"]),
        "plan_v1": {
            "plan_id": sc02_doc["plan"]["plan_id"],
            "version": sc02_doc["plan"]["version"],
            "state": sc02_doc["plan"]["state"],
            "items": copy.deepcopy(sc02_doc["plan"]["items"]),
        },
        "production_plan_version": handoff["production_plan_version"],
        "approval_id": handoff["approval_id"],
        "regular": {
            "truck_id": item["truck_id"],
            "cutoff": truck.get("cutoff"),
            "departure": truck.get("departure"),
            "arrival": item["arrival"],
            "ready_at": item["ready_at"],
            "promised_at": item["promised_at"],
            "shortfall_min": item["shortfall_min"],
            "qty": item["qty"],
        },
    }


# ─────────────────────────── 작업 (일꾼·시험이 같은 함수) ───────────────────────────


def _plan(doc: dict) -> dict:
    if doc["plan"] is None:
        raise DomainError("수행계획 v2가 아직 없다 — A03 제안 뒤에", 409)
    return doc["plan"]


def propose_plan(doc: dict, inquiry: dict | None) -> dict[str, Any]:
    """N03A 재진입 — A03 제안(v1 보존 + U06 참조 · 조건부 U07). 같은 사건에 다시 오면 같은 제안."""
    if doc["plan"] is None:
        doc["plan"] = {
            "plan_id": calc.PLAN_ID,
            "version": 2,
            "case_id": CASE_ID,
            "base_plan": doc["source"]["plan_v1"]["plan_id"],
            "items": calc.propose(
                doc["source"]["plan_v1"],
                doc["source"]["handoff"],
                inquiry,
                new_inquiry=doc["case_id"] == "PLAN-DUP-INQUIRY",
            ),
            "proposed_at": doc["clock"],
            "proposed_by": "A03",
            # 고정 규칙으로 고른다 — 실제 Agent 호출로 표시하지 않는다(F05)
            "execution_mode": "rule",
            "check": None,
            "state": "PROPOSED",
            "applied_at": None,
            "production_plan_version": None,
            "u07_active": False,
        }
        audit(doc, actor="A03", action="plan_proposed", plan_id=calc.PLAN_ID)
    p = doc["plan"]
    return {"plan_id": p["plan_id"], "version": p["version"], "items": len(p["items"])}


def check_plan(doc: dict, inquiry: dict | None) -> dict[str, Any]:
    """N03A — Y01 검사. 차단이면 v1을 유지하고 끝난다(연결·문의 없음)."""
    p = _plan(doc)
    if p["check"] is None:
        p["check"] = {
            **calc.check(
                p["items"],
                doc["source"]["handoff"]["handoff_id"],
                base_version=p["base_plan"],
                current_version=doc["source"]["plan_v1"]["plan_id"],
                inquiry=inquiry,
            ),
            "checked_at": doc["clock"],
        }
        p["state"] = "BLOCKED" if p["check"]["result"] == calc.BLOCKED else "CHECKED"
        audit(doc, actor="Y01", action="plan_checked", result=p["check"]["result"])
    c = p["check"]
    reason = (
        " · ".join(i["message"] for i in c["issues"])
        or "허용 업무 조합 · 원업무 참조 · 결정은 사람"
    )
    return {"result": c["result"], "issues": len(c["issues"]), "reason": reason}


def apply_plan(doc: dict) -> dict[str, Any]:
    """N03A — v2를 사건의 현재 계획으로. 생산계획(PROD-V2)·확인(APP-01)은 그대로다."""
    p = _plan(doc)
    if (p.get("check") or {}).get("result") != calc.PASS:
        raise DomainError("Y01 검사를 통과하지 않은 수행계획은 적용하지 않는다", 409)
    if p["state"] != "APPLIED":
        p.update(
            state="APPLIED",
            applied_at=doc["clock"],
            production_plan_version=doc["source"]["production_plan_version"],
        )
        audit(doc, actor="Y01", action="plan_applied", plan_id=p["plan_id"])
    return {
        "plan_id": p["plan_id"],
        "state": p["state"],
        "production_plan": p["production_plan_version"],
    }


def _reply_summary(r: dict) -> dict[str, Any]:
    keys = (
        "source_id",
        "doc_id",
        "received_at",
        "valid_until",
        "vehicles",
        "sets_per_vehicle",
        "extra_cost_per_vehicle",
        "departure",
        "arrival",
        "status_text",
    )
    return {k: r.get(k) for k in keys}


def link_work(doc: dict, inquiry: dict | None, sources: list[dict]) -> dict[str, Any]:
    """
    N09 U06 — 기존 원업무를 참조로 잇고(새 문의를 만들지 않는다) 지금 회신·고객 확인을 읽는다.
    두 번 와도 링크는 하나다(T01). 같은 회신은 한 번만 관측으로 남긴다.
    """
    if (doc["plan"] or {}).get("state") != "APPLIED":
        raise DomainError("수행계획 v2가 적용되지 않았다 — 원업무를 잇지 않는다", 409)
    if inquiry is None:
        raise DomainError(f"원업무 {WORK_ID}가 회사 시스템에 없다", 404)
    used = None if doc["refresh_basis"] is None else tuple(doc["refresh_basis"])
    found = calc.link_state(inquiry, sources, COMMITMENT, doc["clock"], used)
    link = doc["link"]
    if link is None:
        link = doc["link"] = {
            "link_id": calc.LINK_ID,
            "case_id": CASE_ID,
            "commitment_id": COMMITMENT,
            "work_id": inquiry["work_id"],
            "relation": "references",
            "subject": inquiry.get("subject"),
            "owner_role": inquiry["owner_role"],
            "owner_name": catalog.HOLDERS.get(inquiry["owner_role"], [None])[0],
            "work_started_at": inquiry["started_at"],
            "linked_at": doc["clock"],
            "linked_by": "Y01",
            "new_inquiries": 0,
            "observations": [],
        }
        audit(doc, actor="Y01", action="work_linked", link_id=calc.LINK_ID, work_id=WORK_ID)
    reply, customer = found["reply"], found["customer"]
    seen = (
        None if reply is None else reply["source_id"],
        found["reply_state"],
        None if customer is None else customer["source_id"],
    )
    last = link["observations"][-1] if link["observations"] else None
    if last is None or (last["reply_id"], last["reply_state"], last["customer_id"]) != seen:
        link["observations"].append(
            {
                "at": doc["clock"],
                "reply_id": seen[0],
                "reply_state": seen[1],
                "reply_state_label": calc.REPLY_LABEL[seen[1]],
                "customer_id": seen[2],
            }
        )
    link.update(
        work_state=inquiry["state"],
        reserved=inquiry.get("reserved", False),
        replies=[_reply_summary(r) for r in inquiry.get("replies") or []],
        reply_state=found["reply_state"],
        reply_state_label=calc.REPLY_LABEL[found["reply_state"]],
        current_reply=None if reply is None else _reply_summary(reply),
        customer=None if customer is None else copy.deepcopy(customer),
        ready=found["ready"],
        reasons=found["reasons"],
        read_at=doc["clock"],
    )
    bpm = doc["bpm"]
    if found["ready"]:
        bpm["waiting"] = []
    else:
        bpm["waiting"] = [{"node_id": WAIT_NODE, "title": "운송사 회신·고객 소요 확인 대기"}]
        doc["wait"]["message_pending"] = False
    return {
        "link_id": calc.LINK_ID,
        "ready": found["ready"],
        "reply_state": found["reply_state"],
        "reason": " · ".join(found["reasons"]) or "회신 유효 · 고객 소요 확인 — 비교한다",
    }


def _label(c: dict) -> str:
    return f"{c['comparison_id']} v{c['version']}"


def _comparison(doc: dict) -> dict:
    if not doc["comparisons"]:
        raise DomainError("대안 비교가 아직 없다", 409)
    return doc["comparisons"][-1]


def compare_options(doc: dict, master: dict) -> dict[str, Any]:
    """
    N09 A01 — 지금 연결의 회신·고객 조건·전결 한도로 두 전량 대안을 비교한다. 같은 근거·같은 결과면
    같은 판이다(재조회만으로 새 비교를 만들지 않는다). 근거가 바뀌면 새 판이고 이전 판은 보존한다.
    """
    link = doc["link"]
    if link is None or not link["ready"]:
        raise DomainError("유효한 회신과 고객 소요 확인이 없다 — 비교하지 않는다", 409)
    [authority] = [a for a in master["authority"] if a["rule_id"] == "AUTH-T1"]
    found = calc.compare(
        reply=link["current_reply"],
        customer=link["customer"],
        authority=authority,
        regular=doc["source"]["regular"],
        judged_at=doc["clock"],
    )
    basis = {
        "reply_id": link["current_reply"]["source_id"],
        "customer_id": link["customer"]["source_id"],
        "authority_id": authority["rule_id"],
        "production_plan_version": doc["source"]["production_plan_version"],
        "handoff_id": doc["source"]["handoff"]["handoff_id"],
    }
    last = doc["comparisons"][-1] if doc["comparisons"] else None
    if (
        last is None
        or last["basis"] != basis
        or last["alternatives"] != found["alternatives"]
        or last["state"] != "CURRENT"
    ):
        for c in doc["comparisons"]:
            if c["state"] == "CURRENT":
                c["state"] = "SUPERSEDED"
        n = len(doc["comparisons"]) + 1
        last = {
            "comparison_id": calc.COMPARISON_ID,
            "version": n,
            "label": f"{calc.COMPARISON_ID} v{n}",
            "case_id": CASE_ID,
            "commitment_id": COMMITMENT,
            "basis": basis,
            "snapshot": {
                "reply": copy.deepcopy(link["current_reply"]),
                "customer": copy.deepcopy(link["customer"]),
                "regular": copy.deepcopy(doc["source"]["regular"]),
            },
            **found,
            "compared_at": doc["clock"],
            "compared_by": "A01",
            # 규칙 계산이다 — 실제 Agent 추론으로 표시하지 않는다(F05). 요약 문장도 규칙이 짓는다
            "execution_mode": "rule",
            "state": "CURRENT",
        }
        doc["comparisons"].append(last)
        audit(doc, actor="A01", action="options_compared", version=n)
    doc["refresh_basis"] = None
    doc["bpm"]["waiting"] = [
        {"node_id": RECOMMEND_NODE, "title": f"운송 대안 권고·재보고 — {last['label']}"}
    ]
    exp = calc.alternative(last, calc.ALT_EXP)
    return {
        "comparison_id": calc.COMPARISON_ID,
        "version": last["label"],
        "express_verdict": exp["verdict_label"],
        "excess": exp["excess"],
    }


def _holder(by: str, role: str, what: str) -> None:
    if by not in catalog.HOLDERS[role]:
        label = catalog.ROLES[role]["label"]
        raise DomainError(f"{what}은 {label}({role})만 한다 — {by or '이름 없음'}", 403)


def recommend(doc: dict, args: dict[str, Any]) -> dict[str, Any]:
    """
    D07 팀장 권고·재보고 — 담당 팀장(H03)이 비교 결과를 보고 권고안과 사유를 남긴다. 권고안의
    추가비가 유효 전결 한도를 넘으면 ESC-03(U07 활성), 아니면 팀장 전결 범위다. 시스템은 안을 고르지
    않는다. 조건이 확인되지 않은 안은 권고할 수 없다 — 갱신 요청이다(T03).
    """
    by = str(args.get("answered_by") or "")
    _holder(by, "H03", "운송 대안 권고·재보고")
    choice = str(args.get("recommended") or "")
    if choice not in (calc.ALT_EXP, calc.ALT_REG, REFRESH):
        raise DomainError(f"권고안은 {calc.ALT_EXP}·{calc.ALT_REG}·{REFRESH}다: {choice}", 422)
    c = _comparison(doc)
    version = str(args.get("version") or "")
    if version != c["label"]:
        raise DomainError(f"본 비교({version or '없음'})가 최신({c['label']})이 아니다", 409)
    reason = str(args.get("reason") or "").strip()
    if not reason:
        raise DomainError("권고 사유가 없다", 422)
    done = next(
        (
            r
            for r in doc["recommendations"]
            if r["comparison"] == c["label"] and r["choice"] == choice
        ),
        None,
    )
    if done is not None:
        return _recommend_out(done)
    n = len(doc["recommendations"]) + 1
    entry: dict[str, Any] = {
        "escalation_id": calc.ESCALATION_ID,
        "version": n,
        "case_id": CASE_ID,
        "comparison": c["label"],
        "choice": choice,
        "reason": reason,
        "recommended_by": by,
        "recommended_role": "H03",
        "via": args.get("answered_via"),
        "recommended_at": doc["clock"],
        "authority": {
            k: c["authority"].get(k) for k in ("rule_id", "holder", "limit", "effective_at")
        },
    }
    if choice == REFRESH:
        entry.update(state="REFRESH_REQUESTED", result="REFRESH")
        doc["refresh_basis"] = [c["basis"]["reply_id"], c["basis"]["customer_id"]]
        c["state"] = "REFRESH_REQUESTED"
        doc["bpm"]["waiting"] = []
    else:
        alt = calc.alternative(c, choice)
        if alt["verdict"] in calc.NOT_EXECUTABLE:
            why = " · ".join(alt.get("conditions") or []) or alt["verdict_label"]
            raise DomainError(
                f"{alt['name']}은 {alt['verdict_label']} — 기존 견적으로 확정하지 않는다. "
                f"갱신 요청한다: {why}",
                422,
            )
        until = calc.at(alt.get("valid_until") if choice == calc.ALT_EXP else None)
        if until is not None and parse_at(doc["clock"]) >= until:
            raise DomainError("회신의 예약 유효시각이 지났다 — 갱신 요청한다", 422)
        limit = c["authority"]["applied_limit"]
        over = calc.needs_escalation(alt["extra_cost"], limit)
        entry.update(
            alternative=choice,
            alternative_name=alt["name"],
            extra_cost=alt["extra_cost"],
            margin_min=alt["margin_min"],
            limit=limit,
            excess=alt["excess"],
            to_role="H05" if over else None,
            to_name=catalog.HOLDERS["H05"][0] if over else None,
            evidence=[
                c["basis"]["reply_id"],
                c["basis"]["customer_id"],
                c["basis"]["authority_id"],
                c["basis"]["production_plan_version"],
            ],
        )
        if over:
            entry.update(state="AWAITING_DECISION", result="ESCALATED", unit="U07")
            doc["plan"]["u07_active"] = True
            doc["bpm"]["waiting"] = [
                {"node_id": DECIDE_NODE, "title": f"경영검토 — {calc.ESCALATION_ID} 운송 대안 결정"}
            ]
        else:
            entry.update(
                state="WITHIN_AUTHORITY",
                result="WITHIN_AUTHORITY",
                note="팀장 전결 범위 — 금액만으로 임원에게 재보고하지 않는다",
            )
            doc["bpm"]["waiting"] = []
    doc["recommendations"].append(entry)
    audit(doc, actor=by, action="option_recommended", choice=choice, result=entry["result"])
    return _recommend_out(entry)


def _recommend_out(e: dict) -> dict[str, Any]:
    return {
        "result": e["result"],
        "escalation_id": e["escalation_id"] if e["result"] == "ESCALATED" else None,
        "error_message": None,
    }


def _amount(value: Any) -> int:
    text = re.sub(r"[,\s원]", "", str(value or ""))
    if not re.fullmatch(r"\d+", text):
        raise DomainError(f"결정 한도는 원 단위 숫자다: {value!r}", 422)
    return int(text)


def _escalation(doc: dict) -> dict:
    found = [r for r in doc["recommendations"] if r["result"] == "ESCALATED"]
    if not found:
        raise DomainError("재보고(ESC-03)가 없다 — 경영검토 결정 전에 팀장 권고가 있어야 한다", 409)
    return found[-1]


def decide(
    doc: dict, args: dict[str, Any], inquiry: dict | None, sources: list[dict]
) -> dict[str, Any]:
    """
    D08 H05 결정 — 권한과 최신 비교 판을 서버가 다시 본다. 결정 시각에 근거(회신·고객 확인)가 비교
    때와 다르거나 회신 유효시각이 지났으면 결정하지 않고 다시 연결·비교로 돌린다(`STALE`, T06). 같은
    결정이 다시 오면 DEC-03을 돌려준다(T07). 지출 재결재 단계는 없다.
    """
    by = str(args.get("answered_by") or "")
    _holder(by, "H05", "경영검토 결정")
    choice = str(args.get("decision") or "")
    if choice not in (calc.ALT_EXP, calc.ALT_REG):
        raise DomainError(f"결정은 {calc.ALT_EXP}·{calc.ALT_REG}다: {choice}", 422)
    esc = _escalation(doc)
    done = next((d for d in doc["decisions"] if d["escalation"] == esc["version"]), None)
    if done is not None:
        if done["selected"] != choice:
            raise DomainError(f"이미 {done['decision_id']}로 결정했다 — 소급 변경하지 않는다", 409)
        return _decide_out(done)
    if esc["state"] != "AWAITING_DECISION":
        raise DomainError(
            f"재보고 {esc['escalation_id']}가 결정 대기가 아니다: {esc['state']}", 409
        )
    c = _comparison(doc)
    version = str(args.get("version") or "")
    if version != esc["comparison"] or version != c["label"]:
        raise DomainError(
            f"본 비교({version or '없음'})가 재보고 근거({esc['comparison']})가 아니다", 409
        )
    reason = str(args.get("reason") or "").strip()
    if not reason:
        raise DomainError("결정 사유가 없다", 422)
    limit = _amount(args.get("limit"))
    alt = calc.alternative(c, choice)
    if alt["extra_cost"] is not None and limit < alt["extra_cost"]:
        raise DomainError(
            f"결정 한도 {limit:,}원이 {alt['name']} 추가비 {alt['extra_cost']:,}원보다 작다", 422
        )
    now = calc.link_state(inquiry, sources, COMMITMENT, doc["clock"])
    stale: list[str] = []
    if now["basis"] != (c["basis"]["reply_id"], c["basis"]["customer_id"]):
        stale.append(f"근거 변경 {c['basis']['reply_id']} → {(now['basis'] or ('없음',))[0]}")
    if choice == calc.ALT_EXP and now["reply_state"] != calc.VALID:
        stale.append(f"회신 {calc.REPLY_LABEL[now['reply_state']]}")
    if stale:
        esc["state"] = "STALE"
        esc["stale_reason"] = " · ".join(stale)
        c["state"] = "STALE"
        doc["bpm"]["waiting"] = []
        audit(doc, actor="Y01", action="decision_stale", reason=esc["stale_reason"])
        return {
            "result": "STALE",
            "decision_id": None,
            "action_id": None,
            "error_message": None,
        }
    reg, exp = calc.alternative(c, calc.ALT_REG), calc.alternative(c, calc.ALT_EXP)
    due = exp["valid_until"] if choice == calc.ALT_EXP else None
    terms = {
        "need_qty": alt["need_qty"],
        "trucks": alt["trucks"],
        "extra_cost": alt["extra_cost"],
        "departure": alt["departure"],
        "arrival": alt["arrival"],
        "promised_at": alt["promised_at"],
        "margin_min": alt["margin_min"],
    }
    conditions = (
        [
            f"{terms['trucks']}대 미확보",
            f"추가비 {limit:,}원 초과",
            f"{calc.iso(calc.at(terms['promised_at']))[11:16]} 이후 도착 전망",
        ]
        if choice == calc.ALT_EXP
        else []
    )
    decision = {
        "decision_id": calc.DECISION_ID,
        "case_id": CASE_ID,
        "commitment_id": COMMITMENT,
        "escalation": esc["version"],
        "escalation_id": esc["escalation_id"],
        "comparison": c["label"],
        "selected": choice,
        "selected_label": calc.DECISION_LABEL[choice],
        "not_selected": calc.ALT_REG if choice == calc.ALT_EXP else calc.ALT_EXP,
        "reason": reason,
        "limit": limit,
        "terms": terms,
        "decided_by": by,
        "decided_role": "H05",
        "via": args.get("answered_via"),
        "decided_at": doc["clock"],
        "executor_role": "H04",
        "executor_name": catalog.HOLDERS["H04"][0],
        "reservation_due": due,
        "sales_follow_up": "영업은 고객 인수 시간대를 재확인한다",
        "re_report_conditions": conditions,
        "re_report_to": "H05",
        # 결정 당시 근거 사본 — 이후 회신과 구분한다(구현명세 §3)
        "evidence": {
            "basis": copy.deepcopy(c["basis"]),
            "snapshot": copy.deepcopy(c["snapshot"]),
            "alternatives": copy.deepcopy([reg, exp]),
            "recommendation": {k: esc.get(k) for k in ("choice", "reason", "recommended_by")},
        },
        "actual": {"reserved_at": None, "accepted_at": None, "actual_cost": None},
        "note": "같은 결정에 지출 재결재 단계를 더하지 않는다 — 지출·집행은 결정 범위 안의 Control",
        "state": "DECIDED",
    }
    doc["decisions"].append(decision)
    esc["state"] = "DECIDED"
    doc["action"] = {
        "action_id": calc.ACTION_ID,
        "decision_id": calc.DECISION_ID,
        "case_id": CASE_ID,
        "commitment_id": COMMITMENT,
        "title": (
            f"긴급차 {terms['trucks']}대 확보 — 예약 유효시각 {calc.iso(calc.at(due))[11:16]} 전"
            if due
            else "정기차 유지 — 고객 인수 시간대 재확인"
        ),
        "owner_role": "H04",
        "owner_name": catalog.HOLDERS["H04"][0],
        "work_id": WORK_ID,
        "due": due,
        "limit": limit,
        "conditions": conditions,
        "state": "ASSIGNED",
        "assigned_at": doc["clock"],
        "accepted_at": None,
        "accepted_by": None,
        "comment": None,
        "re_report_required": False,
        "re_reports": [],
        "note": "인수는 지출 재승인이 아니다 — 예약·출발·도착은 미확정",
    }
    doc["bpm"]["waiting"] = [{"node_id": ACCEPT_NODE, "title": f"실행과제 인수 — {calc.ACTION_ID}"}]
    audit(doc, actor=by, action="decision_recorded", decision_id=calc.DECISION_ID, selected=choice)
    return _decide_out(decision)


def _decide_out(d: dict) -> dict[str, Any]:
    return {
        "result": "DECIDED",
        "decision_id": d["decision_id"],
        "action_id": calc.ACTION_ID,
        "error_message": None,
    }


def accept(doc: dict, args: dict[str, Any]) -> dict[str, Any]:
    """D08 끝 H04 인수 — 결정 조건(한도·기한·재보고 조건)을 함께 인수한다. 다시 와도 HAND-03."""
    by = str(args.get("answered_by") or "")
    _holder(by, "H04", "실행과제 인수")
    if str(args.get("decision") or "") != ACCEPT:
        raise DomainError(f"인수 결정은 「{ACCEPT}」다", 422)
    a = doc["action"]
    if a is None or not doc["decisions"]:
        raise DomainError("결정(DEC-03) 전에는 인수할 과제가 없다", 409)
    if a["state"] != "ACCEPTED":
        a.update(
            state="ACCEPTED",
            accepted_at=doc["clock"],
            accepted_by=by,
            comment=str(args.get("comment") or ""),
        )
        d = doc["decisions"][-1]
        c = next(x for x in doc["comparisons"] if x["label"] == d["comparison"])
        doc["handoff"] = {
            "handoff_id": calc.HANDOFF_ID,
            "case_id": CASE_ID,
            "commitment_id": COMMITMENT,
            "demo_run_id": doc["demo_run_id"],
            "decision_id": d["decision_id"],
            "action_id": a["action_id"],
            "selected": d["selected"],
            "selected_label": d["selected_label"],
            "comparison": d["comparison"],
            "evidence": [
                c["comparison_id"],
                c["basis"]["reply_id"],
                c["basis"]["customer_id"],
                c["basis"]["authority_id"],
                c["basis"]["production_plan_version"],
            ],
            "owner_role": a["owner_role"],
            "owner_name": a["owner_name"],
            "due": a["due"],
            "limit": d["limit"],
            "expected_arrival": d["terms"]["arrival"],
            "re_report_conditions": d["re_report_conditions"],
            "follow_up": [
                "예약 기한 전 3대 확정 여부",
                "실제 전량 인수시각·추가비",
                "약정 및 예산 대비 차이",
            ],
            "state": "ACTION_ACCEPTED",
            "state_label": "과제 인수 · 예약 미확정",
            "actual": {"reserved_at": None, "accepted_at": None, "actual_cost": None},
            "observed": list(doc["source"]["observed"]),
            "next_label": "장면 4 — 실제 예약·전량 인수·집행비를 이 결정과 비교",
            "handed_at": doc["clock"],
        }
        doc["bpm"]["waiting"] = []
        audit(doc, actor=by, action="action_accepted", handoff_id=calc.HANDOFF_ID)
    return {
        "action_id": a["action_id"],
        "handoff_id": calc.HANDOFF_ID,
        "state": a["state"],
        "error_message": None,
    }


def run_operation(
    doc: dict, operation: str, args: dict[str, Any], master: dict, company: Any
) -> dict[str, Any]:
    """일감 하나 — 원업무·근거를 읽는 작업은 회사 시스템에서 지금 값을 다시 읽는다."""
    case = args.get("case_id")
    if case is not None and case != CASE_ID:
        raise DomainError(f"이 데모 실행의 사건은 {CASE_ID}다: {case}", 404)
    if operation == "apply_case_plan":
        return apply_plan(doc)
    if operation == "compare_transport_options":
        return compare_options(doc, master)
    if operation == "recommend_transport_option":
        return recommend(doc, args)
    if operation == "accept_transport_action":
        return accept(doc, args)
    inquiry = _inquiry(company, doc["demo_run_id"])
    if operation == "propose_case_plan":
        return propose_plan(doc, inquiry)
    if operation == "check_case_plan":
        return check_plan(doc, inquiry)
    sources = company.case_sources(doc["demo_run_id"])
    if operation == "link_transport_work":
        return link_work(doc, inquiry, sources)
    if operation == "record_transport_decision":
        return decide(doc, args, inquiry, sources)
    raise DomainError(f"모르는 작업: {operation} (가능: {', '.join(OPERATIONS)})", 404)


def _inquiry(company: Any, world_id: str) -> dict | None:
    try:
        return company.shipping_inquiry(world_id, WORK_ID)
    except DomainError as exc:
        if exc.status == 404:
            return None
        raise


#: 일감의 노드 — 앞 셋은 공통 BPM 안의 노드다(호출 활동 `Call_CasePlan` 안쪽)
NODE_OF = {
    "propose_case_plan": "Task_Propose",
    "check_case_plan": "Task_Check",
    "apply_case_plan": "Task_ApplyPlan",
    "link_transport_work": "Task_Link",
    "compare_transport_options": "Task_Compare",
    "recommend_transport_option": "Record_Recommend",
    "record_transport_decision": "Record_Decision",
    "accept_transport_action": "Record_Accept",
}
#: 기록 작업의 결재 — 결재 노드는 일감이 없다. 그 기록이 오면 지나온 것이다
APPROVAL_OF = {
    "recommend_transport_option": RECOMMEND_NODE,
    "record_transport_decision": DECIDE_NODE,
    "accept_transport_action": ACCEPT_NODE,
}


def ends_flow(operation: str, out: dict[str, Any]) -> str | None:
    """그 작업 뒤에 흐름이 끝나는가 — 끝 노드 id."""
    if operation == "check_case_plan" and out.get("result") == calc.BLOCKED:
        return "End_PlanBlocked"
    if operation == "recommend_transport_option" and out.get("result") == "WITHIN_AUTHORITY":
        return "End_WithinAuthority"
    if operation == "accept_transport_action":
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


class S2Sc03Process:
    def __init__(
        self,
        store: Sc01Store,
        *,
        company: CompanyClient,
        sc02: Any,
        center: CenterClient | None = None,
        publish: Callable[[str], None] = lambda _id: None,
    ) -> None:
        self.store = store
        self.company = company
        self.sc02 = sc02
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
            raise DomainError(f"시나리오 2 장면 3을 열지 않은 데모 실행: {demo_run_id}", 404)
        return found

    def get(self, demo_run_id: str) -> dict:
        return self._load(demo_run_id)[0]

    def master(self) -> dict:
        return self.company.s2_master()

    def _write_records(self, doc: dict) -> None:
        from app.s2.sc03.records import records_of

        records.write(self.company, doc, SCENE, records_of(doc, self.master()))

    def _commit(self, doc: dict, version: int, event: str) -> dict:
        self._write_records(doc)
        try:
            self.store.save(doc["demo_run_id"], doc, version, event)
        except StaleWrite as exc:
            raise DomainError("다른 요청이 먼저 바꿨다 — 다시 하라", 409) from exc
        self.publish(f"s2sc03:{doc['demo_run_id']}")
        return doc

    # ───────────── 열기·초기화·거두기 ─────────────

    def _new(self, demo_run_id: str, *, case_id: str, executor: str, world_generation: int | None):
        sc02_doc = self.sc02.get(demo_run_id)
        master = self.master()
        doc = new_doc(
            demo_run_id,
            source_of(sc02_doc, master),
            case_id=case_id,
            executor=executor,
            world_generation=world_generation
            if world_generation is not None
            else sc02_doc.get("world_generation"),
        )
        doc["clock"] = self.company.world(demo_run_id)["clock"]
        inquiry = _inquiry(self.company, demo_run_id)
        doc["company_log"].append(
            {
                "at": doc["clock"],
                "direction": "in",
                "what": f"원업무 {WORK_ID} 읽기 — "
                + (
                    "없음"
                    if inquiry is None
                    else f"{inquiry['state']} · 담당 {inquiry['owner_role']}"
                ),
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
        장면 3 열기 — 장면 2 인계 사본을 들고 문서를 만들고, Center 실행이면 기동한다. 이미 있으면
        그대로 돌려준다(HAND-02 재진입은 기존 연결을 돌려준다, T01).
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
        self.publish(f"s2sc03:{demo_run_id}")
        return doc

    def reset(
        self,
        demo_run_id: str,
        *,
        actor: str = "u-demo",
        case_id: str | None = None,
        executor: str | None = None,
    ) -> dict:
        """장면 3만 처음으로 — Center 작업을 거두고 다시 연다(장면 2 인계 사본도 다시 든다)."""
        self.discard(demo_run_id)
        return self.create(
            demo_run_id, case_id=case_id or "BASE", executor=executor or "center", actor=actor
        )

    def discard(self, demo_run_id: str) -> None:
        """세계가 지워졌거나 장면 3부터 다시 — 기동한 Center 작업을 거두고 문서를 지운다."""
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

    # ───────────── 근거 원천 ─────────────

    def receive_source(self, demo_run_id: str, doc_id: str) -> dict | None:
        """
        세계 따라가기가 기간계의 새 근거(운송사 회신·고객 확인)를 넘긴다. 실행이 근거를 기다리면
        Center에 메시지를 보내 깨운다. 결정 뒤에 온 근거는 결정 조건과 대조해 H05 재보고 대상인지
        남긴다(T09) — 변경 조건으로 집행하거나 사건을 끝내지 않는다. 같은 근거는 한 번만 본다.
        """
        if self.store.load(demo_run_id) is None:
            return None
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if doc_id in doc["sources_seen"]:
                return doc
            sources = self.company.case_sources(demo_run_id)
            src = next((s for s in sources if s["doc_id"] == doc_id), None)
            if src is None:
                raise DomainError(f"없는 근거 원천: {doc_id}", 404)
            doc["sources_seen"].append(doc_id)
            doc["company_log"].append(
                {
                    "at": doc["clock"],
                    "direction": "in",
                    "what": f"근거 받기 {src['source_id']} ({src['kind']}) — 수신 "
                    f"{src['registered_at'][11:16]}",
                }
            )
            if doc["decisions"]:
                self._after_decision(doc, src, sources)
            if any(w["node_id"] == WAIT_NODE for w in doc["bpm"]["waiting"]):
                doc["wait"]["message_pending"] = True
                self._send_message(doc, src["source_id"])
            self._commit(doc, version, "source")
            return doc

    def _after_decision(self, doc: dict, src: dict, sources: list[dict]) -> None:
        d = doc["decisions"][-1]
        reply = calc.latest(
            [s for s in sources if s["kind"] == "transport_reply"], "transport_reply", COMMITMENT
        )
        customer = calc.latest(sources, "customer_condition", COMMITMENT)
        if src["source_id"] in (
            d["evidence"]["basis"]["reply_id"],
            d["evidence"]["basis"]["customer_id"],
        ):
            return
        triggers = calc.re_report_triggers(d, reply, customer)
        if not triggers:
            return
        n = len(doc["re_reports"]) + 1
        entry = {
            "re_report_id": f"{RE_REPORT_PREFIX}{n}",
            "decision_id": d["decision_id"],
            "action_id": calc.ACTION_ID,
            "source_id": src["source_id"],
            "detected_at": doc["clock"],
            "triggers": triggers,
            "reported_by_role": "H04",
            "to_role": "H05",
            "to_name": catalog.HOLDERS["H05"][0],
            "state": "REPORT_REQUIRED",
            "note": (
                "결정 당시 값과 변경값을 함께 재보고한다 — 변경 조건으로 자동 집행·사건 종료 금지"
            ),
        }
        doc["re_reports"].append(entry)
        if doc["action"] is not None:
            doc["action"]["re_report_required"] = True
            doc["action"]["re_reports"].append(entry["re_report_id"])
        audit(doc, actor="Y01", action="re_report_required", re_report_id=entry["re_report_id"])

    def _send_message(self, doc: dict, source_id: str) -> None:
        """Center 실행이면 「사건근거」 메시지 — 받는 실행이 아직 없으면 폴러가 다시 보낸다."""
        if doc["executor"] != "center" or self.center.config.missing(integration=True):
            return
        doc["wait"]["attempts"] += 1
        try:
            self.center.send_message(
                MESSAGE,
                correlation=doc["demo_run_id"],
                payload={"근거ID": source_id},
                idempotency_key=(
                    f"s2sc03:{doc['demo_run_id']}:e{doc['center_epoch']}:{source_id}:"
                    f"{doc['wait']['attempts']}"
                ),
                on_behalf=ON_BEHALF,
            )
        except CenterError as exc:
            log.info(
                "근거 메시지를 넣지 못했다(%s) — 다시 보낸다: %s", doc["demo_run_id"], exc.message
            )
            return
        doc["wait"]["message_pending"] = False
        audit(doc, actor="system", action="center_message_sent", source_id=source_id)

    # ───────────── Center ─────────────

    def _center_key(self, doc: dict) -> str:
        return f"s2sc03:{doc['demo_run_id']}:e{doc['center_epoch']}"

    def _start_job(self, doc: dict) -> None:
        bpm = doc["bpm"]
        problem = self.center.config.missing(integration=True)
        if problem:
            bpm["problem"] = f"{problem} — 장면 3을 기동하지 않았다. Center에서 직접 기동하라"
            return
        try:
            job = self.center.start_job(
                {"데모실행ID": doc["demo_run_id"], "사건ID": CASE_ID},
                idempotency_key=self._center_key(doc),
                on_behalf=ON_BEHALF,
                package=self.center.config.s2_sc03_package,
                note="NowView S2 SC03 — 잔여 납기 위험의 경영검토와 대응 합의",
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
        도는 Center 실행 — 못 넣은 근거 메시지를 다시 보내고, 일감 전에 실패한 실행의 사유를 남긴다
        (장면 2와 같다).
        """
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
            seen = doc["sources_seen"][-1] if doc["sources_seen"] else None
            if not doc["wait"]["message_pending"] or seen is None:
                return 0
            sources = {s["doc_id"]: s for s in self.company.case_sources(demo_run_id)}
            self._send_message(doc, sources[seen]["source_id"])
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
            after = (WAIT_NODE,) if operation == "link_transport_work" and not out["ready"] else ()
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


__all__ = ["CASES", "OPERATIONS", "S2Sc03Process", "WORK", "run_operation"]
