"""
SC02 바깥 실행 — Studio 시험 실행 · Center 서버 실행(SC01 N1~N6과 같은 틀).

* **확장 정의 ↔ BPMN** — `chaeksas/nowview-sc02.extension.json`의 본문 템플릿이 그림의 입력과
  맞는가(어긋나면 어댑터가 실행 중에 멈춘다).
* **Studio** — 진짜 Chaeksas 엔진이 같은 그림을 돌고, 서비스 태스크는 시스템 작업(HTTP 어댑터 흉내,
  시험용 키)을 부르고, 결재는 Studio 대화상자처럼 엔진에 바로 답한다. NowView 화면 답·각본은 409다.
* **Center** — SC01의 가짜 Center·서버 실행기 흉내(`test_sc01_center.py`)를 그대로 쓴다. 요청
  접수가 SC02 패키지를 기동하고, 각본은 대리 답으로 결재를 닫고, 진행은 폴링으로 온다.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from pathlib import Path

import httpx
import pytest
from chaeksas.contracts import extension as ext
from chaeksas.contracts._semver import satisfies
from chaeksas.contracts.bpmn_ext import read_process
from chaeksas.core.engine import Engine, RunEnv, State
from chaeksas.core.run_log import RunLog
from chaeksas.core.services import OpOutcome, ServiceCallError
from test_sc01_center import CONFIG, FakeCenter, FakeRunner

from app.sc01 import demo as sc01_demo
from app.sc01.center import CenterClient
from app.sc01.domain import USERS, DomainError, parse_at
from app.sc01.process import Sc01Process
from app.sc01.store import SqliteSc01Store
from app.sc02 import demo, domain
from app.sc02.process import DECIDED_BY, PROCESS_PATH, RECORDS, Sc02Process
from app.sc02.view import view

ROOT = Path(__file__).resolve().parents[2]


# ─────────────────────────── 확장 정의 ↔ BPMN
# ───────────────────────────


def test_extension_definition_matches_the_bpmn_service_calls() -> None:
    """정의가 최신 계약 검사를 통과하고, 그림의 모든 서비스 호출이 정의의 입력·본문과 맞는다."""
    raw = (ROOT / "chaeksas" / "nowview-sc02.extension.json").read_bytes()
    manifest = ext.ExtensionManifest.model_validate(json.loads(raw))
    assert ext.validate(manifest, from_center=True) == []
    adapter = json.loads(raw)["service"]["adapter"]
    # 운영계가 기본 주소이고 로컬 Center만 덮어쓴다(ADR-0097) — SC01 정의와 같은 범위
    assert manifest.service.base_url == "https://www.nowview.work"
    assert adapter["allowed_hosts"] == ["www.nowview.work", "localhost", "host.docker.internal"]
    assert adapter["auth"] == {"type": "bearer"}
    operations = {o["name"]: o for o in adapter["operations"]}

    process = read_process(PROCESS_PATH.read_bytes())
    for node in process.of_kind("serviceTask"):
        call = node.prop("serviceCall")
        assert call.app_id == manifest.id, node.id
        op = operations[call.operation]
        given = set(call.input)
        assert set(op["input_schema"]["required"]) <= given, node.id
        used = set(re.findall(r"\{\{input\.(\w+)\}\}", json.dumps(op["request"])))
        # 본문 템플릿의 입력이 그림에 없으면 어댑터가 호출을 실패시킨다(CLAUDE.md 4.3)
        assert used <= given, (node.id, used - given)
        assert op["request"]["path"].startswith("/api/engine/sc02/demo-runs/{{input.demo_run_id}}/")
        assert op["request"]["body"]["chaeksas_run_id"] == "{{run_id}}"
        if call.operation in RECORDS or call.operation in DECIDED_BY:
            assert "answered_by" in op["input_schema"]["required"], call.operation
    # 그림이 확장을 선언해야 패키지 `requires.extensions`에 올라 실행기가 정의(주소)를 받는다(SC01
    # 실측)
    [need] = [n for n in process.info.extensions if n.id == manifest.id]
    assert satisfies(manifest.version, need.version)
    # 결재마다 답한 사람·대리 답 경로를 변수로 받고 뒤의 기록 작업에 싣는다(R1)
    for node in process.of_kind("userTask"):
        approval = node.prop("approval")
        assert approval.answered_by_as and approval.answered_via_as, node.id
        [flow] = process.outgoing(node.id)
        call = process.node(flow.target).prop("serviceCall")
        assert call.input["answered_by"] == approval.answered_by_as, node.id
        assert call.input["answered_via"] == approval.answered_via_as, node.id
    # 기록 작업마다 오류 경계 — 거절되면 같은 결재로 돌아간다
    for node in process.of_kind("serviceTask"):
        if node.prop("serviceCall").operation not in RECORDS:
            continue
        [boundary] = [b for b in process.of_kind("boundaryEvent") if b.attached_to == node.id]
        [back] = process.outgoing(boundary.id)
        [into] = [f for f in process.flows if f.target == node.id]
        assert back.target == into.source, node.id


# ─────────────────────────── 공통
# ───────────────────────────


def _handed_off_sc01(sc01: Sc01Process) -> str:
    doc = sc01.create()
    for i in range(len(sc01_demo.BASE)):
        doc = sc01_demo.run_step(sc01, doc["demo_run_id"], i)
    return doc["demo_run_id"]


class _StudioCalls:
    """Studio의 HTTP 어댑터 흉내 — 시험용 키(via=studio). 4xx는 상태 코드만 남긴다."""

    def __init__(self, proc: Sc02Process) -> None:
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
                via="studio",
            )
        except DomainError as exc:
            raise ServiceCallError(
                f"{request.app_id}.{request.operation}이 {exc.status}를 돌려줬다",
                code="http_error",
                status=exc.status,
            ) from exc
        return OpOutcome(output=out)


@pytest.fixture
def center() -> FakeCenter:
    return FakeCenter()


@pytest.fixture
def proc(center: FakeCenter) -> Sc02Process:
    client = CenterClient(CONFIG, transport=httpx.MockTransport(center.handle))
    sc01 = Sc01Process(
        SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False)),
        inline_agent=True,
        center=client,
        center_wait_s=0,
    )
    return Sc02Process(
        SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), "sc02"),
        sc01,
        center=client,
        center_wait_s=0,
    )


def _answer(step: demo.Step) -> dict:
    return {k: v for k, v in step.answer.items() if v is not None and v != ""}


# ─────────────────────────── Studio 시험 실행
# ───────────────────────────


def test_studio_run_reaches_the_handoff_through_system_operations(proc: Sc02Process) -> None:
    """
    Studio가 같은 그림을 돌고 NowView는 작업 호출로만 안다 — 첫 호출이 실행을 묶고, 결정은 기록
    작업으로 적히고, 업무는 기록 때 늦게 연다. 끝까지 가면 인계 완료(위험·전망은 그대로).
    """
    rid = proc.create(sc01_demo_run_id=_handed_off_sc01(proc.sc01), executor="studio")[
        "demo_run_id"
    ]
    doc = proc.receive(rid, domain.REQUEST_ID, actor="u-buy")
    assert doc["bpm"]["executor"] == "studio" and doc["bpm"]["external_run_id"] is None
    assert doc["bpm"]["snapshot"] is None  # 내장 BPM은 돌지 않는다
    shown = view(doc, center=CONFIG)
    assert shown["executor"] == "studio" and not shown["answerHere"]

    engine = Engine()
    run = engine.start(
        proc.process,
        run_id="run_20270617_090000_a1b1c1",
        log=RunLog(run_id="run_20270617_090000_a1b1c1"),
        env=RunEnv(services=_StudioCalls(proc)),
        executor="studio",
        inputs={"데모실행ID": rid, "요청ID": domain.REQUEST_ID},
        now=parse_at(doc["clock"]),
    )
    engine.run_until_blocked(run)
    steps = [s for s in demo.steps_for("BASE") if s.node_id]
    for step in steps:
        if parse_at(step.at) > parse_at(proc.get(rid)["clock"]):
            proc.set_clock(rid, step.at, actor="u-demo")
        [pending] = [p for p in run.pendings.values() if p.node_id == step.node_id]
        engine.answer(run, pending.request_id, _answer(step), answered_by=USERS[step.actor]["name"])
        assert engine.run_until_blocked(run) is not State.FAILED, step.node_id

    assert run.state is State.DONE
    doc = proc.get(rid)
    assert doc["bpm"]["external_run_id"] == "run_20270617_090000_a1b1c1"
    assert doc["bpm"]["state"] == "done"
    assert doc["handoff"]["status"] == "HANDED_OFF" and doc["scene"] == "HANDED_OFF"
    assert doc["approval_status"] == "APPROVED" and "C02-APP01" in doc["cost_versions"]
    assert all(t.get("opened_late") for t in doc["tasks"].values())
    assert all(t["status"] == "COMPLETED" for t in doc["tasks"].values())
    # 숫자는 내장과 같다 — 같은 작업 함수
    year = next(p for p in doc["runs"]["RUN-APP01"]["result"]["periods"] if p["kind"] == "year")
    assert year["profit_combined"] == "3299986680"
    assert {"Verify_Request", "Approve_CEO", "Record_Accept"} <= set(doc["bpm"]["visited"])

    # 화면 답·각본은 Studio에서 답하라는 409
    with pytest.raises(DomainError) as act:
        proc.act(rid, "Approve_Lead", {"결정": "승인", "결재의견": "x"}, actor="u-buy-lead")
    assert act.value.status == 409 and "Studio" in str(act.value)
    with pytest.raises(DomainError) as script:
        demo.run_step(proc, rid, 1)
    assert script.value.status == 409


def test_a_rejected_record_returns_to_the_same_approval(proc: Sc02Process) -> None:
    """
    Studio 대화상자는 NowView 사전 검사를 거치지 않는다 — 기록이 거절되면 오류 경계로 같은 결재가
    다시 열리고, 거절 사유는 감사 이력(`answer_rejected`)에 남고, 업무 효과는 남지 않는다.
    """
    rid = proc.create(sc01_demo_run_id=_handed_off_sc01(proc.sc01), executor="studio")[
        "demo_run_id"
    ]
    proc.receive(rid, "REQ-2706-01-MISSING", actor="u-buy")  # 적용일 누락 — 검사 오류
    engine = Engine()
    run = engine.start(
        proc.process,
        run_id="run_20270617_090000_a2b2c2",
        log=RunLog(run_id="run_20270617_090000_a2b2c2"),
        env=RunEnv(services=_StudioCalls(proc)),
        executor="studio",
        inputs={"데모실행ID": rid, "요청ID": domain.REQUEST_ID},
    )
    engine.run_until_blocked(run)
    [pending] = run.pendings.values()
    # 검사 오류가 남았는데 확인완료 — 이번에는 사전 검사가 없다(콘솔·Studio 답)
    engine.answer(
        run, pending.request_id, {"확인결과": "확인완료", "확인의견": "-"}, answered_by="윤채원"
    )
    engine.run_until_blocked(run)
    assert [p.node_id for p in run.pendings.values()] == ["Verify_Request"]
    doc = proc.get(rid)
    rejected = [a for a in doc["audit"] if a["action"] == "answer_rejected"]
    assert len(rejected) == 1 and rejected[0]["detail"]["status"] == 409
    assert doc["request"]["status"] == "RECEIVED"  # 반쯤 적힌 효과가 없다


def test_studio_key_cannot_feed_a_center_demo_run(proc: Sc02Process) -> None:
    """
    N6 — 키가 실행 위치를 말한다. 시험용 키로 온 호출이 Center용 데모 실행에 오면 409이고 묶이지
    않는다.
    """
    rid = proc.create(sc01_demo_run_id=_handed_off_sc01(proc.sc01), executor="center")[
        "demo_run_id"
    ]
    with pytest.raises(DomainError) as exc:
        proc.operate(
            rid,
            "screen_request",
            {"request_id": domain.REQUEST_ID},
            external_run_id="run_x",
            via="studio",
        )
    assert exc.value.status == 409
    assert proc.get(rid)["bpm"]["external_run_id"] is None


# ─────────────────────────── Center 서버 실행
# ───────────────────────────


def test_center_run_follows_the_demo_script_through_relay_answers(
    proc: Sc02Process, center: FakeCenter
) -> None:
    """
    요청 접수가 SC02 패키지를 기동하고, 각본의 결재는 대리 답으로 닫히고, 진행은 폴링으로 온다.
    업무는 결재가 열릴 때 열린다(늦게 열지 않는다). 끝나면 도달한 종료만 지나온 노드에 있다.
    """
    sc01_id = _handed_off_sc01(proc.sc01)
    rid = proc.create(sc01_demo_run_id=sc01_id, executor="center")["demo_run_id"]
    steps = demo.steps_for("BASE")
    doc = demo.run_step(proc, rid, 0)  # D01 접수
    [job] = center.jobs
    assert job["bpm_process_id"] == "nowview.sc02" and job["target"] == {"type": "server_runner"}
    assert job["inputs"] == {"데모실행ID": rid, "요청ID": domain.REQUEST_ID}
    assert doc["bpm"]["center"]["job"]["job_id"] == job["job_id"]

    runner = FakeRunner(proc, center, job, "run_20270617_090000_c1d1e1")
    assert proc.poll_center() == 1
    doc = proc.get(rid)
    assert [w["node_id"] for w in doc["bpm"]["waiting"]] == ["Verify_Request"]
    task = doc["tasks"]["TASK-VERIFY"]
    assert not task.get("opened_late") and task["request_id"].startswith("apr_")
    shown = view(doc, center=CONFIG)
    assert shown["answerHere"] and shown["bpm"]["waiting"][0]["nodeId"] == "Verify_Request"

    for index in range(1, len(steps)):
        demo.run_step(proc, rid, index)
        runner.step()
        proc.sync_center(rid)

    assert runner.run.state is State.DONE
    after = proc.get(rid)
    assert after["handoff"]["status"] == "HANDED_OFF" and after["bpm"]["state"] == "done"
    assert after["bpm"]["waiting"] == []
    relayed = [a["detail"]["node_id"] for a in after["audit"] if a["action"] == "answer_relayed"]
    assert relayed == [s.node_id for s in steps if s.node_id]
    assert {a["answered_by"] for a in center.approvals.values()} == {
        "윤채원",
        "서도현",
        "문지후",
        "임하준",
        "정하윤",
    }
    assert not [t for t in after["tasks"].values() if t.get("opened_late")]
    # 종료는 「시작」만 기록된다 — 도달한 것(End)만 지나온 노드다. 반려·재협상 종료는 없다.
    assert "End" in after["bpm"]["visited"] and "End_Rejected" not in after["bpm"]["visited"]
    assert after["runs"]["RUN-APP01"]["result"]["next12"]["increase"] == "18817440"


def test_center_relay_ahead_of_the_poller_opens_the_task_on_time(
    proc: Sc02Process, center: FakeCenter
) -> None:
    """
    대리 답이 폴러보다 먼저 결재를 찾아도 업무는 결재가 열려 있던 때 열린 것이다
    (늦게 열지 않는다 — 운영 Center 각본 실측 9/12건).
    """
    rid = proc.create(sc01_demo_run_id=_handed_off_sc01(proc.sc01), executor="center")[
        "demo_run_id"
    ]
    demo.run_step(proc, rid, 0)  # D01 접수
    [job] = center.jobs
    runner = FakeRunner(proc, center, job, "run_20270617_090000_c5d5e5")
    # 폴링 없이 바로 대리 답 — 폴러는 아직 결재를 읽지 않았다
    doc = demo.run_step(proc, rid, 1)
    task = domain.task_for_node(doc, "Verify_Request")
    assert task is not None and task["request_id"] and not task.get("opened_late")
    runner.step()
    proc.sync_center(rid)
    doc = proc.get(rid)
    same = [t for t in doc["tasks"].values() if t["type"] == task["type"]]
    assert [t["task_id"] for t in same] == [task["task_id"]]
    assert same[0]["status"] == "COMPLETED" and not same[0].get("opened_late")


def test_center_script_waits_for_the_record_before_the_next_step(
    proc: Sc02Process, center: FakeCenter
) -> None:
    """
    각본은 대리 답한 결재의 업무가 끝난 뒤 다음 단계로 간다 — 아니면 다음 단계가 시계를 먼저
    옮겨 업무가 뒤 시각으로 끝났다(운영 Center 실측: 원문 대조 09:20 → 10:00).
    """
    rid = proc.create(sc01_demo_run_id=_handed_off_sc01(proc.sc01), executor="center")[
        "demo_run_id"
    ]
    steps = demo.steps_for("BASE")
    demo.run_step(proc, rid, 0)
    [job] = center.jobs
    runner = FakeRunner(proc, center, job, "run_20270617_090000_c6d6e6")
    proc.center_wait_s = 2
    stop = threading.Event()

    def run() -> None:  # 서버 실행기 — 대리 답과 따로 작업을 부른다
        while not stop.is_set():
            runner.step()
            proc.sync_center(rid)
            time.sleep(0.05)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        for index in (1, 2, 3):
            demo.run_step(proc, rid, index)
    finally:
        stop.set()
        worker.join()
    doc = proc.get(rid)
    for index in (1, 2, 3):
        task = domain.task_for_node(doc, steps[index].node_id) or next(
            t for t in doc["tasks"].values() if t["node_id"] == steps[index].node_id
        )
        assert task["status"] == "COMPLETED", steps[index].node_id
        assert parse_at(task["completed_at"]) == parse_at(steps[index].at), steps[index].node_id
    assert not [a for a in doc["audit"] if a["action"] == "overdue_alert"]


def test_center_relay_prechecks_before_touching_center(
    proc: Sc02Process, center: FakeCenter
) -> None:
    """역할(403)·차례·버전(409)은 Center에 묻기 전에 거절한다 — 입력은 지워지지 않는다."""
    rid = proc.create(sc01_demo_run_id=_handed_off_sc01(proc.sc01), executor="center")[
        "demo_run_id"
    ]
    proc.receive(rid, domain.REQUEST_ID, actor="u-buy")
    FakeRunner(proc, center, center.jobs[0], "run_20270617_090000_c2d2e2")
    proc.sync_center(rid)
    before = len(center.calls)
    with pytest.raises(DomainError) as role:
        proc.act(
            rid, "Verify_Request", {"확인결과": "확인완료", "확인의견": "-"}, actor="u-buy-lead"
        )
    assert role.value.status == 403
    assert center.calls[before:] == []
    assert all(a["state"] == "open" for a in center.approvals.values())


def test_center_unconfigured_leaves_a_reason_instead_of_running_embedded(
    proc: Sc02Process,
) -> None:
    """
    설정이 없으면 조용히 내장으로 돌지 않는다 — 요청은 등록되고 「기동하지 않았다」 사유가 남는다.
    """
    bare = Sc02Process(
        SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), "sc02"),
        proc.sc01,
        center=CenterClient(type(CONFIG)()),
        center_wait_s=0,
    )
    rid = bare.create(sc01_demo_run_id=_handed_off_sc01(proc.sc01), executor="center")[
        "demo_run_id"
    ]
    doc = bare.receive(rid, domain.REQUEST_ID, actor="u-buy")
    assert doc["request"]["status"] == "RECEIVED" and doc["bpm"]["snapshot"] is None
    assert "기동하지 않았다" in doc["bpm"]["center"]["problem"]
    with pytest.raises(DomainError) as relay:
        bare.act(rid, "Verify_Request", {"확인결과": "확인완료", "확인의견": "-"}, actor="u-buy")
    assert relay.value.status == 503


def test_reset_on_center_cancels_the_started_job(proc: Sc02Process, center: FakeCenter) -> None:
    rid = proc.create(sc01_demo_run_id=_handed_off_sc01(proc.sc01), executor="center")[
        "demo_run_id"
    ]
    proc.receive(rid, domain.REQUEST_ID, actor="u-buy")
    job_id = center.jobs[0]["job_id"]
    doc = proc.reset(rid, actor="u-demo")
    assert center.cancelled == [job_id]
    assert doc["bpm"]["executor"] == "center" and doc["request"] is None
    # 초기화 뒤 다시 접수하면 멱등 키가 달라 새 작업이다(SC01 N5 실측과 같은 함정)
    proc.receive(rid, domain.REQUEST_ID, actor="u-buy")
    assert (
        len(center.jobs) == 2
        and center.jobs[1]["idempotency_key"] != center.jobs[0]["idempotency_key"]
    )
