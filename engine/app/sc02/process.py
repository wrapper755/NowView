"""
SC02 실행 — `processes/sc02.bpmn`을 **Studio 시험 실행·Center 서버 실행**이 돌고, NowView는 서비스
태스크가 부르는 시스템 작업(외부 확장 `nowview-sc02`)으로 업무를 적는다. SC01의 N1~N6과 같은 틀이다
(`docs/chaeksas-integration.md`).

* **실행 위치는 데모 실행을 만들 때 정한다**(`bpm.executor`). 첫 작업 호출의 `{{run_id}}`가 데모
  실행을 그 실행에 묶는다(`link_external_run`). 어느 키로 왔는지가 실행 위치다(N6) — 선언과 어긋나면
  409.
* **Center**: 요청 접수가 SC02 패키지를 기동하고(`POST /jobs`), 화면 답은 대리 답이며(사전 검사가
  먼저), 진행은 실행 기록을 폴링한다. **Studio**: 결재는 Studio에서 답한다 — 화면은 읽기만 한다.
* **내장 실행기도 남아 있다** — 같은 그림·같은 작업 함수를 같은 프로세스에서 돈다. 화면은 고르지
  않고 시험이 흐름·숫자를 잠그는 데 쓴다(2026-10-27 결정).

**장면 2는 장면 1 인계에서 시작한다.** 데모 실행 id가 장면 1과 같다. 장면 1이 아직 인계 전이면 장면
1 각본을 끝까지 실제로 실행한 뒤 시작한다 — 지름길로 「인계됨」을 만들지 않는다(4.1의 원칙).
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

from app.sc01 import demo as sc01_demo
from app.sc01 import process as sc01_process
from app.sc01.center import CenterClient, CenterConfig, CenterError
from app.sc01.domain import (
    EXECUTOR_LABEL,
    USERS,
    DomainError,
    check_idempotency,
    executor_of,
    link_external_run,
    name_of,
    new_center_ledger,
    note_external_progress,
    parse_at,
    user_for_role,
    user_id_of,
)
from app.sc01.process import Sc01Process, read_run_events
from app.sc01.store import Sc01Store, StaleWrite
from app.sc02 import domain
from app.sc02.seed import Seed, load_seed

PROCESS_PATH = Path(__file__).resolve().parents[2] / "processes" / "sc02.bpmn"
APP_ID = "nowview-sc02"
#: 사람 결정 뒤의 기록 작업 — 캔버스가 결재 노드에 접어 그린다(`view.topology`). 거절되면 그림의
#: 오류 경계가 같은 결재로 되돌린다(`Bnd_Record_*`).
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
#: 결재 뒤의 계산 작업 — 기록 작업처럼 그 결재를 지나왔고 그 업무를 닫는다.
DECIDED_BY = {"analyze_request": "Confirm_Analysis", "analyze_negotiation": "Confirm_Reanalysis"}
#: 대리 답할 결재가 Center에 열리기를 기다리는 시간(초) — SC01과 같다.
CENTER_WAIT_S = sc01_process.CENTER_WAIT_S

log = logging.getLogger(__name__)


def _by(args: dict[str, Any], actor: str | None) -> tuple[str, bool]:
    """
    답한 사람(결재의 `answered_by_as` 변수) → (id 또는 이름, 마스터 안인가). **마스터 밖의 이름은
    거절하지 않고 그대로 적는다** — 콘솔 관리자·Studio 「시험 케이스」는 정상 경로에서 온다(SC01
    `_answerer`와 같다).
    """
    given = args.get("answered_by") or actor
    if not given:
        raise DomainError("답한 사람(answered_by)이 없다", 422)
    try:
        return user_id_of(str(given)), True
    except DomainError:
        return str(given), False


#: 작업 입력 → 결재 칸 — 기록 작업이 사전 검사(`domain.check_answer`)를 **다시** 한다. Center
#: 콘솔·Studio 대화상자의 답은 NowView 사전 검사를 거치지 않는다(SC01 N1과 같다). 검사가 부수
#: 효과보다 먼저다.
_ANSWER_OF = {
    "record_verification": ("Verify_Request", {"확인결과": "result"}),
    "record_report": ("Report_Lead", {"검토필요성": "need"}),
    "analyze_request": ("Confirm_Analysis", {"내부제시단가": "offer_price", "협상기한": "due_at"}),
    "analyze_negotiation": ("Confirm_Reanalysis", {}),
    "record_negotiation": (
        "Record_Negotiation",
        {"협상결과": "outcome", "협상단가": "price", "협상적용일": "effective_date"},
    ),
    "submit_proposal": (
        "Draft_Proposal",
        {
            "기안단가": "price",
            "기안적용일": "effective_date",
            "인상필요성": "reason",
            "차이사유": "diff_reason",
        },
    ),
    "record_decision": (
        None,
        {
            "결정": "decision",
            "결재의견": "comment",
            "지시요구조건": "condition",
            "지시기한": "due_at",
        },
    ),
    "register_cost": ("Register_Cost", {"대조결과": "check"}),
    "request_handoff": ("Request_Handoff", {"경영관리담당자": "fin"}),
    "accept_handoff": ("Accept_Handoff", {"인수의견": "opinion"}),
}


def _recheck(doc: dict, seed: Seed, operation: str, args: dict[str, Any]) -> None:
    node_id, fields = _ANSWER_OF[operation]
    node_id = node_id or str(args.get("node_id") or "")
    answer = {key: args.get(arg) for key, arg in fields.items() if args.get(arg) not in (None, "")}
    domain.check_answer(doc, seed, node_id, answer)


def run_operation(
    doc: dict, seed: Seed, operation: str, args: dict[str, Any], *, actor: str | None = None
) -> dict[str, Any]:
    """
    작업 하나를 문서에 적용하고 출력을 돌려준다. 저장은 부르는 쪽이 한다. 내장 어댑터와 HTTP 길(바깥
    Chaeksas의 HTTP 어댑터)이 **같은 함수**를 쓴다 — 출력 모양이 갈라지면 BPMN의 `output` 대응이
    한쪽에서만 맞는다. 기록 작업의 `error_message: None`은 결재가 보이는 직전 거절 사유를 비운다.
    """
    if operation == "screen_request":
        errors = domain.screen_request(doc, seed, args["request_id"])
        return {"passed": not errors, "error_count": len(errors)}
    if operation == "agent_draft":
        return {"output_id": domain.agent_draft(doc, kind=args["kind"], run_id=args["run_id"])}
    if operation == "judge_authority":
        return {"ceo_required": domain.judge_authority(doc, seed)}

    by, known = _by(args, actor)
    _recheck(doc, seed, operation, args)
    if operation in DECIDED_BY:
        node_id = DECIDED_BY[operation]
        if operation == "analyze_request":
            out = domain.analyze_request(
                doc, seed, offer_price=args["offer_price"], due_at_text=args["due_at"], by=by
            )
        else:
            run = domain.analyze_negotiation(doc, seed, by=by)
            out = {"run_id": run["run_id"], "risk": run["result"]["risk"] or ""}
        domain.ensure_task(doc, node_id)
        domain.complete_task(doc, node_id, actor=by)
        return out

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
        # 마스터 밖의 이름(콘솔 관리자)이면 「담당자만」은 Center가 이미 막았다(ADR-0081).
        domain.accept_handoff(doc, opinion=args.get("opinion") or "", by=by, strict=known)
    else:  # pragma: no cover - OPERATIONS가 막는다
        raise DomainError(f"모르는 작업: {operation}", 404)
    if not known:
        domain.audit(doc, actor=by, action="answer_by_outside_master", node_id=node_id)
    if args.get("answered_via"):
        domain.audit(doc, actor=by, action="answer_via", node_id=node_id, via=args["answered_via"])
    domain.ensure_task(doc, node_id)
    domain.complete_task(doc, node_id, actor=by)
    return {**out, "error_message": None}


class _InProcessCalls:
    """
    내장 실행기의 `chk:serviceCall` → 도메인 함수. 업무 규칙 위반은 그대로 들고 나간다(상태 코드를
    잃지 않게) — 그림은 오류 경계로 같은 결재에 돌아가지만, 내장 경로는 저장하지 않고 그 거절을
    낸다.
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
        center: CenterClient | None = None,
        center_wait_s: float = CENTER_WAIT_S,
    ) -> None:
        """`center`를 주지 않으면 장면 1의 것을 쓴다(같은 Center·같은 키)."""
        self.store = store
        self.sc01 = sc01
        self.seed = seed or load_seed()
        self.process = read_process(PROCESS_PATH.read_bytes())
        self.engine = Engine()
        self.publish = publish
        self.center = center or sc01.center or CenterClient(CenterConfig())
        self.center_wait_s = center_wait_s
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    # ───────────── 공통 ─────────────

    def _lock(self, demo_run_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(demo_run_id, threading.Lock())

    def _load(self, demo_run_id: str) -> tuple[dict, int]:
        found = self.store.load(demo_run_id)
        if found is None:
            raise DomainError(f"외주 단가 인상 검토가 시작되지 않은 데모 실행: {demo_run_id}", 404)
        return found

    def _env(self, calls: _InProcessCalls, doc: dict) -> RunEnv:
        return RunEnv(services=calls, clock=lambda: parse_at(doc["clock"]))

    def _restore(self, doc: dict, calls: _InProcessCalls):
        bpm = doc["bpm"]
        log_ = RunLog(run_id=bpm["run_id"])
        return restore(bpm["snapshot"], process=self.process, log=log_, env=self._env(calls, doc))

    def _advance(self, run: Any, calls: _InProcessCalls) -> None:
        state = self.engine.run_until_blocked(run)
        # 업무 규칙 거절이면 그 사유·코드 그대로 — 그림은 오류 경계로 같은 결재에 돌아갔더라도 내장
        # 경로는 저장하지 않으므로 반쯤 적힌 효과가 없다(사전 검사가 대개 먼저 막는다).
        if calls.error is not None:
            raise calls.error
        if state is State.FAILED:
            failure = next(
                (e.data for e in reversed(run.log.events) if e.kind == "run_finished"), {}
            )
            raise DomainError(f"BPM 실행 실패: {failure.get('error_message') or failure}", 502)

    def _reached(self, node_id: str | None, state: Any) -> bool:
        """
        지나온 노드인가. 종료 이벤트는 「시작」만 기록된다 — 장면 2는 종료가 여섯이라 도달한 것을
        따로 남긴다(안 그러면 캔버스가 가지 않은 반려·재협상 종료까지 완료로 칠한다).
        """
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
                if logged.kind != "node_state":
                    continue
                if self._reached(logged.node_id, logged.data.get("state")):
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
            domain.sync_tasks(doc, dict(doc["bpm"]["snapshot"]["pendings"]), run.variables)
        try:
            self.store.save(doc["demo_run_id"], doc, version, event)
        except StaleWrite as exc:
            raise DomainError("다른 요청이 먼저 바꿨다 — 새로 고친 뒤 다시 하라", 409) from exc
        self.publish(f"sc02:{doc['demo_run_id']}")
        return doc

    # ───────────── 시작 ─────────────

    def _finish_sc01(self, sc01_id: str) -> dict:
        """
        장면 1을 인계까지 — 각본의 남은 단계를 실제로 실행한다(역할 검사·업무 규칙 그대로). Center
        실행이면 각본이 대리 답으로 답한다. Studio 시험 실행은 각본이 답할 수 없다 — Studio에서
        인계까지 진행한다.
        """
        doc = self.sc01.get(sc01_id)
        if doc["scene"] == "HANDED_OFF":
            return doc
        if executor_of(doc) == "studio":
            raise DomainError(
                "고객 생산계획 변경 대응이 Studio 시험 실행이다 — Studio에서 인계까지 진행한 뒤 "
                "외주 단가 인상 검토를 시작한다",
                409,
            )
        try:
            for i in range(doc.get("script_index", -1) + 1, len(sc01_demo.BASE)):
                doc = sc01_demo.run_step(self.sc01, sc01_id, i)
                if executor_of(doc) == "center":
                    # 접수 가상 직원이 있으면 수신 뒤 감독자 일괄 승인이 먼저다(SC01 N5)
                    self.sc01.approve_intake_for_script(
                        sc01_id, opinion="장면 2 시작 — 각본이 장면 1을 인계까지 진행"
                    )
                    try:
                        self.sc01.sync_center(sc01_id)
                    except CenterError as exc:
                        # 실행 기록은 첫 호출보다 늦게 생긴다(실측 404) — 폴러가 따라잡는다
                        log.info("장면 1 진행을 아직 못 읽었다: %s", exc)
        except DomainError as exc:
            raise DomainError(
                f"고객 생산계획 변경 대응을 각본으로 인계까지 끝낼 수 없다 — {exc}. 고객 생산계획 "
                "변경 대응을 초기화한 뒤 다시 한다",
                409,
            ) from exc
        # 바깥 실행은 마지막 인수 뒤에 인계 작업을 따로 부른다 — 잠깐 기다린다.
        deadline = time.monotonic() + self.center_wait_s
        doc = self.sc01.get(sc01_id)
        while doc["scene"] != "HANDED_OFF" and time.monotonic() < deadline:
            time.sleep(min(0.5, self.center_wait_s))
            doc = self.sc01.get(sc01_id)
        if doc["scene"] != "HANDED_OFF":
            raise DomainError(
                "고객 생산계획 변경 대응 각본을 다 돌렸지만 아직 인계가 기록되지 않았다 — "
                "바깥 실행이 인계 작업을 부를 때까지 "
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
        장면 2 데모 실행. `sc01_demo_run_id`가 없으면 장면 1 실행을 새로 만든다(같은 실행 위치로) —
        X 사례는 **별도 데모 실행**이다(ERR-21). 이미 있으면 그대로 돌려준다(같은 사례일 때).
        """
        if case_id not in domain.CASES:
            raise DomainError(f"모르는 시연 사례: {case_id} (가능: {', '.join(domain.CASES)})", 422)
        if sc01_demo_run_id is None:
            sc01_demo_run_id = self.sc01.create(actor=actor, executor=executor)["demo_run_id"]
        existing = self.store.load(sc01_demo_run_id)
        if existing is not None:
            if existing[0]["case_id"] != case_id:
                raise DomainError(
                    f"이 데모 실행의 외주 단가 인상 검토는 이미 {existing[0]['case_id']}다 — "
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
            executor=executor,
        )
        domain.audit(
            doc,
            actor=actor,
            action="sc02_started",
            event_code="D00",
            case_id=case_id,
            sc01_run=baseline["run_id"],
            executor=executor,
        )
        self.store.insert(sc01_demo_run_id, doc)
        self.publish(f"sc02:{sc01_demo_run_id}")
        return doc

    def get(self, demo_run_id: str) -> dict:
        return self._load(demo_run_id)[0]

    def reset(self, demo_run_id: str, *, actor: str, executor: str | None = None) -> dict:
        """
        선택 실행만 D00로 — 장면 1 기준(스냅샷)·시드·다른 실행은 그대로다(ERR-21). 이력은 남긴다.
        실행 위치를 바꿔 다시 시작할 수 있다. Center에 기동한 앞 작업은 거둔다(고아로 남지 않게).
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
                baseline=old["sc01"],
                executor=where,
            )
            doc["audit"] = old["audit"]
            domain.audit(
                doc, actor=actor, action="demo_run_reset", event_code="D00", executor=where
            )
            if old_job and not self.center.config.missing(integration=True):
                self._cancel_center_job(doc, old_job)
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
        """
        S01 요청 접수. 내장이면 BPM을 시작하고, Center면 SC02 패키지를 기동한다(`POST /jobs`).
        Studio면 요청만 등록한다 — Studio 시험 실행이 시작한다. 같은 공문·같은 내용의 재수신은 기존
        요청을 돌려준다(U21-03).
        """
        _require(actor, "구매담당")
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if check_idempotency(doc, idempotency_key, ["receive", fixture_id]):
                return doc
            request_id, created = domain.receive_request(doc, self.seed, fixture_id, actor=actor)
            if not created:
                return doc
            executor = executor_of(doc)
            if executor != "embedded":
                if executor == "center":
                    self._center_start(doc, request_id, actor=actor)
                _mark(doc, event_code, script_index)
                return self._commit(doc, version, None, event_code or "receive")
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
        버전에 대한 승인·인수는 409다. Center면 대리 답, Studio면 409(Studio에서 답한다).
        """
        executor = executor_of(self.get(demo_run_id))
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
        시스템 작업을 HTTP로 — 바깥 BPM(Chaeksas HTTP 어댑터)이 서비스 태스크에서 부른다(SC01
        `operate`와 같다). 첫 호출의 `external_run_id`가 데모 실행을 묶고, 다른 실행·내장 데모
        실행이면 409. 기록이 거절되면 거절만 남기고(반쯤 적힌 효과는 버린다) 상태 코드를 낸다 —
        그림은 같은 결재로 돌아간다.
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
                if operation not in RECORDS and operation not in DECIDED_BY:
                    raise
                doc, version = self._load(demo_run_id)
                link_external_run(doc, external_run_id, via=via)
                domain.audit(
                    doc,
                    actor="system",
                    action="answer_rejected",
                    node_id=args.get("node_id") or DECIDED_BY.get(operation) or operation,
                    status=exc.status,
                    reason=str(exc),
                )
                self._commit(doc, version, None, f"{operation}:rejected")
                raise
            decided = DECIDED_BY.get(operation) or (
                args.get("node_id") if operation in RECORDS else None
            )
            # Studio는 끝을 작업 호출로만 안다. Center는 실행 기록의 `run_finished`로 안다 — 여기서
            # 끝냈다고 적으면 폴링이 멈춰 도달한 종료를 읽지 못한다.
            ends = domain.ends_flow(operation, args) and executor_of(doc) == "studio"
            note_external_progress(doc, node_id, decided=decided, done=ends)
            self._commit(doc, version, None, operation)
        return out

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

    # ───────────── Center 실행 (SC01 N3와 같다) ─────────────

    def _center_start(self, doc: dict, request_id: str, *, actor: str) -> None:
        """
        요청 접수 → SC02 패키지 기동. 설정이 없으면 기동하지 않고 **사유를 문서에 남긴다** — 요청
        등록 자체는 BPM 밖의 일이라 막지 않는다. Center 콘솔에서 직접 기동하면 그 실행이 첫 작업
        호출로 묶인다.
        """
        ledger = doc["bpm"].setdefault("center", new_center_ledger())
        problem = self.center.config.missing(integration=True)
        if problem:
            ledger["problem"] = f"{problem} — SC02를 기동하지 않았다. Center에서 직접 기동하라"
            return
        old = (ledger.get("job") or {}).get("job_id")
        if old:
            self._cancel_center_job(doc, old)
        try:
            job = self.center.start_job(
                {"데모실행ID": doc["demo_run_id"], "요청ID": request_id},
                idempotency_key=_center_key(doc, request_id),
                on_behalf=name_of(actor),
                package=self.center.config.sc02_package,
                note="NowView SC02 — 단가 인상 요청 접수",
            )
        except CenterError as exc:
            raise exc.as_domain("SC02 기동") from exc
        ledger.update(
            job={"job_id": job["job_id"], "request_id": request_id, "at": doc["clock"]},
            problem=None,
        )
        domain.audit(
            doc,
            actor=actor,
            action="center_job_started",
            job_id=job["job_id"],
            request_id=request_id,
        )

    def _cancel_center_job(self, doc: dict, job_id: str) -> None:
        try:
            self.center.cancel_job(job_id)
            outcome = "cancelled"
        except CenterError as exc:
            outcome = f"{exc.code}: {exc.message}"
        domain.audit(
            doc, actor="system", action="center_job_cancelled", job_id=job_id, outcome=outcome
        )

    def _precheck(
        self, doc: dict, node_id: str, actor: str, answer: dict, expect: dict | None
    ) -> None:
        domain.check_actor(doc, node_id, actor)
        _check_expect(doc, expect or {})
        domain.check_answer(doc, self.seed, node_id, answer)

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
        """
        Center 실행의 화면 답 = **대리 답**. 엔진 사전 검사(403·409·422, 입력을 지우지 않는다) →
        Center에 열린 그 사람의 결재를 찾는다 → `X-CHK-On-Behalf-Of`로 답한다. 업무 효과는 결재 뒤의
        기록 작업이 낸다.
        """
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
            self._precheck(doc, node_id, actor, answer, expect)
        except DomainError as exc:
            if exc.status != 409:
                raise
            # 앞 결재 뒤의 계산·기록 작업을 실행기가 아직 부르지 않았을 수 있다(실측 — 재분석 확인
            # 직후 상신이 「재분석이 최신이 아니다」). 결재가 열렸으면 앞 작업은 끝났다 — 다시 본다.
            try:
                self._await_approval(demo_run_id, node_id, name)
            except DomainError:
                raise exc from None  # 결재가 열리지 않는다 — 처음 사유가 맞다
            self._precheck(self.get(demo_run_id), node_id, actor, answer, expect)
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
        """
        Center에 열린 그 사람의 결재 중 이 실행·이 노드의 것 — 실행기가 올리기까지 잠깐 기다린다.
        """
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
                "Center 실행이 아직 NowView를 부르지 않았다 — 요청 검사가 끝나면 결재가 열린다", 409
            )
        raise DomainError(
            f"{node_id}는 지금 Center에서 {name}의 결재로 열려 있지 않다 "
            f"(이 실행에서 열린 것: {', '.join(seen) or '없음'})",
            409,
        )

    def poll_center(self) -> int:
        """도는 center 데모 실행마다 Center 실행 기록을 읽는다(폴러가 2초마다). 바뀐 수를 낸다."""
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
        """
        Center 실행 기록(C3) → 지나온 노드·사람 대기·토큰 위치·끝. 새로 열린 결재는 대리 답용 키로
        읽어(검토 자료·폼) 업무를 **그때** 연다. 끝났으면 도달한 종료를 지나온 노드에 남긴다(종료는
        「시작」만 기록된다).
        """
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
            for rid, entry in opened.items():
                if entry.get("variables") is not None:
                    domain.sync_tasks(doc, {rid: {"node_id": entry["node_id"]}}, entry["variables"])
            self._commit(doc, version, None, "center_progress")
        return True

    def _approval_entry(self, request_id: str, node_id: str) -> dict[str, Any]:
        """
        열린 결재 하나를 화면이 쓸 대기로. 대리 답용 키는 **그 사람이 담당인 것만** 보인다 — 장면
        2도 역할마다 한 사람이라 역할로 담당자를 안다. 읽지 못하면 그림의 폼으로 두고 업무는 열지
        않는다(기록 때 늦게 연다).
        """
        node = self.process.node(node_id)
        spec = domain.NODE_ROLES.get(node_id)
        form = node.prop("approval") if node is not None else None
        entry: dict[str, Any] = {
            "request_id": request_id,
            "node_id": node_id,
            "title": (form.title if form is not None else None) or node_id,
            "review": {},
            "fields": [f.model_dump(exclude_none=True) for f in form.fields] if form else [],
            "review_digest": None,
            "variables": None,
        }
        if spec is None or self.center.config.missing(relay=True):
            return entry
        name = name_of(user_for_role(spec["role"]))
        info = self.center.approval(request_id, on_behalf=name)
        if info is None:
            return entry
        review = dict(info.get("review") or {})
        variables: dict[str, Any] = dict(review)
        if "assignee_var" in spec:
            variables[spec["assignee_var"]] = _user((info.get("assignees") or [name])[0])
        entry.update(
            title=info.get("title") or entry["title"],
            review=review,
            fields=((info.get("form") or {}).get("fields")) or entry["fields"],
            review_digest=info.get("review_digest"),
            variables=variables,
        )
        return entry


def _user(value: Any) -> str:
    try:
        return user_id_of(str(value or ""))
    except DomainError:
        return str(value or "")


def _center_key(doc: dict, request_id: str) -> str:
    """
    Center 멱등 키 — 초기화 회차를 넣는다. SC01 `_center_key`와 같은 이유다: 없으면 초기화 전의
    작업이 그대로 돌아온다.
    """
    generation = sum(1 for a in doc["audit"] if a["action"] == "demo_run_reset")
    return f"sc02:{doc['demo_run_id']}:r{generation}:{request_id}:start"


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


__all__ = ["EXECUTOR_LABEL", "OPERATIONS", "RECORDS", "Sc02Process", "run_operation"]
