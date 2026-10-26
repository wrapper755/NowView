"""
SC02 실행 — Chaeksas 엔진이 `processes/sc02.bpmn`을 돈다. SC01(`app/sc01/process.py`)과 같은 틀이다:
문서를 읽고 → 실행을 되살리고 → 조작하고 → 사람 대기를 업무로 옮기고 → 문서·스냅샷을 **한 번에**
저장.

**내장 실행만 있다.** SC01의 Studio·Center 실행 위치(N2·N3)는 SC02에 아직 없다 — 그림을 바깥
Chaeksas에
올리지 않았다. 서비스 태스크의 `nowview-sc02` 앱은 이 모듈 안의 어댑터다(네트워크를 타지 않는다).

**장면 2는 장면 1 인계에서 시작한다.** 데모 실행 id가 장면 1과 같다. 장면 1이 아직 인계 전이면 장면
1
각본을 끝까지 실제로 실행한 뒤 시작한다 — 지름길로 「인계됨」을 만들지 않는다(4.1의 원칙).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from chaeksas.contracts.bpmn_ext import read_process
from chaeksas.core.engine import Engine, EngineError, RunEnv, State, new_run_id
from chaeksas.core.run_log import RunLog
from chaeksas.core.run_snapshot import dump, restore
from chaeksas.core.services import OpCall, OpOutcome, ServiceCallError

from app.sc01 import demo as sc01_demo
from app.sc01.domain import USERS, DomainError, check_idempotency, parse_at, user_id_of
from app.sc01.process import Sc01Process
from app.sc01.store import Sc01Store, StaleWrite
from app.sc02 import domain
from app.sc02.seed import Seed, load_seed

PROCESS_PATH = Path(__file__).resolve().parents[2] / "processes" / "sc02.bpmn"
APP_ID = "nowview-sc02"
#: 사람 결정 뒤의 기록 작업 — 캔버스가 결재 노드에 접어 그린다(`view.topology`).
RECORDS = (
    "record_verification",
    "record_report",
    "record_negotiation",
    "submit_proposal",
    "record_decision",
    "register_cost",
    "request_handoff",
    "accept_handoff",
)
OPERATIONS = (
    "screen_request",
    "analyze_request",
    "analyze_negotiation",
    "judge_authority",
    "agent_draft",
    *RECORDS,
)


def _by(args: dict[str, Any], actor: str | None) -> str:
    """답한 사람 — 결재의 `answered_by_as` 변수(내장은 `engine.answer(answered_by=행위자)`)."""
    given = args.get("answered_by") or actor
    if not given:
        raise DomainError("답한 사람이 없다", 422)
    return user_id_of(str(given))


def run_operation(
    doc: dict, seed: Seed, operation: str, args: dict[str, Any], *, actor: str | None = None
) -> dict[str, Any]:
    """작업 하나를 문서에 적용하고 출력을 돌려준다. 저장은 부르는 쪽이 한다."""
    if operation == "screen_request":
        errors = domain.screen_request(doc, seed, args["request_id"])
        return {"passed": not errors, "error_count": len(errors)}
    if operation == "agent_draft":
        return {"output_id": domain.agent_draft(doc, kind=args["kind"], run_id=args["run_id"])}
    if operation == "judge_authority":
        return {"ceo_required": domain.judge_authority(doc, seed)}

    by = _by(args, actor)
    if operation == "analyze_request":
        out = domain.analyze_request(
            doc, seed, offer_price=args["offer_price"], due_at_text=args["due_at"], by=by
        )
        domain.complete_task(doc, "Confirm_Analysis", actor=by)
        return out
    if operation == "analyze_negotiation":
        run = domain.analyze_negotiation(doc, seed, by=by)
        domain.complete_task(doc, "Confirm_Reanalysis", actor=by)
        return {"run_id": run["run_id"], "risk": run["result"]["risk"] or ""}

    node_id = str(args.get("node_id") or "")
    if node_id not in domain.NODE_ROLES:
        raise DomainError(f"기록할 결재가 아니다: {node_id or '없음'}", 422)
    out: dict[str, Any] = {}
    if operation == "record_verification":
        domain.record_verification(doc, result=args["result"], opinion=args["opinion"], by=by)
    elif operation == "record_report":
        domain.record_report(doc, args, by=by)
    elif operation == "record_negotiation":
        out = {"negotiation_id": domain.record_negotiation(doc, args, by=by)}
    elif operation == "submit_proposal":
        out = domain.submit_proposal(doc, seed, args, by=by)
    elif operation == "record_decision":
        domain.record_decision(doc, seed, node_id, args, by=by)
    elif operation == "register_cost":
        out = {
            "cost_version_id": domain.register_cost(
                doc, seed, check=args.get("check"), note=args.get("note") or "", by=by
            )
        }
    elif operation == "request_handoff":
        out = domain.request_handoff(doc, fin=args.get("fin"), note=args.get("note") or "", by=by)
    elif operation == "accept_handoff":
        domain.accept_handoff(doc, opinion=args.get("opinion") or "", by=by)
    else:  # pragma: no cover - OPERATIONS가 막는다
        raise DomainError(f"모르는 작업: {operation}", 404)
    domain.complete_task(doc, node_id, actor=by)
    return out


class _InProcessCalls:
    """
    `chk:serviceCall` → 도메인 함수. 업무 규칙 위반은 그대로 들고 나간다(상태 코드를 잃지 않게).
    """

    def __init__(self, doc: dict, seed: Seed, actor: str | None = None) -> None:
        self.doc, self.seed, self.actor = doc, seed, actor
        self.error: DomainError | None = None

    def call(self, request: OpCall) -> OpOutcome:
        if request.app_id != APP_ID or request.operation not in OPERATIONS:
            raise ServiceCallError(request.operation, code="operation_not_found")
        try:
            out = run_operation(
                self.doc, self.seed, request.operation, dict(request.input), actor=self.actor
            )
        except DomainError as exc:
            self.error = exc
            raise ServiceCallError(str(exc), code="input_invalid", status=422) from exc
        return OpOutcome(output=out)


class Sc02Process:
    def __init__(
        self,
        store: Sc01Store,
        sc01: Sc01Process,
        *,
        seed: Seed | None = None,
        publish: Callable[[str], None] = lambda _id: None,
    ) -> None:
        self.store = store
        self.sc01 = sc01
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
            raise DomainError(f"장면 2가 시작되지 않은 데모 실행: {demo_run_id}", 404)
        return found

    def _env(self, calls: _InProcessCalls, doc: dict) -> RunEnv:
        return RunEnv(services=calls, clock=lambda: parse_at(doc["clock"]))

    def _restore(self, doc: dict, calls: _InProcessCalls):
        bpm = doc["bpm"]
        log = RunLog(run_id=bpm["run_id"])
        return restore(bpm["snapshot"], process=self.process, log=log, env=self._env(calls, doc))

    def _advance(self, run: Any, calls: _InProcessCalls) -> None:
        state = self.engine.run_until_blocked(run)
        if state is State.FAILED:
            # 업무 규칙 거절이면 그 사유·코드 그대로 — 문서는 저장하지 않으므로 반쯤 적힌 효과가
            # 없다.
            if calls.error is not None:
                raise calls.error
            failure = next(
                (e.data for e in reversed(run.log.events) if e.kind == "run_finished"), {}
            )
            raise DomainError(f"BPM 실행 실패: {failure.get('error_message') or failure}", 502)

    def _commit(self, doc: dict, version: int, run: Any | None, event: str) -> dict:
        if run is not None:
            visited = list((doc.get("bpm") or {}).get("visited", []))
            for logged in run.log.events:
                if logged.kind != "node_state" or not logged.node_id:
                    continue
                state = logged.data.get("state")
                # 종료 이벤트는 「시작」만 기록된다 — 장면 2는 종료가 여섯이라 도달한 것을 따로
                # 남긴다
                # (안 그러면 캔버스가 가지 않은 반려·재협상 종료까지 완료로 칠한다).
                node = self.process.node(logged.node_id)
                reached = state == "completed" or (
                    state == "started" and node is not None and node.kind == "endEvent"
                )
                if reached and logged.node_id not in visited:
                    visited.append(logged.node_id)
            doc["bpm"] = {
                "executor": "embedded",
                "run_id": run.run_id,
                "state": run.state.value,
                "snapshot": dump(run),
                "visited": visited,
            }
            domain.sync_tasks(doc, dict(doc["bpm"]["snapshot"]["pendings"]), run.variables)
        try:
            self.store.save(doc["demo_run_id"], doc, version, event)
        except StaleWrite as exc:
            raise DomainError("다른 요청이 먼저 바꿨다 — 새로 고친 뒤 다시 하라", 409) from exc
        self.publish(f"sc02:{doc['demo_run_id']}")
        return doc

    # ───────────── 시작 ─────────────

    def _finish_sc01(self, sc01_id: str) -> dict:
        """장면 1을 인계까지 — 각본의 남은 단계를 실제로 실행한다(역할 검사·업무 규칙 그대로)."""
        doc = self.sc01.get(sc01_id)
        if doc["scene"] == "HANDED_OFF":
            return doc
        if doc.get("bpm") and doc["bpm"].get("executor", "embedded") != "embedded":
            raise DomainError(
                "바깥 실행 위치의 장면 1은 각본으로 끝낼 수 없다 — 그쪽에서 인계까지 진행한다", 409
            )
        try:
            for i in range(doc.get("script_index", -1) + 1, len(sc01_demo.BASE)):
                doc = sc01_demo.run_step(self.sc01, sc01_id, i)
        except DomainError as exc:
            raise DomainError(
                f"장면 1을 각본으로 인계까지 끝낼 수 없다 — {exc}. 장면 1을 초기화한 뒤 다시 한다",
                409,
            ) from exc
        return self.sc01.get(sc01_id)

    def create(
        self, *, sc01_demo_run_id: str | None = None, case_id: str = "BASE", actor: str = "u-demo"
    ) -> dict:
        """
        장면 2 데모 실행. `sc01_demo_run_id`가 없으면 장면 1 실행을 새로 만든다 — X 사례는 **별도
        데모
        실행**이다(ERR-21). 이미 있으면 그대로 돌려준다(같은 사례일 때).
        """
        if case_id not in domain.CASES:
            raise DomainError(f"모르는 시연 사례: {case_id} (가능: {', '.join(domain.CASES)})", 422)
        if sc01_demo_run_id is None:
            sc01_demo_run_id = self.sc01.create(actor=actor)["demo_run_id"]
        existing = self.store.load(sc01_demo_run_id)
        if existing is not None:
            if existing[0]["case_id"] != case_id:
                raise DomainError(
                    f"이 데모 실행의 장면 2는 이미 {existing[0]['case_id']}다 — "
                    "다른 사례는 새 실행으로",
                    409,
                )
            return existing[0]
        sc01_doc = self._finish_sc01(sc01_demo_run_id)
        baseline = domain.baseline_from_sc01(sc01_doc, self.seed)
        doc = domain.new_demo_run(
            self.seed,
            sc01_demo_run_id,
            case_id=case_id,
            created_at=datetime.now(UTC),
            baseline=baseline,
        )
        domain.audit(
            doc,
            actor=actor,
            action="sc02_started",
            event_code="D00",
            case_id=case_id,
            sc01_run=baseline["run_id"],
        )
        self.store.insert(sc01_demo_run_id, doc)
        self.publish(f"sc02:{sc01_demo_run_id}")
        return doc

    def get(self, demo_run_id: str) -> dict:
        return self._load(demo_run_id)[0]

    def reset(self, demo_run_id: str, *, actor: str) -> dict:
        """
        선택 실행만 D00로 — 장면 1 기준(스냅샷)·시드·다른 실행은 그대로다(ERR-21). 이력은 남긴다.
        """
        _require(actor, "시연관리자")
        with self._lock(demo_run_id):
            old, version = self._load(demo_run_id)
            doc = domain.new_demo_run(
                self.seed,
                demo_run_id,
                case_id=old["case_id"],
                created_at=datetime.fromisoformat(old["created_at"]),
                baseline=old["sc01"],
            )
            doc["audit"] = old["audit"]
            domain.audit(doc, actor=actor, action="demo_run_reset", event_code="D00")
            return self._commit(doc, version, None, "reset")

    # ───────────── 조작 ─────────────

    def set_clock(
        self, demo_run_id: str, at: str, *, actor: str, event_code: str | None = None
    ) -> dict:
        """가상시계 이동 — 시각만 옮긴다. 승인·인수를 실행하지 않는다(ROLE-01). 넘긴 기한엔 알림."""
        _require(actor, "시연관리자")
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            new = parse_at(at)
            if new < parse_at(doc["clock"]):
                raise DomainError("가상시계는 뒤로 가지 않는다 — 지난 시점은 이력으로 본다", 409)
            doc["clock"] = new.isoformat()
            domain.audit(
                doc, actor=actor, action="clock_moved", event_code=event_code, to=doc["clock"]
            )
            domain.raise_overdue_alerts(doc)
            return self._commit(doc, version, None, event_code or "clock")

    def receive(
        self,
        demo_run_id: str,
        fixture_id: str,
        *,
        actor: str,
        event_code: str | None = None,
        script_index: int | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """S01 요청 접수 → BPM 시작. 같은 공문·같은 내용의 재수신은 기존 요청을 돌려준다(U21-03)."""
        _require(actor, "구매담당")
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if check_idempotency(doc, idempotency_key, ["receive", fixture_id]):
                return doc
            request_id, created = domain.receive_request(doc, self.seed, fixture_id, actor=actor)
            if not created:
                return doc
            calls = _InProcessCalls(doc, self.seed, actor)
            run_id = new_run_id(now=parse_at(doc["clock"]))
            run = self.engine.start(
                self.process,
                run_id=run_id,
                log=RunLog(run_id=run_id),
                env=self._env(calls, doc),
                executor="server_runner",
                inputs={"데모실행ID": doc["demo_run_id"], "요청ID": request_id},
                now=parse_at(doc["clock"]),
            )
            self._advance(run, calls)
            _mark(doc, event_code, script_index)
            return self._commit(doc, version, run, event_code or "receive")

    def act(
        self,
        demo_run_id: str,
        node_id: str,
        answer: dict[str, Any],
        *,
        actor: str,
        expect: dict[str, Any] | None = None,
        event_code: str | None = None,
        script_index: int | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """
        사람 대기 하나에 답한다. `expect` — 화면이 본 기안 버전·인계 자료 해시(U25-03·D12). 오래된
        버전에 대한 승인·인수는 409다.
        """
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if check_idempotency(doc, idempotency_key, ["act", node_id, actor, answer, expect]):
                return doc
            if doc["bpm"] is None:
                raise DomainError("아직 요청이 접수되지 않았다", 409)
            calls = _InProcessCalls(doc, self.seed, actor)
            run = self._restore(doc, calls)
            pending = next((p for p in run.pendings.values() if p.node_id == node_id), None)
            if pending is None:
                waiting = ", ".join(p.node_id for p in run.pendings.values()) or "없음"
                raise DomainError(f"{node_id}는 지금 기다리는 업무가 아니다 (대기: {waiting})", 409)
            domain.check_actor(doc, node_id, actor)
            _check_expect(doc, expect or {})
            domain.check_answer(doc, self.seed, node_id, answer)
            try:
                self.engine.answer(run, pending.request_id, answer, answered_by=actor)
            except EngineError as exc:
                raise DomainError(str(exc), 422) from exc
            self._advance(run, calls)
            _mark(doc, event_code, script_index)
            return self._commit(doc, version, run, event_code or node_id)

    def change_due(self, demo_run_id: str, *, due: str, reason: str, actor: str) -> dict:
        """외부 협상기한 변경 — BPM을 움직이지 않는 기록이다(U23-02)."""
        _require(actor, "구매담당")
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            domain.change_negotiation_due(doc, due=due, reason=reason, actor=actor)
            return self._commit(doc, version, None, "negotiation_due")

    def adopt(self, demo_run_id: str, output_id: str, *, actor: str) -> dict:
        """초안 채택 기록(AG-23) — 원본은 그대로, 채택자·시각만 남긴다. 검토 완료가 아니다."""
        _require(actor, "구매담당")
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            domain.adopt_agent(doc, output_id, actor=actor)
            return self._commit(doc, version, None, "agent_adopt")


def _check_expect(doc: dict, expect: dict[str, Any]) -> None:
    proposal = expect.get("proposal")
    if proposal is not None:
        current = domain.current_proposal(doc)
        if current is None or current["proposal_key"] != proposal:
            raise DomainError(
                f"본 기안 버전({proposal})이 최신이 아니다 — 새로 고친 뒤 다시 결재한다", 409
            )
    bundle = expect.get("bundle")
    if bundle is not None and (doc["handoff"] or {}).get("bundle_hash") != bundle:
        raise DomainError("본 인계 자료가 최신이 아니다 — 새로 고친 뒤 다시 인수한다", 409)


def _mark(doc: dict, event_code: str | None, script_index: int | None) -> None:
    if event_code:
        doc["step"] = event_code
    if script_index is not None:
        doc["script_index"] = script_index


def _require(user_id: str, role: str) -> None:
    user = USERS.get(user_id)
    if user is None or user["role"] != role:
        raise DomainError(f"행위자는 {role}여야 한다 (받은 값: {user_id or '없음'})", 403)
