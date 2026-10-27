"""
SC05 바깥 실행 — Studio 시험 실행 · Center 서버 실행(장면 1~4 N1~N6과 같은 틀).

* **확장 정의 ↔ BPMN** — `chaeksas/nowview-sc05.extension.json`의 본문 템플릿이 그림의 입력과
  맞는가.
* **Studio** — 진짜 Chaeksas 엔진이 같은 그림을 돌고, 서비스 태스크는 시스템 작업(HTTP 어댑터 흉내,
  시험용 키)을
  부르고, 결재는 Studio 대화상자처럼 엔진에 바로 답한다. NowView 화면 답·각본은 409다.
* **Center** — 장면 1의 가짜 Center·서버 실행기 흉내(`test_sc01_center.py`)를 그대로 쓴다. 착수가
  SC05 패키지를
  기동하고, 각본은 대리 답으로 결재를 닫고, 진행은 폴링으로 온다.
"""

from __future__ import annotations

import json
import re
import sqlite3
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

from app.sc01.center import CenterClient
from app.sc01.domain import USERS, DomainError, parse_at
from app.sc01.process import Sc01Process
from app.sc01.store import SqliteSc01Store
from app.sc02.process import Sc02Process
from app.sc03.process import Sc03Process
from app.sc04 import demo as sc04_demo
from app.sc04.process import Sc04Process
from app.sc05 import demo, domain
from app.sc05.process import PROCESS_PATH, RECORDS, Sc05Process
from app.sc05.view import view

ROOT = Path(__file__).resolve().parents[2]


def test_extension_definition_matches_the_bpmn_service_calls() -> None:
    """정의가 최신 계약 검사를 통과하고, 그림의 모든 서비스 호출이 정의의 입력·본문과 맞는다."""
    raw = (ROOT / "chaeksas" / "nowview-sc05.extension.json").read_bytes()
    manifest = ext.ExtensionManifest.model_validate(json.loads(raw))
    assert ext.validate(manifest, from_center=True) == []
    adapter = json.loads(raw)["service"]["adapter"]
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
        assert used <= given, (node.id, used - given)
        assert op["request"]["path"].startswith("/api/engine/sc05/demo-runs/{{input.demo_run_id}}/")
        assert op["request"]["body"]["chaeksas_run_id"] == "{{run_id}}"
        assert set(call.output.values()) <= set(op["response"]["output"]), node.id
        if call.operation in RECORDS:
            assert "answered_by" in op["input_schema"]["required"], call.operation
    [need] = [n for n in process.info.extensions if n.id == manifest.id]
    assert satisfies(manifest.version, need.version)
    for node in process.of_kind("userTask"):
        approval = node.prop("approval")
        assert approval.answered_by_as and approval.answered_via_as, node.id
        [flow] = process.outgoing(node.id)
        call = process.node(flow.target).prop("serviceCall")
        assert call.input["answered_by"] == approval.answered_by_as, node.id
        assert call.input["answered_via"] == approval.answered_via_as, node.id
    for node in process.of_kind("serviceTask"):
        if node.prop("serviceCall").operation not in RECORDS:
            continue
        [boundary] = [b for b in process.of_kind("boundaryEvent") if b.attached_to == node.id]
        [back] = process.outgoing(boundary.id)
        [into] = [f for f in process.flows if f.target == node.id]
        assert back.target == into.source, node.id


# ─────────────────────────── 공통 ───────────────────────────


class _Calls:
    """바깥 실행기의 HTTP 어댑터 흉내 — 4xx는 상태 코드만 남긴다(본문을 버린다)."""

    def __init__(self, proc: Sc05Process, via: str) -> None:
        self.proc, self.via = proc, via

    def call(self, request):
        args = dict(request.input)
        try:
            out = self.proc.operate(
                args.pop("demo_run_id"),
                request.operation,
                args,
                external_run_id=request.run_id,
                node_id=request.node_id,
                via=self.via,
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
def proc(center: FakeCenter) -> Sc05Process:
    client = CenterClient(CONFIG, transport=httpx.MockTransport(center.handle))
    store = lambda p: SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), p)  # noqa: E731
    sc01 = Sc01Process(store("sc01"), inline_agent=True, center=client, center_wait_s=0)
    sc02 = Sc02Process(store("sc02"), sc01, center=client, center_wait_s=0)
    sc03 = Sc03Process(store("sc03"), sc02, center=client, center_wait_s=0)
    sc04 = Sc04Process(store("sc04"), sc03, center=client, center_wait_s=0)
    return Sc05Process(store("sc05"), sc04, center=client, center_wait_s=0)


def _completed_sc04(proc: Sc05Process) -> str:
    """장면 1~4를 내장으로 완료까지 — 장면 5의 출발점만 필요하다(실행 위치는 장면마다 따로다)."""
    sc04 = proc.sc04
    rid = sc04.create(executor="embedded")["demo_run_id"]
    for i in range(len(sc04_demo.steps_for("BASE"))):
        sc04_demo.run_step(sc04, rid, i)
    return rid


def _side(proc: Sc05Process, rid: str, step: demo.Step) -> None:
    """BPM 밖의 각본 단계(Agent·검토·조회)는 실행 위치와 무관하게 NowView 명령이다."""
    if step.kind == "agent":
        proc.agent(rid, step.answer["kind"], actor=step.actor)
    elif step.kind == "review":
        out = demo.latest_output(proc.get(rid), step.answer["kind"])
        if out:
            proc.review_agent(rid, out, actor=step.actor, note=step.answer["note"])


def _studio(proc: Sc05Process, rid: str, run_id: str) -> tuple[Engine, object]:
    engine = Engine()
    run = engine.start(
        proc.process,
        run_id=run_id,
        log=RunLog(run_id=run_id),
        env=RunEnv(services=_Calls(proc, "studio")),
        executor="studio",
        inputs={"데모실행ID": rid},
        now=parse_at(proc.get(rid)["clock"]),
    )
    engine.run_until_blocked(run)
    return engine, run


# ─────────────────────────── Studio 시험 실행 ───────────────────────────


def test_studio_run_reaches_completion_through_system_operations(proc: Sc05Process) -> None:
    """
    Studio가 같은 그림을 돌고 NowView는 작업 호출로만 안다 — 첫 호출이 실행을 묶고, 결정은 기록
    작업으로
    적히고, 업무는 기록 때 늦게 연다. 끝까지 가면 장면 4 완료(위험·전망·목표는 그대로).
    """
    rid = proc.create(sc01_demo_run_id=_completed_sc04(proc), executor="studio")["demo_run_id"]
    doc = proc.start(rid, actor="u-fin")
    assert doc["scene"]["started_at"] is not None
    assert doc["bpm"]["executor"] == "studio" and doc["bpm"]["external_run_id"] is None
    shown = view(doc, center=CONFIG)
    assert shown["executor"] == "studio" and not shown["answerHere"]

    engine, run = _studio(proc, rid, "run_20270713_090000_a4b4c4")
    for step in demo.steps_for("BASE"):
        if parse_at(step.at) > parse_at(proc.get(rid)["clock"]):
            proc.set_clock(rid, step.at, actor="u-demo")
        if step.kind != "act":
            _side(proc, rid, step)
            continue
        [pending] = [p for p in run.pendings.values() if p.node_id == step.node_id]
        engine.answer(
            run,
            pending.request_id,
            demo.resolve(proc.get(rid), dict(step.answer)),
            answered_by=USERS[step.actor]["name"],
        )
        assert engine.run_until_blocked(run) is not State.FAILED, step.node_id

    assert run.state is State.DONE
    doc = proc.get(rid)
    assert doc["bpm"]["external_run_id"] == "run_20270713_090000_a4b4c4"
    assert doc["bpm"]["state"] == "done"
    assert doc["handoff"]["handoff_id"] == "HANDOFF51"
    assert all(t.get("opened_late") for t in doc["tasks"].values())
    assert all(t["status"] == "COMPLETED" for t in doc["tasks"].values())
    # 숫자는 내장과 같다 — 같은 작업 함수
    fs = doc["handoff"]["financial_snapshot"]
    assert (fs["forecast"], fs["gap"]) == ("3428986680", "48303320")
    assert {"Start_Operation", "Approve_Forecast", "Record_Complete"} <= set(doc["bpm"]["visited"])

    with pytest.raises(DomainError) as act:
        proc.act(rid, "Verify_Plan", {}, actor="u-fin-exec")
    assert act.value.status == 409
    with pytest.raises(DomainError) as script:
        demo.run_step(proc, rid, 1)
    assert script.value.status == 409


def test_a_rejected_record_returns_to_the_same_approval(proc: Sc05Process) -> None:
    """
    Studio 대화상자는 NowView 사전 검사를 거치지 않는다 — 기록이 거절되면 오류 경계로 같은 결재가
    다시 열리고,
    거절 사유는 감사 이력에 남고, 업무 효과는 남지 않는다(제외인데 사유 없음).
    """
    rid = proc.create(sc01_demo_run_id=_completed_sc04(proc), executor="studio")["demo_run_id"]
    proc.start(rid, actor="u-fin")
    engine, run = _studio(proc, rid, "run_20270713_090000_b4c4d4")
    step = next(s for s in demo.steps_for("BASE") if s.node_id == "Draft_Plan")
    [p] = [p for p in run.pendings.values() if p.node_id == "Draft_Plan"]
    broken = {**step.answer, "계획초안출처": "", "계획활동": "01 | 칸이 모자란 줄"}
    engine.answer(run, p.request_id, broken, answered_by="서도현")
    engine.run_until_blocked(run)
    assert "Draft_Plan" in [p.node_id for p in run.pendings.values()]
    doc = proc.get(rid)
    rejected = [a for a in doc["audit"] if a["action"] == "answer_rejected"]
    assert len(rejected) == 1 and rejected[0]["detail"]["status"] == 400
    assert doc["plans"] == {}  # 반쯤 적힌 효과가 없다


def test_studio_key_cannot_feed_a_center_demo_run(proc: Sc05Process) -> None:
    """N6 — 시험용 키로 온 호출이 Center용 데모 실행에 오면 409이고 묶이지 않는다."""
    rid = proc.create(sc01_demo_run_id=_completed_sc04(proc), executor="center")["demo_run_id"]
    with pytest.raises(DomainError) as exc:
        proc.operate(rid, "open_scene", {}, external_run_id="run_x", via="studio")
    assert exc.value.status == 409
    assert proc.get(rid)["bpm"]["external_run_id"] is None


# ─────────────────────────── Center 서버 실행 ───────────────────────────


def test_center_run_follows_the_demo_script_through_relay_answers(
    proc: Sc05Process, center: FakeCenter
) -> None:
    """
    착수가 SC04 패키지를 기동하고, 각본의 결재는 대리 답으로 닫히고, 진행은 폴링으로 온다. 업무는
    결재가 열릴
    때 열린다. 인수 결재는 그 책임자의 이름으로 열린다(담당 변수).
    """
    rid = proc.create(sc01_demo_run_id=_completed_sc04(proc), executor="center")["demo_run_id"]
    steps = demo.steps_for("BASE")
    doc = demo.run_step(proc, rid, 0)  # D501 착수
    [job] = [j for j in center.jobs if j["bpm_process_id"] == "nowview.sc05"]
    assert job["inputs"] == {"데모실행ID": rid} and job["target"] == {"type": "server_runner"}
    assert doc["bpm"]["center"]["job"]["job_id"] == job["job_id"]

    runner = FakeRunner(proc, center, job, "run_20270713_090000_c5d5e5")
    assert proc.poll_center() == 1
    doc = proc.get(rid)
    assert [w["node_id"] for w in doc["bpm"]["waiting"]] == ["Draft_Plan"]
    assert not doc["tasks"]["TASK-PLAN_DRAFT"].get("opened_late")
    assert view(doc, center=CONFIG)["answerHere"]

    for index in range(1, len(steps)):
        demo.run_step(proc, rid, index)
        runner.step()
        proc.sync_center(rid)

    assert runner.run.state is State.DONE
    after = proc.get(rid)
    assert after["handoff"]["handoff_id"] == "HANDOFF51" and after["bpm"]["state"] == "done"
    relayed = [a["detail"]["node_id"] for a in after["audit"] if a["action"] == "answer_relayed"]
    assert relayed == [s.node_id for s in steps if s.kind == "act"]
    names = {a["answered_by"] for a in center.approvals.values()}
    assert names == {"정하윤", "강민서", "임하준", "배정훈", "서도현", "권태윤", "문지후", "남유진"}
    ack = next(a for a in center.approvals.values() if a["node_id"] == "Ack_Change")
    assert ack["assignees"] == ["서도현", "윤채원"]
    assert after["handoff"]["financial_snapshot"]["forecast"] == "3428986680"
    assert "End" in after["bpm"]["visited"]


def test_center_relay_ahead_of_the_poller_opens_the_task_on_time(
    proc: Sc05Process, center: FakeCenter
) -> None:
    """
    대리 답이 폴러보다 먼저 결재를 찾아도 업무는 결재가 열려 있던 때 열린 것이다
    (늦게 열지 않는다).
    """
    rid = proc.create(sc01_demo_run_id=_completed_sc04(proc), executor="center")["demo_run_id"]
    node = demo.steps_for("BASE")[2].node_id
    demo.run_step(proc, rid, 0)  # D501 착수
    [job] = [j for j in center.jobs if j["bpm_process_id"] == "nowview.sc05"]
    runner = FakeRunner(proc, center, job, "run_20270713_090000_c7d7e7")
    demo.run_step(proc, rid, 1)  # Agent 초안 — BPM 밖
    # 폴링 없이 바로 대리 답 — 폴러는 아직 결재를 읽지 않았다
    doc = demo.run_step(proc, rid, 2)
    task = domain.task_for_node(doc, node)
    assert task is not None and task["request_id"] and not task.get("opened_late")
    runner.step()
    proc.sync_center(rid)
    doc = proc.get(rid)
    same = [t for t in doc["tasks"].values() if t["type"] == task["type"]]
    assert [t["task_id"] for t in same] == [task["task_id"]]
    assert same[0]["status"] == "COMPLETED" and not same[0].get("opened_late")


def test_center_relay_prechecks_before_touching_center(
    proc: Sc05Process, center: FakeCenter
) -> None:
    """역할(403)·업무 규칙(422)은 Center에 묻기 전에 거절한다 — 입력은 지워지지 않는다."""
    rid = proc.create(sc01_demo_run_id=_completed_sc04(proc), executor="center")["demo_run_id"]
    proc.start(rid, actor="u-fin")
    job = next(j for j in center.jobs if j["bpm_process_id"] == "nowview.sc05")
    FakeRunner(proc, center, job, "run_20270713_090000_c6d6e6")
    proc.sync_center(rid)
    before = len(center.calls)
    step = next(s for s in demo.steps_for("BASE") if s.node_id == "Draft_Plan")
    answer = {**step.answer, "계획초안출처": ""}
    with pytest.raises(DomainError) as role:
        proc.act(rid, "Draft_Plan", answer, actor="u-prod-lead")
    assert role.value.status == 403
    with pytest.raises(DomainError) as rule:
        proc.act(rid, "Draft_Plan", {**answer, "계획활동": ""}, actor="u-buy-lead")
    assert rule.value.status == 422
    assert center.calls[before:] == []


def test_center_unconfigured_leaves_a_reason(proc: Sc05Process) -> None:
    """설정이 없으면 조용히 내장으로 돌지 않는다 — 착수는 되고 「기동하지 않았다」 사유가 남는다."""
    bare = Sc05Process(
        SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), "sc05"),
        proc.sc04,
        center=CenterClient(type(CONFIG)()),
        center_wait_s=0,
    )
    rid = bare.create(sc01_demo_run_id=_completed_sc04(proc), executor="center")["demo_run_id"]
    doc = bare.start(rid, actor="u-fin")
    assert doc["scene"]["started_at"] and doc["bpm"]["snapshot"] is None
    assert "기동하지 않았다" in doc["bpm"]["center"]["problem"]
    with pytest.raises(DomainError) as relay:
        bare.act(rid, "Draft_Plan", {}, actor="u-buy-lead")
    assert relay.value.status == 503


def test_reset_on_center_cancels_the_started_job(proc: Sc05Process, center: FakeCenter) -> None:
    rid = proc.create(sc01_demo_run_id=_completed_sc04(proc), executor="center")["demo_run_id"]
    proc.start(rid, actor="u-fin")
    job = next(j for j in center.jobs if j["bpm_process_id"] == "nowview.sc05")
    doc = proc.reset(rid, actor="u-demo")
    assert job["job_id"] in center.cancelled
    assert doc["bpm"]["executor"] == "center" and doc["scene"]["started_at"] is None
    proc.start(rid, actor="u-fin")
    jobs = [j for j in center.jobs if j["bpm_process_id"] == "nowview.sc05"]
    assert len(jobs) == 2 and jobs[1]["idempotency_key"] != jobs[0]["idempotency_key"]


# ─────────────────────── 화면 직접 진행에서 드러난 것(2026-10-28) ───────────────────────


def test_center_screen_answers_show_inflight_and_move_the_script_marker(
    proc: Sc05Process, center: FakeCenter
) -> None:
    """
    화면 답(대리 답)은 결재만 닫는다 — 기록이 오기 전에는 「Center 반영 중」이고(`inflight`), 기록이
    오면 걷히고 각본 단계가 따라온다. 그 뒤 「다음 단계」(각본)가 남은 단계부터 잇는다 — 예전에는
    D500에 머물러 「단계를 건너뛸 수 없다」였다(화면 직접 진행 실측).
    """
    rid = proc.create(sc01_demo_run_id=_completed_sc04(proc), executor="center")["demo_run_id"]
    steps = demo.steps_for("BASE")
    doc = proc.start(rid, actor="u-fin")
    assert (doc["step"], doc["script_index"]) == ("D501", 0)
    [job] = [j for j in center.jobs if j["bpm_process_id"] == "nowview.sc05"]
    runner = FakeRunner(proc, center, job, "run_20270713_090000_c7d7e7")
    proc.sync_center(rid)

    given = {k: ("" if str(v).startswith("@") else v) for k, v in steps[2].answer.items()}
    relayed = proc.act(rid, "Draft_Plan", given, actor="u-buy-lead")
    assert view(relayed, center=CONFIG)["bpm"]["center"]["inflight"] == ["Draft_Plan"]
    runner.step()
    proc.sync_center(rid)
    doc = proc.get(rid)
    assert view(doc, center=CONFIG)["bpm"]["center"]["inflight"] == []
    assert (doc["step"], doc["script_index"]) == ("D502", 2)

    for index in (3, 4, 5):
        demo.run_step(proc, rid, index)
        runner.step()
        proc.sync_center(rid)
    doc = proc.get(rid)
    # 각본이 대리 답한 결재의 기록은 각본 몫이다 — 두 번 세지 않는다
    assert doc["script_index"] == 5 and doc["script_follow"] == {"ahead": [], "pending": []}
