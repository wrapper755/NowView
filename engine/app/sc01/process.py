"""
SC01 실행 — Chaeksas BPM 엔진(`chaeksas.core.engine`)을 라이브러리로 돌린다.

**Chaeksas는 그림을 해석하고 사람을 기다린다. 숫자는 모른다.** 서비스 태스크가 부르는
`nowview.sc01` 앱은 이 모듈 안의 어댑터(`_InProcessCalls`)다 — 네트워크를 타지 않는다.
Center·서버 실행기는 쓰지 않는다: 정의 변경마다 패키지 서명·배포가 필요하고, 결재 응답은
관리자 토큰으로만 되고, 작업 결과 값을 돌려주지 않아 화면이 결과를 읽을 길이 없다.

한 번의 조작 = 문서를 읽고 → 실행을 되살리고 → 조작하고 → 사람 대기를 업무로 옮기고 →
문서·스냅샷을 **한 번에** 저장한다. 같은 데모 실행의 조작은 잠금으로 줄을 세우고, 워커
사이는 `row_version`이 막는다.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from chaeksas.contracts.bpmn_ext import read_process
from chaeksas.core.engine import Engine, EngineError, RunEnv, State, new_run_id
from chaeksas.core.run_log import RunLog
from chaeksas.core.run_snapshot import dump, restore
from chaeksas.core.services import OpCall, OpOutcome, ServiceCallError

from app.sc01 import domain
from app.sc01.domain import USERS, DomainError
from app.sc01.seed import Seed, load_seed
from app.sc01.store import Sc01Store, StaleWrite

PROCESS_PATH = Path(__file__).resolve().parents[2] / "processes" / "sc01.bpmn"
APP_ID = "nowview.sc01"


class _InProcessCalls:
    """`chk:serviceCall` → 도메인 함수. 업무 규칙 위반은 다시 불러도 같으므로 재시도하지 않는다."""

    def __init__(self, doc: dict, seed: Seed) -> None:
        self.doc, self.seed = doc, seed

    def call(self, request: OpCall) -> OpOutcome:
        if request.app_id != APP_ID:
            raise ServiceCallError(f"모르는 앱: {request.app_id}", code="operation_not_found")
        args = dict(request.input)
        try:
            if request.operation == "validate_source":
                errors = domain.validate_source(self.doc, self.seed, args["source_id"])
                out: dict[str, Any] = {"passed": not errors, "error_count": len(errors)}
            elif request.operation == "compare":
                out = domain.compare(self.doc, self.seed, args["source_id"])
            elif request.operation == "hand_off":
                out = {"handed_off": domain.hand_off(self.doc, args["run_id"])}
            else:
                raise ServiceCallError(request.operation, code="operation_not_found")
        except DomainError as exc:
            raise ServiceCallError(str(exc), code="input_invalid", status=422) from exc
        return OpOutcome(output=out)


class Sc01Process:
    def __init__(
        self,
        store: Sc01Store,
        *,
        seed: Seed | None = None,
        publish: Callable[[str], None] = lambda _id: None,
    ) -> None:
        self.store = store
        self.seed = seed or load_seed()
        self.process = read_process(PROCESS_PATH.read_bytes())
        self.engine = Engine()
        self.publish = publish
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    # ───────────── 공통 ─────────────

    def _lock(self, demo_run_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(demo_run_id, threading.Lock())

    def _load(self, demo_run_id: str) -> tuple[dict, int]:
        found = self.store.load(demo_run_id)
        if found is None:
            raise DomainError(f"없는 데모 실행: {demo_run_id}", 404)
        return found

    def _env(self, doc: dict) -> RunEnv:
        # 가상시계 — 타이머·기한·감사 이력이 모두 데모 실행의 시각을 쓴다(구현명세 2장).
        return RunEnv(
            services=_InProcessCalls(doc, self.seed), clock=lambda: domain.parse_at(doc["clock"])
        )

    def _restore(self, doc: dict):
        bpm = doc["bpm"]
        log = RunLog(run_id=bpm["run_id"])
        return restore(bpm["snapshot"], process=self.process, log=log, env=self._env(doc))

    def _commit(self, doc: dict, version: int, run: Any | None, event: str) -> dict:
        if run is not None:
            doc["bpm"] = {
                "run_id": run.run_id,
                "state": run.state.value,
                "snapshot": dump(run),
                "error": doc["bpm"]["error"] if doc.get("bpm") else None,
            }
            domain.sync_tasks(
                doc, {k: v for k, v in doc["bpm"]["snapshot"]["pendings"].items()}, run.variables
            )
        try:
            self.store.save(doc["demo_run_id"], doc, version, event)
        except StaleWrite as exc:
            raise DomainError("다른 요청이 먼저 바꿨다 — 새로 고친 뒤 다시 하라", 409) from exc
        self.publish(f"sc01:{doc['demo_run_id']}")
        return doc

    def _advance(self, doc: dict, run: Any) -> None:
        state = self.engine.run_until_blocked(run)
        if state is State.FAILED:
            # 실패한 실행을 업무 완료로 보이게 하지 않는다 — 원인을 문서에 남긴다(1.10).
            failure = next(
                (e.data for e in reversed(run.log.events) if e.kind == "run_finished"), {}
            )
            raise DomainError(f"BPM 실행 실패: {failure.get('error_message') or failure}", 502)

    # ───────────── 조작 ─────────────

    def create(self, *, case_id: str = "BASE", actor: str = "u-demo") -> dict:
        demo_run_id = f"demo-{uuid.uuid4().hex[:8]}"
        doc = domain.new_demo_run(
            self.seed, demo_run_id, case_id=case_id, created_at=datetime.now(UTC)
        )
        domain.audit(doc, actor=actor, action="demo_run_created", event_code="S0", case_id=case_id)
        self.store.insert(demo_run_id, doc)
        return doc

    def get(self, demo_run_id: str) -> dict:
        return self._load(demo_run_id)[0]

    def set_clock(
        self, demo_run_id: str, at: str, *, actor: str, event_code: str | None = None
    ) -> dict:
        """가상시계를 옮긴다. **시각 이동만으로 인수·승인을 실행하지 않는다**(구현명세 2장)."""
        _require(actor, "시연관리자")
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            new = domain.parse_at(at)
            if new < domain.parse_at(doc["clock"]):
                raise DomainError("가상시계는 뒤로 가지 않는다 — 지난 시점은 이력으로 본다", 409)
            doc["clock"] = new.isoformat()
            domain.audit(
                doc, actor=actor, action="clock_moved", event_code=event_code, to=doc["clock"]
            )
            return self._commit(doc, version, None, event_code or "clock")

    def receive(
        self,
        demo_run_id: str,
        fixture_id: str,
        *,
        actor: str,
        event_code: str | None = None,
        script_index: int | None = None,
    ) -> dict:
        """시연 원천 수신 → BPM 시작(첫 수신) 또는 정정본 전달(보완 대기 중)."""
        _require(actor, "영업담당")
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            source_id, created = domain.receive_source(doc, self.seed, fixture_id, actor=actor)
            if not created:
                return doc  # 재수신 — 중복 등록·이슈 생성 없이 기존 접수를 돌려준다
            if doc["bpm"] is None:
                run_id = new_run_id(now=domain.parse_at(doc["clock"]))
                log = RunLog(run_id=run_id)
                run = self.engine.start(
                    self.process,
                    run_id=run_id,
                    log=log,
                    env=self._env(doc),
                    executor="server_runner",
                    inputs={"데모실행ID": demo_run_id, "원천ID": source_id},
                    now=domain.parse_at(doc["clock"]),
                )
            else:
                run = self._restore(doc)
                if self.engine.message_target(run, "원천정정") is None:
                    raise DomainError("지금은 정정본을 받을 단계가 아니다", 409)
                self.engine.deliver(run, "원천정정", payload={"원천ID": source_id})
            self._advance(doc, run)
            _mark(doc, event_code, script_index)
            return self._commit(doc, version, run, event_code or "receive")

    def act(
        self,
        demo_run_id: str,
        node_id: str,
        answer: dict[str, Any],
        *,
        actor: str,
        event_code: str | None = None,
        script_index: int | None = None,
    ) -> dict:
        """사람 대기 하나에 답한다 — 확인·검토·배정·요청·인수."""
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if doc["bpm"] is None:
                raise DomainError("아직 시작되지 않은 데모 실행이다", 409)
            run = self._restore(doc)
            pending = next((p for p in run.pendings.values() if p.node_id == node_id), None)
            if pending is None:
                waiting = ", ".join(p.node_id for p in run.pendings.values()) or "없음"
                raise DomainError(f"{node_id}는 지금 기다리는 업무가 아니다 (대기: {waiting})", 409)
            domain.check_actor(doc, node_id, actor)
            self._before_answer(doc, node_id, answer, actor=actor, variables=run.variables)
            try:
                self.engine.answer(run, pending.request_id, answer, answered_by=actor)
            except EngineError as exc:
                raise DomainError(str(exc), 422) from exc
            self._advance(doc, run)
            _mark(doc, event_code, script_index)
            return self._commit(doc, version, run, event_code or node_id)

    def _before_answer(
        self, doc: dict, node_id: str, answer: dict, *, actor: str, variables: dict
    ) -> None:
        """BPM 폼이 못 거는 업무 규칙. 위반이면 엔진에 답을 넣기 전에 막는다."""
        if node_id == "Approve_DQ":
            sid = variables["원천ID"]
            if answer.get("확인결과") == "확인완료":
                domain.verify_source(
                    doc,
                    sid,
                    actor=actor,
                    opinion=answer.get("확인의견", ""),
                    evidence=answer.get("확인근거", ""),
                )
                domain.mark_task(doc, node_id, actor=actor, outcome="completed")
            else:
                domain.request_fix(doc, sid, actor=actor, opinion=answer.get("확인의견", ""))
                domain.mark_task(doc, node_id, actor=actor, outcome="needs_info")
        elif node_id == "Approve_Sales":
            # 검토 완료에는 사람의 의견·근거가 있어야 한다. Agent 성공은 조건이 아니다(UI04-02).
            if (
                not str(answer.get("영업의견", "")).strip()
                or not str(answer.get("영업근거", "")).strip()
            ):
                raise DomainError("검토 의견과 근거가 필요하다", 422)
            run_id = variables["계산ID"]
            doc["reviews"][run_id] = {
                "run_id": run_id,
                "by": actor,
                "at": doc["clock"],
                "opinion": answer["영업의견"],
                "evidence": answer["영업근거"],
                "manual_review": bool(answer.get("경영검토요청")),
            }
            domain.mark_task(doc, node_id, actor=actor, outcome="completed")
        elif node_id == "Approve_Dispatch":
            _require(answer.get("생산담당자", ""), "생산담당", what="생산 담당")
            _require(answer.get("자재담당자", ""), "자재담당", what="자재 담당")
            domain.audit(
                doc,
                actor=actor,
                action="dispatched",
                prod=answer["생산담당자"],
                mat=answer["자재담당자"],
            )
        elif node_id == "Approve_Review":
            _require(answer.get("경영관리담당자", ""), "경영관리담당", what="경영관리 담당")
            domain.audit(doc, actor=actor, action="review_requested", fin=answer["경영관리담당자"])
        elif node_id.startswith("Accept_"):
            domain.mark_task(doc, node_id, actor=actor, outcome="accepted")
        elif node_id == "Confirm_Calc":
            domain.audit(doc, actor=actor, action="calculation_requested")

    def reset(self, demo_run_id: str, *, actor: str) -> dict:
        """현재 데모 실행만 S0로 되돌린다. 이력은 남긴다(DATA-05)."""
        _require(actor, "시연관리자")
        with self._lock(demo_run_id):
            old, version = self._load(demo_run_id)
            doc = domain.new_demo_run(
                self.seed,
                demo_run_id,
                case_id=old["case_id"],
                created_at=datetime.fromisoformat(old["created_at"]),
            )
            doc["audit"] = old["audit"]
            domain.audit(doc, actor=actor, action="demo_run_reset", event_code="S0")
            return self._commit(doc, version, None, "reset")


def _mark(doc: dict, event_code: str | None, script_index: int | None) -> None:
    if event_code:
        doc["step"] = event_code
    if script_index is not None:
        doc["script_index"] = script_index


def _require(user_id: str, role: str, *, what: str | None = None) -> None:
    user = USERS.get(user_id)
    if user is None or user["role"] != role:
        label = what or "행위자"
        raise DomainError(
            f"{label}는 {role}여야 한다 (받은 값: {user_id or '없음'})",
            403 if what is None else 422,
        )
