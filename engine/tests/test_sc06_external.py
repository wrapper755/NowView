"""
SC06 확인 절차의 바깥 실행 — Studio 시험 실행 · Center 서버 실행(장면 1~5 N1~N6과 같은 틀).

* **확장 정의 ↔ BPMN** — `chaeksas/nowview-sc06.extension.json`의 본문 템플릿이 그림의 입력과
  맞는가.
* **Studio** — 진짜 Chaeksas 엔진이 같은 그림을 돌고, 서비스 태스크는 시스템 작업(HTTP 어댑터 흉내,
  시험용 키)을 부르고, 결재는 Studio 대화상자처럼 엔진에 바로 답한다. NowView 화면 답·각본은 409다.
* **Center** — 장면 1의 가짜 Center·서버 실행기 흉내(`test_sc01_center.py`)를 그대로 쓴다. 착수가
  SC06 패키지를 기동하고, 각본은 대리 답으로 결재를 닫고, 진행은 폴링으로 온다.
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
from chaeksas.contracts.bpmn_ext import read_process, validate
from chaeksas.core.engine import Engine, RunEnv, State
from chaeksas.core.run_log import RunLog
from conftest import C15Calls
from test_sc01_center import CONFIG, FakeCenter, FakeRunner

from app.sc01.center import CenterClient
from app.sc01.domain import USERS, DomainError, parse_at
from app.sc01.process import Sc01Process
from app.sc01.store import SqliteSc01Store
from app.sc02.process import Sc02Process
from app.sc03.process import Sc03Process
from app.sc04.process import Sc04Process
from app.sc05 import demo as sc05_demo
from app.sc05.process import Sc05Process
from app.sc06 import confirm, demo
from app.sc06.process import PROCESS_PATH, RECORDS, Sc06Process
from app.sc06.view import view

ROOT = Path(__file__).resolve().parents[2]


def test_extension_definition_matches_the_bpmn_service_calls() -> None:
    """정의가 최신 계약 검사를 통과하고, 그림의 모든 서비스 호출이 정의의 입력·본문과 맞는다."""
    raw = (ROOT / "chaeksas" / "nowview-sc06.extension.json").read_bytes()
    manifest = ext.ExtensionManifest.model_validate(json.loads(raw))
    assert ext.validate(manifest, from_center=True) == []
    adapter = json.loads(raw)["service"]["adapter"]
    assert manifest.service.base_url == "https://www.nowview.work"
    assert adapter["allowed_hosts"] == ["www.nowview.work", "localhost", "host.docker.internal"]
    assert adapter["auth"] == {"type": "bearer"}
    operations = {o["name"]: o for o in adapter["operations"]}
    process = read_process(PROCESS_PATH.read_bytes())
    assert validate(process) == []
    for node in process.of_kind("serviceTask"):
        call = node.prop("serviceCall")
        assert call.app_id == manifest.id, node.id
        op = operations[call.operation]
        given = set(call.input)
        assert set(op["input_schema"]["required"]) <= given, node.id
        used = set(re.findall(r"\{\{input\.(\w+)\}\}", json.dumps(op["request"])))
        assert used <= given, (node.id, used - given)
        assert op["request"]["path"].startswith("/api/engine/sc06/demo-runs/{{input.demo_run_id}}/")
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


@pytest.fixture
def center() -> FakeCenter:
    return FakeCenter()


@pytest.fixture
def proc(center: FakeCenter) -> Sc06Process:
    client = CenterClient(CONFIG, transport=httpx.MockTransport(center.handle))
    store = lambda p: SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), p)  # noqa: E731
    sc01 = Sc01Process(store("sc01"), inline_agent=True, center=client, center_wait_s=0)
    sc02 = Sc02Process(store("sc02"), sc01, center=client, center_wait_s=0)
    sc03 = Sc03Process(store("sc03"), sc02, center=client, center_wait_s=0)
    sc04 = Sc04Process(store("sc04"), sc03, center=client, center_wait_s=0)
    sc05 = Sc05Process(store("sc05"), sc04, center=client, center_wait_s=0)
    return Sc06Process(store("sc06"), sc05, center=client, center_wait_s=0)


def _completed_sc05(proc: Sc06Process) -> str:
    """장면 1~5를 내장으로 완료까지 — 장면 6의 출발점만 필요하다(실행 위치는 장면마다 따로다)."""
    sc05 = proc.sc05
    rid = sc05.create(executor="embedded")["demo_run_id"]
    for i in range(len(sc05_demo.steps_for("BASE"))):
        sc05_demo.run_step(sc05, rid, i)
    return rid


def _studio(proc: Sc06Process, rid: str, run_id: str) -> tuple[Engine, object]:
    engine = Engine()
    run = engine.start(
        proc.process,
        run_id=run_id,
        log=RunLog(run_id=run_id),
        env=RunEnv(services=C15Calls(proc, origin="test")),
        executor="studio",
        inputs={"데모실행ID": rid},
        now=parse_at(proc.get(rid)["clock"]),
    )
    engine.run_until_blocked(run)
    return engine, run


# ─────────────────────────── Studio 시험 실행 ───────────────────────────


def test_studio_run_reaches_the_ceo_report_through_system_operations(proc: Sc06Process) -> None:
    """
    Studio가 같은 그림을 돌고 NowView는 작업 호출로만 안다 — 첫 호출이 실행을 묶고, 결정은 기록
    작업으로 적히고, 업무는 기록 때 늦게 연다. 끝까지 가면 대표 보고(숫자·기록은 내장과 같다).
    """
    rid = proc.create(sc01_demo_run_id=_completed_sc05(proc), executor="studio")["demo_run_id"]
    doc = proc.start(rid, actor="u-fin")
    assert doc["bpm"]["executor"] == "studio" and doc["bpm"]["external_run_id"] is None
    shown = view(doc, center=CONFIG)
    assert shown["executor"] == "studio" and not shown["answerHere"]

    engine, run = _studio(proc, rid, "run_20280111_090000_a6b6c6")
    for step in demo.steps_for():
        if step.kind != "act":
            continue
        [pending] = [p for p in run.pendings.values() if p.node_id == step.node_id]
        engine.answer(
            run, pending.request_id, dict(step.answer), answered_by=USERS[step.actor]["name"]
        )
        assert engine.run_until_blocked(run) is not State.FAILED, step.node_id

    assert run.state is State.DONE
    doc = proc.get(rid)
    assert doc["bpm"]["external_run_id"] == "run_20280111_090000_a6b6c6"
    assert doc["bpm"]["state"] == "done"
    assert doc["report"]["state"] == "REPORTED" and doc["report"]["problems"] == []
    assert all(t["opened_late"] and t["status"] == "COMPLETED" for t in doc["tasks"].values())
    for record_id, planned in doc["schedule"].items():
        got = doc["report_records"][record_id]
        assert (got["actor"], got["at"], got["content"]) == (
            planned["actor"],
            planned["at"],
            planned["content"],
        ), record_id
    assert {"Task_Open", "Report_CEO", "Record_Report_CEO"} <= set(doc["bpm"]["visited"])

    with pytest.raises(DomainError) as act:
        proc.act(rid, "Confirm_Prod", {}, actor="u-prod-exec")
    assert act.value.status == 409
    with pytest.raises(DomainError) as script:
        demo.run_step(proc, rid, 1)
    assert script.value.status == 409


def test_a_rejected_finalize_returns_to_the_same_approval(proc: Sc06Process) -> None:
    """
    Studio 대화상자는 NowView 사전 검사를 거치지 않는다 — 결론 숫자가 산정과 다른데 확정하면 기록이
    거절되고(422 REPORT_INVALID, 남은 항목은 감사 이력에) 오류 경계로 같은 결재가 다시 열린다.
    효과는 없다.
    """
    rid = proc.create(sc01_demo_run_id=_completed_sc05(proc), executor="studio")["demo_run_id"]
    proc.start(rid, actor="u-fin")
    engine, run = _studio(proc, rid, "run_20280111_090000_b6c6d6")
    steps = [s for s in demo.steps_for() if s.kind == "act"]
    for step in steps[:4]:
        answer = dict(step.answer)
        if step.node_id == "Draft_Conclusion":
            answer["보고결론"] = answer["보고결론"].replace("25.8백만원", "26.0백만원")
        [p] = [p for p in run.pendings.values() if p.node_id == step.node_id]
        engine.answer(run, p.request_id, answer, answered_by=USERS[step.actor]["name"])
        engine.run_until_blocked(run)
    [p] = [p for p in run.pendings.values() if p.node_id == "Finalize_Report"]
    engine.answer(run, p.request_id, dict(steps[4].answer), answered_by="강민서")
    engine.run_until_blocked(run)
    assert [p.node_id for p in run.pendings.values()] == ["Finalize_Report"]
    doc = proc.get(rid)
    [rejected] = [a for a in doc["audit"] if a["action"] == "answer_rejected"]
    assert rejected["detail"]["status"] == 422
    assert any("26.0" in i for i in rejected["detail"]["blocking_items"])
    assert doc["report"]["state"] == "DRAFT" and "CF61-R" not in doc["report_records"]


def test_studio_key_cannot_feed_a_center_demo_run(proc: Sc06Process) -> None:
    """N6 — 시험용 키로 온 호출이 Center용 데모 실행에 오면 409이고 묶이지 않는다."""
    rid = proc.create(sc01_demo_run_id=_completed_sc05(proc), executor="center")["demo_run_id"]
    with pytest.raises(DomainError) as exc:
        proc.operate(rid, "open_review", {}, external_run_id="run_x", via="studio")
    assert exc.value.status == 409
    assert proc.get(rid)["bpm"]["external_run_id"] is None


def test_unstarted_review_is_not_opened_by_an_external_run(proc: Sc06Process) -> None:
    """착수는 NowView 화면 명령이다 — 착수 전에 바깥 실행이 열려고 하면 409(묶기는 남는다)."""
    rid = proc.create(sc01_demo_run_id=_completed_sc05(proc), executor="studio")["demo_run_id"]
    with pytest.raises(DomainError) as exc:
        proc.operate(rid, "open_review", {}, external_run_id="run_y", via="studio")
    assert exc.value.status == 409


# ─────────────────────────── Center 서버 실행 ───────────────────────────


def test_center_run_follows_the_demo_script_through_relay_answers(
    proc: Sc06Process, center: FakeCenter
) -> None:
    """
    착수가 SC06 패키지를 기동하고, 각본의 결재는 대리 답으로 닫히고, 진행은 폴링으로 온다. 업무는
    결재가 열릴 때 열린다. 결재 담당은 그 사람 이름이다.
    """
    rid = proc.create(sc01_demo_run_id=_completed_sc05(proc), executor="center")["demo_run_id"]
    steps = demo.steps_for()
    doc = demo.run_step(proc, rid, 0)  # D601 착수
    [job] = [j for j in center.jobs if j["bpm_process_id"] == "nowview.sc06"]
    assert job["inputs"] == {"데모실행ID": rid} and job["target"] == {"type": "server_runner"}
    assert doc["bpm"]["center"]["job"]["job_id"] == job["job_id"]

    runner = FakeRunner(proc, center, job, "run_20280111_090000_c6d6e6")
    assert proc.poll_center() == 1
    doc = proc.get(rid)
    assert sorted(w["node_id"] for w in doc["bpm"]["waiting"]) == ["Confirm_Buy", "Confirm_Prod"]
    assert not doc["tasks"]["TASK-CONFIRM_PROD"]["opened_late"]
    assert view(doc, center=CONFIG)["answerHere"]

    for index in range(1, len(steps)):
        demo.run_step(proc, rid, index)
        runner.step()
        proc.sync_center(rid)

    assert runner.run.state is State.DONE
    after = proc.get(rid)
    assert after["report"]["state"] == "REPORTED" and after["bpm"]["state"] == "done"
    relayed = [a["detail"]["node_id"] for a in after["audit"] if a["action"] == "answer_relayed"]
    assert relayed == [s.node_id for s in steps if s.kind == "act"]
    names = {a["answered_by"] for a in center.approvals.values()}
    assert names == {"권태윤", "문지후", "강민서", "정하윤", "임하준"}
    assert "End" in after["bpm"]["visited"]


def test_center_relay_ahead_of_the_poller_opens_the_task_on_time(
    proc: Sc06Process, center: FakeCenter
) -> None:
    """
    대리 답이 폴러보다 먼저 결재를 찾아도 업무는 결재가 열려 있던 때 열린 것이다
    (늦게 열지 않는다).
    """
    rid = proc.create(sc01_demo_run_id=_completed_sc05(proc), executor="center")["demo_run_id"]
    demo.run_step(proc, rid, 0)  # D601 착수
    [job] = [j for j in center.jobs if j["bpm_process_id"] == "nowview.sc06"]
    runner = FakeRunner(proc, center, job, "run_20280111_090000_c6d6e7")
    # 폴링 없이 바로 대리 답 — 폴러는 아직 결재를 읽지 않았다
    doc = demo.run_step(proc, rid, 1)
    task = doc["tasks"]["TASK-CONFIRM_PROD"]
    assert not task["opened_late"] and task["request_id"]
    runner.step()
    proc.sync_center(rid)
    doc = proc.get(rid)
    assert [t["task_id"] for t in doc["tasks"].values() if t["type"] == "CONFIRM_PROD"] == [
        "TASK-CONFIRM_PROD"
    ]
    assert doc["tasks"]["TASK-CONFIRM_PROD"]["status"] == "COMPLETED"
    assert not doc["tasks"]["TASK-CONFIRM_PROD"]["opened_late"]


def test_center_relay_prechecks_before_touching_center(
    proc: Sc06Process, center: FakeCenter
) -> None:
    """담당(403)·업무 규칙(422)은 Center에 묻기 전에 거절한다 — 입력은 지워지지 않는다."""
    rid = proc.create(sc01_demo_run_id=_completed_sc05(proc), executor="center")["demo_run_id"]
    proc.start(rid, actor="u-fin")
    job = next(j for j in center.jobs if j["bpm_process_id"] == "nowview.sc06")
    FakeRunner(proc, center, job, "run_20280111_090000_c7d7e7")
    proc.sync_center(rid)
    before = len(center.calls)
    answer = demo.steps_for()[1].answer
    with pytest.raises(DomainError) as role:
        proc.act(rid, "Confirm_Prod", answer, actor="u-buy-exec")
    assert role.value.status == 403
    with pytest.raises(DomainError) as rule:
        proc.act(rid, "Confirm_Prod", {**answer, "생산확인근거": ""}, actor="u-prod-exec")
    assert rule.value.status == 422
    assert center.calls[before:] == []


def test_center_unconfigured_leaves_a_reason(proc: Sc06Process) -> None:
    """설정이 없으면 조용히 내장으로 돌지 않는다 — 착수는 되고 「기동하지 않았다」 사유가 남는다."""
    bare = Sc06Process(
        SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), "sc06"),
        proc.sc05,
        center=CenterClient(type(CONFIG)()),
        center_wait_s=0,
    )
    rid = bare.create(sc01_demo_run_id=_completed_sc05(proc), executor="center")["demo_run_id"]
    doc = bare.start(rid, actor="u-fin")
    assert doc["scene_info"]["started_at"] and doc["bpm"]["snapshot"] is None
    assert "기동하지 않았다" in doc["bpm"]["center"]["problem"]
    with pytest.raises(DomainError) as relay:
        bare.act(rid, "Confirm_Prod", {}, actor="u-prod-exec")
    assert relay.value.status == 503


def test_reset_on_center_cancels_the_started_job(proc: Sc06Process, center: FakeCenter) -> None:
    rid = proc.create(sc01_demo_run_id=_completed_sc05(proc), executor="center")["demo_run_id"]
    proc.start(rid, actor="u-fin")
    job = next(j for j in center.jobs if j["bpm_process_id"] == "nowview.sc06")
    doc = proc.reset(rid, actor="u-demo")
    assert job["job_id"] in center.cancelled
    assert doc["bpm"]["executor"] == "center" and doc["scene_info"]["started_at"] is None
    proc.start(rid, actor="u-fin")
    jobs = [j for j in center.jobs if j["bpm_process_id"] == "nowview.sc06"]
    assert len(jobs) == 2 and jobs[1]["idempotency_key"] != jobs[0]["idempotency_key"]
    assert confirm.status(proc.get(rid))["procedure"] == "CONFIRMING"
