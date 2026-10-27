"""
SC06 실행 — 장면 5 인계(HANDOFF51)에서 이어 RV61 검토 문서를 적재하고, **확인 절차**(담당 임원 확인
→ 경영관리 종합 확인 → 보고 결론 → 보고본 확정 → 대표 보고)를 `processes/sc06.bpmn`으로 돌린다.
화면의 세 동작(U601 요약 → ACT42 차이 상세 → U602 보고 요약)은 그 뒤의 **조회**다 — 조회는
상태·이력을 바꾸지 않는다(AT61-09).

* **Studio 시험 실행·Center 서버 실행에서 돈다**(장면 1~5 N1~N6과 같은 틀 — `app/sc05/process.py`).
  서비스 태스크는 외부 확장 `nowview-sc06`의 시스템 작업이고, 첫 작업 호출의 `{{run_id}}`가 데모
  실행을 그 실행에 묶는다.
* **착수는 화면 명령이다** — 경영관리 담당이 「확인 착수」를 누르면 내장이면 BPM을 시작하고,
  Center면 SC06 패키지를 기동하고(`POST /jobs`), Studio면 착수만 적는다.
* 화면 답은 Center면 **대리 답**(사전 검사가 먼저), Studio면 409, 내장이면 엔진에 바로.
* **숫자는 적재 때 만든다**(`domain.new_review`) — 확인 절차는 숫자를 바꾸지 않고 보고본에
  묶는다(`confirm`).
* **데모 실행 id가 장면 1~5와 같다.** 장면 5가 완료 전이면 장면 5 각본을 끝까지 실제로 실행한 뒤
  적재한다. Studio 실행이면 409다 — Studio에서 장면 5를 끝낸 뒤 연다.
* 초기화는 확인 절차만 되돌린다 — 적재(숫자·근거)는 그대로 다시 쓴다.

2026-10-28 전에 만든 문서는 확인 기록을 끝난 것으로 적재했다(`confirm.is_bpm`이 거짓) — 조회는
그대로 되고 확인 절차는 돌지 않는다. 초기화하면 확인 전으로 돌아간다.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from chaeksas.contracts.bpmn_ext import read_process
from chaeksas.core.engine import Engine, EngineError, RunEnv, State, new_run_id
from chaeksas.core.run_log import RunLog
from chaeksas.core.run_snapshot import dump, restore
from chaeksas.core.services import OpCall, OpOutcome, ServiceCallError

from app.sc01.center import CenterClient, CenterConfig, CenterError
from app.sc01.domain import (
    USERS,
    DomainError,
    check_idempotency,
    executor_of,
    link_external_run,
    name_of,
    new_center_ledger,
    note_external_progress,
    parse_at,
)
from app.sc01.process import CENTER_WAIT_S as SC01_CENTER_WAIT_S
from app.sc01.process import read_run_events
from app.sc01.store import Sc01Store, StaleWrite
from app.sc05 import demo as sc05_demo
from app.sc05.process import Sc05Process
from app.sc06 import confirm, domain
from app.sc06.seed import Seed, load_seed

PROCESS_PATH = Path(__file__).resolve().parents[2] / "processes" / "sc06.bpmn"
APP_ID = "nowview-sc06"
RECORDS = confirm.RECORDS
OPERATIONS = ("open_review", *RECORDS)
#: 대리 답할 결재가 Center에 열리기를 기다리는 시간(초) — 장면 1~5와 같다(장면 2·3 실측).
CENTER_WAIT_S = SC01_CENTER_WAIT_S

log = logging.getLogger(__name__)


def run_operation(
    doc: dict, operation: str, args: dict[str, Any], *, actor: str | None = None
) -> dict[str, Any]:
    """
    작업 하나를 문서에 적용하고 출력을 돌려준다. 저장은 부르는 쪽이 한다. 내장 어댑터와 HTTP 길이
    **같은 함수**다. 기록 작업은 검사가 먼저고(부수 효과 없음), 출력의 `error_message: None`이
    결재에 보이던 직전 거절 사유를 비운다.
    """
    if operation == "open_review":
        return confirm.open_review(doc)
    if operation not in RECORDS:
        raise DomainError(f"모르는 작업: {operation}", 404)
    node_id = str(args.get("node_id") or "")
    if node_id not in confirm.NODE_ROLES:
        raise DomainError(f"기록할 결재가 아니다: {node_id or '없음'}", 422)
    by, known = confirm.by_of(args, actor)
    if known:
        confirm.check_actor(node_id, by)
    confirm.check(doc, operation, args)
    # 마스터 밖의 이름(콘솔 관리자)이면 「담당자만」은 Center가 결재 담당자로 이미 막았다 — 기록은
    # 그 결재의 담당으로 적고, 실제로 답한 이름은 감사 이력에 남긴다(장면 1~5와 같은 태도).
    effective = by if known else confirm.NODE_ROLES[node_id]["user"]
    out = confirm.apply(doc, operation, args, by=effective)
    if not known:
        domain.audit(doc, actor=by, action="answer_by_outside_master", node_id=node_id)
    if args.get("answered_via"):
        domain.audit(doc, actor=by, action="answer_via", node_id=node_id, via=args["answered_via"])
    confirm.ensure_task(doc, node_id)
    confirm.complete_task(doc, node_id, actor=effective)
    return {**out, "error_message": None}


class _InProcessCalls:
    """내장 실행기의 `chk:serviceCall` → 도메인 함수. 업무 규칙 위반은 상태 코드째 들고 나간다."""

    def __init__(self, doc: dict, actor: str | None = None) -> None:
        self.doc, self.actor = doc, actor
        self.error: DomainError | None = None

    def call(self, request: OpCall) -> OpOutcome:
        if request.app_id != APP_ID or request.operation not in OPERATIONS:
            raise ServiceCallError(request.operation, code="operation_not_found")
        try:
            out = run_operation(self.doc, request.operation, dict(request.input), actor=self.actor)
        except DomainError as exc:
            self.error = exc
            raise ServiceCallError(str(exc), code="input_invalid", status=422) from exc
        return OpOutcome(output=out)


class Sc06Process:
    def __init__(
        self,
        store: Sc01Store,
        sc05: Sc05Process,
        *,
        seed: Seed | None = None,
        publish: Callable[[str], None] = lambda _id: None,
        center: CenterClient | None = None,
        center_wait_s: float = CENTER_WAIT_S,
    ) -> None:
        """`center`를 주지 않으면 장면 5의 것을 쓴다(같은 Center·같은 키)."""
        self.store = store
        self.sc05 = sc05
        self.seed = seed or load_seed()
        self.process = read_process(PROCESS_PATH.read_bytes())
        self.engine = Engine()
        self.publish = publish
        self.center = center or sc05.center or CenterClient(CenterConfig())
        self.center_wait_s = center_wait_s
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        # 결재 → 뒤의 기록 작업(사전 검사가 답을 작업 입력으로 바꾸는 데 쓴다)
        self.record_of: dict[str, Any] = {}
        for node in self.process.of_kind("userTask"):
            [flow] = self.process.outgoing(node.id)
            target = self.process.node(flow.target)
            if target is not None and target.kind == "serviceTask":
                self.record_of[node.id] = target.prop("serviceCall")

    # ───────────── 공통 ─────────────

    def _lock(self, demo_run_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(demo_run_id, threading.Lock())

    def _load(self, demo_run_id: str) -> tuple[dict, int]:
        found = self.store.load(demo_run_id)
        if found is None:
            raise domain.ReadError(
                f"완료·성과 검토가 열리지 않은 데모 실행: {demo_run_id}", 404, "NOT_FOUND"
            )
        return found

    def _env(self, calls: _InProcessCalls, doc: dict) -> RunEnv:
        return RunEnv(services=calls, clock=lambda: parse_at(doc["clock"]))

    def _restore(self, doc: dict, calls: _InProcessCalls):
        bpm = doc["bpm"]
        log_ = RunLog(run_id=bpm["run_id"])
        return restore(bpm["snapshot"], process=self.process, log=log_, env=self._env(calls, doc))

    def _advance(self, run: Any, calls: _InProcessCalls) -> None:
        state = self.engine.run_until_blocked(run)
        if calls.error is not None:
            raise calls.error
        if state is State.FAILED:
            failure = next(
                (e.data for e in reversed(run.log.events) if e.kind == "run_finished"), {}
            )
            raise DomainError(f"BPM 실행 실패: {failure.get('error_message') or failure}", 502)

    def _reached(self, node_id: str | None, state: Any) -> bool:
        if not node_id:
            return False
        node = self.process.node(node_id)
        return state in ("completed", "replayed") or (
            state == "started" and node is not None and node.kind == "endEvent"
        )

    def _commit(self, doc: dict, version: int, run: Any | None, event: str) -> dict:
        if run is not None:
            visited = list((doc.get("bpm") or {}).get("visited", []))
            for logged in run.log.events:
                if logged.kind == "node_state" and self._reached(
                    logged.node_id, logged.data.get("state")
                ):
                    if logged.node_id not in visited:
                        visited.append(logged.node_id)
            doc["bpm"] = {
                "executor": "embedded",
                "external_run_id": None,
                "run_id": run.run_id,
                "state": run.state.value,
                "snapshot": dump(run),
                "visited": visited,
            }
            confirm.sync_tasks(doc, dict(doc["bpm"]["snapshot"]["pendings"]))
        try:
            self.store.save(doc["demo_run_id"], doc, version, event)
        except StaleWrite as exc:
            raise DomainError("다른 요청이 먼저 바꿨다 — 새로 고친 뒤 다시 하라", 409) from exc
        self.publish(f"sc06:{doc['demo_run_id']}")
        return doc

    def answer_args(self, node_id: str, answer: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """결재 답 → 뒤의 기록 작업 입력(그림의 `input` 대응). 답에 없는 변수는 넣지 않는다."""
        call = self.record_of.get(node_id)
        if call is None:
            raise DomainError(f"{node_id}는 사람 결재가 아니다", 422)
        args: dict[str, Any] = {}
        for key, source in call.input.items():
            if source.startswith("'") and source.endswith("'"):
                args[key] = source.strip("'")
            elif source in answer:
                args[key] = answer[source]
        return call.operation, args

    def precheck(self, doc: dict, node_id: str, answer: dict[str, Any], actor: str) -> None:
        """화면 답의 사전 검사 — 담당(403), 그리고 기록 작업과 같은 업무 규칙(409·422)."""
        if node_id not in confirm.NODE_ROLES:
            raise DomainError(f"{node_id}는 사람 결재가 아니다", 422)
        confirm.check_actor(node_id, actor)
        operation, args = self.answer_args(node_id, answer)
        confirm.check(doc, operation, args)

    # ───────────── 시작 ─────────────

    def _finish_sc05(self, demo_run_id: str | None, executor: str) -> dict:
        """
        장면 5를 완료(HANDOFF51)까지 — 각본의 남은 단계를 실제로 실행한다(장면 5가 없으면 장면
        1부터).
        """
        found = None if demo_run_id is None else self.sc05.store.load(demo_run_id)
        doc = (
            self.sc05.create(sc01_demo_run_id=demo_run_id, executor=executor)
            if found is None
            else found[0]
        )
        rid = doc["demo_run_id"]
        if doc["handoff"] is not None:
            return doc
        if executor_of(doc) == "studio":
            raise DomainError(
                "결정 실행·계획 갱신이 Studio 시험 실행이다 — "
                "Studio에서 결정 실행·계획 갱신 완료까지 진행한 뒤 완료·성과 검토를 연다",
                409,
            )
        steps = sc05_demo.steps_for(doc["case_id"], self.sc05.seed)
        try:
            for i in range(doc.get("script_index", -1) + 1, len(steps)):
                doc = sc05_demo.run_step(self.sc05, rid, i)
                if executor_of(doc) == "center":
                    self.sc05.sync_center(rid)
        except DomainError as exc:
            raise DomainError(
                f"결정 실행·계획 갱신을 각본으로 완료까지 끝낼 수 없다 — {exc}. 결정 실행·계획 "
                "갱신을 초기화한 뒤 다시 한다",
                409,
            ) from exc
        deadline = time.monotonic() + self.center_wait_s
        doc = self.sc05.get(rid)
        while doc["handoff"] is None and time.monotonic() < deadline:
            time.sleep(min(0.5, self.center_wait_s))
            doc = self.sc05.get(rid)
        if doc["handoff"] is None:
            raise DomainError(
                "결정 실행·계획 갱신 각본을 다 돌렸지만 아직 완료가 기록되지 않았다 — "
                "바깥 실행이 완료 기록을 부를 때까지 "
                "기다린 뒤 다시 연다",
                409,
            )
        return doc

    def _new(self, rid: str, sc05_doc: dict, executor: str, created_at: datetime) -> dict:
        doc = domain.new_review(self.seed, rid, sc05_doc, created_at=created_at)
        confirm.pending_state(doc, executor=executor)
        return doc

    def create(
        self,
        *,
        sc01_demo_run_id: str | None = None,
        case_id: str = "BASE",
        executor: str = "embedded",
    ) -> dict:
        """
        장면 6 적재 — 확인 전 상태로. 이미 있으면 그대로 돌려준다(동일 키 중복 생성 없음, 구현명세
        8장 7단계). `executor`는 확인 절차를 어디서 돌릴지이고, 장면 1~5가 아직 없을 때 그 장면들을
        어디서 돌릴지다.
        """
        if case_id not in domain.CASES:
            raise DomainError(
                f"모르는 시연 사례: {case_id} — 완료·성과 검토 예외(X61-*)는 시험 fixture로만 "
                "적재한다",
                422,
            )
        if sc01_demo_run_id is not None:
            existing = self.store.load(sc01_demo_run_id)
            if existing is not None:
                return existing[0]
        sc05_doc = self._finish_sc05(sc01_demo_run_id, executor)
        rid = sc05_doc["demo_run_id"]
        doc = self._new(rid, sc05_doc, executor, datetime.now(UTC))
        self.store.insert(rid, doc)
        self.publish(f"sc06:{rid}")
        return doc

    def get(self, demo_run_id: str) -> dict:
        return self._load(demo_run_id)[0]

    def reset(self, demo_run_id: str, *, actor: str, executor: str | None = None) -> dict:
        """
        확인 절차만 확인 전으로 — 적재 원천·장면 5 스냅샷은 그대로 다시 쓴다. Center 앞 작업은
        거둔다. 구현명세 11장 「확정본·근거·확인 이력은 삭제하지 않는다」 — 지난 확인 기록은
        이력(`sc06_history`)에 있다.
        """
        _require(actor, "시연관리자")
        with self._lock(demo_run_id):
            old, version = self._load(demo_run_id)
            old_job = (((old.get("bpm") or {}).get("center") or {}).get("job") or {}).get("job_id")
            where = executor or (executor_of(old) if confirm.is_bpm(old) else "center")
            doc = domain.new_review(
                self.seed,
                demo_run_id,
                {},
                created_at=datetime.fromisoformat(old["created_at"]),
                sc05=old["sc05"],
            )
            confirm.pending_state(doc, executor=where)
            doc["audit"] = old["audit"]
            domain.audit(doc, actor=actor, action="demo_run_reset", executor=where)
            if old_job and not self.center.config.missing(integration=True):
                self._cancel_center_job(doc, old_job)
            return self._commit(doc, version, None, "reset")

    # ───────────── 조작 ─────────────

    def mark(self, demo_run_id: str, *, event_code: str, script_index: int, note: str = "") -> dict:
        """각본의 조회 단계 — 상태를 바꾸지 않고 진행 지점만 남긴다."""
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            _mark(doc, event_code, script_index)
            return self._commit(doc, version, None, event_code)

    def start(
        self,
        demo_run_id: str,
        *,
        actor: str,
        event_code: str | None = None,
        script_index: int | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """
        확인 착수 — 내장 시작 · Center 기동 · Studio는 착수만. **재착수는 기존 결과를 돌려준다.**
        """
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if not confirm.is_bpm(doc):
                raise DomainError(
                    "이 검토건은 확인 기록을 끝난 것으로 적재했다 — 초기화하면 확인 전으로 "
                    "돌아간다",
                    409,
                )
            if check_idempotency(doc, idempotency_key, ["start"]):
                return doc
            if not confirm.start(doc, by=actor):
                return doc
            executor = executor_of(doc)
            if executor != "embedded":
                if executor == "center":
                    self._center_start(doc, actor=actor)
                _mark(doc, event_code, script_index)
                return self._commit(doc, version, None, event_code or "start")
            calls = _InProcessCalls(doc, actor)
            run_id = new_run_id(now=parse_at(doc["clock"]))
            run = self.engine.start(
                self.process,
                run_id=run_id,
                log=RunLog(run_id=run_id),
                env=self._env(calls, doc),
                executor="server_runner",
                inputs={"데모실행ID": doc["demo_run_id"]},
                now=parse_at(doc["clock"]),
            )
            self._advance(run, calls)
            _mark(doc, event_code, script_index)
            return self._commit(doc, version, run, event_code or "start")

    def act(
        self,
        demo_run_id: str,
        node_id: str,
        answer: dict[str, Any],
        *,
        actor: str,
        event_code: str | None = None,
        script_index: int | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """사람 대기 하나에 답한다. Center면 대리 답, Studio면 409."""
        current = self.get(demo_run_id)
        executor = executor_of(current) if confirm.is_bpm(current) else "embedded"
        if executor == "center":
            return self._relay(
                demo_run_id,
                node_id,
                answer,
                actor=actor,
                event_code=event_code,
                script_index=script_index,
                idempotency_key=idempotency_key,
            )
        if executor == "studio":
            raise DomainError(
                "이 데모 실행은 Studio 시험 실행이 돈다 — 결재는 Studio에서 답하라", 409
            )
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if check_idempotency(doc, idempotency_key, ["act", node_id, actor, answer]):
                return doc
            if doc.get("bpm") is None:
                raise DomainError("아직 확인을 착수하지 않았다", 409)
            calls = _InProcessCalls(doc, actor)
            run = self._restore(doc, calls)
            pending = next((p for p in run.pendings.values() if p.node_id == node_id), None)
            if pending is None:
                waiting = ", ".join(sorted(p.node_id for p in run.pendings.values())) or "없음"
                raise DomainError(f"{node_id}는 지금 기다리는 업무가 아니다 (대기: {waiting})", 409)
            self.precheck(doc, node_id, answer, actor)
            try:
                self.engine.answer(run, pending.request_id, answer, answered_by=actor)
            except EngineError as exc:
                raise DomainError(str(exc), 422) from exc
            self._advance(run, calls)
            _mark(doc, event_code, script_index)
            return self._commit(doc, version, run, event_code or node_id)

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
        시스템 작업을 HTTP로 — 바깥 BPM이 서비스 태스크에서 부른다. 첫 호출이 데모 실행을 묶고,
        기록이 거절되면 거절만 남기고(반쯤 적힌 효과는 버린다) 상태 코드를 낸다 — 그림은 같은 결재로
        돌아간다.
        """
        if operation not in OPERATIONS:
            raise DomainError(f"모르는 작업: {operation} (가능: {', '.join(OPERATIONS)})", 404)
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if not confirm.is_bpm(doc):
                raise DomainError("이 검토건은 확인 절차를 돌지 않는다(끝난 기록으로 적재)", 409)
            link_external_run(doc, external_run_id, via=via)
            try:
                try:
                    out = run_operation(doc, operation, args)
                except KeyError as exc:
                    raise DomainError(f"없는 대상·입력: {exc.args[0]}", 422) from exc
            except DomainError as exc:
                if operation not in RECORDS:
                    raise
                doc, version = self._load(demo_run_id)
                link_external_run(doc, external_run_id, via=via)
                domain.audit(
                    doc,
                    actor="system",
                    action="answer_rejected",
                    node_id=args.get("node_id") or operation,
                    status=exc.status,
                    reason=str(exc),
                    blocking_items=getattr(exc, "items", None),
                )
                self._commit(doc, version, None, f"{operation}:rejected")
                raise
            decided = args.get("node_id") if operation in RECORDS else None
            ends = confirm.ends_flow(operation) and executor_of(doc) == "studio"
            note_external_progress(doc, node_id, decided=decided, done=ends)
            self._commit(doc, version, None, operation)
        return out

    # ───────────── Center 실행 (장면 1~5와 같다) ─────────────

    def _center_start(self, doc: dict, *, actor: str) -> None:
        """
        착수 → SC06 패키지 기동. 설정이 없으면 기동하지 않고 사유를 남긴다(착수 자체는 막지 않는다).
        """
        ledger = doc["bpm"].setdefault("center", new_center_ledger())
        problem = self.center.config.missing(integration=True)
        if problem:
            ledger["problem"] = f"{problem} — SC06을 기동하지 않았다. Center에서 직접 기동하라"
            return
        old = (ledger.get("job") or {}).get("job_id")
        if old:
            self._cancel_center_job(doc, old)
        try:
            job = self.center.start_job(
                {"데모실행ID": doc["demo_run_id"]},
                idempotency_key=_center_key(doc),
                on_behalf=name_of(actor) if actor in USERS else actor,
                package=self.center.config.sc06_package,
                note="NowView SC06 — 완료·성과 검토 확인 착수",
            )
        except CenterError as exc:
            raise exc.as_domain("SC06 기동") from exc
        ledger.update(job={"job_id": job["job_id"], "at": doc["clock"]}, problem=None)
        domain.audit(doc, actor=actor, action="center_job_started", job_id=job["job_id"])

    def _cancel_center_job(self, doc: dict, job_id: str) -> None:
        try:
            self.center.cancel_job(job_id)
            outcome = "cancelled"
        except CenterError as exc:
            outcome = f"{exc.code}: {exc.message}"
        domain.audit(
            doc, actor="system", action="center_job_cancelled", job_id=job_id, outcome=outcome
        )

    def _relay(
        self,
        demo_run_id: str,
        node_id: str,
        answer: dict[str, Any],
        *,
        actor: str,
        event_code: str | None,
        script_index: int | None,
        idempotency_key: str | None,
    ) -> dict:
        """
        Center 실행의 화면 답 = 대리 답. 사전 검사 → 열린 그 사람의 결재 → 답. 효과는 기록 작업이
        낸다.
        """
        problem = self.center.config.missing(relay=True)
        if problem:
            raise DomainError(
                "이 데모 실행은 Center 서버 실행이 돈다 — 결재는 Center 결재함에서 답하라 — "
                f"{problem}",
                503,
            )
        body = ["act", node_id, actor, answer]
        doc = self.get(demo_run_id)
        if check_idempotency(doc, idempotency_key, body):
            return doc
        name = name_of(actor) if actor in USERS else actor
        try:
            self.precheck(doc, node_id, answer, actor)
        except DomainError as exc:
            if exc.status != 409:
                raise
            # 앞 결재 뒤의 기록 작업을 실행기가 아직 부르지 않았을 수 있다(장면 2·3 실측). 이 결재가
            # 열렸으면 앞 작업은 끝났다 — 다시 본다. 아직 Center에 답하기 전이다.
            try:
                self._await_approval(demo_run_id, node_id, name)
            except DomainError:
                raise exc from None
            doc = self.get(demo_run_id)
            self.precheck(doc, node_id, answer, actor)
        ext, approval = self._await_approval(demo_run_id, node_id, name)
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if check_idempotency(doc, idempotency_key, body):
                return doc
            if doc["bpm"]["external_run_id"] != ext:
                raise DomainError("그 사이 Center 실행이 바뀌었다 — 새로 고친 뒤 다시 하라", 409)
            try:
                self.center.answer(
                    approval["request_id"],
                    answer,
                    on_behalf=name,
                    digest=approval.get("review_digest"),
                )
            except CenterError as exc:
                raise exc.as_domain("대리 답") from exc
            # 폴러(2초)보다 대리 답이 먼저 결재를 찾으면 폴러는 대리 답한 결재를
            # 건너뛴다 — 업무를 지금 연다. 결재가 열려 있었으니 늦게 연 것이 아니다
            # (각본 실측: 6건 중 4건이 늦게 열렸다).
            if confirm.task_for_node(doc, node_id) is None:
                confirm.sync_tasks(doc, {approval["request_id"]: {"node_id": node_id}})
            bpm = doc["bpm"]
            bpm["center"]["relayed"].append(approval["request_id"])
            bpm["waiting"] = [
                w for w in bpm.get("waiting", []) if w["request_id"] != approval["request_id"]
            ]
            domain.audit(
                doc,
                actor=actor,
                action="answer_relayed",
                node_id=node_id,
                request_id=approval["request_id"],
            )
            _mark(doc, event_code, script_index)
            return self._commit(doc, version, None, event_code or node_id)

    def _await_approval(self, demo_run_id: str, node_id: str, name: str) -> tuple[str, dict]:
        deadline = time.monotonic() + self.center_wait_s
        seen: list[str] = []
        ext = None
        while True:
            ext = (self.get(demo_run_id)["bpm"] or {}).get("external_run_id")
            seen = []
            if ext:
                try:
                    opened = self.center.open_approvals(on_behalf=name)
                except CenterError as exc:
                    raise exc.as_domain("결재 찾기") from exc
                for item in opened:
                    if item.get("run_id") == ext and item.get("node_id") == node_id:
                        return ext, item
                    if item.get("run_id") == ext:
                        seen.append(str(item.get("node_id")))
            if time.monotonic() >= deadline:
                break
            time.sleep(min(1.0, self.center_wait_s))
        if not ext:
            raise DomainError(
                "Center 실행이 아직 NowView를 부르지 않았다 — 업무가 열리면 결재가 열린다", 409
            )
        raise DomainError(
            f"{node_id}는 지금 Center에서 {name}의 결재로 열려 있지 않다 "
            f"(이 실행에서 열린 것: {', '.join(seen) or '없음'})",
            409,
        )

    def poll_center(self) -> int:
        if self.center.config.missing(integration=True):
            return 0
        changed = 0
        for demo_run_id in self.store.running_external("center"):
            try:
                changed += self.sync_center(demo_run_id)
            except (CenterError, DomainError) as exc:
                log.warning("Center 진행을 읽지 못했다 (%s): %s", demo_run_id, exc)
        return changed

    def sync_center(self, demo_run_id: str) -> bool:
        """Center 실행 기록 → 지나온 노드·사람 대기·위치·끝. 새 결재는 그때 업무를 연다."""
        doc = self.get(demo_run_id)
        bpm = doc.get("bpm") or {}
        ext = bpm.get("external_run_id")
        if bpm.get("executor") != "center" or not ext or bpm.get("state") != "running":
            return False
        progress = read_run_events(self.center.run_events(ext))
        ledger = bpm.get("center") or new_center_ledger()
        if progress["last_seq"] == ledger.get("last_seq"):
            return False
        relayed = set(ledger.get("relayed", []))
        known = {w["request_id"]: w for w in bpm.get("waiting", [])}
        opened = {
            rid: self._approval_entry(rid, nid)
            for rid, nid in progress["open"].items()
            if rid not in relayed and rid not in known
        }
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            bpm = doc["bpm"]
            if bpm.get("external_run_id") != ext:
                return False
            ledger = bpm.setdefault("center", new_center_ledger())
            relayed = set(ledger["relayed"])
            entries = {**known, **opened}
            bpm["waiting"] = [
                entries[rid] for rid in progress["open"] if rid not in relayed and rid in entries
            ]
            for nid in progress["visited"]:
                if nid not in bpm["visited"]:
                    bpm["visited"].append(nid)
            waiting_nodes = {w["node_id"] for w in bpm["waiting"]}
            bpm["position"] = [n for n in progress["active"] if n not in waiting_nodes]
            if progress["finished"]:
                for nid in progress["active"]:
                    if self._reached(nid, "started") and nid not in bpm["visited"]:
                        bpm["visited"].append(nid)
                bpm["state"] = {"success": "done"}.get(progress["finished"], progress["finished"])
                bpm["position"], bpm["waiting"] = [], []
            ledger["last_seq"] = progress["last_seq"]
            ledger["problem"] = None
            confirm.sync_tasks(doc, {rid: {"node_id": e["node_id"]} for rid, e in opened.items()})
            self._commit(doc, version, None, "center_progress")
        return True

    def _approval_entry(self, request_id: str, node_id: str) -> dict[str, Any]:
        """열린 결재 하나를 화면이 쓸 대기로 — 담당의 이름으로 읽는다."""
        node = self.process.node(node_id)
        form = node.prop("approval") if node is not None else None
        entry: dict[str, Any] = {
            "request_id": request_id,
            "node_id": node_id,
            "title": (form.title if form is not None else None) or node_id,
            "review": {},
            "fields": [f.model_dump(exclude_none=True) for f in form.fields] if form else [],
            "review_digest": None,
        }
        if node_id not in confirm.NODE_ROLES or self.center.config.missing(relay=True):
            return entry
        info = self.center.approval(
            request_id, on_behalf=name_of(confirm.NODE_ROLES[node_id]["user"])
        )
        if info is None:
            return entry
        entry.update(
            title=info.get("title") or entry["title"],
            review=dict(info.get("review") or {}),
            fields=((info.get("form") or {}).get("fields")) or entry["fields"],
            review_digest=info.get("review_digest"),
        )
        return entry


def _center_key(doc: dict) -> str:
    """Center 멱등 키 — 초기화 회차를 넣는다(장면 1~5와 같은 함정)."""
    generation = sum(1 for a in doc["audit"] if a["action"] == "demo_run_reset")
    return f"sc06:{doc['demo_run_id']}:r{generation}:start"


def _mark(doc: dict, event_code: str | None, script_index: int | None) -> None:
    if event_code:
        doc["step"] = event_code
    if script_index is not None:
        doc["script_index"] = script_index


def _require(user_id: str, role: str) -> None:
    user = USERS.get(user_id)
    if user is None or user["role"] != role:
        raise DomainError(f"행위자는 {role}여야 한다 (받은 값: {user_id or '없음'})", 403)


__all__ = ["OPERATIONS", "RECORDS", "Sc06Process", "run_operation"]
