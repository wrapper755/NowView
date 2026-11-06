"""
시나리오 3 장면 3 실행 — 팀장 보고 및 승인(업무설계표 01~06, `docs/s3/sc03.md`).

* **장면 2 상신(HAND-S3-02)에서 연다** — 사이트의 「장면 열기」(시나리오 3 장면 3)를 세계 따라가기가
  넘기면 이 문서를 만들고 `company1.s3.sc03`을 기동한다(입력 `데모실행ID`·`결산건ID`). 장면 2 보고가
  상신 전이면 열지 않는다(409). 열 때 상신본(REP-S3-01 v1)을 결과·첨부·검토와 함께 읽어 둔다 —
  팀장이 보는 것은 **상신 당시의 제출본**이다(장면 2 문서를 다시 계산하지 않는다).
* **그림은 순서만 쥔다** — 보고 열기 → 회계팀장의 결정(결재 하나 — 승인 또는 대상·사유 있는 보완
  요청) → 승인이면 후속 업무 인계(전표 반영·주석 취합 두 경로 — 한 경로만 실패하면 그 경로만
  재시도), 보완 요청이면 회계담당자의 보완 처리(참조 보강 재상신 · 입력 반영 재계산 → 영향 항목
  재검토 → 재상신) 뒤 같은 보고 ID의 새 버전으로 다시 결정. 열람은 결재 기록을 만들지 않는다.
* **결정 직전에 다시 본다** — 지정 결재자, 승인 대기 상태, 현재 상신 버전, 두 원업무·요약·첨부 결과
  버전의 일치, 첨부 접근(기간계에서 다시 읽어 지문 대조). 어긋나면 사유와 복구 담당을 남기고 결정을
  보류한다(같은 결재로 돌아간다). 보고 버전마다 유효 결정은 하나다 — 같은 결정의 재전송은 같은 결정
  ID, 다른 결정은 처리된 상태와 현재 버전을 안내한다(409).
* **숫자는 계산 기능만 만든다** — 보완 재계산은 장면 2의 계산 기능(`app/s3/sc02/calc.py`)과 같은
  서식의 계산근거 Excel(`workpaper`)을 쓴다. 실행·결과·파일 번호는 장면 2에 이어 매긴다(기간계
  기록 키가 장면을 가리지 않는다).
* 끝은 승인 2/2 · 승인 보고 1건 · 전표 반영 0/2 · 주석 취합 0/2 — 두 수신 역할이 같은 승인본을
  가리킨다. 실제 전표 반영·주석 취합 완료는 후속 업무의 몫이다.
"""

from __future__ import annotations

import base64
import copy
import hashlib
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
from app.s3.sc02 import calc, workpaper
from app.s3.sc02.process import (
    EXECUTION_MODE,
    EXECUTION_NOTE,
    REVIEW_ORDER,
    REVIEW_PATHS,
    VERSIONS,
    _mark,
    _steps,
    entry,
)
from app.sc01.center import CenterClient, CenterConfig, CenterError
from app.sc01.domain import DomainError, parse_at
from app.sc01.store import Sc01Store, StaleWrite

PROCESS_PATH = Path(__file__).resolve().parents[3] / "processes" / "s3-sc03.bpmn"
SCENARIO = "s3"
SCENE = 3
#: NowView 업무 번호 — 시나리오 3 장면 N은 30 + N(`docs/platform.md` §7)
WORK = 33
CLOSE_ID = "S3-CLOSE-01"
ENTRY_HANDOFF = "HAND-S3-02"
HANDOFF_ID = "HAND-S3-03"
REPORT_ID = "REP-S3-01"
OPERATIONS = (
    "open_close_approval",
    "decide_close_report",
    "hand_off_close_approval",
    "revise_close_report",
    "review_close_revision",
)
CASES = ("BASE",)
ON_BEHALF = "시스템 자동처리"
APPROVE, RETURN = "승인", "보완 요청"
REF, RECALC, RESUBMIT = "참조 보강 재상신", "재계산", "재상신"
REVIEW_DECISION = "검토 완료"
APPROVAL_SCOPE = "두 결산조정항목 및 유형자산·충당금 주석(안) · 첨부 1파일"
#: 보완 대상 선택지 → 조정항목
TARGETS = {
    "감가상각비": ["DEP"],
    "대손충당금": ["ALW"],
    "외상매출금 대손충당금": ["ALW"],
    "두 항목": ["DEP", "ALW"],
    "DEP": ["DEP"],
    "ALW": ["ALW"],
}
#: 주석 취합 경로가 가리키는 첨부 시트(구현명세 §3)
NOTE_SHEET = {"DEP": "유형자산주석", "ALW": "충당금주석"}
#: 근거 조회 동선(화면 02) — 팀장이 첨부와 BPM 근거를 오가며 보는 것
EVIDENCE_PATHS = {
    "ALW": [
        "개별평가 A사 당기 행 → 관련 근거(PLAN-A-26·CONF-26-S·CONF-26-F)",
        "충당금비교 → 충당금주석",
    ],
    "DEP": ["상각비비교 → 자산별계산(E2·E3)", "유형자산주석 합계 행"],
}
#: 경로 등록 장애 스위치(기간계 `sim/close-faults`)
FAIL_FAULT = {"POSTING": "posting_handoff_fail", "NOTES": "notes_handoff_fail"}
LOST_FAULT = {"NOTES": "notes_handoff_lost"}
STATE_LABEL = {
    "WAITING": "승인 대기",
    "NEEDS_REVISION": "보완 필요",
    "REVIEWED_WAIT": "검토 완료 · 공통 보고 보완 대기",
    "APPROVED": "승인 완료",
}
VERSION_LABEL = {
    "WAITING": "승인 대기",
    "RETURNED": "보완 요청",
    "APPROVED": "승인 완료",
}

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def audit(doc: dict, *, actor: str, action: str, **detail: Any) -> None:
    doc["audit"].append({"at": doc["clock"], "actor": actor, "action": action, **detail})


def _new_bpm(executor: str) -> dict[str, Any]:
    return {
        "executor": executor,
        "state": "idle",
        "job_id": None,
        "external_run_id": None,
        "visited": [],
        "waiting": [],
        "problem": None,
    }


def _ver(value: Any) -> int:
    """본 보고 버전 — `1`·`v1`·`REP-S3-01 v1` 어느 것이든 숫자로."""
    text = str(value or "").strip().rsplit(" ", 1)[-1].lstrip("vV")
    if not text.isdigit():
        raise DomainError(f"본 보고 버전을 읽을 수 없다: {value or '없음'}", 422)
    return int(text)


def _str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value == int(value):
        value = int(value)
    return str(value)


# ─────────────────────────── 장면 2 상신 ───────────────────────────


def submitted(sc02_doc: dict | None) -> dict:
    """장면 3 진입 조건 — 장면 2가 한 건으로 상신했고 인계(HAND-S3-02)가 있다. 아니면 409."""
    if sc02_doc is None or sc02_doc.get("report") is None or sc02_doc.get("handoff") is None:
        raise DomainError(
            f"장면 2 상신({ENTRY_HANDOFF}) 전이다 — 회계담당자가 두 항목을 검토해 한 건으로 "
            "상신해야 팀장이 연다",
            409,
        )
    return sc02_doc["report"]


def _evidence(res: dict, full: dict) -> dict[str, Any]:
    """
    화면 02 근거 — 개별평가 A사 행(회수 회차·영업·회계 확인), 충당금비교·주석, 상각비 귀속·주석·
    변동 자산. 모두 그 결과 버전의 계산과 그 입력의 확인기록에서 고른다(새로 계산하지 않는다).
    """
    alw, dep = res["calc"]["allowance"], res["calc"]["depreciation"]
    refs = {
        c
        for i in alw["individual"]
        for c in (i.get("sales_confirmation"), i.get("accounting_confirmation"))
        if c
    }
    confirmations = [
        {
            "confirmation_id": r["confirmation_id"],
            "customer": r["customer"],
            "confirmed_on": r["confirmed_on"],
            "plan_ref": r["plan_ref"],
            "confirmed_by": r["confirmed_by"],
            "amount": _str(r["amount"]),
            "note": r.get("note"),
        }
        for r in full["sheets"]["확인기록"]
        if r["confirmation_id"] in refs
    ]
    return {
        "individual": alw["individual"],
        "confirmations": confirmations,
        "methods": alw["methods"],
        "allowance_note": alw["note"],
        "allocation": dep["by_allocation"],
        "depreciation_note": dep["note"]["total"],
        "asset_changes": [
            {
                k: a[k]
                for k in ("asset_id", "kind", "allocation", "months", "prior", "current", "change")
            }
            for a in dep["assets"]
            if a["change"] not in ("0", 0)
        ],
        "paths": EVIDENCE_PATHS,
    }


def _snapshot(
    doc: dict,
    n: int,
    res: dict,
    att: dict,
    run: dict,
    reviews: list[dict],
    full: dict,
    *,
    by: str,
    via: Any,
    at: str,
    changes: list[dict],
    revision_id: str | None,
    reasons: dict[str, str] | None = None,
) -> dict[str, Any]:
    """제출본 하나 — 결과 버전·첨부·검토·변동 사유·주석·근거를 보고 버전 하나로 고정한다."""
    sections = {s["item"]: s for s in (res.get("draft") or {}).get("sections", [])}
    items = []
    for s in res["calc"]["summary"]:
        item = s["item"]
        items.append(
            {
                "item_id": item,
                "work_id": doc["items"][item]["work_id"],
                "name": s["name"],
                **{
                    k: s[k]
                    for k in (
                        "prior",
                        "current",
                        "change",
                        "change_rate",
                        "book",
                        "request",
                        "request_label",
                    )
                },
                "reason": (reasons or {}).get(item) or sections[item]["text"],
                "refs": sections[item]["refs"],
                "summary_cell": att["summary_cells"][item]["request"],
                "note_sheet": NOTE_SHEET[item],
                "approval": "WAITING",
            }
        )
    return {
        "report_id": REPORT_ID,
        "version": n,
        "title": "결산조정항목 및 관련 주석(안) 보고·승인",
        "close_id": CLOSE_ID,
        "period": {
            "period_end": doc["close"]["period_end"],
            "comparative_end": doc["close"]["comparative_end"],
            "unit": "백만원",
        },
        "result_version": res["result_version"],
        "input_version": res["input_version"],
        "execution": {
            "run_id": run["run_id"],
            "input_version": run["input_version"],
            "executed_by": run["requested_by"],
            "executed_at": run["requested_at"],
            "execution_mode": run["execution_mode"],
            "draft_mode": (res.get("draft") or {}).get("mode"),
        },
        "attachment": {k: att[k] for k in ("file_id", "file_version", "filename", "sha256", "size")}
        | {"result_version": att["result_version"]},
        "items": items,
        "notes": {
            "DEP": res["calc"]["depreciation"]["note"]["total"],
            "ALW": res["calc"]["allowance"]["note"],
        },
        "evidence": _evidence(res, full),
        "reviews": [
            {
                k: r.get(k)
                for k in ("item", "review_id", "reviewed_by", "reviewed_at", "carried_from")
            }
            for r in reviews
        ],
        "submitted_by": by,
        "submitted_via": via,
        "submitted_at": at,
        "recipient": doc["approver"],
        "approval_scope": APPROVAL_SCOPE,
        "changes": changes,
        "revision_id": revision_id,
        "state": "WAITING",
        "decision_id": None,
    }


def new_doc(
    demo_run_id: str,
    sc02_doc: dict,
    master: dict,
    full: dict,
    *,
    case_id: str,
    executor: str,
    world_generation: int | None,
) -> dict[str, Any]:
    if case_id not in CASES:
        raise DomainError(f"모르는 사례: {case_id} (가능: {', '.join(CASES)})", 422)
    if executor not in ("center", "studio"):
        raise DomainError("실행 위치는 center·studio다 — 내장 실행은 쓰지 않는다", 422)
    report = submitted(sc02_doc)
    rv = report["result_version"]
    res = next(r for r in sc02_doc["results"] if r["result_version"] == rv)
    att = next(a for a in sc02_doc["attachments"] if a["result_version"] == rv)
    run = next(r for r in sc02_doc["runs"] if r["run_id"] == res["run_id"])
    reviews = [r for r in sc02_doc["reviews"] if r["result_version"] == rv and r["valid"]]
    items = {
        it["item_id"]: {
            k: it[k] for k in ("item_id", "work_id", "name", "owner_role", "owner_name", "owner_id")
        }
        | {"follow_up": list(it["follow_up"])}
        for it in master["close"]["items"]
    }
    roles = [dict(r) for r in master["close"]["follow_up_roles"]]
    doc: dict[str, Any] = {
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
        "close": dict(sc02_doc["close"]),
        "approver": dict(sc02_doc["close"]["reviewer"]),
        "items": items,
        "roles": roles,
        "entry": {
            "handoff_id": ENTRY_HANDOFF,
            "report_id": report["report_id"],
            "report_version": report["version"],
            "opened_at": None,
        },
        #: 장면 2의 상신본 — 기록으로 다시 적지 않는다(장면 2 기록에 있다)
        "base": {
            "run": copy.deepcopy(run),
            "result": copy.deepcopy(res),
            "attachment": copy.deepcopy(att),
            "reviews": copy.deepcopy(reviews),
        },
        #: 장면 2가 쓴 번호 — 장면 3의 실행·결과·파일·검토 번호는 그 뒤로 매긴다
        "offsets": {
            "runs": len(sc02_doc["runs"]),
            "results": len(sc02_doc["results"]),
            "attachments": len(sc02_doc["attachments"]),
            "reviews": {i: sum(1 for r in sc02_doc["reviews"] if r["item"] == i) for i in items},
        },
        "versions": [],
        "decisions": [],
        "revisions": [],
        "runs": [],
        "results": [],
        "attachments": [],
        "reviews": [],
        "holds": [],
        "hold": None,
        "followups": {
            r["path"]: {
                "path": r["path"],
                "label": r["label"],
                "assignee": {k: r[k] for k in ("role", "name", "user_id")},
                "waiting": r["waiting"],
                "state": "WAITING_APPROVAL",
                "key": None,
                "tasks": [],
                "attempts": 0,
                "reason": None,
                "registered_at": None,
                "recovered": False,
            }
            for r in roles
        },
        "handoff": None,
        "input_notice": None,
        "bpm": _new_bpm(executor),
        "audit": [],
        "company_log": [],
        "company_records": {},
    }
    v1 = _snapshot(
        doc,
        report["version"],
        res,
        att,
        run,
        reviews,
        full,
        by=report["submitted_by"],
        via=report.get("submitted_via"),
        at=report["submitted_at"],
        changes=[],
        revision_id=None,
    )
    for got, sent in zip(v1["items"], report["items"], strict=True):
        if (got["item_id"], got["request"]) != (sent["item_id"], sent["request"]):
            raise DomainError(f"상신본 {REPORT_ID}의 요청액이 결과 {rv}와 다르다", 409)
    doc["versions"].append(v1)
    return doc


# ─────────────────────────── 조회 ───────────────────────────


def current(doc: dict) -> dict:
    return doc["versions"][-1]


def version_of(doc: dict, n: int) -> dict | None:
    return next((v for v in doc["versions"] if v["version"] == n), None)


def results(doc: dict) -> list[dict]:
    return [doc["base"]["result"], *doc["results"]]


def result_of(doc: dict, rv: str | None) -> dict | None:
    return next((r for r in results(doc) if r["result_version"] == rv), None)


def latest_result(doc: dict) -> dict:
    return results(doc)[-1]


def attachment_of(doc: dict, rv: str | None) -> dict | None:
    found = [doc["base"]["attachment"], *doc["attachments"]]
    return next((a for a in found if a["result_version"] == rv), None)


def run_of(doc: dict, run_id: str) -> dict:
    return next(r for r in [doc["base"]["run"], *doc["runs"]] if r["run_id"] == run_id)


def review_of(doc: dict, item: str, rv: str) -> dict | None:
    found = [*doc["base"]["reviews"], *doc["reviews"]]
    return next(
        (r for r in found if r["item"] == item and r["result_version"] == rv and r["valid"]),
        None,
    )


def open_revision(doc: dict) -> dict | None:
    return next((r for r in doc["revisions"] if r["state"] == "OPEN"), None)


def approved(doc: dict) -> dict | None:
    return next((d for d in doc["decisions"] if d["decision"] == "APPROVED"), None)


def item_state(doc: dict, item_id: str) -> str:
    """체크리스트 행의 승인 단계 — 보고 전체가 보완 중이면 대상과 나머지를 가른다."""
    ver = current(doc)
    if ver["state"] == "APPROVED":
        return "APPROVED"
    if ver["state"] == "RETURNED":
        rev = open_revision(doc)
        return "NEEDS_REVISION" if rev and item_id in rev["targets"] else "REVIEWED_WAIT"
    return "WAITING"


def _todo(doc: dict, res: dict) -> list[str]:
    return [i for i in REVIEW_ORDER if not review_of(doc, i, res["result_version"])]


def _owner(doc: dict, by: str, what: str) -> None:
    owners = {i["owner_name"] for i in doc["items"].values()}
    if by not in owners:
        raise DomainError(
            f"{what}은 배정 담당({', '.join(sorted(owners))})만 한다 — {by or '이름 없음'}", 403
        )


def _consistency(doc: dict, ver: dict) -> list[str]:
    """두 원업무·요약·첨부의 결과 버전이 같은 제출본을 가리키는가(어긋난 것 목록)."""
    problems = []
    res = result_of(doc, ver["result_version"])
    att = attachment_of(doc, ver["result_version"])
    if res is None:
        return [f"결과 {ver['result_version']}가 없다"]
    if att is None or att["file_id"] != ver["attachment"]["file_id"]:
        problems.append(f"첨부가 결과 {ver['result_version']}의 파일이 아니다")
    elif att["sha256"] != ver["attachment"]["sha256"]:
        problems.append(f"첨부 {att['file_id']}의 지문이 제출본과 다르다")
    works = sorted(i["work_id"] for i in doc["items"].values())
    if sorted(i["work_id"] for i in ver["items"]) != works:
        problems.append("보고의 원업무가 결산 건의 두 항목과 다르다")
    summary = {s["item"]: s for s in res["calc"]["summary"]}
    for it in ver["items"]:
        if summary[it["item_id"]]["request"] != it["request"]:
            problems.append(f"{it['name']} 요약 요청액이 결과 {res['result_version']}와 다르다")
    return problems


def _access(doc: dict, ver: dict, fetch: Callable[[str], bytes], fault: Callable[[str], bool]):
    """첨부 접근 — 기간계에서 다시 읽어 지문을 맞춘다. 열 수 없으면 사유(열리면 None)."""
    file_id = ver["attachment"]["file_id"]
    if fault("attachment_unavailable"):
        return f"첨부 {file_id}를 열 수 없다 — 첨부 저장소가 응답하지 않는다(시연 스위치)"
    try:
        raw = fetch(file_id)
    except DomainError as exc:
        return f"첨부 {file_id}를 열 수 없다 — {exc}"
    if hashlib.sha256(raw).hexdigest() != ver["attachment"]["sha256"]:
        return f"첨부 {file_id}의 내용이 제출본 지문과 다르다"
    return None


# ─────────────────────────── 작업 ───────────────────────────


def open_report(doc: dict) -> dict[str, Any]:
    """01 보고 열기 — 수신함과 체크리스트 두 행이 같은 보고·버전을 연다. 열람은 결정이 아니다."""
    if doc["entry"]["opened_at"] is None:
        doc["entry"]["opened_at"] = doc["clock"]
    ver = current(doc)
    audit(doc, actor="Y01", action="report_opened", version=ver["version"])
    return _version_out(ver)


def _version_out(ver: dict) -> dict[str, Any]:
    return {
        "report_id": ver["report_id"],
        "report_version": ver["version"],
        "result_version": ver["result_version"],
        "file_id": ver["attachment"]["file_id"],
        "filename": ver["attachment"]["filename"],
    }


def _targets(raw: Any) -> list[str]:
    found: list[str] = []
    for part in str(raw or "").replace("·", ",").split(","):
        for item in TARGETS.get(part.strip(), []):
            if item not in found:
                found.append(item)
    return [i for i in REVIEW_ORDER if i in found]


def decide(
    doc: dict,
    args: dict[str, Any],
    fetch: Callable[[str], bytes],
    fault: Callable[[str], bool],
) -> dict[str, Any]:
    """
    04A·04B 결정 — 지정 팀장만, 현재 상신 버전·승인 대기·결과 버전 일치·첨부 접근이 맞을 때만.
    승인은 두 항목·두 주석을 한 단위로 확정하고 두 후속 경로의 인계 요청을 함께 남긴다. 보완 요청은
    대상 항목·사유가 필수다. 같은 버전의 유효 결정은 하나다.
    """
    by = str(args.get("answered_by") or "")
    approver = doc["approver"]["name"]
    if by != approver:
        raise DomainError(
            f"이 보고의 결정은 지정 결재자({approver})만 한다 — {by or '이름 없음'}", 403
        )
    decision = str(args.get("decision") or "")
    if decision not in (APPROVE, RETURN):
        raise DomainError(f"결정은 「{APPROVE}」 또는 「{RETURN}」이다", 422)
    seen = _ver(args.get("report_version"))
    ver = current(doc)
    targets = _targets(args.get("targets")) if decision == RETURN else []
    reason = str(args.get("reason") or "").strip() if decision == RETURN else ""
    prior = next((d for d in doc["decisions"] if d["report_version"] == seen), None)
    if prior is not None:
        same = prior["label"] == decision and (
            decision == APPROVE or (prior["targets"], prior["reason"]) == (targets, reason)
        )
        if same:
            return _decision_out(prior)
        state = VERSION_LABEL[version_of(doc, seen)["state"]]
        raise DomainError(
            f"보고 {REPORT_ID} v{seen}은 이미 {prior['label']}({prior['decision_id']})로 "
            f"처리됐다 — 지금 상태 {state} · 현재 버전 v{ver['version']}",
            409,
        )
    if seen != ver["version"]:
        raise DomainError(
            f"본 보고 버전(v{seen})이 현재 상신 버전(v{ver['version']})이 아니다 — 현재 버전으로 "
            "다시 열어 결정한다",
            409,
        )
    if ver["state"] != "WAITING":
        raise DomainError(f"보고 v{seen}은 승인 대기가 아니다 — {VERSION_LABEL[ver['state']]}", 409)
    problems = _consistency(doc, ver)
    if problems:
        raise DomainError(
            "결정을 보류한다 — " + "; ".join(problems) + ". 복구 담당: 회계담당(재상신)", 409
        )
    blocked = _access(doc, ver, fetch, fault)
    if blocked:
        raise DomainError(f"결정을 보류한다 — {blocked}. 복구 담당: 회계담당(첨부 재등록)", 409)
    if decision == RETURN:
        if not targets:
            raise DomainError("보완 요청은 대상 항목(감가상각비·대손충당금)을 골라야 한다", 422)
        if not reason:
            raise DomainError("보완 요청은 사유를 적어야 한다", 422)
    dec = {
        "decision_id": f"DEC-S3-{len(doc['decisions']) + 1:02d}",
        "report_id": REPORT_ID,
        "report_version": seen,
        "decision": "APPROVED" if decision == APPROVE else "RETURNED",
        "label": decision,
        "decided_by": by,
        "decided_via": args.get("answered_via"),
        "decided_at": doc["clock"],
        "targets": targets,
        "reason": reason or None,
        "result_version": ver["result_version"],
        "attachment": dict(ver["attachment"]),
        "items": [
            {k: i[k] for k in ("item_id", "work_id", "name", "request", "request_label")}
            for i in ver["items"]
        ],
        "summary_ref": f"{REPORT_ID} v{seen} 승인 요약",
        "revision_id": None,
    }
    doc["decisions"].append(dec)
    ver["decision_id"] = dec["decision_id"]
    doc["hold"] = None
    if decision == APPROVE:
        ver["state"] = "APPROVED"
        for it in ver["items"]:
            it["approval"] = "APPROVED"
        for p in doc["followups"].values():
            p["state"] = "REQUESTED"
        audit(doc, actor=by, action="report_approved", version=seen, decision=dec["decision_id"])
    else:
        ver["state"] = "RETURNED"
        for it in ver["items"]:
            it["approval"] = "RETURNED"
        rev = {
            "revision_id": f"RVS-S3-{len(doc['revisions']) + 1:02d}",
            "decision_id": dec["decision_id"],
            "report_id": REPORT_ID,
            "base_version": seen,
            "targets": targets,
            "reason": reason,
            "owner": {k: doc["items"][targets[0]][k] for k in ("owner_role", "owner_name")},
            "requested_by": by,
            "requested_at": doc["clock"],
            "state": "OPEN",
            "action": None,
            "steps": [],
            "result_version": ver["result_version"],
            "new_version": None,
            "resubmitted_at": None,
        }
        dec["revision_id"] = rev["revision_id"]
        doc["revisions"].append(rev)
        audit(doc, actor=by, action="report_returned", version=seen, targets=targets)
    doc["bpm"]["waiting"] = []
    return _decision_out(dec)


def _decision_out(dec: dict) -> dict[str, Any]:
    return {
        "decision_id": dec["decision_id"],
        "decision": dec["decision"],
        "report_version": dec["report_version"],
        "error_message": None,
    }


def hand_off(
    doc: dict,
    existing: Callable[[], list[dict]],
    register: Callable[[dict], dict],
    fault: Callable[[str], bool],
) -> dict[str, Any]:
    """
    06 후속 업무 인계 — 승인본을 전표 반영·주석 취합 두 경로에 등록한다. 등록한 경로는 다시 보내지
    않고(재시도는 실패 경로만), 보내기 전에 기간계에 이미 등록된 업무를 먼저 찾는다(응답 유실).
    등록 응답의 수신 담당·승인본 연결을 대조한 뒤에만 반영·취합 대기다.
    """
    dec = approved(doc)
    if dec is None:
        raise DomainError("승인 전이다 — 후속 업무는 승인 뒤에 인계한다", 409)
    ver = version_of(doc, dec["report_version"])
    found_all = None
    for role in doc["roles"]:
        path = role["path"]
        p = doc["followups"][path]
        if p["state"] == "REGISTERED":
            continue
        key = f"{REPORT_ID}:v{ver['version']}:{path}"
        p.update(key=key, attempts=p["attempts"] + 1)
        if found_all is None:
            found_all = existing()
        found = next(
            (r for r in found_all if r["key"] == key and r.get("epoch") == doc["center_epoch"]),
            None,
        )
        recovered = found is not None
        if found is None:
            if fault(FAIL_FAULT[path]):
                p.update(
                    state="HANDOFF_WAIT",
                    reason=f"{p['label']} 업무 등록 실패(시연 스위치) — 이 경로만 다시 인계한다",
                )
                audit(doc, actor="Y01", action="handoff_failed", path=path)
                continue
            lost = path in LOST_FAULT and fault(LOST_FAULT[path])
            got = register(_followup_body(doc, ver, dec, role, key))
            if lost:
                p.update(
                    state="HANDOFF_WAIT",
                    reason="등록 응답이 유실됐다 — 재시도에서 기간계의 기존 업무를 먼저 조회한다",
                )
                audit(doc, actor="Y01", action="handoff_response_lost", path=path)
                continue
            found = got
        problem = _verify(found, role, ver)
        if problem:
            p.update(state="HANDOFF_WAIT", reason=problem)
            continue
        p.update(
            state="REGISTERED",
            reason=None,
            registered_at=found["registered_at"],
            recovered=recovered,
            tasks=[
                {
                    k: t.get(k)
                    for k in (
                        "task_id",
                        "item_id",
                        "work_id",
                        "name",
                        "request",
                        "request_label",
                        "note_sheet",
                        "state",
                    )
                }
                for t in found["tasks"]
            ],
        )
        audit(doc, actor="Y01", action="handoff_registered", path=path, recovered=recovered)
        doc["company_log"].append(
            {
                "at": doc["clock"],
                "direction": "out",
                "what": f"{p['label']} 후속 업무 {len(p['tasks'])}건 — {p['assignee']['name']}"
                + (" (기존 등록 확인)" if recovered else ""),
            }
        )
    waiting = [p for p in doc["followups"].values() if p["state"] != "REGISTERED"]
    if not waiting:
        doc["handoff"] = _handoff(doc, ver, dec)
        doc["bpm"]["waiting"] = []
        return {"state": "DONE", "handoff_id": HANDOFF_ID, "reason": None}
    doc["bpm"]["waiting"] = [{"node_id": "Retry_Handoff", "title": "인계 재시도"}]
    return {
        "state": "PARTIAL",
        "handoff_id": None,
        "reason": "; ".join(f"{p['label']}: {p['reason']}" for p in waiting),
    }


def _followup_body(doc: dict, ver: dict, dec: dict, role: dict, key: str) -> dict[str, Any]:
    prefix = {"POSTING": "POST", "NOTES": "NOTE"}[role["path"]]
    return {
        "key": key,
        "path": role["path"],
        "label": role["label"],
        "report_id": REPORT_ID,
        "report_version": ver["version"],
        "decision_id": dec["decision_id"],
        "approved_by": dec["decided_by"],
        "approved_at": dec["decided_at"],
        "assignee": {k: role[k] for k in ("role", "name", "user_id")},
        "attachment": {k: ver["attachment"][k] for k in ("file_id", "file_version", "filename")},
        "items": [
            {
                "item_id": it["item_id"],
                "work_id": it["work_id"],
                "name": it["name"],
                "task_id": f"FUP-S3-{prefix}-{it['item_id']}",
                "request": it["request"],
                "request_label": it["request_label"],
                "note_sheet": it["note_sheet"] if role["path"] == "NOTES" else None,
            }
            for it in ver["items"]
        ],
        "epoch": doc["center_epoch"],
    }


def _verify(found: dict, role: dict, ver: dict) -> str | None:
    """등록 응답 대조 — 수신 담당·승인본 연결·대상 항목이 맞아야 대기로 바꾼다."""
    if found.get("assignee", {}).get("name") != role["name"]:
        return f"등록된 수신 담당이 {role['name']}이 아니다"
    if found.get("report_version") != ver["version"] or found.get("report_id") != REPORT_ID:
        return "등록된 업무가 승인본을 가리키지 않는다"
    if sorted(t["work_id"] for t in found.get("tasks", [])) != sorted(
        i["work_id"] for i in ver["items"]
    ):
        return "등록된 업무의 대상 항목이 승인본과 다르다"
    return None


def _handoff(doc: dict, ver: dict, dec: dict) -> dict[str, Any]:
    return {
        "handoff_id": HANDOFF_ID,
        "close_id": CLOSE_ID,
        "report_id": REPORT_ID,
        "report_version": ver["version"],
        "decision_id": dec["decision_id"],
        "approved_by": dec["decided_by"],
        "approved_at": dec["decided_at"],
        "attachment_ref": ver["attachment"]["file_id"],
        "result_version": ver["result_version"],
        "items": [
            {k: i[k] for k in ("item_id", "work_id", "name", "request", "request_label")}
            for i in ver["items"]
        ],
        "paths": [
            {
                "path": p["path"],
                "label": p["label"],
                "assignee": p["assignee"],
                "waiting": p["waiting"],
                "tasks": [t["task_id"] for t in p["tasks"]],
                "recovered": p["recovered"],
            }
            for p in doc["followups"].values()
        ],
        "next_step": (
            "전표 반영 담당·주석 취합 담당이 같은 승인본으로 후속 처리(완료는 실제 처리 결과)"
        ),
        "handed_at": doc["clock"],
    }


def _run_record(doc: dict, by: str, via: Any, got: dict) -> dict[str, Any]:
    """보완 재계산의 실행 기록 — 장면 2 실행과 같은 모양(연계 PC는 모의, 장애 스위치 없음)."""
    n = doc["offsets"]["runs"] + len(doc["runs"]) + 1
    run = {
        "run_id": f"RUN-S3-{n:02d}",
        "close_id": CLOSE_ID,
        "works": [i["work_id"] for i in doc["items"].values()],
        "requested_by": by,
        "requested_via": via,
        "requested_at": doc["clock"],
        "input_version": got["input_version"],
        "input_digest": got["digest"],
        "fingerprints": got["fingerprints"],
        "versions": dict(VERSIONS),
        "policy": f"결산기준 {got['input_version']}",
        "execution_mode": EXECUTION_MODE,
        "execution_note": EXECUTION_NOTE,
        "state": "ACCEPTED",
        "steps": _steps(doc["clock"]),
        "last_response_at": None,
        "last_success": None,
        "pc_queries": 1,
        "result_version": None,
        "file_id": None,
        "reconciliation": None,
        "findings": [],
        "superseded_at": None,
        "origin": "보완 재계산(장면 3)",
    }
    _mark(run, "ACCEPTED", "done", doc["clock"])
    return run


def _recalculate(
    doc: dict,
    by: str,
    via: Any,
    got: dict,
    full: dict,
    master: dict,
    put: Callable[[dict], dict],
    fetch: Callable[[str], bytes],
) -> dict:
    """입력 반영 재계산 — 장면 2와 같은 계산 기능·같은 서식의 첨부(새 실행·결과·파일 버전)."""
    found = calc.calculate(full, master)
    if found["state"] != calc.OK:
        raise DomainError(
            "재계산이 보완 필요로 끝났다 — "
            + "; ".join(f"{f['sheet']} {f['reason']}" for f in found["findings"]),
            409,
        )
    run = _run_record(doc, by, via, got)
    for step in ("PC_RECEIVED", "CALCULATING", "CALCULATED"):
        _mark(run, step, "done", doc["clock"])
    n = doc["offsets"]["results"] + len(doc["results"]) + 1
    res = {
        "result_version": f"RES-S3-v{n}",
        "run_id": run["run_id"],
        "input_version": run["input_version"],
        "fingerprints": run["fingerprints"],
        "created_at": doc["clock"],
        "state": found["state"],
        "findings": found["findings"],
        "calc": found,
        "draft": calc.draft(found),
        "draft_edits": [],
    }
    run["result_version"] = res["result_version"]
    alw = found["allowance"]
    run["reconciliation"] = {
        "receivable_diff_won": alw["diffs"]["receivable_won"],
        "max_diff_won": found["max_diff_won"],
        "collective": alw["counts"]["current"]["collective"],
        "individual": alw["counts"]["current"]["individual"],
        "prior_collective": alw["counts"]["prior"]["collective"],
        "prior_individual": alw["counts"]["prior"]["individual"],
        "a_plan_match": True,
    }
    file_version = doc["offsets"]["attachments"] + len(doc["attachments"]) + 1
    built = workpaper.build(found, run, full["sheets"]["전이율원천"], file_version=file_version)
    att = {
        "file_id": f"WP-S3-v{file_version}",
        "file_version": file_version,
        "close_id": CLOSE_ID,
        "run_id": run["run_id"],
        "result_version": res["result_version"],
        **{k: built[k] for k in ("filename", "content_type", "sha256", "size", "sheets")},
        "format_version": built["format_version"],
        "summary_cells": built["summary_cells"],
        "trace": built["trace"],
        "created_at": doc["clock"],
        "state": "CREATED",
        "attempts": [],
        "registered_at": None,
        "open_check": None,
    }
    _mark(run, "FILE_CREATED", "done", doc["clock"])
    put(
        {
            **{
                k: att[k]
                for k in (
                    "file_id",
                    "file_version",
                    "close_id",
                    "run_id",
                    "result_version",
                    "filename",
                    "content_type",
                    "sha256",
                    "size",
                )
            },
            "registered_by": by,
            "execution_mode": EXECUTION_MODE,
            "epoch": doc["center_epoch"],
            "scene": SCENE,
            "content_b64": base64.b64encode(built["content"]).decode(),
        }
    )
    att["attempts"].append({"at": doc["clock"], "ok": True, "reason": None})
    att.update(state="REGISTERED", registered_at=doc["clock"])
    _mark(run, "ATTACHED", "done", doc["clock"])
    sheets = workpaper.opens(fetch(att["file_id"]))
    att["open_check"] = {"at": doc["clock"], "ok": sheets == att["sheets"], "sheets": len(sheets)}
    if sheets != att["sheets"]:
        raise DomainError(f"등록한 {att['file_id']}를 다시 열 수 없다 — 시트가 다르다", 409)
    _mark(run, "OPEN_VERIFIED", "done", doc["clock"])
    _mark(run, "REVIEW_READY", "done", doc["clock"])
    run.update(state="REVIEW_READY", file_id=att["file_id"])
    doc["runs"].append(run)
    doc["results"].append(res)
    doc["attachments"].append(att)
    doc["company_log"].append(
        {"at": doc["clock"], "direction": "out", "what": f"첨부 {att['filename']} 등록·열기 확인"}
    )
    return res


def _review_id(doc: dict, item: str) -> str:
    n = doc["offsets"]["reviews"].get(item, 0) + sum(1 for r in doc["reviews"] if r["item"] == item)
    return f"REV-{item}-{n + 1}"


def _carry(doc: dict, before: dict, res: dict) -> list[str]:
    """입력 지문·요청 금액이 같은 항목의 검토는 승계한다 — 바뀐 항목만 다시 검토한다."""
    carried = []
    for item in REVIEW_ORDER:
        old = review_of(doc, item, before["result_version"])
        if old is None:
            continue
        same_input = before["fingerprints"].get(item) == res["fingerprints"].get(item)
        s_old = next(s for s in before["calc"]["summary"] if s["item"] == item)
        s_new = next(s for s in res["calc"]["summary"] if s["item"] == item)
        if same_input and s_old == s_new:
            doc["reviews"].append(
                {
                    **old,
                    "review_id": _review_id(doc, item),
                    "result_version": res["result_version"],
                    "file_id": attachment_of(doc, res["result_version"])["file_id"],
                    "carried_from": old["review_id"],
                    "state": "CARRIED",
                    "valid": True,
                    "note": None,
                }
            )
            carried.append(item)
    return carried


def revise(
    doc: dict,
    args: dict[str, Any],
    sc01_doc: dict,
    master: dict,
    *,
    close_input: Callable[[dict], dict],
    put: Callable[[dict], dict],
    fetch: Callable[[str], bytes],
) -> dict[str, Any]:
    """
    05 보완 처리 — 회계담당자. 참조 보강 재상신(수치·원천 같음 — 문안·근거 참조만 고치고 변경 내역을
    남긴다) · 재계산(입력이 바뀌어 장면 1 재점검이 끝났다 — 새 결과·파일, 영향 항목 재검토) · 재상신
    (재계산·재검토 뒤). 모두 같은 보고 ID의 새 버전으로 다시 결정을 받는다.
    """
    by = str(args.get("answered_by") or "")
    _owner(doc, by, "보완 처리")
    rev = open_revision(doc)
    if rev is None:
        raise DomainError("열린 보완 요청이 없다 — 보완은 팀장의 보완 요청 뒤에 한다", 409)
    seen = _ver(args.get("report_version"))
    ver = current(doc)
    if seen != ver["version"]:
        raise DomainError(
            f"본 보고 버전(v{seen})이 보완 요청을 받은 버전(v{ver['version']})이 아니다", 409
        )
    action = str(args.get("action") or "")
    note = str(args.get("change_note") or "").strip()
    via = args.get("answered_via")
    res = latest_result(doc)
    if action == RECALC:
        got = entry(sc01_doc)
        if got["input_version"] == res["input_version"]:
            raise DomainError(
                f"입력({got['input_version']})이 그대로다 — 다시 계산할 것이 없다. 문안·근거 "
                f"참조만 고쳤으면 「{REF}」",
                409,
            )
        full = close_input(got)
        new = _recalculate(doc, by, via, got, full, master, put, fetch)
        carried = _carry(doc, res, new)
        todo = _todo(doc, new)
        rev["result_version"] = new["result_version"]
        rev["steps"].append(
            {
                "action": RECALC,
                "at": doc["clock"],
                "by": by,
                "input_version": got["input_version"],
                "result_version": new["result_version"],
                "file_id": attachment_of(doc, new["result_version"])["file_id"],
                "carried": carried,
                "todo": todo,
            }
        )
        audit(doc, actor=by, action="revision_recalculated", result=new["result_version"])
        return _revision_out(
            doc, "REVIEW" if todo else "REVISE", todo, "재계산 끝 — 영향 항목 재검토"
        )
    if action not in (REF, RESUBMIT):
        raise DomainError(f"보완 처리는 「{REF}」·「{RECALC}」·「{RESUBMIT}」이다", 422)
    got = entry(sc01_doc)
    if got["input_version"] != res["input_version"]:
        raise DomainError(
            f"입력이 {res['input_version']} → {got['input_version']}로 바뀌었다 — 영향 항목 "
            f"재계산·재검토 전에는 상신을 보류한다(「{RECALC}」 먼저)",
            409,
        )
    full = close_input(got)
    att = attachment_of(doc, res["result_version"])
    try:
        raw = fetch(att["file_id"])
    except DomainError as exc:
        raise DomainError(f"첨부 {att['file_id']}를 열 수 없다 — {exc}", 409) from exc
    if hashlib.sha256(raw).hexdigest() != att["sha256"]:
        raise DomainError(
            f"첨부 {att['file_id']}의 내용이 결과 {res['result_version']}와 다르다", 409
        )
    old_items = {i["item_id"]: i for i in ver["items"]}
    reasons: dict[str, str] = {}
    changes: list[dict] = []
    if action == REF:
        if res["result_version"] != ver["result_version"]:
            raise DomainError(f"재계산한 결과가 있다 — 「{RESUBMIT}」로 올린다", 409)
        if not note:
            raise DomainError("참조 보강 재상신은 변경 내역(보강한 근거 참조)을 적어야 한다", 422)
        for item in rev["targets"]:
            before = old_items[item]["reason"]
            reasons[item] = f"{before} [참조 보강] {note}"
            changes.append(
                {
                    "item": item,
                    "kind": "reference",
                    "field": "reason",
                    "before": before,
                    "after": reasons[item],
                    "amount_same": True,
                }
            )
        for item in rev["targets"]:
            doc["reviews"].append(
                {
                    **review_of(doc, item, res["result_version"]),
                    "review_id": _review_id(doc, item),
                    "reviewed_by": by,
                    "reviewed_via": via,
                    "reviewed_at": doc["clock"],
                    "carried_from": None,
                    "state": "REREVIEWED",
                    "valid": True,
                    "note": f"참조 보강 재검토 — {note}",
                }
            )
    else:
        if res["result_version"] == ver["result_version"]:
            raise DomainError(
                f"바뀐 금액이 없다 — 참조만 보강했으면 「{REF}」, 입력이 바뀌었으면 「{RECALC}」",
                409,
            )
        todo = _todo(doc, res)
        if todo:
            names = ", ".join(doc["items"][i]["name"] for i in todo)
            raise DomainError(f"영향 항목 재검토 전에는 상신을 보류한다 — {names} 검토 전", 409)
        if res["calc"]["max_diff_won"] != 0:
            raise DomainError(f"대사 차이 {res['calc']['max_diff_won']}원 — 상신을 보류한다", 409)
        summary = {s["item"]: s for s in res["calc"]["summary"]}
        for item, old in old_items.items():
            for k in ("current", "change", "book", "request"):
                if summary[item][k] != old[k]:
                    changes.append(
                        {
                            "item": item,
                            "kind": "amount",
                            "field": k,
                            "before": old[k],
                            "after": summary[item][k],
                            "amount_same": False,
                        }
                    )
        changes.append(
            {
                "item": None,
                "kind": "version",
                "field": "result_version",
                "before": ver["result_version"],
                "after": res["result_version"],
                "amount_same": not any(c["kind"] == "amount" for c in changes),
            }
        )
        if note:
            changes.append(
                {
                    "item": None,
                    "kind": "note",
                    "field": "change_note",
                    "before": None,
                    "after": note,
                    "amount_same": None,
                }
            )
    run = run_of(doc, res["run_id"])
    reviews = [review_of(doc, i, res["result_version"]) for i in REVIEW_ORDER]
    new_ver = _snapshot(
        doc,
        ver["version"] + 1,
        res,
        att,
        run,
        reviews,
        full,
        by=by,
        via=via,
        at=doc["clock"],
        changes=changes,
        revision_id=rev["revision_id"],
        reasons={i: reasons.get(i, old_items[i]["reason"]) for i in old_items}
        if action == REF
        else None,
    )
    new_ver["previous"] = {
        "version": ver["version"],
        "decision_id": rev["decision_id"],
        "targets": rev["targets"],
        "reason": rev["reason"],
    }
    doc["versions"].append(new_ver)
    rev.update(
        state="RESUBMITTED",
        action=action,
        new_version=new_ver["version"],
        resubmitted_at=doc["clock"],
        result_version=res["result_version"],
    )
    rev["steps"].append(
        {"action": action, "at": doc["clock"], "by": by, "version": new_ver["version"]}
    )
    audit(doc, actor=by, action="report_resubmitted", version=new_ver["version"], how=action)
    return _revision_out(doc, "RESUBMITTED", [], f"{REPORT_ID} v{new_ver['version']} 재상신")


def _revision_out(doc: dict, nxt: str, todo: list[str], guide: str) -> dict[str, Any]:
    ver = current(doc)
    res = latest_result(doc)
    att = attachment_of(doc, res["result_version"])
    return {
        "next": nxt,
        "report_version": ver["version"],
        "result_version": res["result_version"],
        "file_id": att["file_id"],
        "item": todo[0] if todo else None,
        "guide": guide,
        "error_message": None,
    }


def review_revision(doc: dict, args: dict[str, Any], sc01_doc: dict) -> dict[str, Any]:
    """보완 재계산 뒤 영향 항목 재검토 — 배정 담당만, 최신 결과·열 수 있는 첨부로만."""
    by = str(args.get("answered_by") or "")
    _owner(doc, by, "재검토")
    if open_revision(doc) is None:
        raise DomainError("열린 보완 요청이 없다", 409)
    item = str(args.get("item") or "")
    if item not in doc["items"]:
        raise DomainError(f"없는 조정항목: {item or '없음'}", 404)
    if str(args.get("decision") or "") != REVIEW_DECISION:
        raise DomainError(f"검토 결정은 「{REVIEW_DECISION}」이다", 422)
    res = latest_result(doc)
    seen = str(args.get("result_version") or "")
    if seen != res["result_version"]:
        raise DomainError(
            f"본 결과 버전({seen or '없음'})이 최신({res['result_version']})이 아니다", 409
        )
    got = entry(sc01_doc)
    if got["input_version"] != res["input_version"]:
        raise DomainError(f"{res['result_version']}는 낡았다 — 입력 {got['input_version']}", 409)
    att = attachment_of(doc, res["result_version"])
    if att is None or att["state"] != "REGISTERED":
        raise DomainError("첨부 Excel이 등록·열기 확인 전이다 — 검토할 수 없다", 409)
    if review_of(doc, item, res["result_version"]) is None:
        s = next(x for x in res["calc"]["summary"] if x["item"] == item)
        rec = {
            "review_id": _review_id(doc, item),
            "item": item,
            "work_id": doc["items"][item]["work_id"],
            "result_version": res["result_version"],
            "file_id": att["file_id"],
            "reviewed_by": by,
            "reviewed_via": args.get("answered_via"),
            "reviewed_at": doc["clock"],
            "paths": REVIEW_PATHS[item],
            "request": s["request"],
            "diff_won": res["calc"]["max_diff_won"],
            "carried_from": None,
            "state": "DONE",
            "valid": True,
            "note": "보완 재계산 뒤 재검토",
        }
        doc["reviews"].append(rec)
        audit(doc, actor=by, action="revision_reviewed", item=item, review_id=rec["review_id"])
    todo = _todo(doc, res)
    out = _revision_out(doc, "REVIEW" if todo else "REVISE", todo, "재검토 기록")
    return out | {"review_id": review_of(doc, item, res["result_version"])["review_id"]}


def _close_of(args: dict[str, Any]) -> None:
    close = args.get("close_id")
    if close is not None and close != CLOSE_ID:
        raise DomainError(f"이 데모 실행의 결산 건은 {CLOSE_ID}다: {close}", 404)


def _nodes(doc: dict, operation: str, out: dict[str, Any]) -> list[str]:
    """그 작업으로 지나온 노드 — 결재 노드는 일감이 없어 그 기록이 오면 지나온 것이다."""
    if operation == "open_close_approval":
        return ["Task_Open"]
    if operation == "decide_close_report":
        return ["Approve_Report", "Record_Decision", "Gw_Decision"]
    if operation == "revise_close_report":
        return ["Revise_Report", "Record_Revision", "Gw_Revision"]
    if operation == "review_close_revision":
        return ["Review_Revision", "Record_Revision_Review", "Gw_Review"]
    nodes = ["Task_Handoff", "Gw_Handoff"]
    if any(p["attempts"] > 1 for p in doc["followups"].values()):
        nodes.append("Retry_Handoff")
    if out.get("state") == "DONE":
        nodes.append("End")
    return nodes


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


class S3Sc03Process:
    def __init__(
        self,
        store: Sc01Store,
        *,
        company: CompanyClient,
        sc01: Any,
        sc02: Any,
        center: CenterClient | None = None,
        publish: Callable[[str], None] = lambda _id: None,
    ) -> None:
        self.store = store
        self.company = company
        self.sc01 = sc01
        self.sc02 = sc02
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
            raise DomainError(f"시나리오 3 장면 3을 열지 않은 데모 실행: {demo_run_id}", 404)
        return found

    def get(self, demo_run_id: str) -> dict:
        return self._load(demo_run_id)[0]

    def master(self) -> dict:
        return self.company.s3_master()

    def _write_records(self, doc: dict) -> None:
        from app.s3.sc03.records import records_of

        records.write(self.company, doc, SCENE, records_of(doc))

    def _commit(self, doc: dict, version: int, event: str) -> dict:
        self._write_records(doc)
        try:
            self.store.save(doc["demo_run_id"], doc, version, event)
        except StaleWrite as exc:
            raise DomainError("다른 요청이 먼저 바꿨다 — 다시 하라", 409) from exc
        self.publish(f"s3sc03:{doc['demo_run_id']}")
        return doc

    def _fault(self, demo_run_id: str) -> Callable[[str], bool]:
        return lambda kind: bool(self.company.take_close_fault(demo_run_id, kind)["fault"])

    def _fetch(self, demo_run_id: str) -> Callable[[str], bytes]:
        return lambda file_id: base64.b64decode(
            self.company.close_attachment(demo_run_id, file_id)["content_b64"]
        )

    def _input(self, demo_run_id: str) -> Callable[[dict], dict]:
        return lambda got: self.company.close_input(
            demo_run_id, got["input_version"], got["digest"]
        )

    # ───────────── 열기·초기화·거두기 ─────────────

    def _sc02_doc(self, demo_run_id: str) -> dict | None:
        found = self.sc02.store.load(demo_run_id)
        return None if found is None else found[0]

    def _new(self, demo_run_id: str, *, case_id: str, executor: str, world_generation: int | None):
        sc02_doc = self._sc02_doc(demo_run_id)
        report = submitted(sc02_doc)
        res = next(
            r for r in sc02_doc["results"] if r["result_version"] == report["result_version"]
        )
        run = next(r for r in sc02_doc["runs"] if r["run_id"] == res["run_id"])
        full = self.company.close_input(demo_run_id, run["input_version"], run["input_digest"])
        doc = new_doc(
            demo_run_id,
            sc02_doc,
            self.master(),
            full,
            case_id=case_id,
            executor=executor,
            world_generation=world_generation
            if world_generation is not None
            else sc02_doc.get("world_generation"),
        )
        doc["clock"] = self.company.world(demo_run_id)["clock"]
        doc["company_log"].append(
            {
                "at": doc["clock"],
                "direction": "in",
                "what": f"장면 2 인계 {ENTRY_HANDOFF} — {REPORT_ID} v{report['version']} 상신본 "
                f"(결과 {report['result_version']} · 첨부 {report['attachment']['file_id']})",
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
        장면 3 열기 — 장면 2 상신이 있어야 한다(아니면 409). Center 실행이면 기동한다. 이미 있으면
        그대로 돌려준다(같은 「장면 열기」를 다시 남겨도 두 번 기동하지 않는다).
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
        self.publish(f"s3sc03:{demo_run_id}")
        return doc

    def reset(
        self,
        demo_run_id: str,
        *,
        actor: str = "u-demo",
        case_id: str | None = None,
        executor: str | None = None,
    ) -> dict:
        """장면 3만 처음으로 — Center 작업을 거두고 다시 연다(기간계 후속 업무는 사이트가 비운다)"""
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

    def receive_inputs(self, demo_run_id: str) -> dict | None:
        """
        자료 담당자가 입력을 다시 연결했다 — 제출본의 입력과 지금 입력이 다르면 알림만 남긴다(결정은
        막지 않는다 — 상신 뒤의 변경은 팀장의 보완 요청과 회계담당자의 재계산 몫이다).
        """
        if self.store.load(demo_run_id) is None:
            return None
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            sc01 = self.sc01.get(demo_run_id)
            now, ver = sc01.get("current_version"), current(doc)
            notice = (
                None
                if now == latest_result(doc)["input_version"]
                else {
                    "input_version": now,
                    "report_input": ver["input_version"],
                    "reason": f"제출본(v{ver['version']})은 입력 {ver['input_version']}로 "
                    f"계산했다 — 지금 입력은 {now}",
                }
            )
            if notice == doc["input_notice"]:
                return doc
            doc["input_notice"] = notice
            audit(doc, actor="system", action="input_changed", version=now)
            return self._commit(doc, version, "inputs")

    # ───────────── Center ─────────────

    def _center_key(self, doc: dict) -> str:
        return f"s3sc03:{doc['demo_run_id']}:e{doc['center_epoch']}"

    def _start_job(self, doc: dict) -> None:
        bpm = doc["bpm"]
        problem = self.center.config.missing(integration=True)
        if problem:
            bpm["problem"] = f"{problem} — 장면 3을 기동하지 않았다. Center에서 직접 기동하라"
            return
        try:
            job = self.center.start_job(
                {"데모실행ID": doc["demo_run_id"], "결산건ID": CLOSE_ID},
                idempotency_key=self._center_key(doc),
                on_behalf=ON_BEHALF,
                package=self.center.config.s3_sc03_package,
                note="NowView S3 SC03 — 팀장 보고 및 승인",
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
        """일감 전에 실패한 실행의 사유를 남긴다(장면 1·2와 같다)."""
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
            if doc["bpm"].get("state") != "running" or doc["bpm"].get("job_id") != bpm["job_id"]:
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
        _close_of(args)
        master = self.master()
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            self._link(doc, external_run_id, via)
            sc01_doc = self.sc01.get(demo_run_id)
            try:
                out = self._run_operation(doc, operation, args, sc01_doc, master)
            except DomainError as exc:
                if operation != "decide_close_report" or exc.status not in (403, 409):
                    raise
                if current(doc)["state"] != "WAITING":
                    raise  # 이미 결정된 버전의 충돌 요청 — 보류가 아니라 처리된 상태 안내다
                # 결정 보류 — 사유와 복구 담당을 남긴다(결정·후속 배정은 0건, 같은 결재로 돌아간다)
                doc, version = self._load(demo_run_id)
                self._hold(doc, args, str(exc), exc.status)
                self._commit(doc, version, "hold")
                raise
            bpm = doc["bpm"]
            for nid in _nodes(doc, operation, out):
                if nid not in bpm["visited"]:
                    bpm["visited"].append(nid)
            if operation == "hand_off_close_approval" and out["state"] == "DONE":
                bpm.update(state="done", waiting=[])
            self._commit(doc, version, operation)
        return out

    def _hold(self, doc: dict, args: dict[str, Any], reason: str, status: int) -> None:
        if "복구 담당:" in reason:
            owner = reason.split("복구 담당:", 1)[1].strip()
        elif status == 403:
            owner = "회계팀장(지정 결재자만 결정한다)"
        else:
            owner = "회계팀장(현재 상신 버전으로 다시 연다)"
        hold = {
            "at": doc["clock"],
            "by": args.get("answered_by"),
            "decision": args.get("decision"),
            "report_version": args.get("report_version"),
            "status": status,
            "reason": reason,
            "recovery_owner": owner,
        }
        doc["holds"].append(hold)
        doc["hold"] = hold
        audit(doc, actor=str(args.get("answered_by") or "-"), action="decision_held", status=status)

    def _run_operation(
        self, doc: dict, operation: str, args: dict[str, Any], sc01_doc: dict, master: dict
    ) -> dict[str, Any]:
        rid = doc["demo_run_id"]
        if operation == "open_close_approval":
            return open_report(doc)
        if operation == "decide_close_report":
            return decide(doc, args, self._fetch(rid), self._fault(rid))
        if operation == "hand_off_close_approval":
            return hand_off(
                doc,
                lambda: self.company.close_followups(rid),
                lambda body: self.company.put_close_followup(rid, body),
                self._fault(rid),
            )
        if operation == "revise_close_report":
            return revise(
                doc,
                args,
                sc01_doc,
                master,
                close_input=self._input(rid),
                put=lambda body: self.company.put_close_attachment(rid, body),
                fetch=self._fetch(rid),
            )
        return review_revision(doc, args, sc01_doc)

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
            raise DomainError(
                f"이 결산 건 장면 3은 이미 다른 실행({bpm['external_run_id']})이 처리한다", 409
            )


__all__ = ["CASES", "OPERATIONS", "S3Sc03Process", "WORK", "submitted"]
