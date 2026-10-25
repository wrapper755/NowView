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

import logging
import threading
import time
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
from app.sc01.center import CenterClient, CenterConfig, CenterError
from app.sc01.domain import USERS, DomainError
from app.sc01.seed import Seed, load_seed
from app.sc01.store import Sc01Store, StaleWrite

PROCESS_PATH = Path(__file__).resolve().parents[2] / "processes" / "sc01.bpmn"
#: 바깥 Chaeksas 외부 확장의 id와 같다 — 확장 id에는 점을 쓸 수 없다(C13 `^[a-z][a-z0-9-]{1,49}$`).
APP_ID = "nowview-sc01"
#: 초안 결과를 기록할 때 다른 워커와 부딪히면 다시 읽어 쓰는 횟수.
SAVE_RETRIES = 5
#: 대리 답할 결재가 Center에 열리기를 기다리는 시간(초). 서버 실행기가 앞 작업을 끝내고 결재를
#: 올리기까지 걸린다 — 각본이 수신 직후 원천 확인으로 넘어가도 409로 끊기지 않게 한다.
CENTER_WAIT_S = 10.0

log = logging.getLogger(__name__)


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


#: 시스템 작업 — BPMN 서비스 태스크가 부르는 것. 내장 어댑터(`_InProcessCalls`)와 HTTP
#: (`Sc01Process.operate`, 바깥 Chaeksas의 HTTP 어댑터가 부른다)가 **같은 함수**를 쓴다 —
#: 두 길의 출력 모양이 갈라지면 BPMN의 `output` 대응이 한쪽에서만 맞는다.
#: 사람 결정 뒤의 **기록** 작업. 결재를 어디서 답했든(내장·Studio·Center) 업무 효과는 이 길로만
#: 난다 — 내장 실행기의 답 훅에만 두면 바깥 실행에서 원천이 확인되지 않아 계산이 409로 막힌다
#: (docs/chaeksas-integration.md N1).
RECORDS = (
    "record_dq_review",
    "record_sales_review",
    "record_dispatch",
    "record_review_request",
    "record_acceptance",
)
OPERATIONS = ("validate_source", "compare", "request_agent_draft", "hand_off", *RECORDS)
#: 결재 노드 → 기록 작업 (HTTP `POST …/answers/{node_id}`). 계산 실행(Confirm_Calc)은 없다 — 곧바로
#: `compare`가 요청 기록을 남긴다.
RECORD_OF_NODE = {
    "Approve_DQ": "record_dq_review",
    "Approve_Sales": "record_sales_review",
    "Approve_Dispatch": "record_dispatch",
    "Approve_Review": "record_review_request",
    "Accept_PROD": "record_acceptance",
    "Accept_MAT": "record_acceptance",
    "Accept_FIN": "record_acceptance",
}


def _answerer(doc: dict, node_id: str, args: dict[str, Any], actor: str | None) -> tuple[str, bool]:
    """
    그 결재에 답한 사람과, 그것을 **짐작했는지**.

    내장 실행은 조작한 행위자를 안다. 바깥 Chaeksas는 답한 사람을 아직 변수로 넘기지 않는다
    (요청서 R1) — 그때까지는 그 결재의 담당자로 적고 짐작이라고 표시한다. 담당자만 답하게 막는 것은
    Center다(`assignees`, ADR-0081).
    """
    given = args.get("answered_by") or actor
    if given:
        return domain.user_id_of(str(given)), False
    task = domain.task_for_node(doc, node_id)
    if task is not None and task["assigned_to"]:
        return task["assigned_to"], True
    return domain.user_for_role(domain.NODE_ROLES[node_id]["role"]), True


def check_answer(
    doc: dict, node_id: str, answer: dict[str, Any], variables: dict[str, Any]
) -> None:
    """
    폼이 못 거는 업무 규칙 — **부수 효과가 없다.** 내장 경로는 답을 엔진에 넣기 전에 불러 입력을
    지우지 않고 거절하고(4.6), 기록 작업은 같은 검사를 다시 한다(Center 콘솔 답은 앞 검사를
    거치지 않는다).
    """
    if node_id == "Approve_DQ":
        source = doc["sources"].get(variables.get("원천ID") or "")
        if answer.get("확인결과") == "확인완료" and source is not None and source["errors"]:
            raise DomainError("검증 오류가 남아 있어 확인 완료할 수 없다 — 보완 요청하라", 409)
    elif node_id == "Approve_Sales":
        # 검토 완료에는 사람의 의견·근거가 있어야 한다. Agent 성공은 조건이 아니다(UI04-02).
        if (
            not str(answer.get("영업의견", "")).strip()
            or not str(answer.get("영업근거", "")).strip()
        ):
            raise DomainError("검토 의견과 근거가 필요하다", 422)
    elif node_id == "Approve_Dispatch":
        _require(_user(answer.get("생산담당자")), "생산담당", what="생산 담당")
        _require(_user(answer.get("자재담당자")), "자재담당", what="자재 담당")
    elif node_id == "Approve_Review":
        _require(_user(answer.get("경영관리담당자")), "경영관리담당", what="경영관리 담당")


def _user(value: Any) -> str:
    """폼 값(id 또는 이름) → id. 모르는 값은 그대로 둬 `_require`가 사유를 말하게 한다."""
    try:
        return domain.user_id_of(str(value or ""))
    except DomainError:
        return str(value or "")


def _record(doc: dict, operation: str, args: dict[str, Any], actor: str | None) -> dict[str, Any]:
    """
    기록 작업 하나 — 입력은 BPMN이 결재 칸을 옮겨 실은 것이다(`chk:serviceCall.input`).

    **검사가 먼저, 부수 효과가 나중이다.** 거절되면 그림의 오류 경계가 같은 결재로 되돌린다
    (N1) — 거절된 답이 업무를 열거나 감사 이력에 「기록」으로 남으면 안 된다. 출력의
    `error_message: None`은 직전 거절 사유를 비운다 — 결재가 `show`로 보이는 그 변수다(다음
    결재에 낡은 사유가 남지 않게).
    """
    node_id = args.get("node_id") or {
        "record_dq_review": "Approve_DQ",
        "record_sales_review": "Approve_Sales",
        "record_dispatch": "Approve_Dispatch",
        "record_review_request": "Approve_Review",
    }.get(operation, "")
    if node_id not in domain.NODE_ROLES:
        raise DomainError(f"기록할 결재가 아니다: {node_id or '없음'}", 422)
    if operation == "record_acceptance" and not node_id.startswith("Accept_"):
        raise DomainError(f"인수 결재가 아니다: {node_id}", 422)
    answer, variables = _record_answer(operation, args)
    check_answer(doc, node_id, answer, variables)

    by, guessed = _answerer(doc, node_id, args, actor)
    domain.audit(doc, actor=by, action="answer_recorded", node_id=node_id, guessed=guessed)
    _ensure_task(doc, node_id, args, by)
    return {**_apply_record(doc, operation, node_id, args, by), "error_message": None}


def _record_answer(operation: str, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """기록 입력 → `check_answer`가 보는 (결재 칸, 변수)."""
    if operation == "record_dq_review":
        return {"확인결과": args["result"]}, {"원천ID": args["source_id"]}
    if operation == "record_sales_review":
        return {"영업의견": args.get("opinion"), "영업근거": args.get("evidence")}, {}
    if operation == "record_dispatch":
        return {"생산담당자": args.get("prod"), "자재담당자": args.get("mat")}, {}
    if operation == "record_review_request":
        return {"경영관리담당자": args.get("fin")}, {}
    return {}, {}


def _apply_record(
    doc: dict, operation: str, node_id: str, args: dict[str, Any], by: str
) -> dict[str, Any]:
    if operation == "record_dq_review":
        if args["result"] == "확인완료":
            domain.verify_source(
                doc,
                args["source_id"],
                actor=by,
                opinion=args.get("opinion") or "",
                evidence=args.get("evidence") or "",
            )
            domain.mark_task(doc, node_id, actor=by, outcome="completed")
        else:
            domain.request_fix(doc, args["source_id"], actor=by, opinion=args.get("opinion") or "")
            domain.mark_task(doc, node_id, actor=by, outcome="needs_info")
        return {"recorded": True}

    if operation == "record_sales_review":
        run_id = args["run_id"]
        doc["reviews"][run_id] = {
            "run_id": run_id,
            "by": by,
            "at": doc["clock"],
            "opinion": args["opinion"],
            "evidence": args["evidence"],
            "manual_review": bool(args.get("manual_review")),
            # 검토 시점의 초안 — "AI 초안"과 "담당자 의견"을 가른다(AG-03).
            "agent_output": args.get("agent_output") or None,
        }
        domain.mark_task(doc, node_id, actor=by, outcome="completed")
        return {"recorded": True}

    if operation == "record_dispatch":
        prod, mat = _user(args["prod"]), _user(args["mat"])
        domain.audit(doc, actor=by, action="dispatched", prod=prod, mat=mat)
        # 인수 결재의 담당자는 **이름**이다(`chk:approval.assignees`) — 폼은 id를 고른다.
        return {"prod_name": domain.name_of(prod), "mat_name": domain.name_of(mat)}

    if operation == "record_review_request":
        fin = _user(args["fin"])
        domain.audit(doc, actor=by, action="review_requested", fin=fin)
        return {"fin_name": domain.name_of(fin)}

    if operation == "record_acceptance":
        domain.mark_task(doc, node_id, actor=by, outcome="accepted")
        return {"recorded": True}

    raise DomainError(f"모르는 기록 작업: {operation}", 404)  # pragma: no cover - RECORDS가 막는다


def reject_record(doc: dict, operation: str, args: dict[str, Any], exc: DomainError) -> None:
    """
    거절된 결정 기록을 남긴다. 그림은 오류 경계로 같은 결재에 되돌아가고, Center 결재의
    `error_message`에는 HTTP 어댑터가 본문을 버려 「…이 409를 돌려줬다」만 남는다 —
    **사유는 여기**다.
    """
    domain.audit(
        doc,
        actor="system",
        action="answer_rejected",
        node_id=args.get("node_id") or operation,
        status=exc.status,
        reason=str(exc),
    )


def _ensure_task(doc: dict, node_id: str, args: dict[str, Any], by: str) -> None:
    """
    바깥 실행의 결재를 업무로 옮긴다. 내장 실행은 사람 대기가 열릴 때 업무를 만들지만(`sync_tasks`),
    Studio 시험 실행에서는 대기가 열리는 순간을 NowView가 모른다 — 결정이 기록될 때 처음 안다. 그때
    새로 만든 업무는 **늦게 열렸다고 표시한다** — 기한 초과 판정이 그만큼 느슨하다. Center 실행은
    폴링이 결재를 읽을 때 연다(`Sc01Process.sync_center`) — 폴링보다 기록이 먼저 오면 여기서 연다.

    대기 하나의 id는 (바깥 실행, 결재, 원천·계산)이다. 정정(EX03)으로 새 실행이 오면 같은 결재도 새
    대기다 — 인수한 업무에 재확인이 걸리고, 끝난 업무에는 재검토 업무가 생긴다(내장과 같은 규칙).
    """
    spec = domain.NODE_ROLES[node_id]
    if spec["task"] is None:
        return
    if (
        domain.executor_of(doc) in ("embedded", "center")
        and domain.task_for_node(doc, node_id) is not None
    ):
        return  # 대기가 열릴 때 이미 만들었다 — 내장은 스냅샷, Center는 실행 기록 폴링(N3)
    variables = {"계산ID": args.get("run_id"), "원천ID": args.get("source_id")}
    if "assignee_var" in spec:
        variables[spec["assignee_var"]] = by
    ext = (doc["bpm"] or {}).get("run_id")
    wait_id = f"external:{ext}:{node_id}:{args.get('source_id') or args.get('run_id') or ''}"
    before = set(doc["tasks"])
    domain.sync_tasks(doc, {wait_id: {"node_id": node_id}}, variables)
    for task_id in set(doc["tasks"]) - before:
        task = doc["tasks"][task_id]
        task["opened_late"] = True
        task["history"][-1]["note"] = "바깥 실행 — 대기가 열린 시각을 모른다(결정 기록 시점에 만듦)"


def run_operation(
    doc: dict, seed: Seed, operation: str, args: dict[str, Any], *, actor: str | None = None
) -> dict[str, Any]:
    """
    작업 하나를 문서에 적용하고 출력을 돌려준다. 저장은 부르는 쪽이 한다.

    `actor`는 내장 실행이 아는 「지금 답한 사람」이다 — 바깥 실행은 `None`이다(`_answerer`).
    """
    if operation == "validate_source":
        errors = domain.validate_source(doc, seed, args["source_id"])
        return {"passed": not errors, "error_count": len(errors)}
    if operation == "compare":
        # 계산 실행 결재(Confirm_Calc)는 기록 작업 없이 곧바로 계산으로 간다 —
        # 요청 기록을 여기서 남긴다.
        by, guessed = _answerer(doc, "Confirm_Calc", args, actor)
        domain.audit(doc, actor=by, action="calculation_requested", guessed=guessed)
        return domain.compare(doc, seed, args["source_id"])
    if operation == "request_agent_draft":
        return {"output_id": request_draft(doc, seed, args["run_id"], actor="system", manual=False)}
    if operation == "hand_off":
        return {"handed_off": domain.hand_off(doc, args["run_id"])}
    if operation in RECORDS:
        return _record(doc, operation, args, actor)
    raise DomainError(f"모르는 작업: {operation} (가능: {', '.join(OPERATIONS)})", 404)


class _InProcessCalls:
    """`chk:serviceCall` → 도메인 함수. 업무 규칙 위반은 다시 불러도 같으므로 재시도하지 않는다."""

    def __init__(self, doc: dict, seed: Seed, actor: str | None = None) -> None:
        self.doc, self.seed, self.actor = doc, seed, actor

    def call(self, request: OpCall) -> OpOutcome:
        if request.app_id != APP_ID:
            raise ServiceCallError(f"모르는 앱: {request.app_id}", code="operation_not_found")
        if request.operation not in OPERATIONS:
            raise ServiceCallError(request.operation, code="operation_not_found")
        try:
            out = run_operation(
                self.doc, self.seed, request.operation, dict(request.input), actor=self.actor
            )
        except DomainError as exc:
            if request.operation in RECORDS:
                reject_record(self.doc, request.operation, dict(request.input), exc)
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
        center: CenterClient | None = None,
        center_wait_s: float = CENTER_WAIT_S,
    ) -> None:
        """
        `inline_agent=True`면 초안 작업을 조작이 끝난 직후 같은 스레드에서 돈다 — 테스트용이다.
        운영에서는 스레드 풀이다. `center`를 주지 않으면 **설정 없는** Center다 — center 데모 실행의
        대리 답·기동은 503으로 사유를 낸다(조용히 다른 길로 가지 않는다).
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
        self.center = center or CenterClient(CenterConfig())
        self.center_wait_s = center_wait_s

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

    def _env(self, doc: dict, actor: str | None = None) -> RunEnv:
        # 가상시계 — 타이머·기한·감사 이력이 모두 데모 실행의 시각을 쓴다(구현명세 2장).
        return RunEnv(
            services=_InProcessCalls(doc, self.seed, actor),
            clock=lambda: domain.parse_at(doc["clock"]),
        )

    def _restore(self, doc: dict, actor: str | None = None):
        """`actor` — 이 조작에서 답하는 사람. 결재 뒤의 기록 작업이 그 이름으로 적는다."""
        bpm = doc["bpm"]
        log = RunLog(run_id=bpm["run_id"])
        return restore(bpm["snapshot"], process=self.process, log=log, env=self._env(doc, actor))

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
                "executor": "embedded",
                "external_run_id": None,
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

    def create(
        self, *, case_id: str = "BASE", actor: str = "u-demo", executor: str = "embedded"
    ) -> dict:
        """`executor` — BPMN을 누가 도는가(N2). 내장이 아니면 엔진은 이 문서에서 step하지 않는다."""
        if case_id not in domain.CASES:
            raise DomainError(f"모르는 시연 사례: {case_id} (가능: {', '.join(domain.CASES)})", 422)
        demo_run_id = f"demo-{uuid.uuid4().hex[:8]}"
        doc = domain.new_demo_run(
            self.seed,
            demo_run_id,
            case_id=case_id,
            created_at=datetime.now(UTC),
            agent_mode=self.agent_mode,
            executor=executor,
        )
        domain.audit(
            doc,
            actor=actor,
            action="demo_run_created",
            event_code="S0",
            case_id=case_id,
            executor=executor,
        )
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
        * 바깥 실행에 묶인 데모 실행 → 원천만 등록한다. BPM은 Studio·Center가 시작한다(N2).
          Center면 NowView가 기동한다(`POST /jobs`) — 보완 대기 중의 정정본은 메시지로 보낸다(N3).
        """
        _require(actor, "영업담당")
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if domain.check_idempotency(doc, idempotency_key, ["receive", fixture_id]):
                return doc
            source_id, created = domain.receive_source(doc, self.seed, fixture_id, actor=actor)
            if not created:
                return doc  # 재수신 — 중복 등록·이슈 생성 없이 기존 접수를 돌려준다
            if domain.executor_of(doc) != "embedded":
                # 내장 BPM을 함께 시작하면 한 문서에서 두 실행이 돈다 — 내장 쪽이 Approve_DQ에
                # 멈춘 채 남았다(2026-10-25 실측).
                old_job = ((doc["bpm"].get("center") or {}).get("job") or {}).get("job_id")
                domain.receive_external(doc, source_id)
                if domain.executor_of(doc) == "center":
                    self._center_receive(doc, source_id, actor=actor, old_job=old_job)
                _mark(doc, event_code, script_index)
                doc = self._commit(doc, version, None, event_code or "receive")
                return self._dispatch(doc)
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
        if domain.executor_of(self.get(demo_run_id)) == "center":
            return self._relay(
                demo_run_id,
                node_id,
                answer,
                actor=actor,
                event_code=event_code,
                script_index=script_index,
                idempotency_key=idempotency_key,
            )
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if domain.check_idempotency(doc, idempotency_key, ["act", node_id, actor, answer]):
                return doc  # 같은 요청의 재시도 — 이미 처리했다
            executor = domain.executor_of(doc)
            if executor != "embedded":
                raise DomainError(domain.ANSWER_ELSEWHERE[executor], 409)
            if doc["bpm"] is None:
                raise DomainError("아직 시작되지 않은 데모 실행이다", 409)
            run = self._restore(doc, actor)
            pending = next((p for p in run.pendings.values() if p.node_id == node_id), None)
            if pending is None:
                waiting = ", ".join(p.node_id for p in run.pendings.values()) or "없음"
                raise DomainError(f"{node_id}는 지금 기다리는 업무가 아니다 (대기: {waiting})", 409)
            domain.check_actor(doc, node_id, actor)
            # 업무 효과는 결재 뒤의 기록 작업이 낸다 — 여기서는 입력을 지우지 않고 거절할 것만 본다.
            check_answer(doc, node_id, answer, run.variables)
            try:
                self.engine.answer(run, pending.request_id, answer, answered_by=actor)
            except EngineError as exc:
                raise DomainError(str(exc), 422) from exc
            self._advance(doc, run)
            _mark(doc, event_code, script_index)
            doc = self._commit(doc, version, run, event_code or node_id)
        return self._dispatch(doc)

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
        시스템 작업을 HTTP로 — 바깥 BPM(Chaeksas HTTP 어댑터)이 서비스 태스크에서 부른다.

        **바깥 실행에 묶인 데모 실행에서만 받는다**(N2). 첫 호출의 `external_run_id`(`{{run_id}}`)가
        데모 실행을 그 실행에 묶고, 다른 실행의 호출은 409다. 내장 BPM이 도는 데모 실행에 오면 409다
        — 두 실행이 한 문서에 업무를 적게 두지 않는다. 업무 규칙(확인 전 계산 409, 인계 조건 미충족
        409)은 내장 길과 같다. 돌려주는 것은 작업의 출력뿐이다(어댑터가 `$.passed` 등으로 꺼낸다).
        `node_id`(`{{node_id}}`)는 진행 표시에만 쓴다. `via`는 키가 말하는 실행 위치다(N6, 꺼 두면
        `None`).
        """
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            domain.link_external_run(doc, external_run_id, via=via)
            try:
                try:
                    out = run_operation(doc, self.seed, operation, args)
                except KeyError as exc:
                    raise DomainError(f"없는 대상: {exc.args[0]}", 404) from exc
            except DomainError as exc:
                if operation not in RECORDS:
                    raise
                # 거절만 남긴다 — 다시 읽어 반쯤 적힌 효과를 버린다. 그림은 같은 결재로
                # 되돌아간다(N1).
                doc, version = self._load(demo_run_id)
                domain.link_external_run(doc, external_run_id, via=via)
                reject_record(doc, operation, args, exc)
                self._commit(doc, version, None, f"{operation}:rejected")
                raise
            domain.note_external_progress(
                doc,
                node_id,
                # 계산 실행 결재(Confirm_Calc)는 기록 작업이 없다 — 계산이 불렸으면 지나왔다.
                decided=args.get("node_id")
                if operation in RECORDS
                else ("Confirm_Calc" if operation == "compare" else None),
                done=operation == "hand_off" and out["handed_off"],
            )
            doc = self._commit(doc, version, None, operation)
        self._dispatch(doc)
        return out

    # ───────────── Center 실행 (N3) ─────────────

    def _center_receive(
        self, doc: dict, source_id: str, *, actor: str, old_job: str | None
    ) -> None:
        """
        center 데모 실행의 원천 수신 → Center에 알린다. 묶인 실행이 보완 대기면 정정본을 메시지로,
        그 밖이면 SC01을 새로 기동한다. 정정으로 대체된 앞 작업은 거둔다(바깥에 고아로 남지 않게).

        설정이 없으면 기동하지 않고 **사유를 문서에 남긴다** — 원천 수신 자체는 BPM 밖의 일이라
        막지 않는다. Center 콘솔에서 직접 기동하면 그 실행이 첫 작업 호출로 묶인다(N2).
        """
        bpm = doc["bpm"]
        ledger = bpm.setdefault("center", domain.new_center_ledger())
        problem = self.center.config.missing(integration=True)
        if problem:
            ledger["problem"] = f"{problem} — SC01을 기동하지 않았다. Center에서 직접 기동하라"
            return
        name = domain.name_of(actor)
        if bpm["external_run_id"] is not None:
            # receive_external이 대체하지 않았다 = 같은 실행이 보완 대기 중이다.
            try:
                self.center.send_message(
                    "원천정정",
                    correlation=doc["demo_run_id"],
                    payload={"원천ID": source_id},
                    idempotency_key=f"{doc['demo_run_id']}:{source_id}:correction",
                    on_behalf=name,
                )
            except CenterError as exc:
                raise exc.as_domain("정정본 전달") from exc
            domain.audit(doc, actor=actor, action="center_message_sent", source_id=source_id)
            return
        if old_job and old_job != (ledger.get("job") or {}).get("job_id"):
            self._cancel_center_job(doc, old_job)
        elif ledger.get("job"):
            raise DomainError(
                f"앞서 기동한 Center 작업 {ledger['job']['job_id']}이 아직 NowView를 부르지 않았다 "
                "— 그 실행이 원천을 검증한 뒤 다시 받아라",
                409,
            )
        try:
            job = self.center.start_job(
                {"데모실행ID": doc["demo_run_id"], "원천ID": source_id},
                idempotency_key=f"{doc['demo_run_id']}:{source_id}",
                on_behalf=name,
            )
        except CenterError as exc:
            raise exc.as_domain("SC01 기동") from exc
        ledger.update(
            job={"job_id": job["job_id"], "source_id": source_id, "at": doc["clock"]}, problem=None
        )
        domain.audit(
            doc, actor=actor, action="center_job_started", job_id=job["job_id"], source_id=source_id
        )

    def _cancel_center_job(self, doc: dict, job_id: str) -> None:
        """대체된 작업을 거둔다 — 실패해도 조작을 막지 않고 감사 이력에 남긴다."""
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
        center 데모 실행의 화면 답 = **대리 답**(N3). 엔진 사전 검사(403·409·422, 입력을
        지우지 않는다)
        → Center에 열린 그 사람의 결재를 찾는다 → `X-CHK-On-Behalf-Of`로 답한다. 업무 효과는 여전히
        결재 뒤의 기록 작업이 낸다 — 콘솔 답과 같은 길이다(N1).
        """
        problem = self.center.config.missing(relay=True)
        if problem:
            raise DomainError(f"{domain.ANSWER_ELSEWHERE['center']} — {problem}", 503)
        body = ["act", node_id, actor, answer]
        doc = self.get(demo_run_id)
        if domain.check_idempotency(doc, idempotency_key, body):  # 읽기만 — 저장하지 않는다
            return doc
        domain.check_actor(doc, node_id, actor)
        check_answer(doc, node_id, answer, _center_vars(doc))
        name = domain.name_of(actor)
        ext, approval = self._await_approval(demo_run_id, node_id, name)
        # 결재가 보이는 값이 우선이다 — 사람이 본 원천으로 다시 본다(부수 효과 없음).
        check_answer(doc, node_id, answer, {**_center_vars(doc), **(approval.get("review") or {})})
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            if domain.check_idempotency(doc, idempotency_key, body):
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
            doc = self._commit(doc, version, None, event_code or node_id)
        return self._dispatch(doc)

    def _await_approval(self, demo_run_id: str, node_id: str, name: str) -> tuple[str, dict]:
        """
        Center에 열린 그 사람의 결재 중 이 실행·이 노드의 것. 서버 실행기가 앞 작업을 끝내고 결재를
        올리기까지 잠깐 걸린다 — `center_wait_s`까지 기다린다(잠금 밖에서).
        """
        deadline = time.monotonic() + self.center_wait_s
        while True:
            ext = (self.get(demo_run_id)["bpm"] or {}).get("external_run_id")
            seen: list[str] = []
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
                "Center 실행이 아직 NowView를 부르지 않았다 — 원천 검증이 끝나면 결재가 열린다", 409
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
        읽어(검토 자료·폼) 업무를 **그때** 연다 — 기록 때 늦게 열지 않는다. 바뀌면 저장하고
        SSE를 낸다.
        """
        doc = self.get(demo_run_id)
        bpm = doc["bpm"] or {}
        ext = bpm.get("external_run_id")
        if bpm.get("executor") != "center" or not ext or bpm.get("state") != "running":
            return False
        events = self.center.run_events(ext)
        progress = read_run_events(events)
        ledger = bpm.get("center") or domain.new_center_ledger()
        if progress["last_seq"] == ledger.get("last_seq"):
            return False
        relayed = set(ledger.get("relayed", []))
        known = {w["request_id"]: w for w in bpm.get("waiting", [])}
        opened = {
            rid: self._approval_entry(rid, node_id)
            for rid, node_id in progress["open"].items()
            if rid not in relayed and rid not in known
        }
        with self._lock(demo_run_id):
            doc, version = self._load(demo_run_id)
            bpm = doc["bpm"]
            if bpm.get("external_run_id") != ext:
                return False  # 그 사이 정정으로 대체됐다
            ledger = bpm.setdefault("center", domain.new_center_ledger())
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
                bpm["state"] = {"success": "done"}.get(progress["finished"], progress["finished"])
                bpm["position"], bpm["waiting"] = [], []
            ledger["last_seq"] = progress["last_seq"]
            # 실행이 묶여 기록이 읽히면 수신 때의 사유(「기동하지 않았다」)는 지난 일이다.
            ledger["problem"] = None
            for rid, entry in opened.items():
                if entry.get("variables") is not None:
                    domain.sync_tasks(doc, {rid: {"node_id": entry["node_id"]}}, entry["variables"])
            self._commit(doc, version, None, "center_progress")
        return True

    def _approval_entry(self, request_id: str, node_id: str) -> dict[str, Any]:
        """
        열린 결재 하나를 화면이 쓸 대기로. 대리 답용 키는 **그 사람이 담당인 것만** 보인다 — SC01은
        역할마다 한 사람이라 역할로 담당자를 안다. 읽지 못하면 검토 자료 없이 그림의 폼으로 두고
        업무는 열지 않는다(`variables: None` — 계산 id 없이 열면 인계 판정이 틀린다).
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
        name = domain.name_of(domain.user_for_role(spec["role"]))
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

    def reset(
        self,
        demo_run_id: str,
        *,
        actor: str,
        case_id: str | None = None,
        executor: str | None = None,
    ) -> dict:
        """
        현재 데모 실행만 S0로 되돌린다. 이력은 남긴다(DATA-05). 사례·실행 위치를 바꿔 다시 시작한다
        — 주지 않으면 지금 것을 잇는다. 바깥 실행과의 묶음은 풀린다(새 실행이 다시 묶인다).
        """
        _require(actor, "시연관리자")
        if case_id is not None and case_id not in domain.CASES:
            raise DomainError(f"모르는 시연 사례: {case_id}", 422)
        with self._lock(demo_run_id):
            old, version = self._load(demo_run_id)
            old_job = (((old["bpm"] or {}).get("center") or {}).get("job") or {}).get("job_id")
            case = case_id or old["case_id"]
            where = executor or domain.executor_of(old)
            doc = domain.new_demo_run(
                self.seed,
                demo_run_id,
                case_id=case,
                created_at=datetime.fromisoformat(old["created_at"]),
                agent_mode=self.agent_mode,
                executor=where,
            )
            doc["audit"] = old["audit"]
            domain.audit(
                doc,
                actor=actor,
                action="demo_run_reset",
                event_code="S0",
                case_id=case,
                executor=where,
            )
            if old_job and not self.center.config.missing(integration=True):
                self._cancel_center_job(doc, old_job)
            doc = self._commit(doc, version, None, "reset")
        return self._dispatch(doc)


def read_run_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """
    C3 실행 기록 → 진행. `open`은 결재 id → 노드(요청됐고 아직 답·만료·회수가 없는 것), `active`는
    시작했고 끝나지 않은 노드, `finished`는 `run_finished.status`다. 모르는 종류는 지나간다
    (C3 호환 규칙).
    """
    visited: list[str] = []
    active: dict[str, None] = {}
    opened: dict[str, str] = {}
    finished: str | None = None
    last = 0
    for event in sorted(events, key=lambda e: e.get("seq", 0)):
        last = max(last, int(event.get("seq") or 0))
        kind, node, data = event.get("kind"), event.get("node_id"), event.get("data") or {}
        if kind == "node_state" and node:
            state = data.get("state")
            if state == "started":
                active[node] = None
            elif state in ("completed", "failed", "skipped", "replayed"):
                active.pop(node, None)
                if state in ("completed", "replayed") and node not in visited:
                    visited.append(node)
        elif kind == "human_requested" and data.get("layer", "approval") == "approval" and node:
            opened[str(data["request_id"])] = node
        elif kind in ("human_answered", "human_timeout", "human_withdrawn"):
            opened.pop(str(data.get("request_id")), None)
        elif kind == "run_finished":
            finished = str(data.get("status") or "failed")
    return {
        "visited": visited,
        "active": list(active),
        "open": opened,
        "finished": finished,
        "last_seq": last,
    }


def _center_vars(doc: dict) -> dict[str, Any]:
    """사전 검사에 쓸 변수 — 결재를 읽기 전에는 가장 최근 원천이 확인 대상이다."""
    sources = domain.ordered(doc["sources"])
    return {"원천ID": sources[-1]["source_id"]} if sources else {}


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
