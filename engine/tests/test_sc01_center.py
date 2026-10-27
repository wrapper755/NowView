"""
N3 — Center 연동: SC01 기동 · 대리 답 · 진행 폴링 · 정정본 메시지.

가짜 Center(`FakeCenter`)는 Chaeksas 계약을 그대로 흉내 낸다 — 경로·키 종류·`X-CHK-On-Behalf-Of`
대조(C6·ADR-0081), 결재 하나는 한 번만 닫힘(`already_answered`), 실행 기록은 `seq` 차례(C3). 서버
실행기 몫은 `FakeRunner`가 진짜 Chaeksas 엔진으로 같은 BPMN을 돌려 한다 — 결재는 Center에 올리고,
답은 Center에서 받아 넣고, 서비스 태스크는 NowView 시스템 작업(HTTP 어댑터 흉내)을 부른다.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from typing import Any
from urllib.parse import unquote

import httpx
import pytest
from chaeksas.core.engine import Engine, RunEnv, State
from chaeksas.core.run_log import RunLog
from chaeksas.core.services import OpOutcome, ServiceCallError
from conftest import require_postgres

from app.sc01 import demo
from app.sc01.center import CenterClient, CenterConfig
from app.sc01.domain import DomainError, parse_at
from app.sc01.process import Sc01Process, read_run_events
from app.sc01.store import PostgresSc01Store, SqliteSc01Store
from app.sc01.view import view
from app.store import build_postgres_backend

INTEGRATION, RELAY = "chk_int_test", "chk_relay_test"
CONFIG = CenterConfig(url="http://center.test", integration_key=INTEGRATION, relay_key=RELAY)


class FakeCenter:
    """Center REST의 NowView 몫(C3·C5·C6·C12)."""

    def __init__(self) -> None:
        self.jobs: list[dict] = []
        self.messages: list[dict] = []
        self.cancelled: list[str] = []
        self.approvals: dict[str, dict] = {}
        self.events: dict[str, list[dict]] = {}
        self.calls: list[tuple[str, str]] = []
        #: 대리 답을 받은 뒤 — 서버 실행기가 그 답을 집어 진행하는 것을 흉내 낼 때 쓴다.
        self.on_answer: Callable[[], None] | None = None

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        self.calls.append((request.method, path))
        key = request.headers.get("authorization", "").removeprefix("Bearer ")
        who = unquote(request.headers.get("x-chk-on-behalf-of", "")) or None
        body = json.loads(request.content) if request.content else None
        if key not in (INTEGRATION, RELAY):
            return _err(401, "key_invalid", "모르는 토큰이다")
        if path.startswith("/approvals"):
            if key != RELAY:
                return _err(403, "forbidden", "결재는 콘솔 토큰이나 대리 답용 키로 읽는다")
            if not who:
                return _err(400, "on_behalf_required", "X-CHK-On-Behalf-Of가 필요하다")
            return self._approvals(request.method, path, who, body, request.url.params)
        if key == RELAY:
            return _err(403, "forbidden", "대리 답용 키로는 결재만 읽고 답할 수 있다")
        if request.method == "POST" and path == "/jobs":
            job = {**body, "job_id": f"job_{len(self.jobs) + 1:08x}", "state": "pending"}
            self.jobs.append(job)
            return httpx.Response(201, json=job)
        if request.method == "DELETE" and path.startswith("/jobs/"):
            self.cancelled.append(path.rsplit("/", 1)[1])
            return httpx.Response(202, json={"cancel_result": "accepted"})
        if request.method == "POST" and path == "/messages":
            if body.get("schema") != 1:
                return _err(422, "input_invalid", "메시지가 계약과 맞지 않는다")
            self.messages.append(body)
            return httpx.Response(202, json={"message_id": f"msg_{len(self.messages)}"})
        if request.method == "GET" and path.startswith("/runs/") and path.endswith("/events"):
            run_id = path.split("/")[2]
            if run_id not in self.events:
                return _err(404, "run_not_found", run_id)
            return httpx.Response(200, json={"run_id": run_id, "events": self.events[run_id]})
        return _err(404, "not_found", path)

    def _approvals(self, method: str, path: str, who: str, body: Any, params) -> httpx.Response:
        mine = [a for a in self.approvals.values() if who in a["assignees"]]
        if method == "GET" and path == "/approvals":
            if params.get("assignee") not in (None, who):
                return _err(403, "not_assignee", "대리 답용 키는 그 사람의 결재만 본다")
            state = params.get("state")
            return httpx.Response(
                200, json=[a for a in reversed(mine) if state is None or a["state"] == state]
            )
        request_id = path.split("/")[2]
        found = self.approvals.get(request_id)
        if found is None or (who not in found["assignees"] and method == "GET"):
            return _err(404, "not_found", request_id)
        if method == "GET":
            return httpx.Response(200, json=found)
        if who not in found["assignees"]:
            return _err(403, "not_assignee", f"「{who}」은 이 결재의 담당자가 아니다")
        if found["state"] != "open":
            return _err(409, "already_answered", "이미 답했다")
        if body.get("if_review_digest") not in (None, found["review_digest"]):
            return _err(409, "review_changed", "본 검토 자료가 지금 결재와 다르다")
        found.update(state="answered", answer=body["answer"], answered_by=who, answered_via="nv")
        if self.on_answer is not None:
            self.on_answer()
        return httpx.Response(200, json=found)


def _err(status: int, code: str, message: str) -> httpx.Response:
    return httpx.Response(status, json={"code": code, "message": message, "detail": {}})


class _SystemCalls:
    """서버 실행기의 HTTP 어댑터 흉내 — 4xx는 본문을 버리고 상태 코드만 말한다."""

    def __init__(self, proc: Sc01Process) -> None:
        self.proc = proc

    def call(self, request):
        args = dict(request.input)
        try:
            out = self.proc.operate(
                args.pop("demo_run_id"),
                request.operation,
                args,
                external_run_id=request.run_id,
                node_id=request.node_id,
                via="center",
            )
        except DomainError as exc:
            raise ServiceCallError(
                f"{request.app_id}.{request.operation}이 {exc.status}를 돌려줬다",
                code="http_error",
                status=exc.status,
            ) from exc
        return OpOutcome(output=out)


class FakeRunner:
    """서버 실행기 — 작업 하나로 같은 BPMN을 돌리고, 결재를 Center에 올리고 답을 받아 넣는다."""

    def __init__(
        self,
        proc: Sc01Process,
        center: FakeCenter,
        job: dict,
        run_id: str,
        *,
        process: Any = None,
        sourced: dict[str, Any] | None = None,
        delegate: Any = None,
    ) -> None:
        """
        `process`를 주면 그 그림을 돈다(접수 Bot, N5). `sourced`는 Center가 가상 직원 등록에서
        붙이는 출처 입력이고(ADR-0099), `delegate`는 위임을 받는 쪽이다.
        """
        self.proc, self.center, self.engine = proc, center, Engine()
        inputs = job["inputs"]
        demo_run_id = inputs.get("데모실행ID") or inputs["원천목록"][0]["데모실행ID"]
        env = RunEnv(services=_SystemCalls(proc), **({"delegate": delegate} if delegate else {}))
        self.run = self.engine.start(
            process or proc.process,
            run_id=run_id,
            log=RunLog(run_id=run_id),
            env=env,
            executor="server_runner",
            inputs=inputs,
            sourced=sourced,
            now=parse_at(proc.get(demo_run_id)["clock"]),
        )
        self.step()

    def step(self) -> State:
        """답이 온 결재를 넣고, 막힐 때까지 돌고, 새 결재를 올리고, 실행 기록을 보낸다."""
        while True:
            for p in list(self.run.pendings.values()):
                found = self.center.approvals.get(p.request_id)
                if found and found["state"] == "answered":
                    self.engine.answer(
                        self.run, p.request_id, found["answer"], answered_by=found["answered_by"]
                    )
            state = self.engine.run_until_blocked(self.run)
            fresh = [
                p for p in self.run.pendings.values() if p.request_id not in self.center.approvals
            ]
            for p in fresh:
                self.center.approvals[p.request_id] = {
                    "request_id": p.request_id,
                    "run_id": self.run.run_id,
                    "node_id": p.node_id,
                    "node_instance": p.node_instance,
                    "title": p.title,
                    "form": p.form.model_dump(mode="json") if p.form else None,
                    "review": p.review,
                    "review_digest": f"sha256:{p.request_id}",
                    "assignees": p.assignees,
                    "state": "open",
                }
            self.center.events[self.run.run_id] = [
                e.model_dump(mode="json") for e in self.run.log.events
            ]
            answered = any(
                self.center.approvals[p.request_id]["state"] == "answered"
                for p in self.run.pendings.values()
            )
            if not answered:
                return state

    def deliver(self, message: dict) -> None:
        """Center가 상관 키로 고른 실행에 넣는다 — 실행기와 같은 규칙(`message_target`)이다."""
        assert self.engine.message_target(
            self.run, message["name"], correlation=message["correlation"]
        )
        self.engine.deliver(
            self.run,
            message["name"],
            payload=message["payload"],
            correlation=message["correlation"],
        )
        self.step()


@pytest.fixture
def center() -> FakeCenter:
    return FakeCenter()


@pytest.fixture(params=["sqlite", "postgres"])
def proc(request, center: FakeCenter):
    """두 백엔드 — 폴러가 도는 데모 실행을 고르는 질의(`running_external`)가 JSON 경로를 쓴다."""
    backend = None
    if request.param == "postgres":
        backend = build_postgres_backend(require_postgres())
        store = PostgresSc01Store(backend.pool)
        with backend.pool.connection() as conn:
            conn.execute("TRUNCATE sc01_demo_run, sc01_history")
    else:
        store = SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False))
    client = CenterClient(CONFIG, transport=httpx.MockTransport(center.handle))
    try:
        yield Sc01Process(store, inline_agent=True, center=client, center_wait_s=0)
    finally:
        if backend is not None:
            with backend.pool.connection() as conn:
                conn.execute("TRUNCATE sc01_demo_run, sc01_history")
            backend.close()


def test_demo_script_runs_on_center_through_relay_answers(
    proc: Sc01Process, center: FakeCenter
) -> None:
    """
    각본이 center 데모 실행에서 끝까지 간다 — 수신이 SC01을 기동하고, 결재는 대리 답으로 닫히고,
    진행은 폴링으로 온다. 업무는 대기가 열릴 때 열린다(늦게 열지 않는다). 내장 BPM은 돌지 않는다.
    """
    rid = proc.create(executor="center")["demo_run_id"]
    doc = demo.run_step(proc, rid, 0)  # EV01 수신
    [job] = center.jobs
    assert job["target"] == {"type": "server_runner"} and job["bpm_process_id"] == "nowview.sc01"
    assert job["inputs"] == {"데모실행ID": rid, "원천ID": "SRC02"}
    assert doc["bpm"]["center"]["job"]["job_id"] == job["job_id"] and doc["bpm"]["snapshot"] is None

    runner = FakeRunner(proc, center, job, "run_20270616_090000_c3c3c3")
    proc.create(executor="center")  # 묶이지 않은(첫 호출 전) center 데모 실행은 폴링하지 않는다
    assert proc.store.running_external("center") == [rid]
    assert proc.poll_center() == 1
    doc = proc.get(rid)
    assert [w["node_id"] for w in doc["bpm"]["waiting"]] == ["Approve_DQ"]
    task = doc["tasks"]["TASK-DQ"]
    assert not task.get("opened_late") and task["request_id"].startswith("apr_")
    assert not proc.sync_center(rid)  # 새 기록이 없으면 저장하지 않는다
    shown = view(doc, center=CONFIG)
    assert shown["answerHere"] and shown["bpm"]["waiting"][0]["nodeId"] == "Approve_DQ"
    assert shown["bpm"]["waiting"][0]["review"]["원천ID"] == "SRC02"

    for index in range(1, len(demo.BASE)):
        demo.run_step(proc, rid, index)
        runner.step()
        proc.sync_center(rid)

    assert runner.run.state is State.DONE
    after = proc.get(rid)
    assert after["scene"] == "HANDED_OFF"
    assert after["bpm"]["state"] == "done" and after["bpm"]["waiting"] == []
    assert after["script_index"] == len(demo.BASE) - 1
    relayed = [a["detail"]["node_id"] for a in after["audit"] if a["action"] == "answer_relayed"]
    assert relayed == [s.node_id for s in demo.BASE if s.node_id]
    # 답한 사람은 짐작이 아니다 — 대리 답의 이름이 그대로 Center에 실렸다.
    assert {a["answered_by"] for a in center.approvals.values()} == {
        "이도윤",
        "박서진",
        "김태오",
        "최유나",
        "정하윤",
    }
    assert not [t for t in after["tasks"].values() if t.get("opened_late")]
    assert {"Approve_DQ", "Task_Calc", "Accept_FIN", "Task_Handoff"} <= set(after["bpm"]["visited"])


def test_relay_prechecks_before_touching_center(proc: Sc01Process, center: FakeCenter) -> None:
    """역할(403)·업무 규칙(409)은 Center에 가기 전에 거절한다 — 입력은 지워지지 않는다(4.6)."""
    rid = proc.create(executor="center")["demo_run_id"]
    proc.receive(rid, "EX02", actor="u-sales")
    FakeRunner(proc, center, center.jobs[0], "run_20270616_090000_d4d4d4")
    proc.sync_center(rid)
    before = len(center.calls)
    answer = {"확인결과": "확인완료", "확인의견": "-", "확인근거": "-"}

    with pytest.raises(DomainError) as role:
        proc.act(rid, "Approve_DQ", answer, actor="u-sales-lead")
    assert role.value.status == 403
    with pytest.raises(DomainError) as rule:
        proc.act(rid, "Approve_DQ", answer, actor="u-sales")
    assert rule.value.status == 409 and "검증 오류" in str(rule.value)
    assert center.calls[before:] == []  # Center에 묻지도 않았다
    assert all(a["state"] == "open" for a in center.approvals.values())


def test_relay_reasons_when_center_refuses_or_nothing_is_open(
    proc: Sc01Process, center: FakeCenter
) -> None:
    rid = proc.create(executor="center")["demo_run_id"]
    with pytest.raises(DomainError) as early:
        proc.act(rid, "Approve_DQ", {}, actor="u-sales")
    assert early.value.status == 409 and "아직 NowView를 부르지 않았다" in str(early.value)

    proc.receive(rid, "CP02", actor="u-sales")
    runner = FakeRunner(proc, center, center.jobs[0], "run_20270616_090000_e5e5e5")
    step = demo.BASE[1]
    with pytest.raises(DomainError) as wrong_node:
        proc.act(rid, "Approve_Sales", {"영업의견": "x", "영업근거": "y"}, actor="u-sales-lead")
    assert wrong_node.value.status == 409 and "열려 있지 않다" in str(wrong_node.value)

    # 그 사이 콘솔에서 먼저 답했다 — Center가 409로 거절하고 사유가 그대로 간다.
    def closed(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/answer"):
            return _err(409, "already_answered", "이미 답했다")
        return center.handle(request)

    proc.center = CenterClient(CONFIG, transport=httpx.MockTransport(closed))
    with pytest.raises(DomainError) as taken:
        proc.act(rid, step.node_id, step.answer, actor="u-sales")
    assert taken.value.status == 409 and "already_answered" in str(taken.value)
    assert runner.run.state is State.WAITING


def test_center_without_settings_says_why(center: FakeCenter) -> None:
    """설정이 없으면 조용히 내장으로 돌지 않는다 — 기동하지 않은 사유를 남기고 화면 답은 503."""
    store = SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False))
    proc = Sc01Process(store, inline_agent=True, center_wait_s=0)
    rid = proc.create(executor="center")["demo_run_id"]
    doc = demo.run_step(proc, rid, 0)  # EV01 수신은 된다 — BPM 밖의 일이다
    assert doc["bpm"]["snapshot"] is None and doc["bpm"]["state"] == "not_started"
    assert "CHAEKSAS_CENTER_URL" in doc["bpm"]["center"]["problem"]
    assert view(doc, center=proc.center.config)["answerHere"] is False
    with pytest.raises(DomainError) as act:
        proc.act(rid, "Approve_DQ", {}, actor="u-sales")
    assert act.value.status == 503 and "CHAEKSAS_RELAY_KEY" in str(act.value)
    with pytest.raises(DomainError) as script:
        demo.run_step(proc, rid, 1)
    assert script.value.status == 503
    assert proc.poll_center() == 0


def test_correction_goes_as_a_message_while_waiting_and_supersedes_after(
    proc: Sc01Process, center: FakeCenter
) -> None:
    """
    EX03 — 보완 대기 중의 정정본은 같은 실행에 메시지(상관 키 = 데모실행ID)로 간다. 계산 뒤에 오면
    실행을 이력으로 옮기고 앞 작업을 거둔 뒤 새로 기동한다.
    """
    rid = proc.create(executor="center")["demo_run_id"]
    proc.receive(rid, "EX02", actor="u-sales")
    runner = FakeRunner(proc, center, center.jobs[0], "run_20270616_090000_f6f6f6")
    proc.sync_center(rid)
    fix = {"확인결과": "보완요청", "확인의견": "b모델 7월 물량 누락", "확인근거": "SRC02 15행"}
    proc.act(rid, "Approve_DQ", fix, actor="u-sales")
    runner.step()

    doc = proc.receive(rid, "CP02", actor="u-sales")
    [message] = center.messages
    assert (message["name"], message["correlation"], message["payload"]) == (
        "원천정정",
        rid,
        {"원천ID": "SRC03"},
    )
    assert len(center.jobs) == 1 and doc["bpm"]["external_run_id"] == runner.run.run_id
    runner.deliver(message)
    proc.sync_center(rid)
    assert [w["node_id"] for w in proc.get(rid)["bpm"]["waiting"]] == ["Approve_DQ"]
    # 보완 뒤 다시 열린 결재 — 같은 업무를 이어 쓴다(WF-02).
    assert proc.get(rid)["tasks"]["TASK-DQ"]["status"] == "ASSIGNED"

    proc.act(rid, "Approve_DQ", demo.BASE[1].answer, actor="u-sales")
    runner.step()
    proc.act(rid, "Confirm_Calc", {}, actor="u-sales")
    runner.step()
    proc.sync_center(rid)

    doc = proc.receive(rid, "CP03", actor="u-sales")
    assert center.cancelled == [center.jobs[0]["job_id"]]
    assert len(center.jobs) == 2 and center.jobs[1]["inputs"]["원천ID"] == "SRC04"
    assert doc["bpm"]["external_run_id"] is None
    assert doc["bpm_history"][-1]["state"] == "superseded"


def test_read_run_events_follows_the_c3_shape() -> None:
    events = [
        {"seq": 1, "kind": "run_started", "data": {}},
        {"seq": 2, "kind": "node_state", "node_id": "Task_Validate", "data": {"state": "started"}},
        {"seq": 3, "kind": "node_state", "node_id": "Task_Validate",
         "data": {"state": "completed"}},
        {"seq": 4, "kind": "node_state", "node_id": "Approve_DQ", "data": {"state": "started"}},
        {"seq": 5, "kind": "human_requested", "node_id": "Approve_DQ",
         "data": {"layer": "approval", "request_id": "apr_1", "where": "center"}},
        {"seq": 6, "kind": "something_new", "data": {}},
    ]  # fmt: skip
    got = read_run_events(events)
    assert got == {
        "visited": ["Task_Validate"],
        "active": ["Approve_DQ"],
        "open": {"apr_1": "Approve_DQ"},
        "finished": None,
        "last_seq": 6,
    }
    events.append({"seq": 7, "kind": "human_withdrawn", "data": {"request_id": "apr_1"}})
    events.append({"seq": 8, "kind": "run_finished", "data": {"status": "cancelled"}})
    assert read_run_events(events)["open"] == {}
    assert read_run_events(events)["finished"] == "cancelled"
