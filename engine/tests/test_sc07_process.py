"""
SC07 적재 · 확인·적용 절차(BPM) · 조회 서비스 — 장면 6 대표 보고에서 IMP71을 여는 길, 확인·적용
절차(검증 실행 →
구매 임원 확인 → 경영관리 임원 확인 → 운영 설정 반영 → 설정 확인 → 후속 점검)를 내장 실행기로 끝까지
돌린 문서가
SC07확인이력·SC07적용 시트와 같은지, 결재 규칙(담당 403 · 대상 버전 422 · 설정 일치 422 · 보완
요청·불일치
고리), 조회 계약(구현명세 6장)과 오류·권한, 조회가 이력을 만들지 않는 것(AT712), 원본
보존(AT708·TC707).
**SQLite·Postgres 양쪽**이다.

장면 1~6을 각본으로 끝내는 데 약 10초가 걸린다 — 모듈에서 한 번 만들고(SQLite) 그 문서들을 시험마다
새 저장소에
넣는다. 장면 6을 실제로 끝까지 실행하는 길은 따로 한 번 본다.
"""

from __future__ import annotations

import copy
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from chaeksas.contracts.bpmn_ext import read_process
from conftest import require_postgres
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.events import Hub
from app.preparation import Preparations
from app.sc01.domain import USERS, DomainError
from app.sc01.process import Sc01Process
from app.sc01.store import PostgresSc01Store, SqliteSc01Store
from app.sc02.process import Sc02Process
from app.sc03.process import Sc03Process
from app.sc04.process import Sc04Process
from app.sc05.process import Sc05Process
from app.sc06 import demo as sc06_demo
from app.sc06.process import Sc06Process
from app.sc07 import confirm, demo, domain
from app.sc07.api import build_router
from app.sc07.process import PROCESS_PATH, Sc07Process
from app.sc07.view import topology
from app.store import build_postgres_backend

PREFIXES = ("sc01", "sc02", "sc03", "sc04", "sc05", "sc06", "sc07")
TABLES = ", ".join(f"{p}_demo_run, {p}_history" for p in PREFIXES)
IMP = "/sc07/demo-runs/{rid}/improvements/IMP71"


def _chain(stores: list) -> Sc07Process:
    sc02 = Sc02Process(stores[1], Sc01Process(stores[0], inline_agent=True))
    sc05 = Sc05Process(stores[4], Sc04Process(stores[3], Sc03Process(stores[2], sc02)))
    return Sc07Process(stores[6], Sc06Process(stores[5], sc05))


def _memory() -> list:
    return [
        SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), p) for p in PREFIXES
    ]


@pytest.fixture(scope="module")
def reported_sc06() -> tuple[str, dict[str, dict]]:
    """장면 1~6을 내장 각본으로 대표 보고까지 — 한 번만 만들고 문서를 떠 둔다."""
    proc = _chain(_memory())
    doc = proc.sc06.create(executor="embedded")
    rid = doc["demo_run_id"]
    for i in range(len(sc06_demo.steps_for())):
        sc06_demo.run_step(proc.sc06, rid, i)
    stores = {
        "sc01": proc.sc06.sc05.sc04.sc03.sc02.sc01.store,
        "sc02": proc.sc06.sc05.sc04.sc03.sc02.store,
        "sc03": proc.sc06.sc05.sc04.sc03.store,
        "sc04": proc.sc06.sc05.sc04.store,
        "sc05": proc.sc06.sc05.store,
        "sc06": proc.sc06.store,
    }
    return rid, {p: s.load(rid)[0] for p, s in stores.items()}


@pytest.fixture(params=["sqlite", "postgres"])
def proc(request, reported_sc06) -> Iterator[Sc07Process]:
    backend = None
    if request.param == "postgres":
        backend = build_postgres_backend(require_postgres())
        stores = [PostgresSc01Store(backend.pool, p) for p in PREFIXES]
        with backend.pool.connection() as conn:
            conn.execute(f"TRUNCATE {TABLES}")
    else:
        stores = _memory()
    rid, docs = reported_sc06
    for store, prefix in zip(stores, PREFIXES, strict=False):
        if prefix in docs:
            store.insert(rid, copy.deepcopy(docs[prefix]))
    try:
        yield _chain(stores)
    finally:
        if backend is not None:
            with backend.pool.connection() as conn:
                conn.execute(f"TRUNCATE {TABLES}")
            backend.close()


@pytest.fixture
def rid(reported_sc06) -> str:
    return reported_sc06[0]


@pytest.fixture
def client(proc: Sc07Process) -> TestClient:
    app = FastAPI()
    # 앞 장면들을 각본으로 끝까지 돌리는 데 준비 기다림(기본 20초)을 넘기면 202다 — 이 시험은 조회
    # 계약을 보지 준비 시간을 보지 않는다. 기계가 바쁘면 흔들렸다(Postgres 전체 시험 한 번 실패 ·
    # 3단계 SQLite 전체 시험 다섯 실패, 둘 다 202).
    app.include_router(build_router(proc, Hub(), Preparations(wait_s=900)))
    return TestClient(app)


def applied(proc: Sc07Process, rid: str) -> dict:
    doc = proc.create(sc01_demo_run_id=rid)
    for i in range(len(demo.steps_for())):
        doc = demo.run_step(proc, rid, i)
    return doc


def get(client: TestClient, path: str, actor: str | None = "u-fin", **params):
    headers = {"x-demo-actor": actor} if actor else {}
    return client.get(path, headers=headers, params=params)


# ─────────────────────────── 적재 ───────────────────────────


def test_opening_runs_scene6_to_the_ceo_report_then_loads_imp71() -> None:
    """
    장면 6이 없으면 장면 1부터 각본을 실제로 돌려 대표 보고(RPT61-v1 REPORTED)까지 간 뒤 적재한다.
    같은 데모 실행
    id다. 적재 직후는 **확인 전**이다 — 검증·확인·설정이 없다.
    """
    proc = _chain(_memory())
    doc = proc.create(executor="embedded")
    rid = doc["demo_run_id"]
    assert proc.sc06.get(rid)["report"]["state"] == "REPORTED"
    assert doc["clock"] == confirm.START_AT and doc["sc06"]["report_version"] == "RPT61-v1"
    assert doc["verification"] is None and doc["confirmations"] == {} and doc["setting"] is None
    assert doc["batch"]["seed_id"] == "SYN-SC07-v0.7" and doc["batch"]["dataset_version"] == "v0.7"
    assert (
        doc["sc06"]["agent"]["run_id"] == "AG62" and doc["sc06"]["order"]["cost_krw"] == 1_200_000
    )
    assert doc["inputs"]["IN71"]["order_id"] == "PO61-1103"
    assert doc["inputs"]["IN71"]["evidence_refs"] == ["CH61-1103", "E61-1103", "EV71", "EV72"]
    again = proc.create(sc01_demo_run_id=rid)
    assert again["created_at"] == doc["created_at"] and len(proc.store.history(rid)) == 1


def test_scene6_not_reported_on_studio_is_refused(proc: Sc07Process, rid: str) -> None:
    """장면 6이 Studio 실행이고 보고 전이면 각본으로 끝낼 수 없다 — 409(Studio에서 끝낸 뒤 연다)."""
    proc.sc06.reset(rid, actor="u-demo", executor="studio")
    with pytest.raises(DomainError) as exc:
        proc.create(sc01_demo_run_id=rid)
    assert exc.value.status == 409 and proc.store.load(rid) is None


def test_unknown_case_is_refused(proc: Sc07Process) -> None:
    with pytest.raises(DomainError) as err:
        proc.create(case_id="AT703")
    assert err.value.status == 422


# ─────────────────────────── 확인·적용 절차 ───────────────────────────


def test_procedure_end_matches_the_confirmation_and_application_sheets(
    proc: Sc07Process, rid: str
) -> None:
    """
    각본 D701~D705 끝 — 검증 8건 통과(규칙 재계산), CF71·CF72와 설정 반영·확인이
    SC07확인이력·SC07적용 시트와
    같고(행위자·시각·글·버전), 운영 설정 반영 확인(ST707) · 운영 실행 미확인 · 후속 점검 2/11 10:00.
    """
    doc = applied(proc, rid)
    assert doc["bpm"]["state"] == "done" and "End" in doc["bpm"]["visited"]
    run = doc["verification"]
    assert run["passed"] and run["run_id"] == "VR71-1" and run["executed_at"] == confirm.START_AT
    assert [r["observed"] for r in run["results"]][:5] == [
        "SUPPLY", "INTERNAL", "NEED_EVIDENCE", "NEED_EVIDENCE", "MIXED",
    ]  # fmt: skip
    for rid_, planned in doc["schedule"].items():
        got = doc["confirmations"][rid_]
        assert (got["actor"], got["at"], got["content"], got["version"], got["state"]) == (
            planned["actor"],
            planned["at"],
            planned["content"],
            planned["version"],
            planned["state"],
        ), rid_
    plan, s = doc["plan"], doc["setting"]
    assert (s["applied_by"], s["applied_at"], s["checked_by"], s["checked_at"]) == (
        plan["applied_by"],
        plan["applied_at"],
        plan["checked_by"],
        plan["checked_at"],
    )
    assert (s["snapshot_id"], s["active_version"], s["previous_version"]) == (
        "CFG71",
        "AGT71-v2",
        "AGT71-v1",
    )
    assert s["evidence_type"] == "SETTINGS_SNAPSHOT" and s["check_result"] == "MATCH"
    state = domain.application_state(doc)
    assert state["state"] == "ST707" and state["execution_status"] == "NOT_CONFIRMED"
    assert doc["clock"] == "2028-01-25T10:00:00+09:00"
    assert doc["follow_up"]["planned_at"] == "2028-02-11T10:00:00+09:00"
    assert doc["follow_up"]["owner"] == "USR-FIN" and not doc["follow_up"]["measured"]
    tasks = sorted(doc["tasks"].values(), key=lambda t: t["seq"])
    assert [t["type"] for t in tasks] == [
        "CONFIRM_BUY", "CONFIRM_FINANCE", "APPLY_SETTING", "CHECK_SETTING",
    ]  # fmt: skip
    assert all(t["status"] == "COMPLETED" and not t["opened_late"] for t in tasks)
    assert [t["completed_at"] for t in tasks] == [
        "2028-01-24T10:00:00+09:00",
        "2028-01-24T15:00:00+09:00",
        "2028-01-25T09:00:00+09:00",
        "2028-01-25T10:00:00+09:00",
    ]
    assert confirm.status(doc)["procedure"] == "APPLIED"
    assert demo.done_index(doc) == len(demo.steps_for()) - 1


def test_scene6_records_are_untouched(proc: Sc07Process, rid: str) -> None:
    """AT708 — 적재·검증·확인·적용 전후로 장면 1~6 문서가 그대로다(보고본·초안·보정·수치)."""
    stores = {
        "sc05": proc.sc06.sc05.store,
        "sc06": proc.sc06.store,
        "sc01": proc.sc06.sc05.sc04.sc03.sc02.sc01.store,
    }
    before = {p: s.load(rid) for p, s in stores.items()}
    doc = applied(proc, rid)
    proc.reset(rid, actor="u-demo")
    assert {p: s.load(rid) for p, s in stores.items()} == before
    assert domain.sc06_fingerprint(proc.sc06.get(rid)) == doc["sc06"]["fingerprint"]


def test_a_changed_scene6_record_fails_tc707_and_stops_before_confirmations(
    proc: Sc07Process, rid: str
) -> None:
    """적재 뒤 장면 6 기록이 바뀌었으면 TC707이 실패하고 흐름은 「검증 미통과 — 보완 필요」로
    끝난다."""
    proc.create(sc01_demo_run_id=rid)
    sc06, version = proc.sc06.store.load(rid)
    sc06["agent_runs"]["AG62"]["draft"] = "덮어쓴 초안"
    proc.sc06.store.save(rid, sc06, version, "tamper")
    doc = demo.run_step(proc, rid, 0)
    assert not doc["verification"]["passed"]
    assert [r["check"] for r in doc["verification"]["results"] if r["status"] != "PASS"] == [
        "TC707"
    ]
    assert doc["bpm"]["state"] == "done" and "End_NotVerified" in doc["bpm"]["visited"]
    assert domain.application_state(doc)["state"] == "ST703"
    assert confirm.status(doc)["procedure"] == "NEEDS_WORK"


def test_only_the_assignee_answers_and_the_version_must_match(proc: Sc07Process, rid: str) -> None:
    proc.create(sc01_demo_run_id=rid)
    demo.run_step(proc, rid, 0)
    answer = dict(demo.steps_for()[1].answer)
    with pytest.raises(DomainError) as role:
        proc.act(rid, "Confirm_Buy", answer, actor="u-fin-exec")
    assert role.value.status == 403
    with pytest.raises(DomainError) as version:
        proc.act(rid, "Confirm_Buy", {**answer, "구매확인버전": "AGT71-v1"}, actor="u-buy-exec")
    assert version.value.status == 422 and "AGT71-v2" in str(version.value)
    with pytest.raises(DomainError) as order:
        proc.act(rid, "Confirm_Finance", dict(demo.steps_for()[2].answer), actor="u-fin-exec")
    assert order.value.status == 409
    assert proc.get(rid)["confirmations"] == {}


def test_rework_request_ends_the_flow_as_needs_work(proc: Sc07Process, rid: str) -> None:
    """구매 임원의 보완 요청 — 흐름은 「보완 필요」로 끝나고 적용 상태는 업무 확인 대기(ST704)에
    머문다."""
    proc.create(sc01_demo_run_id=rid)
    demo.run_step(proc, rid, 0)
    answer = {**demo.steps_for()[1].answer, "구매확인결정": "보완요청", "구매확인내용": "근거 부족"}
    doc = proc.act(rid, "Confirm_Buy", answer, actor="u-buy-exec")
    assert doc["confirmations"]["CF71"]["state"] == "REWORK_REQUESTED"
    assert doc["bpm"]["state"] == "done" and "End_Rework" in doc["bpm"]["visited"]
    assert domain.application_state(doc)["state"] == "ST704"
    assert confirm.status(doc)["procedure"] == "NEEDS_WORK"
    with pytest.raises(DomainError):
        demo.run_step(proc, rid, 2)


def test_reserved_setting_cannot_be_confirmed_and_mismatch_loops_back(
    proc: Sc07Process, rid: str
) -> None:
    """
    예약만 한 설정은 반영 확인이 아니다 — 「일치」는 422 SETTING_MISMATCH(남은 항목), 「불일치」면
    설정 반영으로
    돌아가고 다시 반영한 스냅샷으로 확인된다. 앞 반영 기록은 이력에 남는다.
    """
    proc.create(sc01_demo_run_id=rid)
    for i in range(3):
        demo.run_step(proc, rid, i)
    steps = demo.steps_for()
    reserved = {**steps[3].answer, "증적유형": "RESERVED"}
    doc = proc.act(rid, "Apply_Setting", reserved, actor="u-ops")
    assert domain.application_state(doc)["state"] == "ST705"
    with pytest.raises(confirm.PrerequisiteError) as blocked:
        proc.act(rid, "Check_Setting", dict(steps[4].answer), actor="u-fin")
    assert blocked.value.code == "SETTING_MISMATCH" and "RESERVED" in blocked.value.items[0]
    doc = proc.act(
        rid,
        "Check_Setting",
        {"설정확인결과": "불일치", "설정확인내용": "예약만 있음"},
        actor="u-fin",
    )
    assert [w for w in (doc["bpm"]["snapshot"]["pendings"]).values()][0]["node_id"] == (
        "Apply_Setting"
    )
    assert demo.done_index(doc) == 2
    doc = demo.run_step(proc, rid, 3)
    doc = demo.run_step(proc, rid, 4)
    assert domain.application_state(doc)["state"] == "ST707"
    assert [h["evidence_type"] for h in doc["record_history"] if h.get("record_id") == "CFG71"] == [
        "RESERVED"
    ]
    assert [t["task_id"] for t in doc["tasks"].values() if t["type"] == "APPLY_SETTING"] == [
        "TASK-APPLY_SETTING",
        "TASK-APPLY_SETTING-2",
    ]


def test_reset_returns_the_procedure_only(proc: Sc07Process, rid: str) -> None:
    """초기화는 확인·적용 절차만 확인 전으로 — 적재와 장면 6 스냅샷은 그대로다. 지난 기록은 이력
    테이블에 있다."""
    doc = applied(proc, rid)
    with pytest.raises(DomainError):
        proc.reset(rid, actor="u-fin")
    after = proc.reset(rid, actor="u-demo")
    assert after["setting"] is None and after["confirmations"] == {}
    assert after["scene_info"]["started_at"] is None and after["clock"] == confirm.START_AT
    assert after["sc06"] == doc["sc06"] and after["inputs"] == doc["inputs"]
    assert any(a["action"] == "demo_run_reset" for a in after["audit"])
    assert applied(proc, rid)["setting"]["check_result"] == "MATCH"


# ─────────────────────────── 조회 계약 (구현명세 6장) ───────────────────────────


def test_read_contracts_after_the_procedure(
    client: TestClient, proc: Sc07Process, rid: str
) -> None:
    """
    세 조회와 근거 — 모든 응답에 dataset_version·improvement_id·version_bundle·as_of. 설정 반영
    확인과 운영
    실행 미확인을 다른 칸으로 낸다(AT711).
    """
    applied(proc, rid)
    a = get(client, IMP.format(rid=rid)).json()
    for body in (a,):
        assert body["dataset_version"] == "v0.7" and body["improvement_id"] == "IMP71"
        assert body["version_bundle"]["agent"] == "AGT71-v2"
        assert body["as_of"] == "2028-01-25T10:00:00+09:00"
    assert a["before"]["agent"]["draft"].startswith("주담당 확인 기록이 없어")
    assert (
        a["before"]["agent_version"] == "AGT71-v1"
        and "deputy_confirmed_at" not in a["before"]["payload"]
    )
    after = a["after"]
    assert (after["elapsed_minutes"], after["candidate_cause"], after["candidate_label"]) == (
        40,
        "SUPPLY",
        "조달 제약",
    )
    assert after["execution_mode"] == "RULE_RECALC"
    assert all(f["evidence_refs"] for f in after["facts"])
    assert a["improvement"]["framework"]["item_id"] == "IMP71-F"
    v = get(client, IMP.format(rid=rid) + "/verification").json()
    assert v["summary"] == {"total": 8, "passed": 8, "not_run": 0, "state": "PASSED"}
    assert v["representative"]["check"] == "TC701"
    assert v["representative"]["output"]["candidate_cause"] == "SUPPLY"
    assert all(c["simulated_run_id"] is None for c in v["cases"])
    ap = get(client, f"/sc07/demo-runs/{rid}/applications/AP71").json()
    assert ap["state"]["state"] == "ST707" and ap["execution"]["status"] == "NOT_CONFIRMED"
    assert ap["execution"]["operation_run_id"] is None
    assert ap["execution"]["next_run_at"] == "2028-02-01T09:00:00+09:00"
    assert [c["actor"]["name"] for c in ap["confirmations"]] == ["문지후", "강민서"]
    assert ap["snapshot"]["applied_by"]["name"] == "운영담당"
    assert ap["follow_up"]["owner"]["name"] == "정하윤"
    ev = get(client, f"/sc07/demo-runs/{rid}/evidence/EV71").json()
    assert ev["evidence"]["kind"] == "가상 대행 위임"
    e6 = get(client, f"/sc07/demo-runs/{rid}/evidence/E61-1103").json()
    assert e6["source"] == "SC06근거" and e6["evidence"]["written_by"]["account"] == "USR-BUY2"


def test_verification_before_the_run_is_not_shown_as_passed(
    client: TestClient, proc: Sc07Process, rid: str
) -> None:
    """실행 전이면 「미실행」이다 — 빈 결과를 통과로 표시하지 않는다(UI703). 적용은 ST703."""
    proc.create(sc01_demo_run_id=rid)
    v = get(client, IMP.format(rid=rid) + "/verification").json()
    assert v["summary"]["state"] == "NOT_RUN" and v["summary"]["passed"] == 0
    assert {c["status"] for c in v["cases"]} == {"NOT_RUN"}
    assert v["representative"]["output"] is None
    ap = get(client, f"/sc07/demo-runs/{rid}/applications/AP71").json()
    assert ap["state"]["state"] == "ST703" and ap["snapshot"] is None


def test_read_errors(client: TestClient, proc: Sc07Process, rid: str) -> None:
    proc.create(sc01_demo_run_id=rid)
    denied = get(client, IMP.format(rid=rid), actor="u-sales")
    assert denied.status_code == 403
    assert denied.json()["detail"] == {
        "message": "이 개선건을 볼 권한이 없다",
        "error_code": "ACCESS_DENIED",
    }
    assert get(client, f"/sc07/demo-runs/{rid}/improvements/IMP99").status_code == 404
    assert get(client, f"/sc07/demo-runs/{rid}/applications/AP99").status_code == 404
    assert get(client, f"/sc07/demo-runs/{rid}/evidence/EV99").json()["detail"]["error_code"] == (
        "NOT_FOUND"
    )
    stale = get(client, IMP.format(rid=rid), dataset_version="v0.6")
    assert stale.status_code == 409 and stale.json()["detail"]["error_code"] == "VERSION_MISMATCH"
    assert get(client, "/sc07/demo-runs/demo-none/improvements/IMP71").status_code == 404


def test_reads_write_nothing(client: TestClient, proc: Sc07Process, rid: str) -> None:
    """AT712 — 보기 전환·근거 펼침·새로고침으로 이력·감사가 늘지 않는다."""
    applied(proc, rid)
    before = (proc.get(rid), len(proc.store.history(rid)))
    for path in (
        IMP.format(rid=rid),
        IMP.format(rid=rid) + "/verification",
        f"/sc07/demo-runs/{rid}/applications/AP71",
        f"/sc07/demo-runs/{rid}/evidence/EV72",
        f"/sc07/demo-runs/{rid}",
    ):
        assert get(client, path).status_code == 200, path
    assert (proc.get(rid), len(proc.store.history(rid))) == before


# ─────────────────────────── 그림 · HTTP ───────────────────────────


def test_every_user_task_has_a_role_and_matching_assignees() -> None:
    process = read_process(PROCESS_PATH.read_bytes())
    users = [n.id for n in process.all_nodes() if n.kind == "userTask"]
    assert sorted(users) == sorted(confirm.NODE_ROLES)
    for node_id in users:
        assignees = process.node(node_id).prop("approval").assignees
        assert assignees == [USERS[confirm.NODE_ROLES[node_id]["user"]]["name"]], node_id


def test_http_procedure_routes(client: TestClient, rid: str) -> None:
    """착수·결재·각본은 장면 1~6과 같은 경로다. 결재 폼 칸의 기본값은 데이터의 확인 기록이다."""
    r = client.post("/sc07/demo-runs", json={"sc01DemoRunId": rid, "executor": "embedded"})
    assert r.status_code == 201, r.text
    assert r.json()["status"]["procedure"] == "PENDING"
    started = client.post(f"/sc07/demo-runs/{rid}/start", headers={"x-demo-actor": "u-fin"})
    assert started.status_code == 200, started.text
    head = started.json()
    assert head["status"]["verification"] == "PASSED" and head["answerHere"]
    [waiting] = head["bpm"]["waiting"]
    assert waiting["nodeId"] == "Confirm_Buy"
    fields = {f["key"]: f.get("default") for f in waiting["fields"]}
    assert fields == {
        "구매확인결정": "확인",
        "구매확인버전": "AGT71-v2",
        "구매확인내용": "대행 인정 및 원인 후보의 업무 타당성 확인",
    }
    denied = client.post(
        f"/sc07/demo-runs/{rid}/actions/Confirm_Buy",
        json={"answer": fields},
        headers={"x-demo-actor": "u-fin"},
    )
    assert denied.status_code == 403
    for i in range(1, 4):
        assert client.post(f"/sc07/demo-runs/{rid}/script/{i}").status_code == 200
    blocked = client.post(
        f"/sc07/demo-runs/{rid}/actions/Check_Setting",
        json={"answer": {"설정확인결과": "일치", "설정확인내용": "x"}},
        headers={"x-demo-actor": "u-fin"},
    )
    assert blocked.status_code == 200  # 반영이 맞으면 확인된다
    assert [s["code"] for s in client.get("/sc07/script").json()] == [
        "D701", "D702", "D703", "D704", "D705",
    ]  # fmt: skip
    topo = client.get("/sc07/process").json()
    assert {n["recordOf"] for n in topo["nodes"] if n["recordOf"]} == set(confirm.NODE_ROLES)


def test_ts_topology_fixture_is_the_bpmn(proc: Sc07Process) -> None:
    """
    화면 테스트의 토폴로지 사본(`tests/fixtures/sc07-process.json`) = BPMN. BPMN을 고치면 실패한다 —
    다시
    만든다: `curl -s localhost:8077/sc07/process | python3 -m json.tool --indent 1 >
    tests/fixtures/sc07-process.json`
    """
    fixture = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sc07-process.json"
    assert json.loads(fixture.read_text(encoding="utf-8")) == topology(proc.process)
