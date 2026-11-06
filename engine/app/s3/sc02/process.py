"""
시나리오 3 장면 2 실행 — 결산조정 계산 및 담당자 검토(업무설계표 01~07, `docs/s3/sc02.md`).

* **장면 1 인계(HAND-S3-01)에서 연다** — 사이트의 「장면 열기」(시나리오 3 장면 2)를 세계 따라가기가
  넘기면 이 문서를 만들고 `company1.s3.sc02`를 기동한다(입력 `데모실행ID`·`결산건ID`). 장면 1 인계가
  무효이거나 항목이 준비 완료가 아니면 열지 않는다(409).
* **그림은 순서만 쥔다** — 지시 열기 → 회계담당자의 「분석 실행」(결재) → 실행 접수 → 계산
  (연계 PC 작업) → Excel 생성·첨부 → 다음 검토 고르기 → 항목별 「검토 완료」(결재 둘) → 「상신」
  (결재) → 인계. 지시문 열람은 조회라 실행을 만들지 않는다.
* **이번 판은 모의 실행이다**(`execution_mode: simulated`) — 연계 데스크톱 PC·Excel이 없다. 일꾼이
  같은 계산(`calc`)과 같은 시트·수식 구성의 .xlsx(`workpaper`)를 만들고, 작업 단계(접수 → PC 수신 →
  계산 중 → 계산·대사 → 파일 생성 → 첨부 등록 → 열기 확인 → 검토 대기)를 그 응답 시각으로 남긴다.
  PC 미응답·전송 실패는 기간계의 시연 스위치(`sim/close-faults`)로만 생긴다 — 지어낸 지연이 아니다.
* **숫자는 계산 기능만 만든다** — Agent 문안은 결과 칸을 이어 붙인 규칙 문안이다(LLM 호출 없음).
  화면 요약·첨부 Excel·주석 발췌는 같은 결과 버전을 가리킨다.
* **실행 직전과 상신 직전에 장면 1의 준비 판정·최신 입력을 다시 본다** — 입력이 다시 연결돼 장면 1
  인계가 무효가 되면 지금 결과는 낡은 것이다(검토·상신 409 → 다시 실행). 새 결과에서 그 항목의
  입력과 금액이 같으면 앞 검토를 승계하고, 바뀐 항목만 다시 검토한다.
* 상신은 한 번이다 — 같은 상신의 재전송은 같은 보고 ID. 끝은 승인 대기 2행 · 상신 1건 · 승인 0건.
  팀장 승인·전표 반영·주석 취합은 장면 3이다.
"""

from __future__ import annotations

import base64
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
from app.sc01.center import CenterClient, CenterConfig, CenterError
from app.sc01.domain import DomainError, parse_at
from app.sc01.store import Sc01Store, StaleWrite

PROCESS_PATH = Path(__file__).resolve().parents[3] / "processes" / "s3-sc02.bpmn"
SCENARIO = "s3"
SCENE = 2
#: NowView 업무 번호 — 시나리오 3 장면 N은 30 + N(`docs/platform.md` §7)
WORK = 32
CLOSE_ID = "S3-CLOSE-01"
ENTRY_HANDOFF = "HAND-S3-01"
HANDOFF_ID = "HAND-S3-02"
REPORT_ID = "REP-S3-01"
OPERATIONS = (
    "open_close_analysis",
    "request_close_analysis",
    "process_close_analysis",
    "attach_close_workpaper",
    "route_close_review",
    "review_close_item",
    "submit_close_report",
)
CASES = ("BASE",)
ON_BEHALF = "시스템 자동처리"
RUN_DECISION, REVIEW_DECISION, SUBMIT_DECISION = "분석 실행", "검토 완료", "상신"
REVIEW_NODE = {"ALW": "Review_Allowance", "DEP": "Review_Depreciation"}
RECORD_REVIEW_NODE = {"ALW": "Record_Review_Allowance", "DEP": "Record_Review_Depreciation"}
#: 검토 순서 — 시연은 충당금 분석을 중심으로 하고 상각비는 같은 실행 범위에서 확인한다
REVIEW_ORDER = ("ALW", "DEP")
NEXT_SUBMIT, NEXT_RERUN = "SUBMIT", "RERUN"
#: 실행 환경(구현용 가정 id — 자료에 없다, `docs/s3/sc02.md`)
VERSIONS = {
    "prompt": "PRM-S3-SC02-v0.1",
    "format": workpaper.FORMAT_VERSION,
    "calc": calc.RULE_VERSION,
    "agent": "AGT-S3-CLOSE-v0.1(규칙 문안)",
    "environment": "ENV-S3-PC-SIM-v0.1",
}
EXECUTION_MODE = "simulated"
EXECUTION_NOTE = (
    "연계 데스크톱 PC·Excel 연동이 없다. NowView 일꾼이 같은 계산과 같은 시트·수식 구성의 .xlsx를 "
    "만들어 결산 건에 첨부했다. 파트너의 구현 가능 확인과 실제 연동 시험 결과는 아직 없다"
)
#: 화면 01·구현명세 §1 — 담당자가 확인하는 지시문
PROMPT = (
    "이번 결산의 외상매출금 명세와 원장을 대사하고 집합·개별평가를 구분해 주세요. 개별채권은 "
    "회계담당자가 확인한 회수예상액을 사용하고, 주요 거래처의 충당금 변동과 근거를 설명해 주세요. "
    "감가상각비는 자산별로 계산해 비용 귀속별 합계 및 주석과 대조해 주세요. 두 항목의 계산식과 "
    "상세 주석은 Excel 한 파일로, 전기 대비 변동과 이번 조정 요청액은 화면 요약으로 작성해 주세요. "
    "근거가 "
    "부족하면 대상과 보완 사유를 표시해 주세요."
)
STEPS = (
    ("ACCEPTED", "실행 접수"),
    ("PC_RECEIVED", "PC 수신"),
    ("CALCULATING", "계산 중"),
    ("CALCULATED", "계산·대사 완료"),
    ("FILE_CREATED", "파일 생성"),
    ("ATTACHED", "BPM 첨부 등록"),
    ("OPEN_VERIFIED", "열기 확인"),
    ("REVIEW_READY", "검토 대기"),
)
#: 검토 동선(화면 03) — 담당자가 첨부와 BPM 근거를 오가며 보는 것
REVIEW_PATHS = {
    "ALW": [
        "개별평가 A사 두 행 ↔ PLAN-A-26·CONF-26-S·CONF-26-F",
        "충당금비교 → 채권별계산 G사 행",
        "충당금주석 → 승인요약 충당금 행",
    ],
    "DEP": ["상각비비교 자산 합계·귀속 합계", "유형자산주석 합계 행", "원장대사 기계상"],
}
STATE_LABEL = {
    "WAITING_RUN": "분석 실행 대기",
    "RUNNING": "분석 중",
    "ATTACH_WAIT": "첨부 대기",
    "NEEDS_FIX": "보완 필요",
    "REVIEW_WAIT": "검토 대기",
    "REVIEWED": "검토 완료",
    "STALE": "재계산 필요",
    "SUBMITTED": "승인 대기",
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


# ─────────────────────────── 장면 1 인계 ───────────────────────────


def entry(sc01_doc: dict) -> dict[str, Any]:
    """
    장면 2 진입·실행·상신의 조건 — 장면 1 인계가 유효하고 두 항목이 지금 입력으로 준비 완료다.
    아니면
    409와 함께 영향 항목·보완 사유·보완 담당을 낸다(구현명세 §4 인수시험 01·05).
    """
    h = sc01_doc.get("handoff")
    current = sc01_doc.get("current_version")
    v = next((x for x in sc01_doc["inputs"] if x["version"] == current), None)
    blocked = []
    for item in sc01_doc["items"].values():
        if v is None:
            continue
        if item["state"] == "READY" and item["checked_fingerprint"] == v["fingerprints"].get(
            item["item_id"]
        ):
            continue
        fix = next((f for f in sc01_doc["fixes"] if f["fix_id"] == item.get("fix")), None)
        why = item.get("recheck_reason") or "자료 점검 전"
        if fix is not None and fix["state"] == "OPEN":
            why = "; ".join(
                f"{f['check_id']} {f['reason']} — {f['owner_role']}" for f in fix["findings"]
            )
        blocked.append(f"{item['name']}({item['state']}): {why}")
    if h is None or not h.get("valid") or h.get("input_version") != current or blocked:
        detail = "; ".join(blocked) or "장면 1 인계가 없거나 무효다 — 재점검 후 다시 인계한다"
        raise DomainError(
            f"분석 준비가 최신 입력({current})으로 끝나지 않았다 — {detail}. 통합 상신은 보류된다",
            409,
        )
    return {
        "handoff_id": h["handoff_id"],
        "input_version": current,
        "digest": v["digest"],
        "fingerprints": dict(v["fingerprints"]),
    }


def new_doc(
    demo_run_id: str,
    sc01_doc: dict,
    master: dict,
    *,
    case_id: str,
    executor: str,
    world_generation: int | None,
) -> dict[str, Any]:
    if case_id not in CASES:
        raise DomainError(f"모르는 사례: {case_id} (가능: {', '.join(CASES)})", 422)
    if executor not in ("center", "studio"):
        raise DomainError("실행 위치는 center·studio다 — 내장 실행은 쓰지 않는다", 422)
    got = entry(sc01_doc)
    items = {}
    for it in master["close"]["items"]:
        items[it["item_id"]] = {
            k: it[k] for k in ("item_id", "work_id", "name", "owner_role", "owner_name", "owner_id")
        } | {"sheets": list(it["sheets"]), "follow_up": list(it["follow_up"])}
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
        "close": dict(sc01_doc["close"]),
        "entry": {**got, "opened_at": None},
        "instruction": {
            "text": PROMPT,
            "versions": dict(VERSIONS),
            "linked_sheets": list(master["allowed_sheets"]),
            "excluded_sheets": list(master["excluded_sheets"]),
            "scope": [it["item_id"] for it in master["close"]["items"]],
            "entry_item": "ALW",
            "periods": [sc01_doc["close"]["period_end"], sc01_doc["close"]["comparative_end"]],
        },
        "items": items,
        "runs": [],
        "results": [],
        "attachments": [],
        "reviews": [],
        "report": None,
        "handoff": None,
        "stale": None,
        "bpm": _new_bpm(executor),
        "audit": [],
        "company_log": [],
        "company_records": {},
    }


# ─────────────────────────── 조회 ───────────────────────────


def latest_run(doc: dict) -> dict | None:
    return doc["runs"][-1] if doc["runs"] else None


def result_of(doc: dict, version: str | None) -> dict | None:
    return next((r for r in doc["results"] if r["result_version"] == version), None)


def latest_result(doc: dict) -> dict | None:
    run = latest_run(doc)
    return None if run is None else result_of(doc, run["result_version"])


def attachment_of(doc: dict, result_version: str | None) -> dict | None:
    return next((a for a in doc["attachments"] if a["result_version"] == result_version), None)


def review_of(doc: dict, item: str, result_version: str) -> dict | None:
    return next(
        (
            r
            for r in doc["reviews"]
            if r["item"] == item and r["result_version"] == result_version and r["valid"]
        ),
        None,
    )


def is_stale(result: dict, sc01_doc: dict) -> str | None:
    """지금 결과가 낡았는가 — 사유(낡지 않았으면 None)."""
    try:
        got = entry(sc01_doc)
    except DomainError as exc:
        return str(exc)
    if got["input_version"] != result["input_version"]:
        return f"입력이 {result['input_version']} → {got['input_version']}로 바뀌었다 — 다시 실행"
    return None


def item_state(doc: dict, item_id: str) -> str:
    """체크리스트 행의 장면 2 단계."""
    if doc["report"] is not None:
        return "SUBMITTED"
    if doc["stale"]:
        return "STALE"
    run = latest_run(doc)
    if run is None:
        return "WAITING_RUN"
    result = result_of(doc, run["result_version"])
    if run["state"] == "NEEDS_FIX":
        return "NEEDS_FIX"
    if run["state"] == "ATTACH_WAIT":
        return "ATTACH_WAIT"
    if result is None or run["state"] != "REVIEW_READY":
        return "RUNNING"
    return "REVIEWED" if review_of(doc, item_id, result["result_version"]) else "REVIEW_WAIT"


# ─────────────────────────── 작업 단계 ───────────────────────────


def _steps(at: str) -> list[dict[str, Any]]:
    return [
        {"step": s, "label": label, "state": "waiting", "at": None, "responded_at": None}
        for s, label in STEPS
    ]


def _mark(run: dict, step: str, state: str, at: str) -> None:
    for s in run["steps"]:
        if s["step"] == step:
            s.update(state=state, at=at, responded_at=_now())
    run["last_response_at"] = at
    done = [s for s in run["steps"] if s["state"] == "done"]
    run["last_success"] = done[-1]["step"] if done else None


def _owner(doc: dict, by: str, what: str) -> None:
    owners = {i["owner_name"] for i in doc["items"].values()}
    if by not in owners:
        raise DomainError(
            f"{what}은 배정 담당({', '.join(sorted(owners))})만 한다 — {by or '이름 없음'}", 403
        )


# ─────────────────────────── 작업 ───────────────────────────


def open_scene(doc: dict) -> dict[str, Any]:
    """01 지시 열기 — 사용할 자료·지시·버전. 열람은 실행을 만들지 않는다."""
    if doc["entry"]["opened_at"] is None:
        doc["entry"]["opened_at"] = doc["clock"]
    audit(doc, actor="Y01", action="instruction_opened")
    return {
        "input_version": doc["entry"]["input_version"],
        "prompt_version": VERSIONS["prompt"],
        "items": len(doc["items"]),
    }


def request(doc: dict, args: dict[str, Any], sc01_doc: dict) -> dict[str, Any]:
    """
    02 실행 요청 — 배정 담당만, 지금(최신) 입력 버전으로만, 장면 1 준비가 유효할 때만. 같은 입력의
    실행이 이미 있으면 그 실행이다(연속 클릭 1건). 실행 ID를 발급하고 앞 실행은 대체한다.
    """
    by = str(args.get("answered_by") or "")
    _owner(doc, by, "분석 실행")
    if str(args.get("decision") or "") != RUN_DECISION:
        raise DomainError(f"실행 결정은 「{RUN_DECISION}」이다", 422)
    got = entry(sc01_doc)
    seen = str(args.get("version") or "")
    if seen != got["input_version"]:
        raise DomainError(
            f"본 입력 버전({seen or '없음'})이 최신({got['input_version']})이 아니다 — "
            "최신 자료로 다시 실행한다",
            409,
        )
    last = latest_run(doc)
    if last is not None and last["input_version"] == got["input_version"]:
        if last["state"] == "NEEDS_FIX":
            raise DomainError(
                f"같은 입력({got['input_version']})의 실행 {last['run_id']}이 보완 필요로 끝났다 — "
                "자료를 보완해 다시 연결한 뒤 실행한다",
                409,
            )
        if last["state"] != "SUPERSEDED":
            return {
                "run_id": last["run_id"],
                "input_version": last["input_version"],
                "error_message": None,
            }
    if last is not None and last["state"] != "SUPERSEDED":
        last["state"] = "SUPERSEDED"
        last["superseded_at"] = doc["clock"]
    n = len(doc["runs"]) + 1
    run = {
        "run_id": f"RUN-S3-{n:02d}",
        "close_id": CLOSE_ID,
        "works": [i["work_id"] for i in doc["items"].values()],
        "requested_by": by,
        "requested_via": args.get("answered_via"),
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
        "pc_queries": 0,
        "result_version": None,
        "file_id": None,
        "reconciliation": None,
        "findings": [],
        "superseded_at": None,
    }
    _mark(run, "ACCEPTED", "done", doc["clock"])
    doc["runs"].append(run)
    doc["stale"] = None
    doc["bpm"]["waiting"] = []
    audit(
        doc,
        actor=by,
        action="analysis_requested",
        run_id=run["run_id"],
        version=run["input_version"],
    )
    return {"run_id": run["run_id"], "input_version": run["input_version"], "error_message": None}


def _run(doc: dict, run_id: str) -> dict:
    run = latest_run(doc)
    if run is None or run["run_id"] != run_id:
        known = any(r["run_id"] == run_id for r in doc["runs"])
        raise DomainError(
            f"이전 실행({run_id})의 응답은 최신 결과를 덮지 않는다"
            if known
            else f"없는 실행: {run_id}",
            409 if known else 404,
        )
    return run


def process_run(
    doc: dict, run_id: str, full: dict, master: dict, fault: Callable[[str], bool]
) -> dict[str, Any]:
    """
    03·04 계산 — 연계 PC 작업(모의). 같은 실행은 한 번만 계산한다. PC 미응답(시연 스위치)이면
    계산 중에서 멈추고 마지막 응답 시각을 남긴다. 결과가 대사·근거를 통과하지 못하면 보완 필요다.
    """
    run = _run(doc, run_id)
    out = {"run_id": run_id, "error_message": None}
    if run["result_version"] is not None:
        res = result_of(doc, run["result_version"])
        return out | {"state": res["state"], "result_version": res["result_version"]} | _resp(run)
    run["pc_queries"] += 1
    if next(s for s in run["steps"] if s["step"] == "PC_RECEIVED")["state"] != "done":
        _mark(run, "PC_RECEIVED", "done", doc["clock"])
    if fault("pc_delay"):
        _mark(run, "CALCULATING", "running", doc["clock"])
        run["state"] = "PENDING"
        audit(doc, actor="PC", action="pc_no_response", run_id=run_id)
        return out | {"state": "PENDING", "result_version": None} | _resp(run)
    _mark(run, "CALCULATING", "done", doc["clock"])
    found = calc.calculate(full, master)
    n = len(doc["results"]) + 1
    res = {
        "result_version": f"RES-S3-v{n}",
        "run_id": run_id,
        "input_version": run["input_version"],
        "fingerprints": run["fingerprints"],
        "created_at": doc["clock"],
        "state": found["state"],
        "findings": found["findings"],
        "calc": found,
        "draft": calc.draft(found) if found["state"] == calc.OK else None,
        "draft_edits": [],
    }
    doc["results"].append(res)
    run["result_version"] = res["result_version"]
    alw = found["allowance"]
    run["reconciliation"] = {
        "receivable_diff_won": alw["diffs"]["receivable_won"],
        "max_diff_won": found["max_diff_won"],
        "collective": alw["counts"]["current"]["collective"],
        "individual": alw["counts"]["current"]["individual"],
        "prior_collective": alw["counts"]["prior"]["collective"],
        "prior_individual": alw["counts"]["prior"]["individual"],
        "a_plan_match": not any(f["sheet"] == "확인기록" for f in found["findings"]),
    }
    run["findings"] = found["findings"]
    if found["state"] != calc.OK:
        _mark(run, "CALCULATED", "fix", doc["clock"])
        run["state"] = "NEEDS_FIX"
        audit(
            doc,
            actor="PC",
            action="analysis_needs_fix",
            run_id=run_id,
            findings=len(found["findings"]),
        )
        return out | {"state": "NEEDS_FIX", "result_version": res["result_version"]} | _resp(run)
    _mark(run, "CALCULATED", "done", doc["clock"])
    run["state"] = "CALCULATED"
    _carry_reviews(doc, res)
    audit(
        doc, actor="PC", action="analysis_calculated", run_id=run_id, result=res["result_version"]
    )
    return out | {"state": calc.OK, "result_version": res["result_version"]} | _resp(run)


def _resp(run: dict) -> dict[str, Any]:
    rec = run.get("reconciliation") or {}
    return {
        "last_response_at": run["last_response_at"],
        "diff_won": rec.get("max_diff_won"),
        "reason": "; ".join(f["reason"] for f in run["findings"]) or None,
    }


def _carry_reviews(doc: dict, res: dict) -> None:
    """
    새 결과에서 그 항목의 입력 지문·요청 금액이 앞 결과와 같으면 앞 검토를 승계한다 — 영향받은
    항목만 다시 검토한다(구현명세 §4 「영향 항목 재점검·재계산·재검토」).
    """
    prior = [r for r in doc["results"] if r is not res and r["state"] == calc.OK]
    if not prior:
        return
    before = prior[-1]
    for item in REVIEW_ORDER:
        old = review_of(doc, item, before["result_version"])
        if old is None:
            continue
        same_input = before["fingerprints"].get(item) == res["fingerprints"].get(item)
        same_sum = _item_summary(before, item) == _item_summary(res, item)
        if same_input and same_sum:
            doc["reviews"].append(
                {
                    **old,
                    "review_id": f"REV-{item}-{_review_n(doc, item)}",
                    "result_version": res["result_version"],
                    "carried_from": old["review_id"],
                    "state": "CARRIED",
                    "valid": True,
                }
            )


def _item_summary(res: dict, item: str) -> dict:
    return next(s for s in res["calc"]["summary"] if s["item"] == item)


def _review_n(doc: dict, item: str) -> int:
    return sum(1 for r in doc["reviews"] if r["item"] == item) + 1


def attach(
    doc: dict,
    run_id: str,
    rates_source: dict,
    fault: Callable[[str], bool],
    put: Callable[[dict], dict],
    fetch: Callable[[str], bytes],
) -> dict[str, Any]:
    """
    05 파일 생성·첨부 — 결과 버전 하나에 파일 하나. 전송이 실패하면 첨부 대기로 두고 같은 실행·같은
    파일을 다시 보낸다(새 파일을 만들지 않는다). 등록한 파일을 다시 열 수 있어야 검토 대기다.
    """
    run = _run(doc, run_id)
    res = result_of(doc, run["result_version"])
    if res is None or res["state"] != calc.OK:
        raise DomainError(f"실행 {run_id}에 첨부할 계산 결과가 없다", 409)
    att = attachment_of(doc, res["result_version"])
    if att is not None and att["state"] == "REGISTERED":
        return _att_out(att, "REGISTERED")
    file_version = att["file_version"] if att else len(doc["attachments"]) + 1
    built = workpaper.build(res["calc"], run, rates_source, file_version=file_version)
    if att is None:
        att = {
            "file_id": f"WP-S3-v{file_version}",
            "file_version": file_version,
            "close_id": CLOSE_ID,
            "run_id": run_id,
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
        doc["attachments"].append(att)
        _mark(run, "FILE_CREATED", "done", doc["clock"])
    elif built["sha256"] != att["sha256"]:
        raise DomainError(
            f"{att['file_id']}를 다시 만들었더니 내용이 달랐다 — 재전송하지 않는다", 409
        )
    run["file_id"] = att["file_id"]
    if fault("transfer_fail"):
        att["attempts"].append(
            {"at": doc["clock"], "ok": False, "reason": "PC → BPM 파일 전송 실패(시연 스위치)"}
        )
        att["state"] = "TRANSFER_FAILED"
        _mark(run, "ATTACHED", "failed", doc["clock"])
        run["state"] = "ATTACH_WAIT"
        audit(doc, actor="PC", action="attach_failed", file_id=att["file_id"])
        return _att_out(att, "WAITING")
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
            "registered_by": run["requested_by"],
            "execution_mode": EXECUTION_MODE,
            "epoch": doc["center_epoch"],
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
    run["state"] = "REVIEW_READY"
    audit(doc, actor="PC", action="attached", file_id=att["file_id"], result=res["result_version"])
    doc["company_log"].append(
        {"at": doc["clock"], "direction": "out", "what": f"첨부 {att['filename']} 등록·열기 확인"}
    )
    return _att_out(att, "REGISTERED")


def _att_out(att: dict, state: str) -> dict[str, Any]:
    return {
        "state": state,
        "file_id": att["file_id"],
        "filename": att["filename"],
        "result_version": att["result_version"],
    }


def route(doc: dict, sc01_doc: dict) -> dict[str, Any]:
    """다음 검토 — 지금 결과가 낡았으면 다시 실행, 검토가 남은 항목(충당금 먼저), 둘 다면 상신."""
    run = latest_run(doc)
    res = latest_result(doc)
    if run is None or res is None or run["state"] != "REVIEW_READY":
        raise DomainError("검토할 결과가 없다 — 실행·첨부가 먼저다", 409)
    stale = is_stale(res, sc01_doc)
    doc["stale"] = (
        None if stale is None else {"result_version": res["result_version"], "reason": stale}
    )
    reviewed = sum(1 for i in REVIEW_ORDER if review_of(doc, i, res["result_version"]))
    if stale is not None:
        nxt, reason = NEXT_RERUN, stale
        doc["bpm"]["waiting"] = [{"node_id": "Request_Analysis", "title": "다시 분석 실행"}]
    else:
        todo = [i for i in REVIEW_ORDER if not review_of(doc, i, res["result_version"])]
        if todo:
            nxt = todo[0]
            reason = f"{doc['items'][nxt]['name']} 검토 차례 — {res['result_version']}"
            doc["bpm"]["waiting"] = [
                {
                    "node_id": REVIEW_NODE[nxt],
                    "title": f"{doc['items'][nxt]['name']} 계산 근거 검토",
                }
            ]
        else:
            nxt, reason = NEXT_SUBMIT, "두 항목 검토 완료 — 상신"
            doc["bpm"]["waiting"] = [{"node_id": "Submit_Report", "title": "보고 상신"}]
    return {
        "next": nxt,
        "result_version": res["result_version"],
        "reviewed": reviewed,
        "reason": reason,
    }


def _current_result(doc: dict, seen: str, sc01_doc: dict) -> dict:
    res = latest_result(doc)
    run = latest_run(doc)
    if res is None or run is None or run["state"] != "REVIEW_READY":
        raise DomainError("검토할 결과가 없다", 409)
    if seen != res["result_version"]:
        raise DomainError(
            f"본 결과 버전({seen or '없음'})이 최신({res['result_version']})이 아니다 — "
            "최신 결과·첨부로 다시 본다",
            409,
        )
    stale = is_stale(res, sc01_doc)
    if stale is not None:
        raise DomainError(f"{res['result_version']}는 낡았다 — {stale}", 409)
    att = attachment_of(doc, res["result_version"])
    if att is None or att["state"] != "REGISTERED" or not (att["open_check"] or {}).get("ok"):
        raise DomainError("첨부 Excel이 등록·열기 확인 전이다 — 검토할 수 없다", 409)
    return res


def review(doc: dict, args: dict[str, Any], sc01_doc: dict) -> dict[str, Any]:
    """06 항목별 검토 완료 — 배정 담당만, 최신·유효 결과·열 수 있는 첨부로만. 같은 검토는 그대로."""
    item = str(args.get("item") or "")
    if item not in doc["items"]:
        raise DomainError(f"없는 조정항목: {item}", 404)
    by = str(args.get("answered_by") or "")
    _owner(doc, by, f"{doc['items'][item]['name']} 검토")
    if str(args.get("decision") or "") != REVIEW_DECISION:
        raise DomainError(f"검토 결정은 「{REVIEW_DECISION}」이다", 422)
    res = _current_result(doc, str(args.get("result_version") or ""), sc01_doc)
    found = review_of(doc, item, res["result_version"])
    if found is not None:
        return {
            "review_id": found["review_id"],
            "result_version": res["result_version"],
            "error_message": None,
        }
    att = attachment_of(doc, res["result_version"])
    s = _item_summary(res, item)
    rec = {
        "review_id": f"REV-{item}-{_review_n(doc, item)}",
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
    }
    doc["reviews"].append(rec)
    audit(doc, actor=by, action="item_reviewed", item=item, review_id=rec["review_id"])
    doc["bpm"]["waiting"] = []
    return {
        "review_id": rec["review_id"],
        "result_version": res["result_version"],
        "error_message": None,
    }


def submit(doc: dict, args: dict[str, Any], sc01_doc: dict) -> dict[str, Any]:
    """
    07 한 건 상신 — 두 검토 완료·대사 차이 0·최신 입력과 결과 버전 일치·첨부 열기 가능·담당 권한.
    두 항목·요청액·요약·첨부를 보고 ID 하나로 고정한다. 같은 상신의 재전송은 같은 보고 ID.
    """
    by = str(args.get("answered_by") or "")
    _owner(doc, by, "상신")
    if str(args.get("decision") or "") != SUBMIT_DECISION:
        raise DomainError(f"상신 결정은 「{SUBMIT_DECISION}」이다", 422)
    seen = str(args.get("result_version") or "")
    rep = doc["report"]
    if rep is not None:
        if rep["result_version"] == seen:
            return {
                "report_id": rep["report_id"],
                "report_version": rep["version"],
                "handoff_id": HANDOFF_ID,
                "error_message": None,
            }
        raise DomainError(
            f"이미 {rep['report_id']}로 상신했다 — 보완은 장면 3의 팀장 보완 요청으로 한다", 409
        )
    res = _current_result(doc, seen, sc01_doc)
    blocking = [
        f"{doc['items'][i]['name']} 검토 전"
        for i in REVIEW_ORDER
        if not review_of(doc, i, res["result_version"])
    ]
    if res["calc"]["max_diff_won"] != 0 or res["calc"]["diffs_missing"]:
        blocking.append(f"대사 차이 {res['calc']['max_diff_won']}원")
    if blocking:
        raise DomainError("상신 조건 미충족 — " + "; ".join(blocking), 409)
    run = next(r for r in doc["runs"] if r["run_id"] == res["run_id"])
    att = attachment_of(doc, res["result_version"])
    reviews = [review_of(doc, i, res["result_version"]) for i in REVIEW_ORDER]
    items = []
    for s in res["calc"]["summary"]:
        section = next(x for x in res["draft"]["sections"] if x["item"] == s["item"])
        items.append(
            {
                "item_id": s["item"],
                "work_id": doc["items"][s["item"]]["work_id"],
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
                "reason": section["text"],
                "summary_cell": att["summary_cells"][s["item"]]["request"],
                "approval": "WAITING",
            }
        )
    doc["report"] = {
        "report_id": REPORT_ID,
        "version": 1,
        "title": "결산조정항목 및 관련 주석(안) 보고·승인",
        "close_id": CLOSE_ID,
        "period": {
            "period_end": doc["close"]["period_end"],
            "comparative_end": doc["close"]["comparative_end"],
            "unit": "백만원",
        },
        "result_version": res["result_version"],
        "execution": {
            "run_id": run["run_id"],
            "input_version": res["input_version"],
            "executed_by": run["requested_by"],
            "executed_at": run["requested_at"],
            "execution_mode": run["execution_mode"],
            "draft_mode": res["draft"]["mode"],
        },
        "attachment": {
            k: att[k] for k in ("file_id", "file_version", "filename", "sha256", "size")
        },
        "items": items,
        "notes": {
            "DEP": res["calc"]["depreciation"]["note"]["total"],
            "ALW": res["calc"]["allowance"]["note"],
        },
        "reviews": [
            {
                "item": r["item"],
                "review_id": r["review_id"],
                "reviewed_by": r["reviewed_by"],
                "reviewed_at": r["reviewed_at"],
                "carried_from": r["carried_from"],
            }
            for r in reviews
        ],
        "prepared_by": by,
        "submitted_by": by,
        "submitted_via": args.get("answered_via"),
        "submitted_at": doc["clock"],
        "recipient": doc["close"]["reviewer"],
        "state": "SUBMITTED",
        "approvals": {"done": 0, "of": len(items)},
        "note": "승인안에는 팀장의 판단을 지시하는 문구를 넣지 않는다 — 승인·보완 요청은 장면 3",
    }
    doc["handoff"] = {
        "handoff_id": HANDOFF_ID,
        "close_id": CLOSE_ID,
        "report_id": REPORT_ID,
        "report_version": 1,
        "items": [
            {
                k: i[k]
                for k in ("item_id", "work_id", "name", "request", "request_label", "approval")
            }
            for i in items
        ],
        "summary_ref": f"{REPORT_ID} v1 승인 요약",
        "attachment_ref": att["file_id"],
        "result_version": res["result_version"],
        "run_id": run["run_id"],
        "executed_by": run["requested_by"],
        "reviewed_by": sorted({r["reviewed_by"] for r in reviews}),
        "submitted_at": doc["clock"],
        "recipient_task": f"{doc['close']['reviewer']['name']} 승인 대기 — {REPORT_ID}",
        "next_step": "장면 3 — 회계팀장이 같은 보고 건을 열어 승인 또는 보완 요청",
        "follow_up": "전표 반영·주석 취합은 승인 후 인계 예정",
        "handed_at": doc["clock"],
    }
    doc["bpm"]["waiting"] = []
    audit(
        doc, actor=by, action="report_submitted", report_id=REPORT_ID, result=res["result_version"]
    )
    return {
        "report_id": REPORT_ID,
        "report_version": 1,
        "handoff_id": HANDOFF_ID,
        "error_message": None,
    }


def _close_of(args: dict[str, Any]) -> None:
    close = args.get("close_id")
    if close is not None and close != CLOSE_ID:
        raise DomainError(f"이 데모 실행의 결산 건은 {CLOSE_ID}다: {close}", 404)


NODE_OF = {
    "open_close_analysis": "Task_Open",
    "process_close_analysis": "Task_Process",
    "attach_close_workpaper": "Task_Attach",
    "route_close_review": "Task_Route",
}


def _nodes(operation: str, args: dict[str, Any], out: dict[str, Any]) -> list[str]:
    """그 작업으로 지나온 노드 — 결재 노드는 일감이 없어 그 기록이 오면 지나온 것이다."""
    if operation == "request_close_analysis":
        return ["Request_Analysis", "Record_Request"]
    if operation == "review_close_item":
        it = str(args.get("item") or "")
        return [REVIEW_NODE.get(it, ""), RECORD_REVIEW_NODE.get(it, "")]
    if operation == "submit_close_report":
        return ["Submit_Report", "Record_Submit", "End"]
    nodes = [NODE_OF[operation]]
    if operation == "process_close_analysis":
        nodes.append("Gw_Run")
    if operation == "attach_close_workpaper":
        nodes.append("Gw_Attach")
    if operation == "route_close_review":
        nodes.append("Gw_Next")
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


class S3Sc02Process:
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
        self.processes: dict[str, Any] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock(self, demo_run_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(demo_run_id, threading.Lock())

    def _load(self, demo_run_id: str) -> tuple[dict, int]:
        found = self.store.load(demo_run_id)
        if found is None:
            raise DomainError(f"시나리오 3 장면 2를 열지 않은 데모 실행: {demo_run_id}", 404)
        return found

    def get(self, demo_run_id: str) -> dict:
        return self._load(demo_run_id)[0]

    def master(self) -> dict:
        return self.company.s3_master()

    def _write_records(self, doc: dict) -> None:
        from app.s3.sc02.records import records_of

        records.write(self.company, doc, SCENE, records_of(doc))

    def _commit(self, doc: dict, version: int, event: str) -> dict:
        self._write_records(doc)
        try:
            self.store.save(doc["demo_run_id"], doc, version, event)
        except StaleWrite as exc:
            raise DomainError("다른 요청이 먼저 바꿨다 — 다시 하라", 409) from exc
        self.publish(f"s3sc02:{doc['demo_run_id']}")
        return doc

    def _fault(self, demo_run_id: str) -> Callable[[str], bool]:
        return lambda kind: bool(self.company.take_close_fault(demo_run_id, kind)["fault"])

    # ───────────── 열기·초기화·거두기 ─────────────

    def _new(self, demo_run_id: str, *, case_id: str, executor: str, world_generation: int | None):
        sc01_doc = self.sc01.get(demo_run_id)
        doc = new_doc(
            demo_run_id,
            sc01_doc,
            self.master(),
            case_id=case_id,
            executor=executor,
            world_generation=world_generation
            if world_generation is not None
            else sc01_doc.get("world_generation"),
        )
        doc["clock"] = self.company.world(demo_run_id)["clock"]
        doc["company_log"].append(
            {
                "at": doc["clock"],
                "direction": "in",
                "what": (
                    f"장면 1 인계 {ENTRY_HANDOFF} — 입력 {doc['entry']['input_version']} 준비 2/2"
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
        장면 2 열기 — 장면 1 인계가 유효해야 한다(아니면 409). Center 실행이면 기동한다. 이미 있으면
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
        self.publish(f"s3sc02:{demo_run_id}")
        return doc

    def reset(
        self,
        demo_run_id: str,
        *,
        actor: str = "u-demo",
        case_id: str | None = None,
        executor: str | None = None,
    ) -> dict:
        """장면 2만 처음으로 — Center 작업을 거두고 다시 연다(기간계 첨부는 사이트가 비운다)."""
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
        장면 1이 새 입력을 들인 뒤 — 지금 결과가 낡았는지 다시 보고 체크리스트에 「재계산 필요」를
        남긴다(검토·상신은 그 자리에서 409로 막힌다). 상신한 뒤의 변경은 장면 3의 보완 요청 몫이다.
        """
        if self.store.load(demo_run_id) is None:
            return None
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            res = latest_result(doc)
            if res is None or doc["report"] is not None:
                return doc
            stale = is_stale(res, self.sc01.get(demo_run_id))
            new = (
                None
                if stale is None
                else {"result_version": res["result_version"], "reason": stale}
            )
            if new == doc["stale"]:
                return doc
            doc["stale"] = new
            audit(doc, actor="system", action="result_stale", result=res["result_version"])
            return self._commit(doc, version, "inputs")

    # ───────────── Center ─────────────

    def _center_key(self, doc: dict) -> str:
        return f"s3sc02:{doc['demo_run_id']}:e{doc['center_epoch']}"

    def _start_job(self, doc: dict) -> None:
        bpm = doc["bpm"]
        problem = self.center.config.missing(integration=True)
        if problem:
            bpm["problem"] = f"{problem} — 장면 2를 기동하지 않았다. Center에서 직접 기동하라"
            return
        try:
            job = self.center.start_job(
                {"데모실행ID": doc["demo_run_id"], "결산건ID": CLOSE_ID},
                idempotency_key=self._center_key(doc),
                on_behalf=ON_BEHALF,
                package=self.center.config.s3_sc02_package,
                note="NowView S3 SC02 — 결산조정 계산 및 담당자 검토",
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
        """일감 전에 실패한 실행의 사유를 남긴다(장면 1과 같다)."""
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
            out = self._run_operation(doc, operation, args, sc01_doc, master)
            bpm = doc["bpm"]
            for nid in _nodes(operation, args, out):
                if nid and nid not in bpm["visited"]:
                    bpm["visited"].append(nid)
            if operation == "submit_close_report":
                bpm.update(state="done", waiting=[])
            self._commit(doc, version, operation)
        return out

    def _run_operation(
        self, doc: dict, operation: str, args: dict[str, Any], sc01_doc: dict, master: dict
    ) -> dict[str, Any]:
        rid = doc["demo_run_id"]
        if operation == "open_close_analysis":
            return open_scene(doc)
        if operation == "request_close_analysis":
            return request(doc, args, sc01_doc)
        if operation == "process_close_analysis":
            run = _run(doc, str(args.get("run_id") or ""))
            full = self.company.close_input(rid, run["input_version"], run["input_digest"])
            return process_run(doc, run["run_id"], full, master, self._fault(rid))
        if operation == "attach_close_workpaper":
            run = _run(doc, str(args.get("run_id") or ""))
            full = self.company.close_input(rid, run["input_version"], run["input_digest"])
            return attach(
                doc,
                run["run_id"],
                full["sheets"]["전이율원천"],
                self._fault(rid),
                lambda body: self.company.put_close_attachment(rid, body),
                lambda file_id: base64.b64decode(
                    self.company.close_attachment(rid, file_id)["content_b64"]
                ),
            )
        if operation == "route_close_review":
            return route(doc, sc01_doc)
        if operation == "review_close_item":
            return review(doc, args, sc01_doc)
        return submit(doc, args, sc01_doc)

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
                f"이 결산 건 장면 2는 이미 다른 실행({bpm['external_run_id']})이 처리한다", 409
            )


__all__ = ["CASES", "OPERATIONS", "S3Sc02Process", "WORK", "entry"]
