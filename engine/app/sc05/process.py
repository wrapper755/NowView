"""
SC05 실행 — `processes/sc05.bpmn`을 **Studio 시험 실행·Center 서버 실행**이 돌고, NowView는 서비스
태스크가 부르는
시스템 작업(외부 확장 `nowview-sc05`)으로 업무를 적는다. 장면 3·4(`app/sc04/process.py`)와 같은
틀이다.

* **실행 위치는 데모 실행을 만들 때 정한다**(`bpm.executor`). 첫 작업 호출의 실행 id가 데모
  실행을 그 실행에
  묶고, 일감의 `origin`이 실행 위치다(C15 — 어긋나면 409).
* **착수(S01)는 화면 명령이다** — 경영관리 담당이 「장면 5 착수」를 누르면 HANDOFF41이 이어지고,
  내장이면 BPM을
  시작하고, Center면 SC05 패키지를 기동한다(`POST /jobs`). Studio면 착수만 적는다 — Studio가
  시작한다.
* 화면 답은 Center면 **대리 답**(사전 검사가 먼저), Studio면 409, 내장이면 엔진에 바로.
* **사전 검사는 그림에서 읽는다** — 결재 뒤 기록 작업의 `input` 대응으로 답을 작업 입력으로 바꿔
  `domain.check`를
  부른다. 기록 작업도 같은 검사를 다시 한다. 칸 이름 ↔ 입력 표를 따로 적지 않는다.
* **가상시계를 옮기면 배경 원천이 들어온다**(`domain.catch_up`) — 시각 이동은 사람의 승인·착수를
  만들지 않는다.
* Agent 초안(AG51~AG58)과 그 검토 기록은 BPM 밖의 명령이다.

**장면 5는 장면 4 인계(HANDOFF41)에서 시작한다.** 데모 실행 id가 장면 1~4와 같다. 장면 4가 완료
전이면 장면 4
각본을 끝까지 실제로 실행한 뒤 시작한다 — 지름길로 「완료됨」을 만들지 않는다(4.1의 원칙).
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
    user_id_of,
)
from app.sc01.process import CENTER_WAIT_S as SC01_CENTER_WAIT_S
from app.sc01.process import read_run_events
from app.sc01.store import Sc01Store, StaleWrite
from app.sc04 import demo as sc04_demo
from app.sc04.process import Sc04Process
from app.sc05 import domain
from app.sc05.seed import Seed, load_seed

PROCESS_PATH = Path(__file__).resolve().parents[2] / "processes" / "sc05.bpmn"
APP_ID = "nowview-sc05"
RECORDS = domain.RECORDS
OPERATIONS = ("open_scene", *RECORDS)
#: 대기가 아니어도 요건부터 보는 결재 — 착수·대표 승인 요청·장면 완료(422와 남은 항목,
#: T505·T523·T531)
GATED = {
    "Start_Operation": domain.check_start,
    "Submit_Forecast": domain.check_submit_forecast,
}
#: 대리 답할 결재가 Center에 열리기를 기다리는 시간(초) — 장면 1~3과 같은 값이다(10초로는
#: 실행기가 다음 결재를 올리기 전에 포기했다 — 장면 2·3 실측).
CENTER_WAIT_S = SC01_CENTER_WAIT_S

log = logging.getLogger(__name__)


def _by(args: dict[str, Any], actor: str | None) -> tuple[str, bool]:
    """답한 사람 → (id 또는 이름, 마스터 안인가). 마스터 밖의 이름(콘솔 관리자)은 거절하지
    않는다."""
    given = args.get("answered_by") or actor
    if not given:
        raise DomainError("답한 사람(answered_by)이 없다", 422)
    try:
        return user_id_of(str(given)), True
    except DomainError:
        return str(given), False


def run_operation(
    doc: dict, seed: Seed, operation: str, args: dict[str, Any], *, actor: str | None = None
) -> dict[str, Any]:
    """
    작업 하나를 문서에 적용하고 출력을 돌려준다. 저장은 부르는 쪽이 한다. 내장 어댑터와 C15 일꾼이
    **같은
    함수**다. 기록 작업은 검사가 먼저고(부수 효과 없음), 출력의 `error_message: None`이 결재에
    보이던 직전
    거절 사유를 비운다.
    """
    if operation == "open_scene":
        return domain.open_scene(doc)
    if operation not in RECORDS:
        raise DomainError(f"모르는 작업: {operation}", 404)
    node_id = str(args.get("node_id") or "")
    if node_id not in domain.NODE_ROLES:
        raise DomainError(f"기록할 결재가 아니다: {node_id or '없음'}", 422)
    by, known = _by(args, actor)
    domain.check(doc, operation, args)
    # 마스터 밖의 이름(콘솔 관리자)이면 「담당자만」은 Center가 결재 담당자로 이미 막았다 — 업무
    # 기록은
    # 그 결재의 담당으로 적고, 실제로 답한 이름은 감사 이력에 남긴다(장면 1·2와 같은 태도).
    effective = by if known else domain.assignee_of(doc, node_id)
    out = domain.apply(doc, seed, operation, args, by=effective, strict=known)
    if not known:
        domain.audit(doc, actor=by, action="answer_by_outside_master", node_id=node_id)
    if args.get("answered_via"):
        domain.audit(doc, actor=by, action="answer_via", node_id=node_id, via=args["answered_via"])
    domain.ensure_task(doc, node_id)
    domain.complete_task(doc, node_id, actor=effective)
    _follow_script(doc, seed, node_id)
    _landed(doc, node_id)
    return {**out, "error_message": None}


class _InProcessCalls:
    """내장 실행기의 `chk:serviceCall` → 도메인 함수. 업무 규칙 위반은 상태 코드째 들고 나간다."""

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


class Sc05Process:
    def __init__(
        self,
        store: Sc01Store,
        sc04: Sc04Process,
        *,
        seed: Seed | None = None,
        publish: Callable[[str], None] = lambda _id: None,
        center: CenterClient | None = None,
        center_wait_s: float = CENTER_WAIT_S,
    ) -> None:
        """`center`를 주지 않으면 장면 4의 것을 쓴다(같은 Center·같은 키)."""
        self.store = store
        self.sc04 = sc04
        self.seed = seed or load_seed()
        self.process = read_process(PROCESS_PATH.read_bytes())
        self.engine = Engine()
        self.publish = publish
        self.center = center or sc04.center or CenterClient(CenterConfig())
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
            raise DomainError(f"결정 실행·계획 갱신이 시작되지 않은 데모 실행: {demo_run_id}", 404)
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
            domain.sync_tasks(doc, dict(doc["bpm"]["snapshot"]["pendings"]))
        try:
            self.store.save(doc["demo_run_id"], doc, version, event)
        except StaleWrite as exc:
            raise DomainError("다른 요청이 먼저 바꿨다 — 새로 고친 뒤 다시 하라", 409) from exc
        self.publish(f"sc05:{doc['demo_run_id']}")
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
        """화면 답의 사전 검사 — 역할·담당(403), 그리고 기록 작업과 같은 업무 규칙(409·422)."""
        domain.check_actor(doc, node_id, actor)
        operation, args = self.answer_args(node_id, answer)
        domain.check(doc, operation, args)

    # ───────────── 시작 ─────────────

    def _finish_sc04(self, demo_run_id: str | None, executor: str) -> dict:
        """
        장면 4를 완료까지 — 각본의 남은 단계를 실제로 실행한다(장면 4가 없으면 장면 1부터). Center면
        각본이 대리
        답한다. Studio는 각본이 답할 수 없다 — Studio에서 완료까지 진행한 뒤 장면 5를 시작한다.
        """
        found = None if demo_run_id is None else self.sc04.store.load(demo_run_id)
        if found is None:
            doc = self.sc04.create(sc01_demo_run_id=demo_run_id, executor=executor)
        else:
            doc = found[0]
        rid = doc["demo_run_id"]
        if doc["review"]["state"] == "SC04_COMPLETED":
            return doc
        if executor_of(doc) == "studio":
            raise DomainError(
                (
                    "개선안 검토·실행 승인이 Studio 시험 실행이다 — Studio에서 개선안 검토·실행 "
                    "승인 완료까지 진행한 뒤 결정 실행·계획 갱신을 "
                    "시작한다"
                ),
                409,
            )
        steps = sc04_demo.steps_for(doc["case_id"], self.sc04.seed)
        try:
            for i in range(doc.get("script_index", -1) + 1, len(steps)):
                doc = sc04_demo.run_step(self.sc04, rid, i)
                if executor_of(doc) == "center":
                    self.sc04.sync_center(rid)
        except DomainError as exc:
            raise DomainError(
                f"개선안 검토·실행 승인을 각본으로 완료까지 끝낼 수 없다 — {exc}. 개선안 검토·실행 "
                "승인을 초기화한 뒤 다시 한다",
                409,
            ) from exc
        deadline = time.monotonic() + self.center_wait_s
        doc = self.sc04.get(rid)
        while doc["review"]["state"] != "SC04_COMPLETED" and time.monotonic() < deadline:
            time.sleep(min(0.5, self.center_wait_s))
            doc = self.sc04.get(rid)
        if doc["review"]["state"] != "SC04_COMPLETED":
            raise DomainError(
                "개선안 검토·실행 승인 각본을 다 돌렸지만 아직 완료가 기록되지 않았다 — 바깥 "
                "실행이 완료 "
                "기록을 부를 때까지 "
                "기다린 뒤 다시 시작한다",
                409,
            )
        return doc

    def create(
        self,
        *,
        sc01_demo_run_id: str | None = None,
        case_id: str = "BASE",
        actor: str = "u-demo",
        executor: str = "embedded",
    ) -> dict:
        """
        장면 5 데모 실행. 데모 실행 id가 없으면 장면 1부터 새로 만든다 — X 사례는 **별도 데모
        실행**이다.
        이미 있으면 그대로 돌려준다(같은 사례일 때).
        """
        if case_id not in domain.CASES:
            raise DomainError(f"모르는 시연 사례: {case_id} (가능: {', '.join(domain.CASES)})", 422)
        if sc01_demo_run_id is not None:
            existing = self.store.load(sc01_demo_run_id)
            if existing is not None:
                if existing[0]["case_id"] != case_id:
                    raise DomainError(
                        f"이 데모 실행의 결정 실행·계획 갱신은 이미 {existing[0]['case_id']}다 — "
                        "다른 사례는 새 실행으로",
                        409,
                    )
                return existing[0]
        sc04_doc = self._finish_sc04(sc01_demo_run_id, executor)
        baseline = domain.baseline_from_sc04(sc04_doc)
        rid = sc04_doc["demo_run_id"]
        doc = domain.new_demo_run(
            self.seed,
            rid,
            case_id=case_id,
            created_at=datetime.now(UTC),
            baseline=baseline,
            executor=executor,
        )
        domain.audit(
            doc,
            actor=actor,
            action="sc05_started",
            event_code="D500",
            case_id=case_id,
            executor=executor,
            sc04_handoff=baseline["handoff"]["handoff_id"],
        )
        self.store.insert(rid, doc)
        self.publish(f"sc05:{rid}")
        return doc

    def get(self, demo_run_id: str) -> dict:
        return self._load(demo_run_id)[0]

    def reset(self, demo_run_id: str, *, actor: str, executor: str | None = None) -> dict:
        """
        선택 실행만 D500으로 — 장면 4 기준(스냅샷)·다른 실행은 그대로다. Center 앞 작업은 거둔다.
        """
        _require(actor, "시연관리자")
        with self._lock(demo_run_id):
            old, version = self._load(demo_run_id)
            old_job = (((old["bpm"] or {}).get("center") or {}).get("job") or {}).get("job_id")
            where = executor or executor_of(old)
            doc = domain.new_demo_run(
                self.seed,
                demo_run_id,
                case_id=old["case_id"],
                created_at=datetime.fromisoformat(old["created_at"]),
                baseline=old["sc04"],
                executor=where,
            )
            doc["audit"] = old["audit"]
            domain.audit(
                doc, actor=actor, action="demo_run_reset", event_code="D500", executor=where
            )
            if old_job and not self.center.config.missing(integration=True):
                self._cancel_center_job(doc, old_job)
            return self._commit(doc, version, None, "reset")

    # ───────────── 조작 ─────────────

    def set_clock(
        self, demo_run_id: str, at: str, *, actor: str, event_code: str | None = None
    ) -> dict:
        """
        가상시계 이동 — 시각만 옮긴다. 승인·착수를 만들지 않는다(구현명세 16장). 그 시각까지의 배경
        원천이 들어오고,
        넘긴 기한엔 알림.
        """
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
            domain.catch_up(doc, self.seed)
            domain.raise_overdue_alerts(doc)
            return self._commit(doc, version, None, event_code or "clock")

    def mark(self, demo_run_id: str, *, event_code: str, script_index: int, note: str = "") -> dict:
        """
        각본의 조회 단계 — 상태를 바꾸지 않고 진행 지점만 남긴다(지난 시점으로 돌아올 수 있게).
        """
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            _mark(doc, event_code, script_index)
            domain.audit(
                doc, actor="u-demo", action="demo_viewed", event_code=event_code, note=note
            )
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
        S01 착수 — HANDOFF41을 잇고 BPM을 시작한다(내장 시작 · Center 기동 · Studio는 착수만).
        **재착수는 기존
        결과를 돌려준다**(장면 중복 생성 금지 — 새 실행·이벤트 없음).
        """
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if check_idempotency(doc, idempotency_key, ["start"]):
                return doc
            if not domain.start_scene(doc, by=actor):
                return doc
            executor = executor_of(doc)
            if executor != "embedded":
                if executor == "center":
                    self._center_start(doc, actor=actor)
                _mark(doc, event_code, script_index)
                if script_index is None:
                    _follow_script(doc, self.seed, "start")
                return self._commit(doc, version, None, event_code or "start")
            calls = _InProcessCalls(doc, self.seed, actor)
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
            if script_index is None:
                _follow_script(doc, self.seed, "start")
            return self._commit(doc, version, run, event_code or "start")

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
        사람 대기 하나에 답한다. `expect` — 화면이 본 계획
        버전(`plan`)·검토안(`forecast`)·산정본(`run`).
        오래된 것에 대한 확정·확인·승인은 409다. Center면 대리 답, Studio면 409.

        **착수·대표 승인 요청·장면 완료는 대기가 아니어도 요건을 먼저 다시 본다** — 품의 미승인에서
        착수를 누르면
        「대기가 아니다」가 아니라 남은 요건(422 START_BLOCKED)을 돌려준다(T505·T523·T531).
        """
        current = self.get(demo_run_id)
        if node_id in GATED:
            GATED[node_id](current, self.answer_args(node_id, answer)[1])
        if node_id == "Complete_Scene":
            domain.check_complete(current, self.answer_args(node_id, answer)[1])
        executor = executor_of(current)
        if executor == "center":
            return self._relay(
                demo_run_id,
                node_id,
                answer,
                actor=actor,
                expect=expect,
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
            if check_idempotency(doc, idempotency_key, ["act", node_id, actor, answer, expect]):
                return doc
            if doc["bpm"] is None:
                raise DomainError("아직 착수하지 않았다", 409)
            calls = _InProcessCalls(doc, self.seed, actor)
            run = self._restore(doc, calls)
            pending = next((p for p in run.pendings.values() if p.node_id == node_id), None)
            if pending is None:
                waiting = ", ".join(sorted(p.node_id for p in run.pendings.values())) or "없음"
                raise DomainError(f"{node_id}는 지금 기다리는 업무가 아니다 (대기: {waiting})", 409)
            _check_expect(doc, node_id, expect or {})
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
        시스템 작업 — 바깥 BPM의 서비스 태스크 일감을 C15 일꾼이 가져와 부른다
        (장면 2 `operate`와 같다). 첫 호출이 데모
        실행을 묶고, 기록이 거절되면 거절만 남기고(반쯤 적힌 효과는 버린다) 상태 코드를 낸다 —
        그림은 같은
        결재로 돌아간다.
        """
        if operation not in OPERATIONS:
            raise DomainError(f"모르는 작업: {operation} (가능: {', '.join(OPERATIONS)})", 404)
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            link_external_run(doc, external_run_id, via=via)
            try:
                try:
                    out = run_operation(doc, self.seed, operation, args)
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
                )
                if args.get("node_id"):
                    _landed(doc, str(args["node_id"]))
                self._commit(doc, version, None, f"{operation}:rejected")
                raise
            decided = args.get("node_id") if operation in RECORDS else None
            ends = domain.ends_flow(operation) and executor_of(doc) == "studio"
            note_external_progress(doc, node_id, decided=decided, done=ends)
            self._commit(doc, version, None, operation)
        return out

    # ───────────── BPM 밖의 명령 ─────────────

    def _command(self, demo_run_id: str, event: str, fn: Callable[[dict], Any]) -> dict:
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            fn(doc)
            return self._commit(doc, version, None, event)

    def agent(
        self,
        demo_run_id: str,
        kind: str,
        *,
        actor: str,
        event_code: str | None = None,
        script_index: int | None = None,
    ) -> dict:
        """AG51~AG58 — 그 단계의 업무 담당이 요청한다. 실패해도 업무는 그대로다(수동 작성, T530)."""
        if actor not in USERS or actor == "u-demo":
            raise DomainError("Agent 초안은 업무 역할이 요청한다", 403)

        def do(doc: dict) -> None:
            domain.agent_draft(doc, kind=kind)
            _mark(doc, event_code, script_index)

        return self._command(demo_run_id, event_code or "agent", do)

    def review_agent(
        self,
        demo_run_id: str,
        output_id: str,
        *,
        actor: str,
        note: str = "",
        event_code: str | None = None,
        script_index: int | None = None,
    ) -> dict:
        """제안 검토 기록 — 원 초안은 그대로, 검토자·시각만. 업무 확인·승인을 대신하지 않는다."""

        def do(doc: dict) -> None:
            domain.review_agent(doc, output_id, actor=actor, note=note)
            _mark(doc, event_code, script_index)

        return self._command(demo_run_id, event_code or "agent_review", do)

    # ───────────── Center 실행 (장면 1·2와 같다) ─────────────

    def _center_start(self, doc: dict, *, actor: str) -> None:
        """
        착수 → SC05 패키지 기동. 설정이 없으면 기동하지 않고 사유를 남긴다(착수 자체는 막지 않는다).
        """
        ledger = doc["bpm"].setdefault("center", new_center_ledger())
        problem = self.center.config.missing(integration=True)
        if problem:
            ledger["problem"] = f"{problem} — SC05를 기동하지 않았다. Center에서 직접 기동하라"
            return
        old = (ledger.get("job") or {}).get("job_id")
        if old:
            self._cancel_center_job(doc, old)
        try:
            job = self.center.start_job(
                {"데모실행ID": doc["demo_run_id"]},
                idempotency_key=_center_key(doc),
                on_behalf=name_of(actor),
                package=self.center.config.sc05_package,
                note="NowView SC05 — 결정 실행과 계획 갱신 착수",
            )
        except CenterError as exc:
            raise exc.as_domain("SC05 기동") from exc
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
        expect: dict[str, Any] | None,
        event_code: str | None,
        script_index: int | None,
        idempotency_key: str | None,
    ) -> dict:
        """Center 실행의 화면 답 = 대리 답. 사전 검사 → 열린 그 사람의 결재 → 답. 효과는 기록
        작업이 낸다."""
        problem = self.center.config.missing(relay=True)
        if problem:
            raise DomainError(
                "이 데모 실행은 Center 서버 실행이 돈다 — 결재는 Center 결재함에서 답하라 — "
                f"{problem}",
                503,
            )
        body = ["act", node_id, actor, answer, expect]
        doc = self.get(demo_run_id)
        if check_idempotency(doc, idempotency_key, body):
            return doc
        name = name_of(actor)
        try:
            _check_expect(doc, node_id, expect or {})
            self.precheck(doc, node_id, answer, actor)
        except DomainError as exc:
            if exc.status != 409:
                raise
            # 앞 결재 뒤의 기록·계산 작업을 실행기가 아직 부르지 않았을 수 있다(장면 2·3
            # 실측). 이 결재가 열렸으면 앞 작업은 끝났다 — 다시 본다. 아직 Center에 답하기 전이다.
            try:
                self._await_approval(demo_run_id, node_id, name)
            except DomainError:
                raise exc from None  # 결재가 열리지 않는다 — 처음 사유가 맞다
            doc = self.get(demo_run_id)
            _check_expect(doc, node_id, expect or {})
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
            # (각본 실측: 늦게 연 업무가 장면 3 8/18 · 장면 4 11/24 · 장면 5 12/46건).
            if domain.task_for_node(doc, node_id) is None:
                domain.sync_tasks(doc, {approval["request_id"]: {"node_id": node_id}})
            bpm = doc["bpm"]
            bpm["center"]["relayed"].append(approval["request_id"])
            # 이 결재의 기록 작업은 실행기가 따로 부른다(약 10초 — 화면 직접 진행 실측). 그동안 폼은
            # 사라지고 다음 업무는 아직이라 화면이 비었다 — 「반영 중」으로 보인다(장면 3과 같다).
            bpm["center"].setdefault("inflight", []).append(node_id)
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
            if script_index is not None:
                # 각본이 대리 답했다 — 실행기가 나중에 부르는 이 결재의 기록은 각본 몫이다
                _script_follow(doc)["pending"].append(node_id)
                _follow_script(doc, self.seed, None)
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
        bpm = doc["bpm"] or {}
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
            rid: self._approval_entry(doc, rid, nid)
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
            domain.sync_tasks(doc, {rid: {"node_id": e["node_id"]} for rid, e in opened.items()})
            self._commit(doc, version, None, "center_progress")
        return True

    def _approval_entry(self, doc: dict, request_id: str, node_id: str) -> dict[str, Any]:
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
        if node_id not in domain.NODE_ROLES or self.center.config.missing(relay=True):
            return entry
        info = self.center.approval(request_id, on_behalf=name_of(domain.assignee_of(doc, node_id)))
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
    """Center 멱등 키 — 초기화 회차를 넣는다(장면 1~4와 같은 함정)."""
    generation = sum(1 for a in doc["audit"] if a["action"] == "demo_run_reset")
    return f"sc05:{doc['demo_run_id']}:r{generation}:start"


def _check_expect(doc: dict, node_id: str, expect: dict[str, Any]) -> None:
    """
    화면이 본 버전 — 계획(`plan`), 검토안(`forecast`), 산정본(`run`). 그 사이 바뀌었으면
    409(VERSION_CONFLICT).
    """
    plan = expect.get("plan")
    if plan is not None:
        current = domain.current_plan(doc)
        if current is None or current["plan_id"] != plan:
            raise DomainError(f"본 계획({plan})이 최신이 아니다 — 새로 고친 뒤 다시 한다", 409)
    forecast = expect.get("forecast")
    if forecast is not None:
        current = domain.review_forecast(doc)
        if current is None or current["forecast_id"] != forecast:
            raise DomainError(f"본 검토안({forecast})이 최신이 아니다 — 다시 본다", 409)
    run = expect.get("run")
    if run is not None:
        current = domain.review_forecast(doc)
        if current is None or current["run_id"] != run:
            raise DomainError(f"본 산정본({run})이 최신이 아니다 — 다시 확인한다", 409)


def _landed(doc: dict, node_id: str) -> None:
    """대리 답한 결재의 기록이 왔다(적혔든 거절됐든) — 「반영 중」에서 뺀다."""
    inflight = ((doc.get("bpm") or {}).get("center") or {}).get("inflight")
    if inflight and node_id in inflight:
        inflight.remove(node_id)


def _script_follow(doc: dict) -> dict[str, list[str]]:
    return doc.setdefault("script_follow", {"ahead": [], "pending": []})


def _follow_script(doc: dict, seed: Seed, done: str | None) -> None:
    """
    화면에서 직접 한 일도 각본의 진행 표시(`step`·`script_index`)를 옮긴다 — 장면 3과 같다.
    안 그러면 손으로 착수·계획 확정을 해도 플레이어가 D500에 머물고, 「다음」이 「단계를 건너뛸
    수 없다 — 다음은 0번이다」로 멈췄다(2026-10-28 화면 직접 진행 실측). 효과가 난 자리(기록
    작업)에서 부르므로 내장·Studio·Center가 같다.

    화면이 한 결정을 `ahead`에 모으고, 각본의 다음 결재가 거기 있으면 그것과 그 앞의 비결재
    단계(Agent·검토·조회)를 함께 지나간다 — 조건·품의 결재는 병렬이라 순서가 바뀌고, 사이의 Agent
    요청은 화면에서 건너뛰어도 된다. 대표 변경 고리의 결재(접수·공유·확인·대응·발주)는 각본에 두 번
    나오지만 결정마다 하나씩 쓰므로 순서대로 맞는다. Center 각본이 대리 답한 결재의 기록은
    `pending`에 있어 각본 몫으로 지운다.
    """
    from app.sc05.demo import steps_for  # demo가 이 모듈을 가져온다

    follow = _script_follow(doc)
    if done is not None:
        if done in follow["pending"]:
            follow["pending"].remove(done)
        else:
            follow["ahead"].append(done)
    steps = steps_for(doc["case_id"], seed)
    i = doc.get("script_index", -1) + 1
    moved = None
    while i < len(steps):
        step = steps[i]
        key = "start" if step.kind == "start" else step.node_id if step.kind == "act" else None
        if key is not None:
            if key not in follow["ahead"]:
                break
            follow["ahead"].remove(key)
            moved = i
        i += 1
    if moved is not None:
        doc["step"] = steps[moved].code
        doc["script_index"] = moved


def _mark(doc: dict, event_code: str | None, script_index: int | None) -> None:
    if event_code:
        doc["step"] = event_code
    if script_index is not None:
        doc["script_index"] = script_index


def _require(user_id: str, role: str) -> None:
    user = USERS.get(user_id)
    if user is None or user["role"] != role:
        raise DomainError(f"행위자는 {role}여야 한다 (받은 값: {user_id or '없음'})", 403)


__all__ = ["OPERATIONS", "RECORDS", "Sc05Process", "run_operation"]
