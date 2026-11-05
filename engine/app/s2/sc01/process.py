"""
시나리오 2 장면 1 실행 — 구매 입고예정 개정을 받아 경보·Case·영향 분석을 잇고 장면 2(N03A)에 넘긴다.

* **개정 하나 = BPM 실행 하나**(`processes/s2-sc01.bpmn`, Center 서버 실행). 판정(N01)
  뒤의 Case 연결·영향 분석·인계는 **공통 BPM `platform.case-intake`**
  (`processes/case-intake.bpmn`)를 호출해 돈다 — 그 작업 셋(`link_case`·
  `analyze_case_impact`·`hand_off_case_analysis`)은 공통 이름이고, 이 업무가 제 규칙으로
  수행한다. 호출된 흐름도 같은 실행이라 일감의 BPM 프로세스 id는 바깥 패키지
  (`company1.s2.sc01`)다. 세계 따라가기가 기간계
  구매 개정
  수신함의 새 문서를 보면 `receive_inbox`가 Center에 기동한다(`POST /jobs`, 입력
  `데모실행ID`·`원천개정`). 그림의
  서비스 태스크 넷은 C15 일꾼이 가져와 `operate`를 부른다(`run_operation` — 시험도 같은 함수).
* **사람 결재가 없다.** 장면 1의 사람은 조회만 한다 — 대리 답·폴러가 필요 없다. 실행이 끝났는지는
  일감이
  알려 준다: 판정이 경보가 아니면 그림은 곧바로 「이력만 저장」 끝이고, 경보면 인계 작업 다음이
  끝이다.
* **같은 개정의 재수신은 평가하지 않는다**(구현명세 §3 Y01 ①) — 판정 `DUPLICATE`로 그림이 이력
  끝으로 간다.
  경보·Case·분석은 하나로 남는다(T05). 앞선 개정이 늦게 오면 `LATE` — 이력은 보존하고 최신값을
  되돌리지 않는다.
* **경영 기록은 저장 직전에 회사에 적는다**(`app/records.py` — 회사가 받지 못하면 그 조작은
  저장되지 않는다).
  이 회차는 시나리오 2 회차라 기록 id에 장면 접두를 붙이지 않는다(`docs/platform.md` §3).
* **생산계획을 바꾸지 않는다** — 장면 1 끝의 원계획은 그대로다(T09). 이 문서에 생산계획 칸이 없다.
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
from app.s2.sc01 import calc
from app.sc01.center import CenterClient, CenterConfig, CenterError
from app.sc01.domain import DomainError, parse_at
from app.sc01.store import Sc01Store, StaleWrite

PROCESS_PATH = Path(__file__).resolve().parents[3] / "processes" / "s2-sc01.bpmn"
#: 그림이 호출하는 공통 BPM(`docs/platform.md` §5) — 패키지의 `libs/`에 받아 둔 사본과 같은 그림
CALLED_PATHS = (Path(__file__).resolve().parents[3] / "processes" / "case-intake.bpmn",)
SCENARIO = "s2"
SCENE = 1
#: NowView 업무 번호 — 시나리오 2 장면 N은 20 + N(`docs/platform.md` §7)
WORK = 21
OPERATIONS = (
    "evaluate_receipt_change",
    # 공통 BPM `platform.case-intake`의 작업 — 이름은 공통이고 내용은 이 업무의 것이다
    "link_case",
    "analyze_case_impact",
    "hand_off_case_analysis",
)
#: 판정 — 계산(`calc`)의 넷 + 수신 처리의 둘. 경보만 Case로 간다.
DUPLICATE, LATE = "DUPLICATE", "LATE"
LABEL = {**calc.JUDGMENT_LABEL, DUPLICATE: "중복 수신", LATE: "늦게 온 개정"}
#: 사례 — 시연 회차의 `case_id`. A01-FAIL은 분석이 한 번 실패한 뒤 재시도로 성공한다(T08).
CASES = ("BASE", "A01-FAIL")
#: Center 기동의 대리인 — 개정은 구매시스템에서 오고 NowView 일꾼(Y01)이 기동한다
ON_BEHALF = "시스템 자동처리"
CASE_ID, ALERT_ID, ANALYSIS_ID, HANDOFF_ID = "CASE-S2-01", "AL-S2-01", "ANA-01", "HAND-01"

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def audit(doc: dict, *, actor: str, action: str, **detail: Any) -> None:
    doc["audit"].append({"at": doc["clock"], "actor": actor, "action": action, **detail})


def new_doc(
    demo_run_id: str, *, case_id: str, executor: str, world_generation: int | None
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
        #: 저장소 이력 칸(시나리오 1과 같은 저장소) — 장면 1은 각본 지점을 쓰지 않는다
        "step": "S0",
        "script_index": None,
        "clock": "",
        "created_at": _now(),
        "world_generation": world_generation,
        #: 문서를 새로 만들 때마다 다른 값 — Center 멱등 키에 넣는다(시나리오 1의 함정과 같다)
        "center_epoch": uuid.uuid4().hex[:8],
        "receipts": {},
        "events": {},
        "series": {},
        "alert": None,
        "case": None,
        "analyses": [],
        "attempts": [],
        "handoff": None,
        "audit": [],
        "company_log": [],
        "company_records": {},
    }


# ─────────────────────────── 작업 (일꾼·시험이 같은 함수) ───────────────────────────


def _receipt(doc: dict, doc_id: str) -> dict:
    found = doc["receipts"].get(doc_id)
    if found is None or found.get("source") is None:
        raise DomainError(f"들이지 않은 구매 개정: {doc_id}", 404)
    return found


def _event_of(doc: dict, doc_id: str) -> dict:
    rid = _receipt(doc, doc_id).get("revision_id")
    event = doc["events"].get(rid or "")
    if event is None or event.get("doc_id") != doc_id:
        raise DomainError(f"판정하지 않은 개정: {doc_id}", 409)
    return event


def _event_id(doc: dict, po_line: str, revision_no: int) -> str:
    """
    원천 사건 id — 발주행마다 계열 번호(`EV-S2-01`)·개정 번호(`R2`). 수정 수신은 새
    revision이다(F09).
    """
    series = doc["series"].setdefault(po_line, f"EV-S2-{len(doc['series']) + 1:02d}")
    return f"{series}-R{revision_no}"


def evaluate(doc: dict, doc_id: str, master: dict) -> dict[str, Any]:
    """N01 — 개정 한 건을 판정한다. 재수신·늦게 온 개정은 평가하지 않는다."""
    entry = _receipt(doc, doc_id)
    source = entry["source"]
    rid = source["revision_id"]
    known = doc["events"].get(rid)
    if known is not None:
        if known["doc_id"] != doc_id:
            entry["outcome"] = DUPLICATE
            known.setdefault("redeliveries", []).append({"doc_id": doc_id, "at": doc["clock"]})
            audit(doc, actor="Y01", action="duplicate_receipt", doc_id=doc_id, revision=rid)
            return {
                "judgment": DUPLICATE,
                "reason": f"{rid} 재수신 — 기존 판정({known['judgment_label']}) 유지",
                "revision_id": rid,
                "change_count": known["change_count"],
            }
        return _evaluated(known)  # 같은 일감이 다시 왔다(최소 한 번 실행)
    same_line = [e for e in doc["events"].values() if e["po_line"] == source["po_line"]]
    latest = max((e["revision_no"] for e in same_line), default=-1)
    found = calc.evaluate(source, same_line, master)
    found.update(
        event_id=_event_id(doc, source["po_line"], int(source["revision_no"])),
        doc_id=doc_id,
        evaluated_at=doc["clock"],
        source_system="구매시스템",
        execution_mode="rule",
    )
    if int(source["revision_no"]) < latest:
        found.update(judgment=LATE, judgment_label=LABEL[LATE])
        found["reasons"] = [f"앞선 개정이 늦게 도착 — 이력만 보존, 최신값(R{latest}) 유지"]
    doc["events"][rid] = found
    entry["outcome"] = found["judgment"]
    audit(doc, actor="Y01", action="receipt_evaluated", revision=rid, judgment=found["judgment"])
    return _evaluated(found)


def _evaluated(event: dict) -> dict[str, Any]:
    return {
        "judgment": event["judgment"],
        "reason": " · ".join(event["reasons"]),
        "revision_id": event["revision_id"],
        "change_count": event["change_count"],
    }


def link_case(doc: dict, doc_id: str) -> dict[str, Any]:
    """
    N02 — 경보를 공급 대응 Case에 잇는다. 활성 Case가 있으면 새로 만들지 않고 이 개정·영향 약정만
    더한다
    (구현명세 §3 ④). 경보 발생은 경영검토 요청이나 납기 미준수 확정이 아니다.
    """
    event = _event_of(doc, doc_id)
    if event["judgment"] != calc.ALERT:
        raise DomainError(f"경보가 아닌 개정은 Case에 잇지 않는다: {event['revision_id']}", 409)
    alert, case = doc["alert"], doc["case"]
    if alert is None:
        alert = doc["alert"] = {
            "alert_id": ALERT_ID,
            "kri": "공급 입고예정 변경",
            "rule_version": event["rule_version"],
            "raised_at": doc["clock"],
            "risk_level": "RISK",
            "risk_label": "위험",
            "part_id": sorted({lot["part_id"] for lot in event["lots"]}),
            "po_line": event["po_line"],
            "events": [],
            "reasons": [],
            "case_id": CASE_ID,
            "dedupe_key": f"{event['po_line']}:{event['rule_version']}",
        }
    if case is None:
        case = doc["case"] = {
            "case_id": CASE_ID,
            "case_type": "supply",
            "case_type_label": "공급 대응",
            "title": "A제품 공급 불안과 납기 위험",
            "plant": "울산",
            "product": "A",
            "goal": "영향 납기약정의 고객 약정 준수 — 대응 경로는 장면 2 수행계획에서 정한다",
            "owner_role": "H03",
            "state": "ANALYZING",
            "opened_at": doc["clock"],
            "events": [],
            "commitments": [],
            "alert_id": ALERT_ID,
            "current_plan_version": None,
            "analysis": None,
            "next_node": "N03",
        }
    if event["event_id"] not in alert["events"]:
        alert["events"].append(event["event_id"])
        alert["reasons"] = event["reasons"]
        alert["evaluated_at"] = doc["clock"]
    if event["event_id"] not in case["events"]:
        case["events"].append(event["event_id"])
    for cid in event["affected"]:
        if cid not in case["commitments"]:
            case["commitments"].append(cid)
    event["case_id"], event["alert_id"] = CASE_ID, ALERT_ID
    audit(doc, actor="Y01", action="case_linked", case_id=CASE_ID, revision=event["revision_id"])
    return {"case_id": CASE_ID, "alert_id": ALERT_ID, "affected": len(case["commitments"])}


def _latest_alert_event(doc: dict) -> dict:
    linked = [e for e in doc["events"].values() if e.get("case_id") == CASE_ID]
    return max(linked, key=lambda e: e["revision_no"])


def must_fail(doc: dict, revision_id: str) -> bool:
    """A01-FAIL 사례 — 그 개정의 첫 분석 시도만 실패한다(재시도는 성공, T08)."""
    tried = [a for a in doc["attempts"] if a["revision_id"] == revision_id]
    return doc["case_id"] == "A01-FAIL" and not tried


def analyze(doc: dict, doc_id: str, master: dict) -> dict[str, Any]:
    """
    N03 — 영향 약정별 근거를 같은 근거 버전으로 연결한다. 입력이 같으면 새 판을 만들지
    않는다(재시도·재수신에
    분석 중복 생성 없음). 재계산은 새 판이고 이전 판은 보존한다.
    """
    _event_of(doc, doc_id)
    case = doc["case"]
    if case is None:
        raise DomainError("Case가 없다 — 경보·사건 연결 뒤에 분석한다", 409)
    event = _latest_alert_event(doc)
    if must_fail(doc, event["revision_id"]):
        raise DomainError("A01 분석 실행이 실패했다(시연 사례 A01-FAIL) — 다시 시도한다", 503)
    rows = calc.analyze(event, case["commitments"], master)
    previous = doc["analyses"][-1] if doc["analyses"] else None
    if (
        previous is not None
        and previous["revision_id"] == event["revision_id"]
        and previous["rows"] == rows
    ):
        return {
            "analysis_id": ANALYSIS_ID,
            "version": previous["version"],
            "missing": len(previous["missing"]),
        }
    first = min(
        (e for e in doc["events"].values() if e["po_line"] == event["po_line"]),
        key=lambda e: e["revision_no"],
    )
    missing = sorted({f"{r['commitment_id']}:{m}" for r in rows for m in r["missing"]})
    version = len(doc["analyses"]) + 1
    found = {
        "analysis_id": ANALYSIS_ID,
        "version": version,
        "case_id": CASE_ID,
        "revision_id": event["revision_id"],
        "event_id": event["event_id"],
        "data_as_of": event["registered_at"],
        "calculated_at": doc["clock"],
        "rule_version": event["rule_version"],
        "execution_mode": "rule",
        "actor_role": "A01",
        "rows": rows,
        "total_qty": {"first": first["total_qty"], "latest": event["total_qty"]},
        "missing": missing,
        "evidence": _evidence(event, master),
        "note": "착수 차질 = 사용 가능시각 − 기존 조립 착수시각. 고객 납기 지연시간이 아니다.",
    }
    doc["analyses"].append(found)
    doc["attempts"].append(
        {
            "revision_id": event["revision_id"],
            "at": doc["clock"],
            "state": "SUCCEEDED",
            "version": version,
        }
    )
    case.update(state="ANALYZED", analysis={"analysis_id": ANALYSIS_ID, "version": version})
    audit(
        doc, actor="A01", action="impact_analyzed", version=version, revision=event["revision_id"]
    )
    return {"analysis_id": ANALYSIS_ID, "version": version, "missing": len(missing)}


def _evidence(event: dict, master: dict) -> list[dict[str, Any]]:
    """
    근거 스냅샷(M14) — 원천 종류·키·개정·자료시각. 시스템이 수집한 자료는 자동으로 잇는다(담당자가
    다시 첨부하지
    않는다). 입고는 아직 **예정**이다.
    """
    return [
        {
            "evidence_id": f"EVD-{event['revision_id']}",
            "source": "구매 입고예정",
            "source_key": event["po_line"],
            "revision": event["revision_id"],
            "as_of": event["registered_at"],
            "kind": "예정",
            "note": "분할 입고 통지 — 실제 입고 아님",
        },
        {
            "evidence_id": "EVD-COMMITMENT",
            "source": "납기약정",
            "source_key": master["dataset_version"],
            "revision": None,
            "as_of": event["registered_at"],
            "kind": "약정",
            "note": "고객 약정시각·약정수량",
        },
        {
            "evidence_id": "EVD-PLAN",
            "source": "기존 조립계획·BOM·배정재고",
            "source_key": master["dataset_version"],
            "revision": None,
            "as_of": event["registered_at"],
            "kind": "계획",
            "note": "원계획 — 변경 미승인·미반영",
        },
        {
            "evidence_id": "EVD-SHIPMENT",
            "source": "정기차 마감",
            "source_key": master["dataset_version"],
            "revision": None,
            "as_of": event["registered_at"],
            "kind": "출하",
            "note": "운송 가능 여부는 추정해 확정하지 않는다",
        },
    ]


def hand_off(doc: dict, doc_id: str) -> dict[str, Any]:
    """
    N03 종료 — 같은 Case를 장면 2 N03A에 넘긴다. 담당자의 열람은 승인·계획 변경·통제
    종료가 아니다.
    """
    _event_of(doc, doc_id)
    case = doc["case"]
    if case is None or not doc["analyses"]:
        raise DomainError("분석이 끝나지 않았다 — 인계할 수 없다", 409)
    latest = doc["analyses"][-1]
    event = _latest_alert_event(doc)
    doc["handoff"] = {
        "handoff_id": HANDOFF_ID,
        "case_id": CASE_ID,
        "alert_id": ALERT_ID,
        "revision_id": event["revision_id"],
        "commitments": list(case["commitments"]),
        "analysis": {"analysis_id": ANALYSIS_ID, "version": latest["version"]},
        "data_as_of": latest["data_as_of"],
        "missing": latest["missing"],
        "next_node": "N03A",
        "next_label": "수행계획 구성 대기 (장면 2 · D03)",
        "production_plan": "원본 유지 — 변경 미승인·미반영",
        "approvals": 0,
        "handed_at": doc["clock"],
    }
    case["next_node"] = "N03A"
    audit(doc, actor="Y01", action="handed_off", next_node="N03A", version=latest["version"])
    return {"handoff_id": HANDOFF_ID, "next_node": "N03A"}


def run_operation(doc: dict, operation: str, args: dict[str, Any], master: dict) -> dict[str, Any]:
    doc_id = str(args.get("doc_id") or "")
    if not doc_id:
        raise DomainError("원천개정(doc_id)이 없다", 422)
    if operation == "evaluate_receipt_change":
        return evaluate(doc, doc_id, master)
    if operation == "link_case":
        return link_case(doc, doc_id)
    if operation == "analyze_case_impact":
        return analyze(doc, doc_id, master)
    if operation == "hand_off_case_analysis":
        return hand_off(doc, doc_id)
    raise DomainError(f"모르는 작업: {operation} (가능: {', '.join(OPERATIONS)})", 404)


def _center_key(doc: dict, doc_id: str) -> str:
    """Center 멱등 키 — 문서마다 다른 값(`center_epoch`) — 초기화 뒤 옛 작업이 오지 않게."""
    return f"s2sc01:{doc['demo_run_id']}:e{doc['center_epoch']}:{doc_id}"


#: 그 작업 뒤에 흐름이 끝나는가 — 판정이 경보가 아니면 「이력만 저장」,
#: 공통 BPM의 인계 다음은 바깥 끝
def ends_flow(operation: str, out: dict[str, Any]) -> str | None:
    if operation == "evaluate_receipt_change" and out.get("judgment") != calc.ALERT:
        return "End_Recorded"
    if operation == "hand_off_case_analysis":
        return "End"
    return None


NODE_OF = {
    "evaluate_receipt_change": "Task_Evaluate",
    # 아래 셋은 공통 BPM 안의 노드다(호출 활동 `Call_CaseIntake` 안쪽)
    "link_case": "Task_Link",
    "analyze_case_impact": "Task_Analyze",
    "hand_off_case_analysis": "Task_Handoff",
}


# ─────────────────────────── 프로세스 ───────────────────────────


class S2Sc01Process:
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
        #: 호출 활동이 찾을 정의(`RunEnv.processes`) — 서버 실행기가 패키지 `libs/`에서
        #: 읽는 것과 같다
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
            raise DomainError(f"시나리오 2 장면 1을 열지 않은 데모 실행: {demo_run_id}", 404)
        return found

    def get(self, demo_run_id: str) -> dict:
        return self._load(demo_run_id)[0]

    def master(self) -> dict:
        return self.company.s2_master()

    def _write_records(self, doc: dict) -> None:
        from app.s2.sc01.records import records_of

        records.write(self.company, doc, SCENE, records_of(doc, self.master()))

    def _commit(self, doc: dict, version: int, event: str) -> dict:
        self._write_records(doc)
        try:
            self.store.save(doc["demo_run_id"], doc, version, event)
        except StaleWrite as exc:
            raise DomainError("다른 요청이 먼저 바꿨다 — 다시 하라", 409) from exc
        self.publish(f"s2sc01:{doc['demo_run_id']}")
        return doc

    # ───────────── 만들기·초기화·거두기 ─────────────

    def _new(self, demo_run_id: str, *, case_id: str, executor: str, world_generation: int | None):
        doc = new_doc(
            demo_run_id, case_id=case_id, executor=executor, world_generation=world_generation
        )
        self.company.ensure_world(demo_run_id, SCENARIO)
        doc["clock"] = self.company.world(demo_run_id)["clock"]
        self.master()  # 회사 자료를 읽을 수 있어야 연다(503이면 만들지 않는다)
        records.restart(self.company, doc, SCENE)
        self._write_records(doc)
        return doc

    def create(
        self,
        demo_run_id: str | None = None,
        *,
        case_id: str = "BASE",
        executor: str = "center",
        world_generation: int | None = None,
    ) -> dict:
        rid = demo_run_id or f"demo-{uuid.uuid4().hex[:8]}"
        with self._lock(rid):
            if self.store.load(rid) is not None:
                raise DomainError(f"이미 있는 데모 실행: {rid}", 409)
            doc = self._new(
                rid, case_id=case_id, executor=executor, world_generation=world_generation
            )
            audit(doc, actor="system", action="demo_run_created", case_id=case_id)
            self.store.insert(rid, doc)
        self.publish(f"s2sc01:{rid}")
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
        처음으로 — 기동한 Center 작업을 거두고 이 장면 기록을 처음부터. 세계 초기화를
        따라간다.
        """
        with self._lock(demo_run_id):
            old, version = self._load(demo_run_id)
            self._cancel_jobs(old)
            doc = self._new(
                demo_run_id,
                case_id=case_id or old["case_id"],
                executor=executor or old["executor"],
                world_generation=world_generation or old.get("world_generation"),
            )
            audit(doc, actor=actor, action="demo_run_reset")
            try:
                self.store.save(demo_run_id, doc, version, "reset")
            except StaleWrite as exc:
                raise DomainError("다른 요청이 먼저 바꿨다 — 다시 하라", 409) from exc
        self.publish(f"s2sc01:{demo_run_id}")
        return doc

    def discard(self, demo_run_id: str) -> None:
        """세계가 지워졌다 — 기동한 Center 작업을 거두고 문서를 지운다."""
        found = self.store.load(demo_run_id)
        if found is not None:
            self._cancel_jobs(found[0])
        self.store.delete(demo_run_id)

    def follow_clock(self, demo_run_id: str, at: str) -> dict:
        """세계 시각을 따라간다 — 상황판의 기준시각이 같이 간다(조회만, 판정을 다시 하지 않는다)."""
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if doc["clock"] and parse_at(at) <= parse_at(doc["clock"]):
                return doc
            doc["clock"] = at
            return self._commit(doc, version, "clock")

    # ───────────── 수신 → Center 기동 ─────────────

    def receive_inbox(self, demo_run_id: str, doc_id: str, *, actor: str = "system") -> dict:
        """
        기간계 구매 개정 수신함의 새 문서 — 사본을 들이고 그 개정의 실행을 기동한다. Center 설정이
        없으면
        기동하지 않고 사유를 남긴다(조용히 다른 길로 돌지 않는다).
        """
        source = self.company.receipt(demo_run_id, doc_id)
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if doc_id in doc["receipts"]:
                return doc
            entry = doc["receipts"][doc_id] = {
                "doc_id": doc_id,
                "revision_id": source["revision_id"],
                "received_at": doc["clock"],
                "source": source,
                "outcome": None,
                "run": {
                    "job_id": None,
                    "external_run_id": None,
                    "state": "waiting",
                    "visited": [],
                    "problem": None,
                },
            }
            doc["company_log"].append(
                {
                    "at": doc["clock"],
                    "direction": "in",
                    "what": f"구매 입고예정 개정 {source['revision_id']} ({source['po_line']})",
                    "doc_id": doc_id,
                }
            )
            audit(
                doc,
                actor=actor,
                action="receipt_received",
                doc_id=doc_id,
                revision=source["revision_id"],
            )
            if doc["executor"] == "center":
                self._start_job(doc, entry)
            return self._commit(doc, version, "receive")

    def _start_job(self, doc: dict, entry: dict) -> None:
        run = entry["run"]
        problem = self.center.config.missing(integration=True)
        if problem:
            run["problem"] = (
                f"{problem} — 이 개정의 판정을 기동하지 않았다. Center에서 직접 기동하라"
            )
            return
        try:
            job = self.center.start_job(
                {"데모실행ID": doc["demo_run_id"], "원천개정": entry["doc_id"]},
                idempotency_key=_center_key(doc, entry["doc_id"]),
                on_behalf=ON_BEHALF,
                package=self.center.config.s2_sc01_package,
                note=f"NowView S2 SC01 — 구매 개정 {entry['revision_id']} 판정",
            )
        except CenterError as exc:
            run["problem"] = f"Center가 기동을 거절했다 — {exc.code}: {exc.message}"
            return
        run.update(job_id=job["job_id"], state="running", problem=None)
        audit(
            doc,
            actor="system",
            action="center_job_started",
            job_id=job["job_id"],
            doc_id=entry["doc_id"],
        )

    def _cancel_jobs(self, doc: dict) -> None:
        for entry in doc.get("receipts", {}).values():
            run = entry.get("run") or {}
            if run.get("job_id") and run.get("state") == "running":
                try:
                    self.center.cancel_job(run["job_id"])
                except CenterError as exc:
                    log.info("Center 작업을 거두지 못했다 %s: %s", run["job_id"], exc.message)

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
        """
        서비스 태스크 — 일감의 입력이 그림의 `chk:serviceCall.input` 그대로다. 개정의 첫 일감이 그
        실행을 개정에
        묶는다(다른 실행이 같은 개정에 오면 409). 일감의 `origin`(via)이 데모 실행의 실행 위치와
        다르면 409.
        """
        if operation not in OPERATIONS:
            raise DomainError(f"모르는 작업: {operation} (가능: {', '.join(OPERATIONS)})", 404)
        master = self.master()
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            entry = _receipt(doc, str(args.get("doc_id") or ""))
            self._link(doc, entry, external_run_id, via)
            try:
                out = run_operation(doc, operation, args, master)
            except DomainError as exc:
                if operation != "analyze_case_impact" or exc.status != 503:
                    raise
                doc, version = self._load(demo_run_id)  # 반쯤 적힌 효과는 버리고 실패 시도만 남긴다
                event = _latest_alert_event(doc)
                doc["attempts"].append(
                    {
                        "revision_id": event["revision_id"],
                        "at": doc["clock"],
                        "state": "FAILED",
                        "reason": str(exc),
                    }
                )
                if doc["case"] is not None:
                    doc["case"]["analysis_failed_at"] = doc["clock"]
                audit(doc, actor="A01", action="analysis_failed", reason=str(exc))
                self._commit(doc, version, f"{operation}:failed")
                raise
            run = entry["run"]
            for nid in (node_id or NODE_OF[operation], ends_flow(operation, out)):
                if nid and nid not in run["visited"]:
                    run["visited"].append(nid)
            if ends_flow(operation, out):
                run["state"] = "done"
            self._commit(doc, version, operation)
        return out

    def _link(self, doc: dict, entry: dict, external_run_id: str | None, via: str | None) -> None:
        if via is not None and via != doc["executor"]:
            raise DomainError(
                f"일감이 {via}에서 왔는데 이 데모 실행은 {doc['executor']}용이다 — "
                "실행 위치를 맞춰라",
                409,
            )
        if not external_run_id:
            raise DomainError("바깥 실행 id가 없다 — 일감의 멱등 칸에 run_id가 있어야 한다", 422)
        run = entry["run"]
        if run["external_run_id"] is None:
            run.update(external_run_id=external_run_id, state="running")
        elif run["external_run_id"] != external_run_id:
            raise DomainError(
                f"{entry['doc_id']}는 이미 다른 실행({run['external_run_id']})이 처리한다", 409
            )


__all__ = ["CASES", "OPERATIONS", "S2Sc01Process", "WORK", "run_operation"]
