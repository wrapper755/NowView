"""
SC01 실행 — Chaeksas BPM 엔진(`chaeksas.core.engine`)을 라이브러리로 돌린다.

**Chaeksas는 그림을 해석하고 사람을 기다린다. 숫자는 모른다.** 서비스 태스크가 부르는
`nowview.sc01` 앱은 이 모듈 안의 어댑터(`_InProcessCalls`)다 — 네트워크를 타지 않는다.
Center·서버 실행기는 쓰지 않는다: 정의 변경마다 패키지 서명·배포가 필요하고, 결재 응답은
관리자 토큰으로만 되고, 작업 결과 값을 돌려주지 않아 화면이 결과를 읽을 길이 없다.

한 번의 조작 = 문서를 읽고 → 실행을 되살리고 → 조작하고 → 사람 대기를 업무로 옮기고 →
문서·스냅샷을 **한 번에** 저장한다. 같은 데모 실행의 조작은 잠금으로 줄을 세우고, 워커
사이는 `row_version`이 막는다.

**Agent 초안은 잠금 밖에서 만든다.** LLM은 수십 초가 걸린다 — 조작의 잠금을 쥔 채 기다리면 같은
데모 실행의 다른 조작이 모두 멈추고, 요청 안에서 기다리면 프록시가 끊는다(CLAUDE.md 4.15).
저장이 끝난 뒤 작업을 던지고, 결과는 다시 잠금을 잡아 기록한다.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from chaeksas.contracts.bpmn_ext import read_process
from chaeksas.core.engine import Engine, EngineError, RunEnv, State, new_run_id
from chaeksas.core.run_log import RunLog
from chaeksas.core.run_snapshot import dump, restore
from chaeksas.core.services import OpCall, OpOutcome, ServiceCallError

from app.sc01 import agent, domain
from app.sc01.domain import USERS, DomainError
from app.sc01.seed import Seed, load_seed
from app.sc01.store import Sc01Store, StaleWrite

PROCESS_PATH = Path(__file__).resolve().parents[2] / "processes" / "sc01.bpmn"
APP_ID = "nowview.sc01"
#: 초안 결과를 기록할 때 다른 워커와 부딪히면 다시 읽어 쓰는 횟수.
SAVE_RETRIES = 5


def _now_real() -> str:
    return datetime.now(UTC).isoformat()


def request_draft(doc: dict, seed: Seed, run_id: str, *, actor: str, manual: bool) -> str:
    payload = agent.build_input(doc, run_id, seed.rules)
    return domain.request_agent(
        doc,
        run_id,
        payload=payload,
        payload_hash=agent.input_hash(payload),
        mode=doc.get("agent_mode", "mock"),
        actor=actor,
        manual=manual,
        now_real=_now_real(),
    )


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
            elif request.operation == "request_agent_draft":
                output_id = request_draft(
                    self.doc, self.seed, args["run_id"], actor="system", manual=False
                )
                out = {"output_id": output_id}
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
        agent_factory: Callable[[str], agent.Runner] = agent.runner_for,
        agent_mode: str | None = None,
        executor: Executor | None = None,
        inline_agent: bool = False,
    ) -> None:
        """
        `inline_agent=True`면 초안 작업을 조작이 끝난 직후 같은 스레드에서 돈다 — 테스트용이다.
        운영에서는 스레드 풀이다.
        """
        self.store = store
        self.seed = seed or load_seed()
        self.process = read_process(PROCESS_PATH.read_bytes())
        self.engine = Engine()
        self.publish = publish
        self.agent_factory = agent_factory
        self.agent_mode = agent_mode or agent.default_mode()
        self.executor = None if inline_agent else (executor or ThreadPoolExecutor(2, "sc01-agent"))
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
        doc, version = found
        return domain.upgrade(doc), version

    def _env(self, doc: dict) -> RunEnv:
        # 가상시계 — 타이머·기한·감사 이력이 모두 데모 실행의 시각을 쓴다(구현명세 2장).
        return RunEnv(
            services=_InProcessCalls(doc, self.seed), clock=lambda: domain.parse_at(doc["clock"])
        )

    def _restore(self, doc: dict):
        bpm = doc["bpm"]
        log = RunLog(run_id=bpm["run_id"])
        return restore(bpm["snapshot"], process=self.process, log=log, env=self._env(doc))

    def _start(self, doc: dict, source_id: str):
        run_id = new_run_id(now=domain.parse_at(doc["clock"]))
        return self.engine.start(
            self.process,
            run_id=run_id,
            log=RunLog(run_id=run_id),
            env=self._env(doc),
            executor="server_runner",
            inputs={"데모실행ID": doc["demo_run_id"], "원천ID": source_id},
            now=domain.parse_at(doc["clock"]),
        )

    def _commit(self, doc: dict, version: int, run: Any | None, event: str) -> dict:
        if run is not None:
            # 지나온 노드를 누적한다 — 기록(RunLog)은 조작마다 새로 열리고 스냅샷은 현재
            # 위치만 들고 있어, 쌓아 두지 않으면 캔버스가 "어디를 지나왔나"를 그릴 수 없다.
            visited = list((doc.get("bpm") or {}).get("visited", []))
            for logged in run.log.events:
                if logged.kind == "node_state" and logged.data.get("state") == "completed":
                    if logged.node_id and logged.node_id not in visited:
                        visited.append(logged.node_id)
            doc["bpm"] = {
                "run_id": run.run_id,
                "state": run.state.value,
                "snapshot": dump(run),
                "visited": visited,
                "error": None,
            }
            domain.sync_tasks(
                doc, {k: v for k, v in doc["bpm"]["snapshot"]["pendings"].items()}, run.variables
            )
        # 초안 작업 대기열은 저장하지 않는다 — 저장이 끝난 뒤 던진다(_dispatch).
        jobs = doc.pop("_agent_queue", [])
        try:
            self.store.save(doc["demo_run_id"], doc, version, event)
        except StaleWrite as exc:
            raise DomainError("다른 요청이 먼저 바꿨다 — 새로 고친 뒤 다시 하라", 409) from exc
        self.publish(f"sc01:{doc['demo_run_id']}")
        doc["_jobs"] = jobs  # 메모리에만 — 잠금을 놓은 뒤 _dispatch가 꺼낸다
        return doc

    def _dispatch(self, doc: dict) -> dict:
        """저장된 조작이 만든 초안 작업을 던진다. **잠금 밖에서** 부른다."""
        jobs = doc.pop("_jobs", [])
        for output_id in jobs:
            if self.executor is None:
                self._run_agent(doc["demo_run_id"], output_id)
            else:
                self.executor.submit(self._run_agent, doc["demo_run_id"], output_id)
        return self.get(doc["demo_run_id"]) if jobs and self.executor is None else doc

    def _advance(self, doc: dict, run: Any) -> None:
        state = self.engine.run_until_blocked(run)
        if state is State.FAILED:
            # 실패한 실행을 업무 완료로 보이게 하지 않는다 — 원인을 문서에 남긴다(1.10).
            failure = next(
                (e.data for e in reversed(run.log.events) if e.kind == "run_finished"), {}
            )
            raise DomainError(f"BPM 실행 실패: {failure.get('error_message') or failure}", 502)

    # ───────────── Agent 작업 ─────────────

    def _run_agent(self, demo_run_id: str, output_id: str) -> None:
        """
        초안 하나를 만든다 — 실패하면 **한 번 자동 재시도**하고(AG-02), 그래도 안 되면 실패로
        남긴다.
        검증을 통과하지 못한 응답은 `rejected`에만 두고 화면에 초안으로 내지 않는다.
        """
        try:
            record = self.get(demo_run_id)["agent_outputs"][output_id]
        except (DomainError, KeyError):
            return
        payload, runner = record["input"], self.agent_factory(record["mode"])
        result: dict[str, Any] = {"prompt_version": agent.PROMPT_VERSION, "errors": []}
        for attempt in (1, 2):
            result["attempts"] = attempt
            try:
                draft = runner.run(payload)
            except agent.AgentFailure as exc:
                result["errors"].append(f"{attempt}차: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 — 배경 작업은 무엇이든 삼켜지면 안 된다
                result["errors"].append(f"{attempt}차: 예기치 못한 오류 {exc}")
                continue
            result.update(
                provenance=draft.provenance, model=draft.model, latency_ms=draft.latency_ms
            )
            problems = agent.validate(draft.output, payload)
            if not problems:
                result.update(status="SUCCEEDED", draft=draft.output)
                break
            result["errors"].append(f"{attempt}차 검증 실패: " + "; ".join(problems))
            result["rejected"] = draft.output
        else:
            result["status"] = "FAILED"
        result["finished_real"] = _now_real()

        for _ in range(SAVE_RETRIES):
            with self._lock(demo_run_id):
                try:
                    doc, version = self._load(demo_run_id)
                except DomainError:
                    return
                if not domain.finish_agent(doc, output_id, result=result):
                    return  # 초기화 등으로 이미 사라졌거나 끝난 기록이다
                try:
                    self.store.save(demo_run_id, doc, version, f"agent:{output_id}")
                except StaleWrite:
                    continue  # 다른 워커가 먼저 썼다 — 다시 읽어 얹는다
            self.publish(f"sc01:{demo_run_id}")
            return

    def regenerate(self, demo_run_id: str, run_id: str, *, actor: str) -> dict:
        """담당자의 초안 재생성 요청(AG-01 호출 시점 둘째). 이전 초안은 보존한다."""
        if USERS.get(actor, {}).get("role") not in ("영업담당", "영업팀장"):
            raise DomainError("영업담당·영업팀장만 초안을 다시 요청할 수 있다", 403)
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if run_id not in doc["calc_runs"] or run_id == "RUN-F01-001":
                raise DomainError(f"초안을 만들 계산이 없다: {run_id}", 404)
            request_draft(doc, self.seed, run_id, actor=actor, manual=True)
            doc = self._commit(doc, version, None, "agent_regenerate")
        return self._dispatch(doc)

    def adopt(self, demo_run_id: str, output_id: str, *, actor: str) -> dict:
        """초안 채택 기록(AG-03). 의견란에 가져다 쓰는 것은 화면이 하고, 여기서는 사실만 남긴다."""
        _require(actor, "영업팀장")
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            domain.adopt_agent(doc, output_id, actor=actor)
            doc = self._commit(doc, version, None, "agent_adopt")
        return self._dispatch(doc)

    # ───────────── 조작 ─────────────

    def create(self, *, case_id: str = "BASE", actor: str = "u-demo") -> dict:
        if case_id not in domain.CASES:
            raise DomainError(f"모르는 시연 사례: {case_id} (가능: {', '.join(domain.CASES)})", 422)
        demo_run_id = f"demo-{uuid.uuid4().hex[:8]}"
        doc = domain.new_demo_run(
            self.seed,
            demo_run_id,
            case_id=case_id,
            created_at=datetime.now(UTC),
            agent_mode=self.agent_mode,
        )
        domain.audit(doc, actor=actor, action="demo_run_created", event_code="S0", case_id=case_id)
        self.store.insert(demo_run_id, doc)
        return doc

    def get(self, demo_run_id: str) -> dict:
        return self._load(demo_run_id)[0]

    def set_clock(
        self, demo_run_id: str, at: str, *, actor: str, event_code: str | None = None
    ) -> dict:
        """
        가상시계를 옮긴다. **시각 이동만으로 인수·승인을 실행하지 않는다**(구현명세 2장). 기한을
        넘긴 업무가 생기면 화면 내 알림을 만든다(EX07).
        """
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
            domain.raise_overdue_alerts(doc)
            doc = self._commit(doc, version, None, event_code or "clock")
        return self._dispatch(doc)

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
        """
        시연 원천 수신.

        * 처음 → BPM 시작.
        * 보완 대기 중 → 정정본을 메시지로 전달해 같은 실행에서 다시 검증한다.
        * 그 밖(계산 뒤·인계 뒤의 정정, EX03) → **이전 실행을 이력으로 옮기고 새 실행을 시작한다.**
          새 계산은 새 run이고 같은 이슈에 이어진다. 이미 인수한 업무에는 재확인을 요청한다(WF-02).
        """
        _require(actor, "영업담당")
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if domain.check_idempotency(doc, idempotency_key, ["receive", fixture_id]):
                return doc
            source_id, created = domain.receive_source(doc, self.seed, fixture_id, actor=actor)
            if not created:
                return doc  # 재수신 — 중복 등록·이슈 생성 없이 기존 접수를 돌려준다
            run = self._restore(doc) if doc["bpm"] is not None else None
            if run is not None and self.engine.message_target(run, "원천정정") is not None:
                self.engine.deliver(run, "원천정정", payload={"원천ID": source_id})
            else:
                if run is not None:
                    final = run.state.value
                    if run.state not in (State.DONE, State.FAILED):
                        self.engine.cancel(run, reason=f"정정본 {source_id} 수신으로 대체")
                        # Chaeksas의 취소는 상태가 FAILED다 — 이력에서 실패와 섞이지 않게 적는다.
                        final = "cancelled"
                    domain.supersede_bpm(doc, source_id=source_id, final_state=final)
                run = self._start(doc, source_id)
            self._advance(doc, run)
            _mark(doc, event_code, script_index)
            doc = self._commit(doc, version, run, event_code or "receive")
        return self._dispatch(doc)

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
        """사람 대기 하나에 답한다 — 확인·검토·배정·요청·인수."""
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if domain.check_idempotency(doc, idempotency_key, ["act", node_id, actor, answer]):
                return doc  # 같은 요청의 재시도 — 이미 처리했다
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
            doc = self._commit(doc, version, run, event_code or node_id)
        return self._dispatch(doc)

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
                # 검토 시점의 초안 — "AI 초안"과 "담당자 의견"을 가른다(AG-03).
                "agent_output": variables.get("초안ID") or None,
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

    def reset(self, demo_run_id: str, *, actor: str, case_id: str | None = None) -> dict:
        """현재 데모 실행만 S0로 되돌린다. 이력은 남긴다(DATA-05). 사례를 바꿔 다시 시작한다."""
        _require(actor, "시연관리자")
        if case_id is not None and case_id not in domain.CASES:
            raise DomainError(f"모르는 시연 사례: {case_id}", 422)
        with self._lock(demo_run_id):
            old, version = self._load(demo_run_id)
            case = case_id or old["case_id"]
            doc = domain.new_demo_run(
                self.seed,
                demo_run_id,
                case_id=case,
                created_at=datetime.fromisoformat(old["created_at"]),
                agent_mode=self.agent_mode,
            )
            doc["audit"] = old["audit"]
            domain.audit(doc, actor=actor, action="demo_run_reset", event_code="S0", case_id=case)
            doc = self._commit(doc, version, None, "reset")
        return self._dispatch(doc)


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
