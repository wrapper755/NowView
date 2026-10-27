"""
SC03 바깥 실행 — Studio 시험 실행 · Center 서버 실행(장면 1·2 N1~N6과 같은 틀).

* **확장 정의 ↔ BPMN** — `chaeksas/nowview-sc03.extension.json`의 본문 템플릿이 그림의 입력과
  맞는가.
* **Studio** — 진짜 Chaeksas 엔진이 같은 그림을 돌고, 서비스 태스크는 시스템 작업(HTTP 어댑터 흉내,
  시험용
  키)을 부르고, 결재는 Studio 대화상자처럼 엔진에 바로 답한다. NowView 화면 답·각본은 409다.
* **Center** — 장면 1의 가짜 Center·서버 실행기 흉내(`test_sc01_center.py`)를 그대로 쓴다. 착수가
  SC03
  패키지를 기동하고, 각본은 대리 답으로 결재를 닫고, 진행은 폴링으로 온다.
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
from app.sc02 import demo as sc02_demo
from app.sc02.process import Sc02Process
from app.sc03 import demo
from app.sc03.process import PROCESS_PATH, RECORDS, Sc03Process
from app.sc03.view import view

ROOT = Path(__file__).resolve().parents[2]


def test_extension_definition_matches_the_bpmn_service_calls() -> None:
    """정의가 최신 계약 검사를 통과하고, 그림의 모든 서비스 호출이 정의의 입력·본문과 맞는다."""
    raw = (ROOT / "chaeksas" / "nowview-sc03.extension.json").read_bytes()
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
        assert op["request"]["path"].startswith("/api/engine/sc03/demo-runs/{{input.demo_run_id}}/")
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

    def __init__(self, proc: Sc03Process, via: str) -> None:
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
def proc(center: FakeCenter) -> Sc03Process:
    client = CenterClient(CONFIG, transport=httpx.MockTransport(center.handle))
    store = lambda p: SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), p)  # noqa: E731
    sc01 = Sc01Process(store("sc01"), inline_agent=True, center=client, center_wait_s=0)
    sc02 = Sc02Process(store("sc02"), sc01, center=client, center_wait_s=0)
    return Sc03Process(store("sc03"), sc02, center=client, center_wait_s=0)


def _handed_off_sc02(proc: Sc03Process) -> str:
    """장면 1·2를 내장으로 인수까지 — 장면 3의 출발점만 필요하다(실행 위치는 장면마다 따로다)."""
    rid = proc.sc02.create()["demo_run_id"]
    for i in range(len(sc02_demo.steps_for("BASE"))):
        sc02_demo.run_step(proc.sc02, rid, i)
    return rid


def _answer(step: demo.Step) -> dict:
    return dict(step.answer)


def _side(proc: Sc03Process, rid: str, step: demo.Step) -> None:
    """BPM 밖의 각본 단계(회의 기록·Agent·조회)는 실행 위치와 무관하게 NowView 명령이다."""
    if step.kind == "record":
        proc.meeting_record(rid, actor=step.actor, **step.answer)
    elif step.kind == "agent":
        proc.agent(rid, step.answer["kind"], actor=step.actor)


# ─────────────────────────── Studio 시험 실행 ───────────────────────────


def test_studio_run_reaches_completion_through_system_operations(proc: Sc03Process) -> None:
    """
    Studio가 같은 그림을 돌고 NowView는 작업 호출로만 안다 — 첫 호출이 실행을 묶고, 결정은 기록
    작업으로
    적히고, 업무는 기록 때 늦게 연다. 끝까지 가면 장면 3 완료(위험·전망·목표는 그대로).
    """
    rid = proc.create(sc01_demo_run_id=_handed_off_sc02(proc), executor="studio")["demo_run_id"]
    doc = proc.start(rid, actor="u-fin")
    assert doc["review"]["state"] == "ANALYSIS_IN_PROGRESS"
    assert doc["bpm"]["executor"] == "studio" and doc["bpm"]["external_run_id"] is None
    shown = view(doc, center=CONFIG)
    assert shown["executor"] == "studio" and not shown["answerHere"]

    engine = Engine()
    run = engine.start(
        proc.process,
        run_id="run_20270624_100500_a3b3c3",
        log=RunLog(run_id="run_20270624_100500_a3b3c3"),
        env=RunEnv(services=_Calls(proc, "studio")),
        executor="studio",
        inputs={"데모실행ID": rid},
        now=parse_at(doc["clock"]),
    )
    engine.run_until_blocked(run)
    for step in demo.steps_for("BASE"):
        if parse_at(step.at) > parse_at(proc.get(rid)["clock"]):
            proc.set_clock(rid, step.at, actor="u-demo")
        if step.kind != "act":
            _side(proc, rid, step)
            continue
        [pending] = [p for p in run.pendings.values() if p.node_id == step.node_id]
        engine.answer(run, pending.request_id, _answer(step), answered_by=USERS[step.actor]["name"])
        assert engine.run_until_blocked(run) is not State.FAILED, step.node_id

    assert run.state is State.DONE
    doc = proc.get(rid)
    assert doc["bpm"]["external_run_id"] == "run_20270624_100500_a3b3c3"
    assert doc["bpm"]["state"] == "done"
    assert (
        doc["review"]["state"] == "SC03_COMPLETED" and doc["handoff"]["handoff_id"] == "HANDOFF31"
    )
    assert all(t.get("opened_late") for t in doc["tasks"].values())
    assert all(t["status"] == "COMPLETED" for t in doc["tasks"].values())
    # 숫자는 내장과 같다 — 같은 작업 함수
    year = doc["runs"]["RUN-SC03-01"]["result"]["periods"]["year"]
    assert (year["combined"], year["total_gap"]) == ("3299986680", "177303320")
    assert {"Save_Analysis", "Decide_Review", "Record_Complete"} <= set(doc["bpm"]["visited"])

    with pytest.raises(DomainError) as act:
        proc.act(rid, "Confirm_Minutes", {"회의록확인의견": "x"}, actor="u-fin-exec")
    assert act.value.status == 409
    with pytest.raises(DomainError) as script:
        demo.run_step(proc, rid, 1)
    assert script.value.status == 409


def test_a_rejected_record_returns_to_the_same_approval(proc: Sc03Process) -> None:
    """
    Studio 대화상자는 NowView 사전 검사를 거치지 않는다 — 기록이 거절되면 오류 경계로 같은 결재가
    다시
    열리고, 거절 사유는 감사 이력에 남고, 업무 효과는 남지 않는다(타부서가 아닌데 미확인에 질문
    없음).
    """
    rid = proc.create(sc01_demo_run_id=_handed_off_sc02(proc), executor="studio")["demo_run_id"]
    proc.start(rid, actor="u-fin")
    engine = Engine()
    run = engine.start(
        proc.process,
        run_id="run_20270624_100500_a4b4c4",
        log=RunLog(run_id="run_20270624_100500_a4b4c4"),
        env=RunEnv(services=_Calls(proc, "studio")),
        executor="studio",
        inputs={"데모실행ID": rid},
    )
    engine.run_until_blocked(run)
    steps = {s.node_id: s for s in demo.steps_for("BASE") if s.node_id}
    for node in ("Save_Analysis", "Request_Confirm"):
        [p] = [p for p in run.pendings.values() if p.node_id == node]
        engine.answer(run, p.request_id, _answer(steps[node]), answered_by="정하윤")
        engine.run_until_blocked(run)
    [prod] = [p for p in run.pendings.values() if p.node_id == "Confirm_Prod"]
    bad = {**_answer(steps["Confirm_Prod"]), "생산질문": ""}  # 미확인인데 질문이 없다
    engine.answer(run, prod.request_id, bad, answered_by="배정훈")
    engine.run_until_blocked(run)
    assert "Confirm_Prod" in [p.node_id for p in run.pendings.values()]
    doc = proc.get(rid)
    rejected = [a for a in doc["audit"] if a["action"] == "answer_rejected"]
    assert len(rejected) == 1 and rejected[0]["detail"]["status"] == 422
    assert [r["dept"] for r in doc["replies"]] == []  # 반쯤 적힌 효과가 없다


def test_studio_key_cannot_feed_a_center_demo_run(proc: Sc03Process) -> None:
    """N6 — 시험용 키로 온 호출이 Center용 데모 실행에 오면 409이고 묶이지 않는다."""
    rid = proc.create(sc01_demo_run_id=_handed_off_sc02(proc), executor="center")["demo_run_id"]
    with pytest.raises(DomainError) as exc:
        proc.operate(rid, "open_review", {}, external_run_id="run_x", via="studio")
    assert exc.value.status == 409
    assert proc.get(rid)["bpm"]["external_run_id"] is None


# ─────────────────────────── Center 서버 실행 ───────────────────────────


def test_center_run_follows_the_demo_script_through_relay_answers(
    proc: Sc03Process, center: FakeCenter
) -> None:
    """
    착수가 SC03 패키지를 기동하고, 각본의 결재는 대리 답으로 닫히고, 진행은 폴링으로 온다. 업무는
    결재가
    열릴 때 열린다. 과제 인수 결재는 그 과제 책임자의 이름으로 열린다(담당 변수).
    """
    rid = proc.create(sc01_demo_run_id=_handed_off_sc02(proc), executor="center")["demo_run_id"]
    steps = demo.steps_for("BASE")
    doc = demo.run_step(proc, rid, 0)  # D31 착수
    [job] = [j for j in center.jobs if j["bpm_process_id"] == "nowview.sc03"]
    assert job["inputs"] == {"데모실행ID": rid} and job["target"] == {"type": "server_runner"}
    assert doc["bpm"]["center"]["job"]["job_id"] == job["job_id"]

    runner = FakeRunner(proc, center, job, "run_20270624_100500_c5d5e5")
    assert proc.poll_center() == 1
    doc = proc.get(rid)
    assert [w["node_id"] for w in doc["bpm"]["waiting"]] == ["Save_Analysis"]
    assert not doc["tasks"]["TASK-ANALYSIS"].get("opened_late")
    assert view(doc, center=CONFIG)["answerHere"]

    for index in range(1, len(steps)):
        demo.run_step(proc, rid, index)
        runner.step()
        proc.sync_center(rid)

    assert runner.run.state is State.DONE
    after = proc.get(rid)
    assert after["review"]["state"] == "SC03_COMPLETED" and after["bpm"]["state"] == "done"
    relayed = [a["detail"]["node_id"] for a in after["audit"] if a["action"] == "answer_relayed"]
    assert relayed == [s.node_id for s in steps if s.kind == "act"]
    names = {a["answered_by"] for a in center.approvals.values()}
    assert names == {"정하윤", "박서진", "서도현", "배정훈", "오세린", "강민서"}
    at31 = next(a for a in center.approvals.values() if a["node_id"] == "Accept_AT31")
    assert at31["assignees"] == ["배정훈"]
    assert "End" in after["bpm"]["visited"]


def test_center_relay_prechecks_before_touching_center(
    proc: Sc03Process, center: FakeCenter
) -> None:
    """역할(403)·업무 규칙(422)은 Center에 묻기 전에 거절한다 — 입력은 지워지지 않는다."""
    rid = proc.create(sc01_demo_run_id=_handed_off_sc02(proc), executor="center")["demo_run_id"]
    proc.start(rid, actor="u-fin")
    job = next(j for j in center.jobs if j["bpm_process_id"] == "nowview.sc03")
    FakeRunner(proc, center, job, "run_20270624_100500_c6d6e6")
    proc.sync_center(rid)
    before = len(center.calls)
    with pytest.raises(DomainError) as role:
        proc.act(rid, "Save_Analysis", {"기준확인": "확인"}, actor="u-fin-exec")
    assert role.value.status == 403
    assert center.calls[before:] == []


def test_center_unconfigured_leaves_a_reason(proc: Sc03Process) -> None:
    """설정이 없으면 조용히 내장으로 돌지 않는다 — 착수는 되고 「기동하지 않았다」 사유가 남는다."""
    bare = Sc03Process(
        SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), "sc03"),
        proc.sc02,
        center=CenterClient(type(CONFIG)()),
        center_wait_s=0,
    )
    rid = bare.create(sc01_demo_run_id=_handed_off_sc02(proc), executor="center")["demo_run_id"]
    doc = bare.start(rid, actor="u-fin")
    assert doc["review"]["state"] == "ANALYSIS_IN_PROGRESS" and doc["bpm"]["snapshot"] is None
    assert "기동하지 않았다" in doc["bpm"]["center"]["problem"]
    with pytest.raises(DomainError) as relay:
        bare.act(rid, "Save_Analysis", {"기준확인": "확인"}, actor="u-fin")
    assert relay.value.status == 503


def test_reset_on_center_cancels_the_started_job(proc: Sc03Process, center: FakeCenter) -> None:
    rid = proc.create(sc01_demo_run_id=_handed_off_sc02(proc), executor="center")["demo_run_id"]
    proc.start(rid, actor="u-fin")
    job = next(j for j in center.jobs if j["bpm_process_id"] == "nowview.sc03")
    doc = proc.reset(rid, actor="u-demo")
    assert job["job_id"] in center.cancelled
    assert doc["bpm"]["executor"] == "center" and doc["review"]["state"] == "PENDING"
    proc.start(rid, actor="u-fin")
    jobs = [j for j in center.jobs if j["bpm_process_id"] == "nowview.sc03"]
    assert len(jobs) == 2 and jobs[1]["idempotency_key"] != jobs[0]["idempotency_key"]


# ─────────────────────── 화면 직접 진행에서 드러난 것(2026-10-28) ───────────────────────


def test_console_rejection_on_center_reopens_the_same_task_with_its_reason(
    proc: Sc03Process, center: FakeCenter
) -> None:
    """
    Center 콘솔 답은 NowView 사전 검사를 거치지 않는다 — 기록이 거절되면 그림은 같은 결재를
    **새 결재 id로** 다시 연다. 예전에는 그때 새 업무(TASK-REQUEST-2)를 열어 앞 업무가 영영
    「진행」으로 남았고, 다시 열린 폼에는 사유가 없었다(화면 직접 진행 실측). 이제 같은 업무에
    잇고, 사유가 폼에 보인다.
    """
    rid = proc.create(sc01_demo_run_id=_handed_off_sc02(proc), executor="center")["demo_run_id"]
    demo.run_step(proc, rid, 0)
    job = next(j for j in center.jobs if j["bpm_process_id"] == "nowview.sc03")
    runner = FakeRunner(proc, center, job, "run_20270624_100500_e7f7a7")
    proc.sync_center(rid)
    for index in (1, 2):
        demo.run_step(proc, rid, index)
        runner.step()
        proc.sync_center(rid)
    [req] = [a for a in center.approvals.values() if a["node_id"] == "Request_Confirm"]
    good = dict(demo.steps_for("BASE")[3].answer)
    req.update(
        state="answered",
        answer={**good, "회신기한": good["회신기한"] + "6/28 18:00"},  # 기본값에 이어 친 것
        answered_by="정하윤",
    )
    runner.step()
    proc.sync_center(rid)

    doc = proc.get(rid)
    requests = [t for t in doc["tasks"].values() if t["type"] == "REQUEST"]
    assert [t["task_id"] for t in requests] == ["TASK-REQUEST"]
    assert requests[0]["status"] == "ASSIGNED"
    assert "회신기한" in requests[0]["rejected"]["reason"]
    assert requests[0]["history"][-1]["note"] == "기록이 거절되어 같은 결재가 다시 열렸다"
    [shown] = [
        w for w in view(doc, center=CONFIG)["bpm"]["waiting"] if w["nodeId"] == "Request_Confirm"
    ]
    assert shown["rejected"]["status"] == 422 and "회신기한" in shown["rejected"]["reason"]

    # 화면에서 고쳐 다시 내면 같은 업무가 끝나고 사유는 걷힌다 — 화면 답도 각본 단계를 옮긴다
    relayed = proc.act(rid, "Request_Confirm", good, actor="u-fin")
    # 기록이 오기 전에는 「반영 중」이다 — 폼은 사라졌고 다음 업무는 아직이다
    assert view(relayed, center=CONFIG)["bpm"]["center"]["inflight"] == ["Request_Confirm"]
    runner.step()
    proc.sync_center(rid)
    doc = proc.get(rid)
    assert view(doc, center=CONFIG)["bpm"]["center"]["inflight"] == []
    [task] = [t for t in doc["tasks"].values() if t["type"] == "REQUEST"]
    assert task["status"] == "COMPLETED" and "rejected" not in task
    assert (doc["step"], doc["script_index"]) == ("D34", 3)


def test_relay_precheck_refuses_a_malformed_reply_due(
    proc: Sc03Process, center: FakeCenter
) -> None:
    """회신기한 형식은 사전 검사가 본다 — Center에 답하기 전에 422(입력 보존)."""
    rid = proc.create(sc01_demo_run_id=_handed_off_sc02(proc), executor="center")["demo_run_id"]
    demo.run_step(proc, rid, 0)
    job = next(j for j in center.jobs if j["bpm_process_id"] == "nowview.sc03")
    runner = FakeRunner(proc, center, job, "run_20270624_100500_e8f8a8")
    proc.sync_center(rid)
    demo.run_step(proc, rid, 1)
    runner.step()
    proc.sync_center(rid)
    answer = {"회신기한": "2027-06-28T18:00:00+09:006/28 18:00", "요청메모": ""}
    with pytest.raises(DomainError) as exc:
        proc.act(rid, "Request_Confirm", answer, actor="u-fin")
    assert exc.value.status == 422 and "회신기한" in str(exc.value)
    assert not [
        a
        for a in center.approvals.values()
        if a.get("state") == "answered" and a["node_id"] == "Request_Confirm"
    ]
