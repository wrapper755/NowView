"""
N5 — 고객계획 접수 가상 직원: 접수 Bot(`sc01-intake.bpmn`) · 감독자 일괄 결재 · SC01 위임.

가짜 Center는 N3의 것에 메시지 시작(`virtual_worker`, ADR-0099)과 가상 직원 읽기(C5 CON-13)를
더한다.
접수 Bot과 위임된 SC01은 진짜 Chaeksas 엔진이 돈다(`FakeRunner`) — 출처가 가상 직원인 입력은
Center가 붙이는 값(`sourced`)으로 들어가고, 위임은 `RecordingDelegator`가 받는다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from chaeksas.contracts.bpmn_ext import read_process, validate
from chaeksas.core.delegation import RecordingDelegator
from chaeksas.core.engine import Engine, EngineError, RunEnv, State
from chaeksas.core.run_log import RunLog
from test_sc01_center import CONFIG, FakeCenter, FakeRunner, _err

from app.sc01 import demo
from app.sc01.center import CenterClient, CenterConfig
from app.sc01.domain import DomainError
from app.sc01.process import INTAKE_PATH, PROCESS_PATH, Sc01Process, summarize_intake
from app.sc01.view import view

WORKER = {
    "id": "nowview-intake",
    "name": "고객계획 접수 담당",
    "supervisors": ["이도윤"],
    "intake": "nowview.sc01-intake",
    "state": "active",
}
#: Center가 가상 직원 등록에서 붙이는 값 — 접수 Bot의 출처 입력(ADR-0099)
SOURCED = {"감독자": WORKER["supervisors"], "가상직원": WORKER["name"]}
INTAKE_CONFIG = CenterConfig(
    url=CONFIG.url,
    integration_key=CONFIG.integration_key,
    relay_key=CONFIG.relay_key,
    intake_worker=WORKER["id"],
)
INTAKE = read_process(INTAKE_PATH.read_bytes())
RUN_X = "run_20270616_090000_0f0f0f"


class FakeIntakeCenter(FakeCenter):
    """메시지 시작 → 접수 Bot 작업, 가상 직원 읽기(최근 일괄)."""

    def __init__(self) -> None:
        super().__init__()
        self.started: dict[str, dict[str, Any]] = {}  # 접수 Bot 실행 → 일괄 정보
        self.job_states: dict[str, dict[str, Any]] = {}  # 작업 id → 실행기가 알린 상태

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        key = request.headers.get("authorization", "").removeprefix("Bearer ")
        if request.method == "GET" and path.startswith("/virtual-workers/"):
            self.calls.append((request.method, path))
            if key != CONFIG.integration_key:
                return _err(403, "forbidden", "연동용 키로 읽는다")
            if path.rsplit("/", 1)[1] != WORKER["id"]:
                return _err(404, "not_found", path)
            return httpx.Response(200, json={**WORKER, "batches": self._batches()})
        if request.method == "GET" and path.startswith("/jobs/"):
            self.calls.append((request.method, path))
            job_id = path.rsplit("/", 1)[1]
            found = next((j for j in self.jobs if j["job_id"] == job_id), None)
            if found is None:
                return _err(404, "not_found", job_id)
            return httpx.Response(200, json={**found, **self.job_states.get(job_id, {})})
        if request.method == "POST" and path == "/messages":
            import json

            body = json.loads(request.content)
            if body.get("correlation") is None:
                self.calls.append((request.method, path))
                return self._message_start(body)
        return super().handle(request)

    def _message_start(self, body: dict) -> httpx.Response:
        if body.get("schema") != 1:
            return _err(422, "input_invalid", "메시지가 계약과 맞지 않는다")
        if body["name"] != "고객계획접수":
            return _err(422, "no_receiver", body["name"])
        # 출처가 가상 직원인 입력은 부르는 쪽이 줄 수 없다(ADR-0099)
        given = sorted(set(body["payload"]) & set(SOURCED))
        if given:
            return _err(422, "input_not_from_caller", ", ".join(given))
        if body.get("virtual_worker") not in (None, WORKER["id"]):
            return _err(422, "virtual_worker_mismatch", str(body.get("virtual_worker")))
        for sent in self.messages:  # 멱등 — 같은 키면 같은 응답(C5)
            if sent["idempotency_key"] == body["idempotency_key"]:
                job_id = sent["_job_id"]
                return httpx.Response(202, json={"message_id": "msg_dup", "job_id": job_id})
        self.messages.append({**body, "_job_id": f"job_{len(self.jobs) + 1:08x}"})
        job = {
            "job_id": f"job_{len(self.jobs) + 1:08x}",
            "bpm_process_id": WORKER["intake"],
            "inputs": body["payload"],
            "virtual_worker": WORKER["id"],
            "state": "pending",
        }
        self.jobs.append(job)
        return httpx.Response(
            202,
            json={"message_id": f"msg_{len(self.messages)}", "delivered_to": "new_job",
                  "job_id": job["job_id"]},
        )  # fmt: skip

    def _batches(self) -> list[dict[str, Any]]:
        out = []
        for run_id, info in reversed(self.started.items()):
            events = self.events.get(run_id, [])
            finished = next((e for e in events if e["kind"] == "run_finished"), None)
            out.append(
                {
                    "run_id": run_id,
                    "status": finished["data"]["status"] if finished else "waiting",
                    "started_at": info["started_at"],
                    "children": len(info["children"]),
                    "children_by_status": {"running": len(info["children"])}
                    if info["children"]
                    else {},
                    "open_approvals": [
                        a["request_id"]
                        for a in self.approvals.values()
                        if a["run_id"] == run_id and a["state"] == "open"
                    ],
                }
            )
        return out


@pytest.fixture
def center() -> FakeIntakeCenter:
    return FakeIntakeCenter()


@pytest.fixture(params=["sqlite", "postgres"])
def proc(request, center: FakeIntakeCenter):
    import sqlite3

    from conftest import require_postgres

    from app.sc01.store import PostgresSc01Store, SqliteSc01Store
    from app.store import build_postgres_backend

    backend = None
    if request.param == "postgres":
        backend = build_postgres_backend(require_postgres())
        store = PostgresSc01Store(backend.pool)
        with backend.pool.connection() as conn:
            conn.execute("TRUNCATE sc01_demo_run, sc01_history")
    else:
        store = SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False))
    client = CenterClient(INTAKE_CONFIG, transport=httpx.MockTransport(center.handle))
    try:
        yield Sc01Process(store, inline_agent=True, center=client, center_wait_s=0)
    finally:
        if backend is not None:
            with backend.pool.connection() as conn:
                conn.execute("TRUNCATE sc01_demo_run, sc01_history")
            backend.close()


def _intake(proc: Sc01Process, center: FakeIntakeCenter, job: dict, run_id: str) -> FakeRunner:
    """접수 Bot 실행 — 서버 실행기가 Center가 붙인 가상 직원으로 도는 것을 흉내 낸다."""
    center.started[run_id] = {"started_at": datetime.now(UTC).isoformat(), "children": []}
    return FakeRunner(
        proc, center, job, run_id, process=INTAKE, sourced=SOURCED, delegate=RecordingDelegator()
    )


# ─────────────────────────── 그림 ───────────────────────────


def test_intake_bpmn_is_gated_and_names_no_supervisor() -> None:
    """
    접수 Bot은 계약 검사를 통과하고 **B16이 없다** — Center가 가상 직원에 묶는 관문이다
    (`intake_not_gated`). 감독자는 이름이 아니라 가상 직원 출처의 입력이다.
    """
    assert validate(INTAKE) == []
    inputs = {i.name: i for i in INTAKE.info.inputs}
    assert inputs["감독자"].source == "virtual_worker.supervisors" and inputs["감독자"].required
    assert inputs["가상직원"].source == "virtual_worker.name"
    approval = INTAKE.node("Approve_Batch").prop("approval")
    assert approval.assignees == "감독자"
    assert set(approval.show) >= {"원천목록", "검토목록"}
    sc01 = read_process(PROCESS_PATH.read_bytes())
    call = INTAKE.node("Call_SC01").prop("call")
    assert call.delegate.bpm_process_id == sc01.id == "nowview.sc01"
    assert set(call.input) == {"데모실행ID", "원천ID"}  # 처리자는 넘기지 않는다 — 선언만
    worker = {i.name: i for i in sc01.info.inputs}["처리자"]
    assert worker.source == "virtual_worker.name" and not worker.required


def test_virtual_worker_inputs_come_only_from_center() -> None:
    """
    b421880 이후 엔진: 가상 직원 없이 돌린 접수 Bot은 시작하지 않고(`input_required`), 부르는 쪽이
    출처 입력을 주면 거절한다(`input_not_from_caller`). 감독자를 필수로 두지 않았다면 담당자
    변수가 `None`이라 결재를 만들 때 실행이 실패로 멈춘다(`assignees_missing`) — 「담당자
    없음」으로 넘어가지 않는다.
    """
    engine = Engine()
    items = {"원천목록": [{"데모실행ID": "demo-x", "원천ID": "SRC02"}]}

    def start(process, **kwargs):
        return engine.start(
            process, run_id=RUN_X, log=RunLog(run_id=RUN_X), executor="server_runner", **kwargs
        )

    with pytest.raises(EngineError) as required:
        start(INTAKE, inputs=items)
    assert required.value.code == "input_required"
    with pytest.raises(EngineError) as caller:
        start(INTAKE, inputs={**items, "감독자": ["누구나"]})
    assert caller.value.code == "input_not_from_caller"
    with pytest.raises(EngineError) as sc01:
        start(
            read_process(PROCESS_PATH.read_bytes()),
            inputs={"데모실행ID": "demo-x", "원천ID": "SRC02", "처리자": "지어낸 이름"},
        )
    assert sc01.value.code == "input_not_from_caller"

    optional = read_process(
        INTAKE_PATH.read_bytes().replace(
            b'"required": true, "source": "virtual_worker.supervisors"',
            b'"source": "virtual_worker.supervisors"',
        )
    )

    class Screen:
        def call(self, request):
            from chaeksas.core.services import OpOutcome

            return OpOutcome(output={"summary": {}})

    run = start(optional, inputs=items, env=RunEnv(services=Screen()))
    assert engine.run_until_blocked(run) is State.FAILED  # 결재를 만들지 않고 실행이 멈춘다
    finished = run.log.events[-1]
    assert (finished.kind, finished.data["error_code"]) == ("run_finished", "assignees_missing")


# ─────────────────────────── 접수 → 승인 → SC01 ───────────────────────────


def test_receive_wakes_the_intake_bot_and_approval_delegates_sc01(
    proc: Sc01Process, center: FakeIntakeCenter
) -> None:
    """
    수신 → 메시지 시작(가상 직원 id, 원천목록만) → 접수 Bot이 검증·일괄 결재 → 감독자 승인(NowView
    대리 답) → SC01 위임 → 위임된 SC01이 처리자를 싣고 데모 실행을 묶어 인계까지. 접수 Bot의 호출은
    데모 실행을 묶지 않는다.
    """
    rid = proc.create(executor="center")["demo_run_id"]
    doc = demo.run_step(proc, rid, 0)  # EV01 수신
    assert center.jobs[0]["bpm_process_id"] == "nowview.sc01-intake"
    [message] = center.messages
    assert message["name"] == "고객계획접수" and "correlation" not in message
    assert message["virtual_worker"] == "nowview-intake"
    assert message["payload"] == {"원천목록": [{"데모실행ID": rid, "원천ID": "SRC02"}]}
    job = doc["bpm"]["center"]["job"]
    assert (job["via"], job["decision"]) == ("intake", None)
    assert job["job_id"] == center.jobs[0]["job_id"]

    intake = _intake(proc, center, center.jobs[0], "run_20270616_090000_a1a1a1")
    doc = proc.get(rid)
    assert doc["bpm"]["external_run_id"] is None  # 접수 Bot은 묶지 않는다
    [batch] = [a for a in center.approvals.values() if a["node_id"] == "Approve_Batch"]
    assert batch["assignees"] == ["이도윤"]  # 그림에 없는 이름 — 가상 직원 등록에서 왔다
    [screened] = batch["review"]["검토목록"]
    assert screened["검증통과"] and screened["변경"] == [
        {"model": "A-b", "period": "2027-07-01", "from": 9500, "to": 8800}
    ]
    assert doc["sources"]["SRC02"]["screened_by"] == "고객계획 접수 담당"

    # 승인 전에는 SC01 결재가 없다 — 화면 답은 사유를 말한다. 다른 원천도 받지 않는다.
    first = demo.BASE[1]
    with pytest.raises(DomainError) as early:
        proc.act(rid, first.node_id, first.answer, actor=first.actor)
    assert early.value.status == 409 and "감독자 승인" in str(early.value)
    with pytest.raises(DomainError) as twice:
        proc.receive(rid, "CP03", actor="u-sales")
    assert twice.value.status == 409 and "승인을 기다린다" in str(twice.value)

    card = proc.intake_status()
    assert card["configured"] and card["name"] == "고객계획 접수 담당"
    assert card["today"] == 1 and card["started"] == 0
    assert [p["requestId"] for p in card["pendingApprovals"]] == [batch["request_id"]]

    approve = {"결정": "승인", "의견": "b모델 7월 감소 확인 — 공급전망 갱신"}
    with pytest.raises(DomainError) as not_supervisor:
        proc.answer_intake(batch["request_id"], approve, actor="u-sales-lead")
    assert not_supervisor.value.status == 403
    proc.answer_intake(batch["request_id"], approve, actor="u-sales")
    intake.step()

    doc = proc.get(rid)
    reviewed = [a for a in doc["audit"] if a["action"] == "intake_reviewed"]
    assert reviewed[-1]["actor"] == "u-sales" and reviewed[-1]["detail"]["decision"] == "승인"
    assert doc["bpm"]["center"]["job"]["decision"] == "승인"
    [call] = intake.run.env.delegate.calls
    assert call.bpm_process_id == "nowview.sc01" and call.loop_index == 0
    assert dict(call.inputs) == {"데모실행ID": rid, "원천ID": "SRC02"}

    # 위임된 SC01 — 일괄의 가상 직원을 이어받아 처리자가 들어간다(ADR-0099 §3)
    child = FakeRunner(
        proc, center, {"inputs": dict(call.inputs)}, "run_20270616_090100_b2b2b2",
        sourced={"처리자": WORKER["name"]},
    )  # fmt: skip
    center.started["run_20270616_090000_a1a1a1"]["children"].append(child.run.run_id)
    doc = proc.get(rid)
    assert doc["bpm"]["external_run_id"] == child.run.run_id
    assert doc["bpm"]["processed_by"] == "고객계획 접수 담당"
    assert view(doc, center=INTAKE_CONFIG)["bpm"]["center"]["processedBy"] == "고객계획 접수 담당"
    assert proc.intake_status()["started"] == 1

    proc.sync_center(rid)
    for index in range(1, len(demo.BASE)):
        demo.run_step(proc, rid, index)
        child.step()
        proc.sync_center(rid)
    assert child.run.state is State.DONE and proc.get(rid)["scene"] == "HANDED_OFF"

    intake.engine.delegation_done(intake.run, "job_dlg001", state="finished")
    assert intake.engine.run_until_blocked(intake.run) is State.DONE
    assert "End_Started" in {e.node_id for e in intake.run.log.events if e.node_id}


def test_script_approves_the_batch_as_the_supervisor(
    proc: Sc01Process, center: FakeIntakeCenter
) -> None:
    """
    장면 2 시작이 장면 1을 각본으로 인계까지 끝낼 때 — 일괄을 감독자(가상 직원 등록의 이름)로
    대리 승인한다. 화면의 대리 답과 같은 길이다. 기다리는 일괄이 없으면 아무것도 하지 않는다.
    """
    rid = proc.create(executor="center")["demo_run_id"]
    assert proc.approve_intake_for_script(rid, opinion="각본") is False  # 수신 전
    demo.run_step(proc, rid, 0)
    run_id = "run_20270616_090000_c3c3c3"
    center.job_states[center.jobs[0]["job_id"]] = {"run_id": run_id}
    intake = _intake(proc, center, center.jobs[0], run_id)
    [batch] = [a for a in center.approvals.values() if a["node_id"] == "Approve_Batch"]

    child_bound: dict[str, FakeRunner] = {}

    def bind() -> None:  # 위임된 SC01의 첫 호출 — 승인 뒤 실행기가 한다
        intake.step()
        [call] = intake.run.env.delegate.calls
        child_bound["runner"] = FakeRunner(
            proc, center, {"inputs": dict(call.inputs)}, "run_20270616_090100_d4d4d4",
            sourced={"처리자": WORKER["name"]},
        )  # fmt: skip

    center.on_answer = bind  # 대리 답을 받으면 실행기가 움직인다
    assert proc.approve_intake_for_script(rid, opinion="각본") is True
    assert batch["state"] != "open" and batch["answered_by"] == "이도윤"
    assert proc.get(rid)["bpm"]["center"]["job"]["decision"] == "승인"
    assert proc.get(rid)["bpm"]["external_run_id"] == "run_20270616_090100_d4d4d4"


def test_script_step_after_receive_approves_the_batch_and_goes_on(
    proc: Sc01Process, center: FakeIntakeCenter
) -> None:
    """
    장면 1 플레이어의 자동 재생·「다음」 — 수신 다음 단계가 접수 일괄을 감독자로 대리
    승인하고 이어서 원천 확인까지 한다(운영에서 자동 재생이 승인 대기에서 멈췄다). 화면 답은
    그대로 사람의 승인을 기다린다.
    """
    rid = proc.create(executor="center")["demo_run_id"]
    demo.run_step(proc, rid, 0)
    run_id = "run_20270616_090000_e5e5e5"
    center.job_states[center.jobs[0]["job_id"]] = {"run_id": run_id}
    intake = _intake(proc, center, center.jobs[0], run_id)
    [batch] = [a for a in center.approvals.values() if a["node_id"] == "Approve_Batch"]
    children: list[FakeRunner] = []

    def bind() -> None:  # 일괄 승인 한 번만 — 뒤의 원천 확인 대리 답은 위임된 SC01이 받는다
        center.on_answer = None
        intake.step()
        [call] = intake.run.env.delegate.calls
        children.append(FakeRunner(
            proc, center, {"inputs": dict(call.inputs)}, "run_20270616_090100_f6f6f6",
            sourced={"처리자": WORKER["name"]},
        ))  # fmt: skip

    center.on_answer = bind
    doc = demo.run_step(proc, rid, 1)
    assert batch["answered_by"] == "이도윤"
    assert doc["bpm"]["external_run_id"] == "run_20270616_090100_f6f6f6"
    assert doc["script_index"] == 1
    children[0].step()
    proc.sync_center(rid)
    for index in range(2, len(demo.BASE)):
        demo.run_step(proc, rid, index)
        children[0].step()
        proc.sync_center(rid)
    assert children[0].run.state is State.DONE and proc.get(rid)["scene"] == "HANDED_OFF"


def test_rejected_batch_does_not_start_sc01_and_asks_for_a_fix(
    proc: Sc01Process, center: FakeIntakeCenter
) -> None:
    """
    반려 → SC01을 시작하지 않는다. 원천은 NEEDS_INFO, 영업담당 업무는 보완 요청(TASK-DQ NEEDS_INFO).
    정정본은 새 일괄이 되고, 승인되면 위임된 SC01의 원천 확인이 같은 업무를 이어 쓴다.
    """
    rid = proc.create(executor="center")["demo_run_id"]
    proc.receive(rid, "EX02", actor="u-sales")  # b모델 7월 수량 누락
    intake = _intake(proc, center, center.jobs[0], "run_20270616_090000_c3c3c3")
    [batch] = center.approvals.values()
    [screened] = batch["review"]["검토목록"]
    assert not screened["검증통과"] and screened["검증오류수"] == 1

    with pytest.raises(DomainError) as no_reason:
        proc.answer_intake(batch["request_id"], {"결정": "반려", "의견": " "}, actor="u-sales")
    assert no_reason.value.status == 422
    fix = {"결정": "반려", "의견": "b모델 7월 수량 누락 — 고객에 재요청"}
    proc.answer_intake(batch["request_id"], fix, actor="u-sales")
    intake.step()

    assert intake.run.state is State.DONE and intake.run.env.delegate.calls == []
    doc = proc.get(rid)
    assert doc["sources"]["SRC02"]["status"] == "NEEDS_INFO"
    assert doc["sources"]["SRC02"]["fix_opinion"] == fix["의견"]
    task = doc["tasks"]["TASK-DQ"]
    assert task["status"] == "NEEDS_INFO" and task["assigned_to"] == "u-sales"
    assert "접수 일괄 반려" in task["history"][-1]["note"]
    assert doc["bpm"]["external_run_id"] is None and doc["bpm"]["state"] == "not_started"
    shown = view(doc, center=INTAKE_CONFIG)
    assert [t["status"] for t in shown["tasks"]] == ["NEEDS_INFO"]

    # 정정본 — 반려된 일괄은 끝났으니 새 일괄을 보낸다
    proc.receive(rid, "CP02", actor="u-sales")
    assert len(center.messages) == 2
    assert center.messages[1]["payload"]["원천목록"][0]["원천ID"] == "SRC03"
    second = _intake(proc, center, center.jobs[1], "run_20270616_100000_d4d4d4")
    [batch2] = [a for a in center.approvals.values() if a["run_id"] == second.run.run_id]
    proc.answer_intake(batch2["request_id"], {"결정": "승인", "의견": "정정 확인"}, actor="u-sales")
    second.step()
    [call] = second.run.env.delegate.calls
    FakeRunner(proc, center, {"inputs": dict(call.inputs)}, "run_20270616_100100_e5e5e5",
               sourced={"처리자": WORKER["name"]})  # fmt: skip
    proc.sync_center(rid)
    task = proc.get(rid)["tasks"]["TASK-DQ"]
    assert task["status"] == "ASSIGNED" and task["history"][-1]["note"] == "보완 후 재배정"


def test_intake_calls_belong_to_center_demo_runs_only(
    proc: Sc01Process, center: FakeIntakeCenter
) -> None:
    """접수 Bot은 Center 서버 Bot이다 — 내장 데모 실행·시험용 키(Studio)는 409다."""
    embedded = proc.create()["demo_run_id"]
    proc.receive(embedded, "CP02", actor="u-sales")
    with pytest.raises(DomainError) as inside:
        proc.operate(embedded, "screen_source", {"source_id": "SRC02"}, external_run_id="run_i")
    assert inside.value.status == 409
    rid = proc.create(executor="center")["demo_run_id"]
    proc.receive(rid, "CP02", actor="u-sales")
    with pytest.raises(DomainError) as studio:
        proc.operate(
            rid, "screen_source", {"source_id": "SRC02"}, external_run_id="run_i", via="studio"
        )
    assert studio.value.status == 409
    with pytest.raises(DomainError) as unknown:
        proc.operate(
            rid,
            "record_intake_review",
            {"source_id": "SRC02", "decision": "보류", "opinion": "-", "answered_by": "이도윤"},
            external_run_id="run_i",
        )
    assert unknown.value.status == 422


def test_intake_card_says_why_when_not_configured(center: FakeIntakeCenter) -> None:
    import sqlite3

    from app.sc01.store import SqliteSc01Store

    store = SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False))
    bare = Sc01Process(store, inline_agent=True, center=CenterClient(CONFIG), center_wait_s=0)
    assert "CHAEKSAS_INTAKE_WORKER" in bare.intake_status()["problem"]

    def refused(request: httpx.Request) -> httpx.Response:
        return _err(401, "key_invalid", "모르는 토큰이다")

    bad = Sc01Process(
        store,
        inline_agent=True,
        center=CenterClient(INTAKE_CONFIG, transport=httpx.MockTransport(refused)),
    )
    card = bad.intake_status()
    assert card["configured"] and "받아들여지지 않았다" in card["problem"]


def test_summarize_intake_counts_today_in_kst() -> None:
    now = datetime(2026, 10, 26, 1, 0, tzinfo=UTC)  # KST 10:00
    info = {
        **WORKER,
        "batches": [
            {"run_id": "r3", "status": "waiting", "started_at": "2026-10-25T16:30:00+00:00",
             "children": 0, "children_by_status": {}, "open_approvals": ["apr_3"]},
            {"run_id": "r2", "status": "running", "started_at": "2026-10-25T14:00:00+00:00",
             "children": 2, "children_by_status": {"running": 1, "success": 1},
             "open_approvals": []},
        ],
    }  # fmt: skip
    card = summarize_intake(info, now=now)
    assert card["today"] == 1  # 16:30Z = KST 01:30 오늘, 14:00Z = KST 23:00 어제
    assert card["started"] == 2 and card["startedByStatus"] == {"running": 1, "success": 1}
    assert card["pendingApprovals"] == [
        {"requestId": "apr_3", "runId": "r3", "startedAt": "2026-10-25T16:30:00+00:00"}
    ]


def test_summarize_intake_drops_approvals_of_finished_batches() -> None:
    """
    운영 실측(2026-10-28): 초기화가 접수 작업을 취소해도 Center는 그 실행의 결재를 `open`으로
    세어 카드에 승인 대기로 남았다(답하면 효과 없이 200). 끝난 일괄의 결재는 대기가 아니다.
    """
    now = datetime(2026, 10, 28, 2, 0, tzinfo=UTC)
    info = {
        **WORKER,
        "batches": [
            {"run_id": "r9", "status": "waiting", "started_at": "2026-10-28T01:15:23+00:00",
             "children": 0, "children_by_status": {}, "open_approvals": ["apr_9"]},
            {"run_id": "r8", "status": "cancelled", "started_at": "2026-10-28T01:07:51+00:00",
             "children": 0, "children_by_status": {}, "open_approvals": ["apr_8"]},
            {"run_id": "r7", "status": "failed", "started_at": "2026-10-28T01:05:00+00:00",
             "children": 0, "children_by_status": {}, "open_approvals": ["apr_7"]},
        ],
    }  # fmt: skip
    card = summarize_intake(info, now=now)
    assert [p["requestId"] for p in card["pendingApprovals"]] == ["apr_9"]
    assert [(b["runId"], b["status"], b["openApprovals"]) for b in card["batches"]] == [
        ("r9", "waiting", 1),
        ("r8", "cancelled", 0),
        ("r7", "failed", 0),
    ]


def test_a_job_center_refused_does_not_block_the_next_receive(
    proc: Sc01Process, center: FakeIntakeCenter
) -> None:
    """
    실측(2026-10-26): 실행기가 접수 작업을 `not_ready`로 거절했는데 NowView는 「승인 대기」로 남아
    다음 수신이 409였다. 수신 때 앞 작업의 Center 상태를 읽어 끝났으면 사유를 남기고 새로 보낸다.
    """
    rid = proc.create(executor="center")["demo_run_id"]
    proc.receive(rid, "EX02", actor="u-sales")
    first = center.jobs[0]["job_id"]
    with pytest.raises(DomainError):
        proc.receive(rid, "CP02", actor="u-sales")  # 아직 모른다 — 대기 중이면 막는다
    center.job_states[first] = {"state": "rejected", "state_reason": "not_ready"}
    doc = proc.receive(rid, "CP02", actor="u-sales")
    assert len(center.jobs) == 2 and doc["bpm"]["center"]["job"]["job_id"] != first
    ended = [a for a in doc["audit"] if a["action"] == "center_job_ended"]
    assert ended[-1]["detail"] == {"job_id": first, "reason": "rejected: not_ready"}


def test_reset_does_not_reuse_the_center_idempotency_key(
    proc: Sc01Process, center: FakeIntakeCenter
) -> None:
    """
    실측(2026-10-26): 초기화 뒤 원천 번호가 다시 SRC02라 멱등 키가 겹쳐 Center가 초기화 전의
    (거절된) 작업을 그대로 돌려줬다. 키에 초기화 회차가 들어간다.
    """
    rid = proc.create(executor="center")["demo_run_id"]
    proc.receive(rid, "CP02", actor="u-sales")
    proc.reset(rid, actor="u-demo")
    proc.receive(rid, "CP02", actor="u-sales")
    keys = [m["idempotency_key"] for m in center.messages]
    assert len(set(keys)) == 2 and len(center.jobs) == 2
    assert center.cancelled == [center.jobs[0]["job_id"]]  # 초기화가 앞 일괄을 거뒀다
