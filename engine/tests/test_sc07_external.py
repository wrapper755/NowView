"""
SC07 확인·적용 절차의 바깥 실행 — Studio 시험 실행 · Center 서버 실행(장면 1~6 N1~N6과 같은 틀).

* **확장 정의 ↔ BPMN** — 기본 확장 `chaeksas/external.extension.json`의 작업이 그림의 서비스
  호출·입력·출력을
  덮는가(어긋나면 Center가 일감을 막거나 일꾼이 입력 없이 멈춘다).
* **Studio** — 진짜 Chaeksas 엔진이 같은 그림을 돌고, 서비스 태스크는 C15 일감(`origin: test`)으로
  일꾼 수행기를
  지나고, 결재는 Studio 대화상자처럼 엔진에 바로 답한다. NowView 화면 답·각본은 409다.
* **Center** — 장면 1의 가짜 Center·서버 실행기 흉내(`test_sc01_center.py`)를 그대로 쓴다. 착수가
  SC07 패키지를
  기동하고, 각본은 대리 답으로 결재를 닫고, 진행은 폴링으로 온다.

장면 1~6은 `test_sc07_process`처럼 모듈에서 한 번 만들고 문서를 시험마다 새 저장소에 넣는다.
"""

from __future__ import annotations

import copy
import json
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
from app.sc05.process import Sc05Process
from app.sc06 import demo as sc06_demo
from app.sc06.process import Sc06Process
from app.sc07 import confirm, demo, domain
from app.sc07.process import PROCESS_PATH, RECORDS, Sc07Process
from app.sc07.view import view

ROOT = Path(__file__).resolve().parents[2]
PREFIXES = ("sc01", "sc02", "sc03", "sc04", "sc05", "sc06", "sc07")


def test_extension_definition_matches_the_bpmn_service_calls() -> None:
    """정의가 최신 계약 검사를 통과하고, 그림의 모든 서비스 호출이 정의의 입력·출력과 맞는다."""
    raw = (ROOT / "chaeksas" / "external.extension.json").read_bytes()
    manifest = ext.ExtensionManifest.model_validate(json.loads(raw))
    assert ext.validate(manifest, from_center=True) == []
    assert manifest.version == "0.7.0"
    adapter = json.loads(raw)["service"]["adapter"]
    operations = {o["name"]: o for o in adapter["operations"]}
    process = read_process(PROCESS_PATH.read_bytes())
    assert validate(process) == []
    for node in process.of_kind("serviceTask"):
        call = node.prop("serviceCall")
        assert call.app_id == manifest.id, node.id
        op = operations[call.operation]
        assert set(op["input_schema"]["required"]) <= set(call.input), node.id
        assert op["request"] == {"method": "POST", "path": "/"}, call.operation
        assert set(call.output.values()) <= set(op["output_schema"]["properties"]), node.id
        if call.operation in RECORDS:
            assert "answered_by" in op["input_schema"]["required"], call.operation
    [need] = [n for n in process.info.extensions if n.id == manifest.id]
    assert satisfies(manifest.version, need.version) and need.version.startswith(">=0.7.0")
    for node in process.of_kind("userTask"):
        approval = node.prop("approval")
        assert approval.answered_by_as and approval.answered_via_as, node.id
        assert "데모실행ID" in approval.show, node.id
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


@pytest.fixture(scope="module")
def reported_sc06() -> tuple[str, dict[str, dict]]:
    store = lambda p: SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), p)  # noqa: E731
    sc02 = Sc02Process(store("sc02"), Sc01Process(store("sc01"), inline_agent=True))
    sc05 = Sc05Process(store("sc05"), Sc04Process(store("sc04"), Sc03Process(store("sc03"), sc02)))
    sc06 = Sc06Process(store("sc06"), sc05)
    rid = sc06.create(executor="embedded")["demo_run_id"]
    for i in range(len(sc06_demo.steps_for())):
        sc06_demo.run_step(sc06, rid, i)
    procs = {
        "sc01": sc02.sc01, "sc02": sc02, "sc03": sc05.sc04.sc03, "sc04": sc05.sc04,
        "sc05": sc05, "sc06": sc06,
    }  # fmt: skip
    return rid, {p: x.store.load(rid)[0] for p, x in procs.items()}


@pytest.fixture
def center() -> FakeCenter:
    return FakeCenter()


@pytest.fixture
def proc(center: FakeCenter, reported_sc06) -> Sc07Process:
    client = CenterClient(CONFIG, transport=httpx.MockTransport(center.handle))
    stores = {
        p: SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), p)
        for p in PREFIXES
    }
    rid, docs = reported_sc06
    for p, doc in docs.items():
        stores[p].insert(rid, copy.deepcopy(doc))
    kw = {"center": client, "center_wait_s": 0}
    sc01 = Sc01Process(stores["sc01"], inline_agent=True, **kw)
    sc02 = Sc02Process(stores["sc02"], sc01, **kw)
    sc03 = Sc03Process(stores["sc03"], sc02, **kw)
    sc04 = Sc04Process(stores["sc04"], sc03, **kw)
    sc05 = Sc05Process(stores["sc05"], sc04, **kw)
    sc06 = Sc06Process(stores["sc06"], sc05, **kw)
    return Sc07Process(stores["sc07"], sc06, **kw)


@pytest.fixture
def rid(reported_sc06) -> str:
    return reported_sc06[0]


def _studio(proc: Sc07Process, rid: str, run_id: str) -> tuple[Engine, object]:
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


def _answer(engine: Engine, run, node_id: str, answer: dict, by: str) -> None:
    [pending] = [p for p in run.pendings.values() if p.node_id == node_id]
    engine.answer(run, pending.request_id, answer, answered_by=by)
    assert engine.run_until_blocked(run) is not State.FAILED, node_id


# ─────────────────────────── Studio 시험 실행 ───────────────────────────


def test_studio_run_reaches_the_follow_up_through_system_operations(
    proc: Sc07Process, rid: str
) -> None:
    """
    Studio가 같은 그림을 돌고 NowView는 작업 호출로만 안다 — 첫 호출이 실행을 묶고, 검증은 서비스
    태스크가
    규칙으로 하고, 결정은 기록 작업으로 적히고, 업무는 기록 때 늦게 연다. 끝까지 가면 운영 설정 반영
    확인
    (기록·시각은 내장과 같다).
    """
    proc.create(sc01_demo_run_id=rid, executor="studio")
    doc = proc.start(rid, actor="u-fin")
    assert doc["bpm"]["executor"] == "studio" and doc["bpm"]["external_run_id"] is None
    shown = view(doc, center=CONFIG)
    assert shown["executor"] == "studio" and not shown["answerHere"]

    engine, run = _studio(proc, rid, "run_20280117_090000_a7b7c7")
    for step in demo.steps_for():
        if step.kind == "act":
            _answer(engine, run, step.node_id, dict(step.answer), USERS[step.actor]["name"])

    assert run.state is State.DONE
    doc = proc.get(rid)
    assert doc["bpm"]["external_run_id"] == "run_20280117_090000_a7b7c7"
    assert doc["bpm"]["state"] == "done"
    assert domain.application_state(doc)["state"] == "ST707" and doc["follow_up"] is not None
    assert all(t["opened_late"] and t["status"] == "COMPLETED" for t in doc["tasks"].values())
    for record_id, planned in doc["schedule"].items():
        got = doc["confirmations"][record_id]
        assert (got["actor"], got["at"], got["content"]) == (
            planned["actor"],
            planned["at"],
            planned["content"],
        ), record_id
    assert doc["setting"]["applied_by"] == "USR-OPS71"
    assert {"Task_Verify", "Task_FollowUp", "Record_Check_Setting"} <= set(doc["bpm"]["visited"])
    with pytest.raises(DomainError) as act:
        proc.act(rid, "Confirm_Buy", {}, actor="u-buy-exec")
    assert act.value.status == 409
    with pytest.raises(DomainError) as script:
        demo.run_step(proc, rid, 1)
    assert script.value.status == 409


def test_a_rejected_check_returns_to_the_same_approval(proc: Sc07Process, rid: str) -> None:
    """
    Studio 대화상자는 NowView 사전 검사를 거치지 않는다 — 예약만 한 설정을 「일치」로 확인하면
    기록이 거절되고
    (422 SETTING_MISMATCH, 남은 항목은 감사 이력에) 오류 경계로 같은 결재가 다시 열린다. 효과는
    없다.
    """
    proc.create(sc01_demo_run_id=rid, executor="studio")
    proc.start(rid, actor="u-fin")
    engine, run = _studio(proc, rid, "run_20280117_090000_b7c7d7")
    steps = [s for s in demo.steps_for() if s.kind == "act"]
    for step in steps[:3]:
        answer = dict(step.answer)
        if step.node_id == "Apply_Setting":
            answer["증적유형"] = "RESERVED"
        _answer(engine, run, step.node_id, answer, USERS[step.actor]["name"])
    _answer(engine, run, "Check_Setting", dict(steps[3].answer), "정하윤")
    assert [p.node_id for p in run.pendings.values()] == ["Check_Setting"]
    doc = proc.get(rid)
    [rejected] = [a for a in doc["audit"] if a["action"] == "answer_rejected"]
    assert rejected["detail"]["status"] == 422
    assert any("RESERVED" in i for i in rejected["detail"]["blocking_items"])
    assert doc["setting"]["check_result"] is None and doc["follow_up"] is None


def test_console_admin_answer_is_recorded_as_the_assignee(proc: Sc07Process, rid: str) -> None:
    """마스터 밖의 이름(콘솔 관리자)은 거절하지 않는다 — 기록은 그 결재의 담당으로, 답한 이름은 감사
    이력에."""
    proc.create(sc01_demo_run_id=rid, executor="studio")
    proc.start(rid, actor="u-fin")
    engine, run = _studio(proc, rid, "run_20280117_090000_b7c7d8")
    _answer(engine, run, "Confirm_Buy", dict(demo.steps_for()[1].answer), "console-admin")
    doc = proc.get(rid)
    assert doc["confirmations"]["CF71"]["actor"] == "EX-BUY"
    assert any(a["action"] == "answer_by_outside_master" for a in doc["audit"])


def test_studio_origin_cannot_feed_a_center_demo_run(proc: Sc07Process, rid: str) -> None:
    """N6 — 시험 실행에서 온 일감이 Center용 데모 실행에 오면 409이고 묶이지 않는다."""
    proc.create(sc01_demo_run_id=rid, executor="center")
    with pytest.raises(DomainError) as exc:
        proc.operate(rid, "open_improvement", {}, external_run_id="run_x", via="studio")
    assert exc.value.status == 409
    assert proc.get(rid)["bpm"]["external_run_id"] is None


def test_unstarted_improvement_is_not_opened_by_an_external_run(
    proc: Sc07Process, rid: str
) -> None:
    """착수는 NowView 화면 명령이다 — 착수 전에 바깥 실행이 열려고 하면 409."""
    proc.create(sc01_demo_run_id=rid, executor="studio")
    with pytest.raises(DomainError) as exc:
        proc.operate(rid, "open_improvement", {}, external_run_id="run_y", via="studio")
    assert exc.value.status == 409


# ─────────────────────────── Center 서버 실행 ───────────────────────────


def _job(center: FakeCenter) -> dict:
    [job] = [j for j in center.jobs if j["bpm_process_id"] == "company1.sc07"]
    return job


def test_center_run_follows_the_demo_script_through_relay_answers(
    proc: Sc07Process, center: FakeCenter, rid: str
) -> None:
    """
    착수가 SC07 패키지를 기동하고, 각본의 결재는 대리 답으로 닫히고, 진행은 폴링으로 온다. 업무는
    결재가 열릴
    때 열린다. 결재 담당은 그 사람 이름이다(운영 담당은 역할명).
    """
    proc.create(sc01_demo_run_id=rid, executor="center")
    steps = demo.steps_for()
    doc = demo.run_step(proc, rid, 0)  # D701 착수
    job = _job(center)
    assert job["inputs"] == {"데모실행ID": rid} and job["target"] == {"type": "server_runner"}
    assert doc["bpm"]["center"]["job"]["job_id"] == job["job_id"]

    runner = FakeRunner(proc, center, job, "run_20280117_090000_c7d7e7")
    assert proc.poll_center() == 1
    doc = proc.get(rid)
    assert [w["node_id"] for w in doc["bpm"]["waiting"]] == ["Confirm_Buy"]
    assert doc["verification"]["passed"] and not doc["tasks"]["TASK-CONFIRM_BUY"]["opened_late"]
    assert view(doc, center=CONFIG)["answerHere"]

    for index in range(1, len(steps)):
        demo.run_step(proc, rid, index)
        runner.step()
        proc.sync_center(rid)

    assert runner.run.state is State.DONE
    after = proc.get(rid)
    assert after["bpm"]["state"] == "done" and "End" in after["bpm"]["visited"]
    assert domain.application_state(after)["state"] == "ST707"
    relayed = [a["detail"]["node_id"] for a in after["audit"] if a["action"] == "answer_relayed"]
    assert relayed == [s.node_id for s in steps if s.kind == "act"]
    assert {a["answered_by"] for a in center.approvals.values()} == {
        "문지후",
        "강민서",
        "운영담당",
        "정하윤",
    }
    assert not any(t["opened_late"] for t in after["tasks"].values())
    assert not any(a["action"] == "answer_rejected" for a in after["audit"])


def test_center_relay_prechecks_before_touching_center(
    proc: Sc07Process, center: FakeCenter, rid: str
) -> None:
    """담당(403)·대상 버전(422)은 Center에 묻기 전에 거절한다 — 입력은 지워지지 않는다."""
    proc.create(sc01_demo_run_id=rid, executor="center")
    proc.start(rid, actor="u-fin")
    FakeRunner(proc, center, _job(center), "run_20280117_090000_c8d8e8")
    proc.sync_center(rid)
    before = len(center.calls)
    answer = demo.steps_for()[1].answer
    with pytest.raises(DomainError) as role:
        proc.act(rid, "Confirm_Buy", answer, actor="u-fin-exec")
    assert role.value.status == 403
    with pytest.raises(DomainError) as rule:
        proc.act(rid, "Confirm_Buy", {**answer, "구매확인버전": "AGT71-v1"}, actor="u-buy-exec")
    assert rule.value.status == 422
    assert center.calls[before:] == []


def test_center_unconfigured_leaves_a_reason(proc: Sc07Process, rid: str) -> None:
    """설정이 없으면 조용히 내장으로 돌지 않는다 — 착수는 되고 「기동하지 않았다」 사유가 남는다."""
    bare = Sc07Process(
        SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), "sc07"),
        proc.sc06,
        center=CenterClient(type(CONFIG)()),
        center_wait_s=0,
    )
    bare.create(sc01_demo_run_id=rid, executor="center")
    doc = bare.start(rid, actor="u-fin")
    assert doc["scene_info"]["started_at"] and doc["bpm"]["snapshot"] is None
    assert "기동하지 않았다" in doc["bpm"]["center"]["problem"]
    with pytest.raises(DomainError) as relay:
        bare.act(rid, "Confirm_Buy", {}, actor="u-buy-exec")
    assert relay.value.status == 503


def test_reset_on_center_cancels_the_started_job(
    proc: Sc07Process, center: FakeCenter, rid: str
) -> None:
    proc.create(sc01_demo_run_id=rid, executor="center")
    proc.start(rid, actor="u-fin")
    job = _job(center)
    doc = proc.reset(rid, actor="u-demo")
    assert job["job_id"] in center.cancelled
    assert doc["bpm"]["executor"] == "center" and doc["scene_info"]["started_at"] is None
    proc.start(rid, actor="u-fin")
    jobs = [j for j in center.jobs if j["bpm_process_id"] == "company1.sc07"]
    assert len(jobs) == 2 and jobs[1]["idempotency_key"] != jobs[0]["idempotency_key"]
    assert confirm.status(proc.get(rid))["procedure"] == "CONFIRMING"


def test_center_script_follows_a_site_answer(
    proc: Sc07Process, center: FakeCenter, rid: str
) -> None:
    """
    회사 사이트가 구매 임원 확인을 먼저 답하면(기록이 오면) 각본 위치가 따라간다 — 플레이어
    「다음」은 그 단계를
    다시 대리 답하지 않고 다음 결재로 간다(장면 6 섞어 진행 실측과 같은 이유).
    """
    proc.create(sc01_demo_run_id=rid, executor="center")
    demo.run_step(proc, rid, 0)
    runner = FakeRunner(proc, center, _job(center), "run_20280117_090000_c9d9e9")
    proc.sync_center(rid)
    buy = demo.steps_for()[1]
    [req] = [a for a in center.approvals.values() if a["node_id"] == "Confirm_Buy"]
    req.update(state="answered", answer=buy.answer, answered_by="문지후")
    runner.step()
    proc.sync_center(rid)
    doc = proc.get(rid)
    assert doc["confirmations"]["CF71"]["actor"] == "EX-BUY" and demo.done_index(doc) == 1
    doc = demo.run_step(proc, rid, 1)  # 이미 지난 단계 — 할 일이 없다
    assert [a for a in doc["audit"] if a["action"] == "answer_relayed"] == []
    demo.run_step(proc, rid, 2)
    runner.step()
    proc.sync_center(rid)
    assert proc.get(rid)["confirmations"]["CF72"]["actor"] == "USR-CFO"
