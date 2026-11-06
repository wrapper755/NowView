"""
시나리오 3 장면 1 실행 — 결산조정 업무 착수(업무설계표 01~06, `docs/s3/sc01.md`).

* **결산 건 하나 = BPM 실행 하나**(`processes/s3-sc01.bpmn`, Center 서버 실행). 회차를 만들면 선행
  업무(입력 IN-26-01 연결·두 조정항목 배정)가 끝난 상태다 — 세계 따라가기가 이 문서를 만들고
  `company1.s3.sc01`을 기동한다(입력 `데모실행ID`·`결산건ID`).
* **그림은 순서만 쥔다** — 자료 연결 확인 → 다음 점검 항목 고르기(`route_close_items`, 이 모듈의
  규칙) → 회계담당자의 「점검 실행」(결재 둘 — 감가상각비·대손충당금) → 점검 기록
  (`check_close_item`, 규칙 점검 `calc`) → 다시 고르기. 보완 필요 항목만 남으면 메시지
  「결산자료보완」을 기다리고, 둘 다 준비 완료면 장면 2에 넘긴다.
* **입력은 회사 시스템의 것이다** — 결산 건에 연결된 입력 버전(기간계 `close-inputs`)을 읽기만 한다.
  자료 담당자가 다시 연결하면 세계 따라가기가 `receive_inputs`로 넘기고, 그 항목이 쓰는 입력이 바뀐
  항목만 재점검 대상이 된다. 보완을 기다리는 실행은 메시지로 깨우고, 이미 인계한 결산 건이면 재점검
  실행을 새로 기동한다(앞 실행은 `bpm_history`).
* **점검은 그때의 최신 버전으로만 한다** — 담당자가 본 입력 버전(폼의 「본 입력 버전」)이 지금과
  다르면 409로 거절해 같은 점검으로 되돌린다. 옛 점검 응답의 재전송이 새 자료 상태를 덮지 않는다
  (인수시험 07). 같은 버전의 같은 점검을 다시 보내면 기존 결과를 돌려준다.
* **승인·상신을 만들지 않는다** — 담당자의 점검은 원업무의 할 일이지 결재가 아니다. 장면 1 끝은
  준비 2/2 · 승인 0/2 · 상신 0건이다. 분석 실행·Excel 생성은 장면 2다.
* 경영 기록은 저장 직전에 회사에 적는다(`app/records.py`). 시나리오 3 회차라 장면 접두를 붙이지
  않는다.
"""

from __future__ import annotations

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
from app.s3.sc01 import calc
from app.sc01.center import CenterClient, CenterConfig, CenterError
from app.sc01.domain import DomainError, parse_at
from app.sc01.store import Sc01Store, StaleWrite

PROCESS_PATH = Path(__file__).resolve().parents[3] / "processes" / "s3-sc01.bpmn"
SCENARIO = "s3"
SCENE = 1
#: NowView 업무 번호 — 시나리오 3 장면 N은 30 + N(`docs/platform.md` §7)
WORK = 31
CLOSE_ID = "S3-CLOSE-01"
HANDOFF_ID = "HAND-S3-01"
OPERATIONS = ("link_close_inputs", "route_close_items", "check_close_item", "hand_off_close_items")
CASES = ("BASE",)
#: Center 기동·메시지의 대리인 — 결산 건은 회사 업무 배정에서 오고 NowView 일꾼이 기동한다
ON_BEHALF = "시스템 자동처리"
MESSAGE = "결산자료보완"
WAIT_NODE = "Wait_Fix"
CHECK_NODE = {"DEP": "Check_Depreciation", "ALW": "Check_Allowance"}
RECORD_NODE = {"DEP": "Record_Depreciation", "ALW": "Record_Allowance"}
DECISION = "점검 실행"
#: 다음 — 그림의 분기(`Gw_Next`)
NEXT_DEP, NEXT_ALW, NEXT_WAIT, NEXT_DONE = "DEP", "ALW", "WAIT", "DONE"
STATE_LABEL = {
    "ASSIGNED": "배정 · 점검 전",
    "READY": "분석 준비 완료",
    "NEEDS_FIX": "보완 필요",
    "RECHECK": "재점검 필요",
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
        "reason": "착수",
    }


def new_doc(
    demo_run_id: str,
    master: dict[str, Any],
    *,
    case_id: str,
    executor: str,
    world_generation: int | None,
) -> dict[str, Any]:
    if case_id not in CASES:
        raise DomainError(f"모르는 사례: {case_id} (가능: {', '.join(CASES)})", 422)
    if executor not in ("center", "studio"):
        raise DomainError("실행 위치는 center·studio다 — 내장 실행은 쓰지 않는다", 422)
    close = master["close"]
    items = {}
    for it in close["items"]:
        items[it["item_id"]] = {
            **{k: it[k] for k in ("item_id", "work_id", "name", "owner_role", "owner_name")},
            "owner_id": it["owner_id"],
            "sheets": list(it["sheets"]),
            "follow_up": list(it["follow_up"]),
            "due": close["schedule"]["submit_due"],
            "state": "ASSIGNED",
            "started_at": None,
            "checked_version": None,
            "checked_fingerprint": None,
            "last_check": None,
            "checks": [],
            "fix": None,
            "recheck_reason": None,
        }
    return {
        "demo_run_id": demo_run_id,
        "scenario": SCENARIO,
        "scene": SCENE,
        "case_id": case_id,
        "executor": executor,
        #: 저장소 이력 칸(시나리오 1과 같은 저장소) — 장면 1은 각본 지점을 쓰지 않는다
        "step": "S0",
        "script_index": None,
        "clock": "",
        "created_at": _now(),
        "world_generation": world_generation,
        #: 문서를 새로 만들 때마다 다른 값 — Center 멱등 키에 넣는다
        "center_epoch": uuid.uuid4().hex[:8],
        "close": {
            **{k: close[k] for k in ("close_id", "title", "period_end", "comparative_end")},
            "unit": close["unit"],
            "reviewer": close["reviewer"],
            "schedule": close["schedule"],
            "dataset_version": master["dataset_version"],
            "allowed_sheets": list(master["allowed_sheets"]),
            "excluded_sheets": list(master["excluded_sheets"]),
        },
        "inputs": [],
        "current_version": None,
        "items": items,
        "checks": [],
        "fixes": [],
        "handoff": None,
        "bpm": _new_bpm(executor),
        "bpm_history": [],
        "wait": {"message_pending": False, "attempts": 0},
        "audit": [],
        "company_log": [],
        "company_records": {},
    }


def _current(doc: dict) -> dict:
    found = next((v for v in doc["inputs"] if v["version"] == doc["current_version"]), None)
    if found is None:
        raise DomainError("결산 건에 연결된 입력이 없다 — 자료 담당자가 먼저 연결한다", 409)
    return found


def _item(doc: dict, item_id: str) -> dict:
    found = doc["items"].get(item_id)
    if found is None:
        raise DomainError(f"없는 조정항목: {item_id} (가능: {', '.join(doc['items'])})", 404)
    return found


# ─────────────────────────── 입력 버전 ───────────────────────────


def take_inputs(doc: dict, listed: list[dict], fetch: Callable[[dict], dict], master: dict) -> list:
    """
    기간계의 입력 버전 목록을 문서에 들인다 — 새 버전마다 항목별 지문을 남기고, 지문이 바뀐 항목을
    재점검 대상으로 둔다. 새로 들인 버전 목록을 돌려준다.
    """
    known = {v["version"]: v for v in doc["inputs"]}
    new = []
    for summary in sorted(listed, key=lambda s: s["seq"]):
        if summary["version"] in known and known[summary["version"]]["digest"] == summary["digest"]:
            continue
        full = fetch(summary)
        prints = {it: calc.item_fingerprint(full, master, it) for it in calc.ITEMS}
        entry = {
            **{k: summary[k] for k in ("version", "seq", "registered_at", "variants", "digest")},
            "changed_sheets": list(summary["changed_sheets"]),
            "fingerprints": prints,
            "linked_at": doc["clock"],
            "affected": [],
        }
        doc["inputs"] = [v for v in doc["inputs"] if v["version"] != entry["version"]]
        doc["inputs"].append(entry)
        doc["current_version"] = entry["version"]
        doc["company_log"].append(
            {
                "at": doc["clock"],
                "direction": "in",
                "what": f"입력 {entry['version']} 연결 읽기 — 시트 "
                + (", ".join(entry["changed_sheets"]) or "변경 없음"),
            }
        )
        for it, item in doc["items"].items():
            if item["checked_fingerprint"] is None or item["checked_fingerprint"] == prints[it]:
                continue
            entry["affected"].append(it)
            item.update(
                state="RECHECK",
                recheck_reason=f"입력 {entry['version']}에서 이 항목의 자료가 바뀌었다 — "
                f"이전 점검({item['checked_version']}) 결과는 이력으로 남는다",
            )
            if doc["handoff"] is not None:
                doc["handoff"]["valid"] = False
            audit(doc, actor="Y01", action="recheck_required", item=it, version=entry["version"])
        new.append(entry)
    return new


def link_inputs(doc: dict) -> dict[str, Any]:
    """03 자료 연결 확인 — 지금 연결된 입력 버전(들이는 것은 프로세스가 앞서 한다)."""
    v = _current(doc)
    audit(doc, actor="Y01", action="inputs_linked", version=v["version"])
    return {"input_version": v["version"], "items": len(doc["items"])}


def _counts(doc: dict) -> tuple[int, int]:
    states = [i["state"] for i in doc["items"].values()]
    return states.count("READY"), states.count("NEEDS_FIX")


def route(doc: dict) -> dict[str, Any]:
    """
    다음 점검 항목 — 지금 입력으로 점검하지 않은 항목이 있으면 그것(감가상각비 먼저), 없고 둘 다
    준비 완료면 인계, 보완 필요만 남으면 보완 대기. 보완을 기다리는 항목 때문에 다른 항목의 점검을
    막지 않는다(인수시험 03 「충당금 정상 점검 가능」).
    """
    v = _current(doc)
    todo = [
        it for it in calc.ITEMS if doc["items"][it]["checked_fingerprint"] != v["fingerprints"][it]
    ]
    ready, fix = _counts(doc)
    if todo:
        nxt = todo[0]
        doc["bpm"]["waiting"] = [
            {"node_id": CHECK_NODE[nxt], "title": f"{doc['items'][nxt]['name']} 입력자료 점검"}
        ]
        reason = f"{doc['items'][nxt]['name']} 점검 차례 — 입력 {v['version']}"
    elif ready == len(doc["items"]):
        nxt, reason = NEXT_DONE, "두 항목 분석 준비 완료"
        doc["bpm"]["waiting"] = []
    else:
        nxt = NEXT_WAIT
        names = [i["name"] for i in doc["items"].values() if i["state"] == "NEEDS_FIX"]
        reason = f"보완 대기 — {', '.join(names)}"
        doc["bpm"]["waiting"] = [{"node_id": WAIT_NODE, "title": "자료 보완 대기"}]
    return {
        "next": nxt,
        "input_version": v["version"],
        "ready": ready,
        "needs_fix": fix,
        "reason": reason,
    }


def _fix_summary(c: dict) -> dict[str, Any]:
    keys = ("check_id", "label", "sheet", "ref", "expected", "actual", "owner_role", "reason")
    return {k: c[k] for k in keys}


def check(doc: dict, args: dict[str, Any], full: dict, master: dict) -> dict[str, Any]:
    """
    04·05 점검 기록 — 담당자(배정된 회계담당자)만, 지금 입력 버전으로만. 모든 필수 점검이 통과하면
    분석 준비 완료, 아니면 보완 필요와 보완 요청(대상·기대값·확인값·담당·기한). 같은 버전·같은
    입력의 같은 점검은 기존 결과다.
    """
    item_id = str(args.get("item") or "")
    item = _item(doc, item_id)
    by = str(args.get("answered_by") or "")
    if by != item["owner_name"]:
        raise DomainError(
            f"{item['name']} 점검은 배정 담당({item['owner_name']})만 한다 — {by or '이름 없음'}",
            403,
        )
    if str(args.get("decision") or "") != DECISION:
        raise DomainError(f"점검 결정은 「{DECISION}」이다", 422)
    v = _current(doc)
    seen = str(args.get("version") or "")
    if seen != v["version"]:
        raise DomainError(
            f"본 입력 버전({seen or '없음'})이 최신({v['version']})이 아니다 — 최신 버전으로 다시 "
            "점검한다(이전 버전의 점검은 새 자료 상태를 덮지 않는다)",
            409,
        )
    last = item["last_check"]
    if item["checked_fingerprint"] == v["fingerprints"][item_id] and last is not None:
        prior = next(c for c in doc["checks"] if c["check_id"] == last)
        return {"result": prior["result"], "check_id": last, "error_message": None}
    found = calc.check_item(full, master, item_id)
    result = calc.verdict(found)
    n = len(item["checks"]) + 1
    check_id = f"CHK-{item_id}-{n}"
    record = {
        "check_id": check_id,
        "item": item_id,
        "work_id": item["work_id"],
        "version": v["version"],
        "fingerprint": v["fingerprints"][item_id],
        "rule_version": calc.RULE_VERSION,
        "checked_at": doc["clock"],
        "checked_by": by,
        "via": args.get("answered_via"),
        "execution_mode": "rule",
        "result": result,
        "checks": found,
        "evidence": calc.evidence(full, item_id),
        "fix_id": None,
    }
    for f in doc["fixes"]:
        if f["item"] == item_id and f["state"] == "OPEN":
            f.update(
                state="RESOLVED" if result == calc.READY else "SUPERSEDED",
                closed_at=doc["clock"],
                closed_by_version=v["version"],
                closed_by_check=check_id,
            )
    if result == calc.NEEDS_FIX:
        failing = [_fix_summary(c) for c in found if c["verdict"] == "FAIL"]
        fix = {
            "fix_id": f"FIX-S3-{len(doc['fixes']) + 1:02d}",
            "item": item_id,
            "work_id": item["work_id"],
            "version": v["version"],
            "check_id": check_id,
            "raised_at": doc["clock"],
            "raised_by": by,
            "owners": sorted({c["owner_role"] for c in failing}),
            "due": calc.next_business_day_18(doc["clock"]),
            "findings": failing,
            "state": "OPEN",
            "closed_at": None,
            "closed_by_version": None,
            "closed_by_check": None,
            "note": "누락·불일치는 0이나 추정액으로 채우지 않는다 — 보완 후 재점검",
        }
        doc["fixes"].append(fix)
        record["fix_id"] = fix["fix_id"]
    doc["checks"].append(record)
    item["checks"].append(check_id)
    item.update(
        state=result,
        started_at=item["started_at"] or doc["clock"],
        checked_version=v["version"],
        checked_fingerprint=v["fingerprints"][item_id],
        last_check=check_id,
        fix=record["fix_id"],
        recheck_reason=None,
    )
    doc["bpm"]["waiting"] = []
    audit(doc, actor=by, action="item_checked", item=item_id, check_id=check_id, result=result)
    return {"result": result, "check_id": check_id, "error_message": None}


def hand_off(doc: dict) -> dict[str, Any]:
    """
    06 장면 2 인계 — 두 항목이 지금 입력으로 준비 완료여야 한다. 같은 입력으로 다시 오면 같은 인계.
    """
    v = _current(doc)
    blocked = [
        i["name"]
        for i in doc["items"].values()
        if i["state"] != "READY"
        or i["checked_version"] is None
        or i["checked_fingerprint"] != v["fingerprints"][i["item_id"]]
    ]
    if blocked:
        raise DomainError(f"분석 준비 전 항목이 있다 — {', '.join(blocked)}", 409)
    h = doc["handoff"]
    if h is not None and h["input_version"] == v["version"] and h.get("valid", True):
        return {"handoff_id": HANDOFF_ID, "next_step": h["next_step"]}
    checks = {c["check_id"]: c for c in doc["checks"]}
    items = []
    for i in doc["items"].values():
        c = checks[i["last_check"]]
        refs = sorted({x["ref"] for x in c["checks"] if x["ref"]})
        items.append(
            {
                "item_id": i["item_id"],
                "work_id": i["work_id"],
                "name": i["name"],
                "owner_role": i["owner_role"],
                "owner_name": i["owner_name"],
                "state": "READY",
                "check_id": c["check_id"],
                "checked_at": c["checked_at"],
                "checked_by": c["checked_by"],
                "verdicts": [
                    {"check_id": x["check_id"], "verdict": x["verdict"], "ref": x["ref"]}
                    for x in c["checks"]
                ],
                "evidence_refs": refs,
                "next_action": next_action(i),
            }
        )
    doc["handoff"] = {
        "handoff_id": HANDOFF_ID,
        "close_id": CLOSE_ID,
        "period_end": doc["close"]["period_end"],
        "comparative_end": doc["close"]["comparative_end"],
        "input_version": v["version"],
        "allowed_sheets": doc["close"]["allowed_sheets"],
        "excluded_sheets": doc["close"]["excluded_sheets"],
        "items": items,
        "ready": len(items),
        "approvals": 0,
        "reports": 0,
        "next_step": "장면 2 — 대손충당금 [분석 지시 보기]",
        "scene2_entry": "준비·배정 권한·최신 입력 버전을 서버가 다시 확인한 뒤 분석 지시를 연다",
        "follow_up": "전표 반영·주석 취합은 승인 후 인계 예정",
        "handed_at": doc["clock"],
        "valid": True,
    }
    audit(doc, actor="Y01", action="handed_off", handoff_id=HANDOFF_ID, version=v["version"])
    return {"handoff_id": HANDOFF_ID, "next_step": doc["handoff"]["next_step"]}


def next_action(item: dict) -> str:
    """체크리스트 행의 다음 조치(화면 03)."""
    if item["state"] == "READY":
        return "분석 지시 보기" if item["item_id"] == "ALW" else "자산대장 점검 결과 보기"
    if item["state"] == "NEEDS_FIX":
        return "보완 근거 보기"
    if item["state"] == "RECHECK":
        return "재점검"
    return "자료 점검"


def _close_of(args: dict[str, Any]) -> None:
    close = args.get("close_id")
    if close is not None and close != CLOSE_ID:
        raise DomainError(f"이 데모 실행의 결산 건은 {CLOSE_ID}다: {close}", 404)


def run_operation(
    doc: dict, operation: str, args: dict[str, Any], master: dict, full: Callable[[], dict]
) -> dict[str, Any]:
    """일감 하나 — 점검은 지금 입력 버전의 시트 전부(`full`)를 읽는다."""
    _close_of(args)
    if operation == "link_close_inputs":
        return link_inputs(doc)
    if operation == "route_close_items":
        return route(doc)
    if operation == "check_close_item":
        return check(doc, args, full(), master)
    if operation == "hand_off_close_items":
        return hand_off(doc)
    raise DomainError(f"모르는 작업: {operation} (가능: {', '.join(OPERATIONS)})", 404)


NODE_OF = {
    "link_close_inputs": "Task_Link",
    "route_close_items": "Task_Route",
    "hand_off_close_items": "Task_Handoff",
}


def _nodes(operation: str, args: dict[str, Any], out: dict[str, Any]) -> list[str]:
    """그 작업으로 지나온 노드 — 결재 노드는 일감이 없어 그 기록이 오면 지나온 것이다."""
    if operation == "check_close_item":
        it = str(args.get("item") or "")
        return [CHECK_NODE.get(it, ""), RECORD_NODE.get(it, "")]
    nodes = [NODE_OF[operation]]
    if operation == "route_close_items":
        nodes.append("Gw_Next")
        if out["next"] == NEXT_WAIT:
            nodes.append(WAIT_NODE)
    if operation == "hand_off_close_items":
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


class S3Sc01Process:
    def __init__(
        self,
        store: Sc01Store,
        *,
        company: CompanyClient,
        center: CenterClient | None = None,
        publish: Callable[[str], None] = lambda _id: None,
    ) -> None:
        self.store = store
        self.company = company
        self.center = center or CenterClient(CenterConfig())
        self.publish = publish
        self.process = read_process(PROCESS_PATH.read_bytes())
        #: 호출 활동이 없다 — 공통 BPM을 부르지 않는다(`docs/s3/common.md`)
        self.processes: dict[str, Any] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock(self, demo_run_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(demo_run_id, threading.Lock())

    def _load(self, demo_run_id: str) -> tuple[dict, int]:
        found = self.store.load(demo_run_id)
        if found is None:
            raise DomainError(f"시나리오 3 장면 1을 열지 않은 데모 실행: {demo_run_id}", 404)
        return found

    def get(self, demo_run_id: str) -> dict:
        return self._load(demo_run_id)[0]

    def master(self) -> dict:
        return self.company.s3_master()

    def _full(self, doc: dict) -> dict:
        v = _current(doc)
        return self.company.close_input(doc["demo_run_id"], v["version"], v["digest"])

    def _take(self, doc: dict) -> list:
        """기간계의 입력 버전 목록을 문서에 들인다."""
        rid = doc["demo_run_id"]
        return take_inputs(
            doc,
            self.company.close_inputs(rid),
            lambda s: self.company.close_input(rid, s["version"], s["digest"]),
            self.master(),
        )

    def _write_records(self, doc: dict) -> None:
        from app.s3.sc01.records import records_of

        records.write(self.company, doc, SCENE, records_of(doc))

    def _commit(self, doc: dict, version: int, event: str) -> dict:
        self._write_records(doc)
        try:
            self.store.save(doc["demo_run_id"], doc, version, event)
        except StaleWrite as exc:
            raise DomainError("다른 요청이 먼저 바꿨다 — 다시 하라", 409) from exc
        self.publish(f"s3sc01:{doc['demo_run_id']}")
        return doc

    # ───────────── 만들기·초기화·거두기 ─────────────

    def _new(self, demo_run_id: str, *, case_id: str, executor: str, world_generation: int | None):
        self.company.ensure_world(demo_run_id, SCENARIO)
        doc = new_doc(
            demo_run_id,
            self.master(),
            case_id=case_id,
            executor=executor,
            world_generation=world_generation,
        )
        doc["clock"] = self.company.world(demo_run_id)["clock"]
        self._take(doc)
        records.restart(self.company, doc, SCENE)
        return doc

    def create(
        self,
        demo_run_id: str | None = None,
        *,
        case_id: str = "BASE",
        executor: str = "center",
        world_generation: int | None = None,
    ) -> dict:
        """
        결산 건을 연다 — 배정된 두 원업무와 연결된 입력을 들이고, Center 실행이면 기동한다. 이미
        있으면 그대로 돌려준다(재진입은 같은 업무다 — 인수시험 01).
        """
        rid = demo_run_id or f"demo-{uuid.uuid4().hex[:8]}"
        with self._lock(rid):
            found = self.store.load(rid)
            if found is not None:
                return found[0]
            doc = self._new(
                rid, case_id=case_id, executor=executor, world_generation=world_generation
            )
            audit(doc, actor="system", action="close_opened", close_id=CLOSE_ID)
            if executor == "center":
                self._start_job(doc)
            self._write_records(doc)
            self.store.insert(rid, doc)
        self.publish(f"s3sc01:{rid}")
        return doc

    def reset(
        self,
        demo_run_id: str,
        *,
        actor: str = "u-demo",
        case_id: str | None = None,
        executor: str | None = None,
        world_generation: int | None = None,
    ) -> dict:
        """
        처음으로 — 기동한 Center 작업을 거두고 이 장면 기록을 처음부터. 세계 초기화를 따라간다.
        """
        with self._lock(demo_run_id):
            old, version = self._load(demo_run_id)
            self._cancel_job(old)
            doc = self._new(
                demo_run_id,
                case_id=case_id or old["case_id"],
                executor=executor or old["executor"],
                world_generation=world_generation or old.get("world_generation"),
            )
            audit(doc, actor=actor, action="demo_run_reset")
            if doc["executor"] == "center":
                self._start_job(doc)
            self._write_records(doc)
            try:
                self.store.save(demo_run_id, doc, version, "reset")
            except StaleWrite as exc:
                raise DomainError("다른 요청이 먼저 바꿨다 — 다시 하라", 409) from exc
        self.publish(f"s3sc01:{demo_run_id}")
        return doc

    def discard(self, demo_run_id: str) -> None:
        """세계가 지워졌다 — 기동한 Center 작업을 거두고 문서를 지운다."""
        found = self.store.load(demo_run_id)
        if found is not None:
            self._cancel_job(found[0])
        self.store.delete(demo_run_id)

    def follow_clock(self, demo_run_id: str, at: str) -> dict:
        """세계 시각을 따라간다 — 잔여일·기한 경과가 같이 간다(조회만, 점검을 다시 하지 않는다)."""
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if doc["clock"] and parse_at(at) <= parse_at(doc["clock"]):
                return doc
            doc["clock"] = at
            return self._commit(doc, version, "clock")

    # ───────────── 입력 다시 연결 ─────────────

    def receive_inputs(self, demo_run_id: str) -> dict | None:
        """
        세계 따라가기가 기간계의 새 입력 버전을 넘긴다 — 들이고, 그 항목이 쓰는 자료가 바뀐 항목을
        재점검 대상으로 둔다. 실행이 보완을 기다리면 메시지로 깨우고, 이미 인계했고 재점검 대상이
        생겼으면 재점검 실행을 기동한다.
        """
        if self.store.load(demo_run_id) is None:
            return None
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            new = self._take(doc)
            if not new:
                return doc
            bpm = doc["bpm"]
            if any(w["node_id"] == WAIT_NODE for w in bpm["waiting"]):
                # Studio 시험 실행은 사람이 Studio에서 메시지를 넣는다 — 보낼 것이 없다
                doc["wait"]["message_pending"] = doc["executor"] == "center"
                self._send_message(doc)
            elif bpm["state"] in ("done", "failed") and any(
                i["state"] == "RECHECK" for i in doc["items"].values()
            ):
                self._restart_run(doc, f"입력 {doc['current_version']} 재점검")
            return self._commit(doc, version, "inputs")

    def _restart_run(self, doc: dict, reason: str) -> None:
        doc["bpm_history"].append(doc["bpm"])
        doc["bpm"] = {**_new_bpm(doc["executor"]), "reason": reason}
        doc["center_epoch"] = uuid.uuid4().hex[:8]
        audit(doc, actor="system", action="recheck_run", reason=reason)
        if doc["executor"] == "center":
            self._start_job(doc)

    def _send_message(self, doc: dict) -> None:
        """Center 실행이면 「결산자료보완」 — 받는 실행이 아직 없으면 폴러가 다시 보낸다."""
        if doc["executor"] != "center" or self.center.config.missing(integration=True):
            return
        doc["wait"]["attempts"] += 1
        try:
            self.center.send_message(
                MESSAGE,
                correlation=doc["demo_run_id"],
                payload={"입력버전": doc["current_version"]},
                idempotency_key=(
                    f"s3sc01:{doc['demo_run_id']}:e{doc['center_epoch']}:"
                    f"{doc['current_version']}:{doc['wait']['attempts']}"
                ),
                on_behalf=ON_BEHALF,
            )
        except CenterError as exc:
            log.info("보완 메시지를 넣지 못했다(%s) — 다시 보낸다: %s", doc["demo_run_id"], exc)
            return
        doc["wait"]["message_pending"] = False
        audit(doc, actor="system", action="center_message_sent", version=doc["current_version"])

    # ───────────── Center ─────────────

    def _center_key(self, doc: dict) -> str:
        return f"s3sc01:{doc['demo_run_id']}:e{doc['center_epoch']}"

    def _start_job(self, doc: dict) -> None:
        bpm = doc["bpm"]
        problem = self.center.config.missing(integration=True)
        if problem:
            bpm["problem"] = f"{problem} — 결산 건 착수를 기동하지 않았다. Center에서 직접 기동하라"
            return
        try:
            job = self.center.start_job(
                {"데모실행ID": doc["demo_run_id"], "결산건ID": CLOSE_ID},
                idempotency_key=self._center_key(doc),
                on_behalf=ON_BEHALF,
                package=self.center.config.s3_sc01_package,
                note=f"NowView S3 SC01 — 결산조정 업무 착수 ({bpm['reason']})",
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
        도는 Center 실행 — 못 넣은 보완 메시지를 다시 보내고, 일감 전에 실패한 실행의 사유를
        남긴다.
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
            if not doc["wait"]["message_pending"]:
                return 0
            self._send_message(doc)
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
        master = self.master()
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            self._link(doc, external_run_id, via)
            if operation == "link_close_inputs":
                self._take(doc)
            out = run_operation(doc, operation, args, master, lambda: self._full(doc))
            bpm = doc["bpm"]
            for nid in _nodes(operation, args, out):
                if nid and nid not in bpm["visited"]:
                    bpm["visited"].append(nid)
            if operation == "hand_off_close_items":
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
            raise DomainError(
                f"이 결산 건은 이미 다른 실행({bpm['external_run_id']})이 처리한다", 409
            )


__all__ = ["CASES", "OPERATIONS", "S3Sc01Process", "WORK", "run_operation"]
