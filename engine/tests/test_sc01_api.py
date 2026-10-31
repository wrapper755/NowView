"""
SC01 HTTP 경계 — 오류 코드 계약(API-03)과 각본 진행, 대시보드 노출 규칙(AT01·UI01-05).

흐름 자체는 `test_sc01_process.py`가 잠근다. 여기서는 HTTP로 바꿔 말할 때 새는 것들을 본다:
DomainError가 정해진 상태 코드로 나가는지, 행위자 헤더가 없으면 막히는지, F02가 계산
전에 보이지 않는지.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import main
from app.sc01 import demo
from app.sc01.api import build_router
from app.sc01.process import Sc01Process
from app.sc01.store import SqliteSc01Store
from app.store import build_sqlite_backend


@pytest.fixture
def client(tmp_path):
    backend = build_sqlite_backend(str(tmp_path / "sc01.sqlite"))
    process = Sc01Process(
        SqliteSc01Store(sqlite3.connect(backend.sqlite_path, check_same_thread=False)),
        publish=main.notifier.publish,
        inline_agent=True,
    )
    app = main.FastAPI()
    app.include_router(build_router(process, main.hub))
    try:
        with TestClient(app) as c:
            c.process = process  # 시스템 작업은 HTTP가 아니라 C15 일꾼으로 온다(_op)
            yield c
    finally:
        backend.close()


def _run(client) -> str:
    # 내장 실행 — 화면 기본은 Center지만(2026-10-27), 여기서는 업무 규칙을 같은 프로세스에서 잠근다.
    r = client.post("/sc01/demo-runs", json={"executor": "embedded"})
    assert r.status_code == 201, r.text
    return r.json()["demoRunId"]


def test_process_topology_comes_from_the_bpmn(client) -> None:
    body = client.get("/sc01/process").json()
    assert body["processId"] == "autopart1.sc01"
    ids = {n["id"] for n in body["nodes"]}
    assert {"Approve_DQ", "Task_Calc", "Accept_PROD", "Accept_MAT", "Accept_FIN"} <= ids
    roles = {n["id"]: n["role"] for n in body["nodes"]}
    assert roles["Approve_Sales"] == "영업팀장" and roles["Task_Calc"] is None


def test_every_user_task_has_a_role(client) -> None:
    """BPMN에 사람 노드를 더하고 역할 표를 빠뜨리면 아무도 그 업무를 할 수 없다."""
    nodes = client.get("/sc01/process").json()["nodes"]
    human = [n for n in nodes if n["kind"] in ("userTask", "manualTask")]
    assert human and all(n["role"] for n in human)


def test_dashboard_hides_f02_until_calculated(client) -> None:
    """AT01·UI01-01 — 계산 전에는 T01·F01만. 계산 후 F02가 병렬로 나온다."""
    rid = _run(client)
    before = client.get(f"/sc01/demo-runs/{rid}/dashboard").json()
    assert before["versions"] == ["T01", "F01"] and before["review"] is None
    assert before["totals"]["F01"]["mgmtProfit"] == "3323351000"

    for i in range(3):
        assert client.post(f"/sc01/demo-runs/{rid}/script/{i}").status_code == 200
    after = client.get(f"/sc01/demo-runs/{rid}/dashboard").json()
    assert after["versions"] == ["T01", "F01", "F02"] and after["approved"] == "F01"
    t, f2 = int(after["totals"]["T01"]["mgmtProfit"]), int(after["totals"]["F02"]["mgmtProfit"])
    assert t - f2 == 167_939_000  # UI01-05 목표 대비 부족액 — 사건 감소액 1,400만원과 다르다
    b = next(m for m in after["models"] if m["modelId"] == "A-b")
    assert (b["target"], b["prior"], b["latest"], b["risk"]) == (10000, 9500, 8800, "CRITICAL")


def test_quarter_and_month_views(client) -> None:
    rid = _run(client)
    for i in range(3):
        client.post(f"/sc01/demo-runs/{rid}/script/{i}")
    q3 = client.get(f"/sc01/demo-runs/{rid}/dashboard", params={"period": "Q3"}).json()
    assert (
        int(q3["totals"]["F01"]["mgmtProfit"]) - int(q3["totals"]["F02"]["mgmtProfit"])
        == 14_000_000
    )
    assert (
        client.get(f"/sc01/demo-runs/{rid}/dashboard", params={"period": "Q9"}).status_code == 422
    )


def test_actor_header_is_required(client) -> None:
    rid = _run(client)
    r = client.post(f"/sc01/demo-runs/{rid}/sources/receive", json={"fixtureId": "CP02"})
    assert r.status_code == 403


def test_error_codes(client) -> None:
    """API-03 — 404·403·409·422."""
    assert client.get("/sc01/demo-runs/nope").status_code == 404
    rid = _run(client)
    h = {"X-Demo-Actor": "u-sales"}
    # 아직 시작 전 — 상태 충돌
    assert (
        client.post(f"/sc01/demo-runs/{rid}/actions/Approve_DQ", json={}, headers=h).status_code
        == 409
    )
    client.post(f"/sc01/demo-runs/{rid}/sources/receive", json={"fixtureId": "CP02"}, headers=h)
    # 필수 칸 누락 — 입력 오류
    r = client.post(f"/sc01/demo-runs/{rid}/actions/Approve_DQ", json={"answer": {}}, headers=h)
    assert r.status_code == 422
    # 다른 역할 — 권한
    r = client.post(
        f"/sc01/demo-runs/{rid}/actions/Approve_DQ",
        json={"answer": {"확인결과": "확인완료", "확인의견": "x", "확인근거": "y"}},
        headers={"X-Demo-Actor": "u-prod"},
    )
    assert r.status_code == 403
    # 모르는 시연 원천
    r = client.post(f"/sc01/demo-runs/{rid}/sources/receive", json={"fixtureId": "ZZ"}, headers=h)
    assert r.status_code == 404


def test_script_runs_to_handoff_and_history_is_readable(client) -> None:
    rid = _run(client)
    for i in range(len(demo.BASE)):
        r = client.post(f"/sc01/demo-runs/{rid}/script/{i}")
        assert r.status_code == 200, r.text
    body = r.json()
    assert body["scene"] == "HANDED_OFF" and body["handoffCheck"]["met"]
    assert body["bpm"]["state"] == "done" and body["bpm"]["waiting"] == []
    # 단계를 건너뛰면 막는다
    rid2 = _run(client)
    assert client.post(f"/sc01/demo-runs/{rid2}/script/3").status_code == 409

    history = client.get(f"/sc01/demo-runs/{rid}/history").json()
    assert history[0]["event"] == "S0"
    past = client.get(f"/sc01/demo-runs/{rid}/history/{history[1]['seq']}").json()
    assert past["historical"] is True and past["scene"] != "HANDED_OFF"


def test_waiting_view_names_the_role_and_task(client) -> None:
    rid = _run(client)
    for i in range(5):
        client.post(f"/sc01/demo-runs/{rid}/script/{i}")
    waiting = client.get(f"/sc01/demo-runs/{rid}").json()["bpm"]["waiting"]
    by_node = {w["nodeId"]: w for w in waiting}
    assert set(by_node) == {"Accept_PROD", "Accept_MAT", "Approve_Review"}
    assert (
        by_node["Accept_PROD"]["role"] == "생산담당"
        and by_node["Accept_PROD"]["taskId"] == "TASK-PROD"
    )


def test_concurrent_reads_during_writes_do_not_break(tmp_path) -> None:
    """
    SSE 읽기(스레드풀)와 쓰기가 같은 SQLite 연결에서 겹쳐도 깨지지 않는다.

    잠금 없이 연결을 나눠 쓰자 쓰는 도중의 읽기가 빈 행을 받아 SSE 스트림이 죽었다.
    """
    import sqlite3
    import threading

    process = Sc01Process(
        SqliteSc01Store(sqlite3.connect(str(tmp_path / "c.sqlite"), check_same_thread=False)),
        inline_agent=True,
    )
    rid = process.create()["demo_run_id"]
    errors: list[BaseException] = []
    done = threading.Event()

    def reader() -> None:
        while not done.is_set():
            try:
                process.get(rid)
                process.store.history(rid)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
                return

    threads = [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    try:
        for i in range(len(demo.BASE)):
            demo.run_step(process, rid, i)
    finally:
        done.set()
        for t in threads:
            t.join()
    assert errors == []
    assert process.get(rid)["scene"] == "HANDED_OFF"


def test_visited_nodes_accumulate_for_the_canvas(client) -> None:
    """캔버스가 지나온 경로를 그린다 — 조작마다 기록이 새로 열려도 누적된다."""
    rid = _run(client)
    for i in range(3):
        client.post(f"/sc01/demo-runs/{rid}/script/{i}")
    visited = client.get(f"/sc01/demo-runs/{rid}").json()["bpm"]["visited"]
    assert visited[:2] == ["Start", "Task_Validate"]
    assert {"Approve_DQ", "Gw_DQ", "Confirm_Calc", "Task_Calc"} <= set(visited)
    assert "Approve_Sales" not in visited  # 지금 기다리는 곳은 지나온 곳이 아니다


def test_history_carries_the_script_index_for_rewinding(client) -> None:
    """데모 플레이어가 장면 → 이력 seq를 찾는다. 시각 이동도 이력에 남지만 지점은 그대로다."""
    rid = _run(client)
    for i in range(3):
        client.post(f"/sc01/demo-runs/{rid}/script/{i}")
    history = client.get(f"/sc01/demo-runs/{rid}/history").json()
    assert history[0]["scriptIndex"] == -1
    assert [h["scriptIndex"] for h in history if h["event"] != "EV01"][-1] == 2
    last_for = {h["scriptIndex"]: h["seq"] for h in history}
    assert sorted(last_for) == [-1, 0, 1, 2]


def test_past_dashboard_hides_what_did_not_exist_yet(client) -> None:
    """지난 시점의 대시보드는 그때의 문서로 계산한다 — S0에는 F02가 없다."""
    rid = _run(client)
    for i in range(3):
        client.post(f"/sc01/demo-runs/{rid}/script/{i}")
    past = client.get(f"/sc01/demo-runs/{rid}/dashboard", params={"seq": 1}).json()
    assert past["review"] is None
    assert client.get(f"/sc01/demo-runs/{rid}/dashboard", params={"seq": 999}).status_code == 404


def test_customer_plan_seed(client) -> None:
    rows = client.get("/sc01/customer-plans/CP01").json()
    assert len(rows) == 15
    b7 = next(r for r in rows if r["modelId"] == "A-b" and r["period"] == "2027-07-01")
    assert b7["quantity"] == 9500
    assert client.get("/sc01/customer-plans/CP99").status_code == 404


def test_rules_come_from_the_seed(client) -> None:
    rules = client.get("/sc01/rules").json()
    assert rules["감소율_중요"] == "0.05" and rules["감소액_관심"] == "5000000"


def test_ts_fixture_matches_the_bpmn(client) -> None:
    """
    TS 테스트(`tests/sc01.test.ts`)가 쓰는 토폴로지 사본이 BPMN과 같은지 본다.

    BPMN을 고치면 여기서 실패한다 — 저장소 루트에서 사본을 다시 만든다:
    `curl -s localhost:8077/sc01/process | python3 -m json.tool --indent 1`
    `> tests/fixtures/sc01-process.json`
    """
    import json
    from pathlib import Path

    fixture = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sc01-process.json"
    assert json.loads(fixture.read_text(encoding="utf-8")) == client.get("/sc01/process").json()


# ───────────── 시스템 작업 — 바깥 BPM의 일감을 C15 일꾼이 가져와 부르는 길 ─────────────


#: 바깥 실행의 id — 일감의 멱등 칸 `run_id`(C15). 첫 일감이 데모 실행을 이 실행에 묶는다(N2).
RUN = "run_20270616_090000_a1a1a1"


class _Worked:
    """일꾼이 일감 하나를 끝낸 결과 — `complete`면 200과 출력, `fail`이면 코드의 상태와 사유."""

    def __init__(self, outcome) -> None:
        from app.consumer import CODE_OF_STATUS

        status_of = {code: status for status, code in CODE_OF_STATUS.items()}
        status_of["operation_not_found"] = 404
        self.outcome = outcome
        self.status_code = 200 if outcome.ok else status_of.get(outcome.code, 500)
        self.text = "" if outcome.ok else f"{outcome.code}: {outcome.message}"

    def json(self) -> dict:
        if self.outcome.ok:
            return dict(self.outcome.response.output)
        return {"detail": self.outcome.message}


def _op(client, rid: str, operation: str, *, origin="test", run=RUN, node="Task_Validate", **args):
    """그 데모 실행에 시스템 작업 하나를 일감으로 — Center가 일꾼에게 넘기는 모양 그대로."""
    from chaeksas.contracts.external_task import LockedTask

    from app.consumer import scene_service

    task = LockedTask.model_validate(
        {
            "task_id": "xt_test",
            "topic": "nowview",
            "operation": operation,
            "mode": "deterministic",
            "origin": origin,
            "idempotency": {
                "run_id": run,
                "node_id": node,
                "node_instance": 1,
                "attempt": 1,
                "call_seq": 1,
            },
            "caller": {"type": "studio", "host": "t", "bpm_process_id": "autopart1.sc01"},
            "input": {"demo_run_id": rid, **args},
            "lock_until": "2099-01-01T00:00:00Z",
            "deadline": "2099-01-01T00:00:00Z",
        }
    )
    # 일감마다 새 수행기 — 같은 멱등 칸을 다시 보내도 저장된 결과가 아니라 지금 상태를 본다
    return _Worked(scene_service("nowview", client.process).execute(task))


def _received(client) -> tuple[str, str]:
    """Studio 실행용 데모 실행을 만들고 CP02를 받는다 → (데모 실행 id, 원천 id)."""
    r = client.post("/sc01/demo-runs", json={"executor": "studio"})
    assert r.status_code == 201, r.text
    rid = r.json()["demoRunId"]
    h = {"X-Demo-Actor": "u-sales"}
    r = client.post(f"/sc01/demo-runs/{rid}/sources/receive", json={"fixtureId": "CP02"}, headers=h)
    assert r.status_code == 200, r.text
    return rid, r.json()["sources"][-1]["source_id"]


def _verify(client, rid: str, sid: str = "SRC02") -> None:
    r = _op(
        client,
        rid,
        "record_plan_review",
        node="Record_DQ",
        node_id="Approve_DQ",
        source_id=sid,
        result="확인완료",
        opinion="통과",
        evidence=sid,
    )
    assert r.status_code == 200, r.text


def test_operation_validate_returns_the_in_process_output(client) -> None:
    """출력 모양이 내장 어댑터와 같다 — BPMN `output` 대응(`passed`·`error_count`)이 맞는다."""
    rid, sid = _received(client)
    r = _op(client, rid, "validate_customer_plan", source_id=sid)
    assert r.status_code == 200, r.text
    assert r.json() == {"passed": True, "error_count": 0}


def test_operation_compare_needs_a_verified_source(client) -> None:
    rid, sid = _received(client)
    r = _op(client, rid, "assess_supply_risk", source_id=sid)
    assert r.status_code == 409  # 확인 전 계산
    _verify(client, rid)
    r = _op(client, rid, "assess_supply_risk", source_id=sid)
    assert r.status_code == 200, r.text
    out = r.json()
    assert set(out) == {"run_id", "risk", "issue_id"} and out["run_id"] == "RUN-F02-001"
    doc = client.get(f"/sc01/demo-runs/{rid}").json()
    assert doc["latestRunId"] == "RUN-F02-001"


def test_operation_agent_draft_and_handoff(client) -> None:
    rid, sid = _received(client)
    _verify(client, rid)
    run_id = _op(client, rid, "assess_supply_risk", source_id=sid).json()["run_id"]

    r = _op(client, rid, "request_review_draft", run_id=run_id)
    assert r.status_code == 200, r.text
    output_id = r.json()["output_id"]
    drafts = client.get(f"/sc01/demo-runs/{rid}").json()["agentOutputs"]
    assert any(d["output_id"] == output_id for d in drafts)

    # 현업 인수 전 — 인계 조건 미충족
    r = _op(client, rid, "hand_off_case", run_id=run_id)
    assert r.status_code == 409 and "인계 조건 미충족" in r.json()["detail"]


def test_operation_unknown_targets_are_404(client) -> None:
    rid, _ = _received(client)
    assert _op(client, "nope", "validate_customer_plan", source_id="SRC-1").status_code == 404
    assert _op(client, rid, "validate_customer_plan", source_id="SRC-ZZ").status_code == 404
    assert _op(client, rid, "request_review_draft", run_id="RUN-ZZ").status_code == 404
    # 확장 정의에 없는 작업 — 수행기가 받지 않는다(Center도 manifest로 먼저 막는다)
    assert _op(client, rid, "record_nothing").status_code == 404


# ─────── 결정 기록(N1)·결재 담당자(N4) — 바깥 Chaeksas에서 돌려도 업무 효과가 난다 ───────


def _bpmn_nodes():
    from chaeksas.contracts.bpmn_ext import read_process

    from app.sc01.process import PROCESS_PATH

    return read_process(PROCESS_PATH.read_bytes()).nodes


def test_every_approval_names_assignees_matching_the_role_table() -> None:
    """
    바깥 Chaeksas는 결재 담당자(이름)로 「담당자만 답한다」를 막는다(ADR-0081). 그 이름이 역할 표
    (`NODE_ROLES`)와 어긋나면 내장 실행과 바깥 실행의 권한이 갈라진다.
    """
    from app.sc01.domain import NODE_ROLES, USERS

    human = [n for n in _bpmn_nodes() if n.kind in ("userTask", "manualTask")]
    assert {n.id for n in human} == set(NODE_ROLES)
    for n in human:
        assert n.kind == "userTask", f"{n.id}: 확인(manualTask)에는 담당자를 둘 수 없다(C14 B12)"
        spec, assignees = NODE_ROLES[n.id], n.prop("approval").assignees
        if "assignee_var" in spec:
            # 인수 담당자는 배정 결과다 — 배정 기록이 돌려주는 「…명」 변수(이름)를 쓴다.
            assert assignees == spec["assignee_var"] + "명", n.id
        else:
            assert [USERS[u]["role"] for u in USERS if USERS[u]["name"] in assignees] == [
                spec["role"]
            ], n.id


def test_every_decision_is_followed_by_its_record_task() -> None:
    """결재 뒤에 기록 작업이 없으면 그 결정은 바깥 실행에서 NowView에 닿지 않는다(실측: 409)."""
    from chaeksas.contracts.bpmn_ext import read_process

    from app.sc01.process import PROCESS_PATH, RECORD_OF_NODE

    process = read_process(PROCESS_PATH.read_bytes())
    for node_id, operation in RECORD_OF_NODE.items():
        [flow] = process.outgoing(node_id)
        nxt = process.node(flow.target)
        assert nxt.kind == "serviceTask", node_id
        call = nxt.prop("serviceCall")
        assert (call.operation, call.input["node_id"]) == (operation, f"'{node_id}'"), node_id


def test_extension_definition_matches_the_bpmn_service_calls() -> None:
    """
    확장 정의(`chaeksas/nowview.extension.json`)와 BPMN이 갈라지면 어댑터가 실행 중에
    멈춘다 — 본문 템플릿의 `{{input.x}}`가 입력에 없으면 호출이 실패한다(4.3). 정의는 한 벌이고
    (R4) 답한 사람을 받는 작업은 결재의 `answered_by_as` 변수를 싣는다(R1).
    """
    import json
    import re
    from pathlib import Path

    from chaeksas.contracts import extension as ext
    from chaeksas.contracts.bpmn_ext import read_process

    from app.sc01.process import INTAKE_PATH, PROCESS_PATH, RECORD_OF_NODE

    root = Path(__file__).resolve().parents[2] / "chaeksas"
    # NowView 고정 확장 `nowview`(장면 1) — 옮기기 전 장면 2~6은 `nowview-sc02`~`sc06`
    assert sorted(p.name for p in root.glob("*.extension.json")) == [
        "nowview-sc02.extension.json",
        "nowview-sc03.extension.json",
        "nowview-sc04.extension.json",
        "nowview-sc05.extension.json",
        "nowview-sc06.extension.json",
        "nowview.extension.json",
    ]
    raw = (root / "nowview.extension.json").read_bytes()
    manifest = ext.ExtensionManifest.model_validate(json.loads(raw))
    assert ext.validate(manifest, from_center=True) == []
    adapter = json.loads(raw)["service"]["adapter"]
    # C15 일꾼만 부른다 — 주소·요청은 계약(C13)이 요구하는 자리 채움이고 키도 없다(범용 어댑터
    # 일꾼으로 부를 길을 열어 두지 않는다).
    assert adapter["allowed_hosts"] == ["www.nowview.work"]
    assert "auth" not in adapter and not manifest.requires_keys
    assert {json.dumps(o["request"]) for o in adapter["operations"]} == {
        json.dumps({"method": "POST", "path": "/"})
    }
    operations = {o["name"]: o for o in adapter["operations"]}

    process = read_process(PROCESS_PATH.read_bytes())
    intake = read_process(INTAKE_PATH.read_bytes())  # 접수 Bot(N5)도 같은 정의를 부른다
    answered = {RECORD_OF_NODE[n]: n for n in RECORD_OF_NODE} | {
        "assess_supply_risk": "Confirm_Calc",
        "record_intake_decision": "Approve_Batch",
    }
    for node in [*process.of_kind("serviceTask"), *intake.of_kind("serviceTask")]:
        call = node.prop("serviceCall")
        op = operations[call.operation]
        given = set(call.input)
        assert set(op["input_schema"]["required"]) <= given, node.id
        used = set(
            re.findall(r"\{\{input\.(\w+)\}\}", json.dumps(op["request"], ensure_ascii=False))
        )
        assert used <= given, (node.id, used - given)
        if call.operation in answered:
            assert "answered_by" in op["input_schema"]["required"], call.operation
    # 그림이 외부 확장을 선언해야 패키지 `requires.extensions`에 오르고, 서버 실행기가 Center에서
    # 정의(주소)를 받아 온다 — 빠지면 「서비스 앱 주소를 모른다」로 실행이 실패했다(실측).
    from chaeksas.contracts._semver import satisfies

    for drawn in (process, intake):
        [need] = [n for n in drawn.info.extensions if n.id == manifest.id]
        assert satisfies(manifest.version, need.version), (drawn.id, need.version)
    for node_id in [*RECORD_OF_NODE, "Confirm_Calc"]:
        approval = process.node(node_id).prop("approval")
        assert approval.answered_by_as and approval.answered_via_as, node_id
        [flow] = process.outgoing(node_id)
        call = process.node(flow.target).prop("serviceCall")
        assert call.input["answered_by"] == approval.answered_by_as, node_id
        assert call.input["answered_via"] == approval.answered_via_as, node_id


def test_record_plan_review_unblocks_the_assessment_without_the_embedded_hook(client) -> None:
    """
    Studio에서 「확인완료」해도 원천이 RECEIVED로 남아 계산이 409였다(2026-10-25 실측). 바깥 실행은
    결재 뒤 기록 작업으로 확인을 적는다. 이 본문은 `answered_by`가 없던 옛 정의(0.5.0 이하)의
    것이다 — 그때만 담당자로 적고 짐작이라 표시한다(R1 이후의 길은 아래 시험).
    """
    rid, sid = _received(client)
    base = f"/sc01/demo-runs/{rid}"
    assert _op(client, rid, "assess_supply_risk", source_id=sid).status_code == 409

    r = _op(
        client,
        rid,
        "record_plan_review",
        node_id="Approve_DQ",
        source_id=sid,
        result="확인완료",
        opinion="자동 검증 통과",
        evidence="SRC02",
    )
    assert r.status_code == 200, r.text
    doc = client.get(base).json()
    source = next(s for s in doc["sources"] if s["source_id"] == sid)
    assert (source["status"], source["verified_by"]) == ("VERIFIED", "u-sales")
    recorded = next(a for a in doc["audit"] if a["action"] == "answer_recorded")
    assert recorded["actor"] == "u-sales" and recorded["detail"]["guessed"] is True

    assert _op(client, rid, "assess_supply_risk", source_id=sid).status_code == 200


def test_record_answer_keeps_the_business_rules(client) -> None:
    """콘솔 답은 NowView의 사전 검사를 거치지 않는다 — 기록 작업이 마지막 관문이다."""
    rid, _ = _received(client)
    # 배정한 사람이 그 역할이 아니면 422 (이름으로 와도 id로 와도 같다)
    r = _op(client, rid, "assign_follow_up", node_id="Approve_Dispatch", prod="최유나", mat="u-mat")
    assert r.status_code == 422 and "생산 담당" in r.json()["detail"]
    r = _op(client, rid, "assign_follow_up", node_id="Approve_Dispatch", prod="김태오", mat="u-mat")
    assert r.status_code == 200 and r.json() == {
        "prod_name": "김태오",
        "mat_name": "최유나",
        "error_message": None,  # 기록이 성공하면 직전 거절 사유를 비운다(N1)
    }
    # 의견·근거 없는 영업 검토 422
    r = _op(
        client,
        rid,
        "record_risk_review",
        node_id="Approve_Sales",
        run_id="RUN-F01-001",
        opinion=" ",
    )
    assert r.status_code == 422


def test_record_writes_who_answered_without_guessing(client) -> None:
    """
    R1(ADR-0096) — 결재의 `answered_by_as` 변수가 기록 작업 `answered_by`로 온다. 마스터에 있는
    이름은 사용자 id로, 없는 이름(콘솔 관리자 · Studio 「시험 케이스」)은 거절하지 않고 그 이름
    그대로 적는다 — 거절하면 오류 경계가 같은 결재로 되돌리는데 답한 사람은 고칠 길이 없다.
    """
    rid, sid = _received(client)
    base = f"/sc01/demo-runs/{rid}"
    body = {"node_id": "Approve_DQ", "opinion": "확인", "evidence": "SRC02"}
    r = _op(
        client,
        rid,
        "record_plan_review",
        **body,
        source_id=sid,
        result="보완요청",
        answered_by="이도윤",
        answered_via="nowview-relay",
    )
    assert r.status_code == 200, r.text
    doc = client.get(base).json()
    [first] = [a for a in doc["audit"] if a["action"] == "answer_recorded"]
    assert first["actor"] == "u-sales"
    assert first["detail"] == {
        "node_id": "Approve_DQ",
        "guessed": False,
        "answered_via": "nowview-relay",
    }

    rid, sid = _received(client)
    base = f"/sc01/demo-runs/{rid}"
    r = _op(
        client,
        rid,
        "record_plan_review",
        **body,
        source_id=sid,
        result="확인완료",
        answered_by="관리자",
        answered_via=None,
    )
    assert r.status_code == 200, r.text
    doc = client.get(base).json()
    source = next(s for s in doc["sources"] if s["source_id"] == sid)
    assert (source["status"], source["verified_by"]) == ("VERIFIED", "관리자")
    [recorded] = [a for a in doc["audit"] if a["action"] == "answer_recorded"]
    assert recorded["actor"] == "관리자" and recorded["detail"]["outside_master"] is True
    assert recorded["detail"]["guessed"] is False
    # 업무의 담당자는 답한 사람이 아니라 그 결재의 담당자다
    [task] = [t for t in doc["tasks"] if t["type"] == "DQ"]
    assert task["assigned_to"] == "u-sales"


# ───────────── 데모 실행 ↔ 바깥 실행 (N2) ─────────────


def test_external_demo_run_does_not_start_the_embedded_bpm(client) -> None:
    """
    수신이 내장 BPM을 늘 시작해, 바깥 실행과 내장 실행이 한 문서에서 함께 돌았다 — 내장 쪽이
    Approve_DQ에 멈춘 채 남았다(2026-10-25 실측). 바깥 실행용 데모 실행은 원천만 등록한다.
    """
    rid, sid = _received(client)
    doc = client.get(f"/sc01/demo-runs/{rid}").json()
    assert doc["executor"] == "studio"
    assert doc["bpm"]["state"] == "not_started" and doc["bpm"]["externalRunId"] is None
    assert doc["bpm"]["waiting"] == [] and doc["tasks"] == []
    # 화면 조작·각본은 거절한다 — 결재는 Studio에서 답한다.
    r = client.post(
        f"/sc01/demo-runs/{rid}/actions/Approve_DQ",
        json={"answer": demo.BASE[1].answer},
        headers={"X-Demo-Actor": "u-sales"},
    )
    assert r.status_code == 409 and "Studio" in r.json()["detail"]
    assert client.post(f"/sc01/demo-runs/{rid}/script/0").status_code == 409


def test_first_call_links_the_external_run_and_others_are_409(client) -> None:
    rid, sid = _received(client)
    base = f"/sc01/demo-runs/{rid}"
    assert _op(client, rid, "validate_customer_plan", source_id=sid).status_code == 200
    doc = client.get(base).json()
    assert doc["bpm"]["externalRunId"] == RUN
    assert doc["bpm"]["state"] == "running" and doc["bpm"]["visited"] == ["Task_Validate"]
    linked = [a for a in doc["audit"] if a["action"] == "external_run_linked"]
    assert len(linked) == 1 and linked[0]["detail"]["executor"] == "studio"
    # 같은 실행은 다시 와도 된다, 다른 실행은 409
    assert _op(client, rid, "validate_customer_plan", source_id=sid).status_code == 200
    r = _op(client, rid, "validate_customer_plan", source_id=sid, run="run_20270616_091500_b2b2b2")
    assert r.status_code == 409 and "이미 바깥 실행" in r.json()["detail"]


def test_embedded_demo_run_refuses_external_calls(client) -> None:
    """내장 BPM이 도는 데모 실행에 바깥 작업이 오면 두 실행이 한 문서에 업무를 적는다 — 409."""
    rid = _run(client)
    h = {"X-Demo-Actor": "u-sales"}
    client.post(f"/sc01/demo-runs/{rid}/sources/receive", json={"fixtureId": "CP02"}, headers=h)
    r = _op(client, rid, "validate_customer_plan", source_id="SRC02")
    assert r.status_code == 409 and "내장 BPM" in r.json()["detail"]


def test_record_marks_the_decision_as_visited(client) -> None:
    """기록 작업은 그 앞의 결재도 지나왔다는 뜻이다 — 캔버스가 결재를 완료로 칠한다."""
    rid, sid = _received(client)
    _verify(client, rid, sid)
    bpm = client.get(f"/sc01/demo-runs/{rid}").json()["bpm"]
    assert bpm["visited"] == ["Approve_DQ", "Record_DQ"] and bpm["position"] == []


def test_reset_keeps_the_executor_and_unlinks(client) -> None:
    rid, sid = _received(client)
    _op(client, rid, "validate_customer_plan", source_id=sid)
    h = {"X-Demo-Actor": "u-demo"}
    doc = client.post(f"/sc01/demo-runs/{rid}/reset", json={}, headers=h).json()
    assert doc["executor"] == "studio" and doc["bpm"]["externalRunId"] is None
    doc = client.post(
        f"/sc01/demo-runs/{rid}/reset", json={"executor": "embedded"}, headers=h
    ).json()
    assert doc["executor"] == "embedded" and doc["bpm"] is None
    r = client.post(f"/sc01/demo-runs/{rid}/reset", json={"executor": "cloud"}, headers=h)
    assert r.status_code == 422
    assert client.post("/sc01/demo-runs", json={"executor": "cloud"}).status_code == 422


# ───────────── 실행 위치 — 일감의 origin (C15) ─────────────


def test_the_origin_must_match_the_declared_executor(client) -> None:
    """
    실행 위치는 데모 실행을 만들 때 선언한다(N2). 일감의 `origin`이 인증된 실행 위치다 — Center가
    올린 쪽을 보고 붙인다(Studio는 `test`, 서버 실행기는 `run`). 어긋나면 409이고 묶이지 않는다.
    사유가 그대로 간다 — 어댑터가 4xx 본문을 버리던 때와 다르다.
    """
    rid, sid = _received(client)  # studio
    r = _op(client, rid, "validate_customer_plan", source_id=sid, origin="run")
    assert r.status_code == 409 and "Center 서버 실행에서 왔는데" in r.json()["detail"]
    assert r.outcome.code == "conflict" and r.outcome.retryable is False
    assert client.get(f"/sc01/demo-runs/{rid}").json()["bpm"]["externalRunId"] is None

    center = client.post("/sc01/demo-runs", json={"executor": "center"}).json()["demoRunId"]
    h = {"X-Demo-Actor": "u-sales"}
    client.post(f"/sc01/demo-runs/{center}/sources/receive", json={"fixtureId": "CP02"}, headers=h)
    assert _op(client, center, "validate_customer_plan", source_id="SRC02").status_code == 409
    r = _op(client, center, "validate_customer_plan", source_id="SRC02", origin="run")
    assert r.status_code == 200, r.text


def test_system_operations_have_no_http_path(client) -> None:
    """바깥에서 HTTP로 업무를 적는 길은 없다 — 일감은 Center를 거쳐 일꾼만 가져간다(ADR-0102)."""
    rid, sid = _received(client)
    for path in (
        f"/sc01/demo-runs/{rid}/sources/{sid}/validation",
        f"/sc01/demo-runs/{rid}/answers/Approve_DQ",
    ):
        assert client.post(path, json={}).status_code in (404, 405)


def test_the_default_executor_is_center(client) -> None:
    """화면은 내장 실행을 쓰지 않는다(2026-10-27) — 실행 위치를 주지 않으면 Center 서버 실행이다."""
    r = client.post("/sc01/demo-runs", json={})
    assert r.status_code == 201 and r.json()["executor"] == "center"
