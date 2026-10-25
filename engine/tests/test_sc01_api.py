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
            yield c
    finally:
        backend.close()


def _run(client) -> str:
    r = client.post("/sc01/demo-runs", json={})
    assert r.status_code == 201, r.text
    return r.json()["demoRunId"]


def test_process_topology_comes_from_the_bpmn(client) -> None:
    body = client.get("/sc01/process").json()
    assert body["processId"] == "nowview.sc01"
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


# ───────────── 시스템 작업 HTTP — 바깥 BPM(Chaeksas HTTP 어댑터)이 부르는 길 ─────────────


def _received(client) -> tuple[str, str]:
    """데모 실행을 만들고 CP02를 받는다 → (데모 실행 id, 원천 id)."""
    rid = _run(client)
    h = {"X-Demo-Actor": "u-sales"}
    r = client.post(f"/sc01/demo-runs/{rid}/sources/receive", json={"fixtureId": "CP02"}, headers=h)
    assert r.status_code == 200, r.text
    return rid, r.json()["sources"][-1]["source_id"]


def _verify(client, rid: str) -> None:
    r = client.post(
        f"/sc01/demo-runs/{rid}/actions/Approve_DQ",
        json={"answer": demo.BASE[1].answer},
        headers={"X-Demo-Actor": "u-sales"},
    )
    assert r.status_code == 200, r.text


def test_operation_validate_returns_the_in_process_output(client) -> None:
    """출력 모양이 내장 어댑터와 같다 — BPMN `output` 대응(`passed`·`error_count`)이 맞는다."""
    rid, sid = _received(client)
    r = client.post(f"/sc01/demo-runs/{rid}/sources/{sid}/validation")
    assert r.status_code == 200, r.text
    assert r.json() == {"passed": True, "error_count": 0}


def test_operation_compare_needs_a_verified_source(client) -> None:
    rid, sid = _received(client)
    r = client.post(f"/sc01/demo-runs/{rid}/sources/{sid}/comparison")
    assert r.status_code == 409  # 확인 전 계산
    _verify(client, rid)
    r = client.post(f"/sc01/demo-runs/{rid}/sources/{sid}/comparison")
    assert r.status_code == 200, r.text
    out = r.json()
    assert set(out) == {"run_id", "risk", "issue_id"} and out["run_id"] == "RUN-F02-001"
    doc = client.get(f"/sc01/demo-runs/{rid}").json()
    assert doc["latestRunId"] == "RUN-F02-001"


def test_operation_agent_draft_and_handoff(client) -> None:
    rid, sid = _received(client)
    _verify(client, rid)
    run_id = client.post(f"/sc01/demo-runs/{rid}/sources/{sid}/comparison").json()["run_id"]

    r = client.post(f"/sc01/demo-runs/{rid}/calc-runs/{run_id}/agent-draft")
    assert r.status_code == 200, r.text
    output_id = r.json()["output_id"]
    drafts = client.get(f"/sc01/demo-runs/{rid}").json()["agentOutputs"]
    assert any(d["output_id"] == output_id for d in drafts)

    # 현업 인수 전 — 인계 조건 미충족
    r = client.post(f"/sc01/demo-runs/{rid}/calc-runs/{run_id}/handoff")
    assert r.status_code == 409 and "인계 조건 미충족" in r.json()["detail"]


def test_operation_unknown_targets_are_404(client) -> None:
    rid, _ = _received(client)
    assert client.post("/sc01/demo-runs/nope/sources/SRC-1/validation").status_code == 404
    assert client.post(f"/sc01/demo-runs/{rid}/sources/SRC-ZZ/validation").status_code == 404
    assert client.post(f"/sc01/demo-runs/{rid}/calc-runs/RUN-ZZ/agent-draft").status_code == 404


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


def test_record_dq_review_unblocks_compare_without_the_embedded_hook(client) -> None:
    """
    Studio에서 「확인완료」해도 원천이 RECEIVED로 남아 계산이 409였다(2026-10-25 실측). 바깥 실행은
    결재 뒤 기록 작업으로 확인을 적는다 — 답한 사람을 모르면 담당자로 적고 짐작이라 표시한다(R1 전).
    """
    rid, sid = _received(client)
    base = f"/sc01/demo-runs/{rid}"
    assert client.post(f"{base}/sources/{sid}/comparison").status_code == 409

    r = client.post(
        f"{base}/answers/Approve_DQ",
        json={
            "source_id": sid,
            "result": "확인완료",
            "opinion": "자동 검증 통과",
            "evidence": "SRC02",
        },
    )
    assert r.status_code == 200, r.text
    doc = client.get(base).json()
    source = next(s for s in doc["sources"] if s["source_id"] == sid)
    assert (source["status"], source["verified_by"]) == ("VERIFIED", "u-sales")
    recorded = next(a for a in doc["audit"] if a["action"] == "answer_recorded")
    assert recorded["actor"] == "u-sales" and recorded["detail"]["guessed"] is True

    assert client.post(f"{base}/sources/{sid}/comparison").status_code == 200


def test_record_answer_keeps_the_business_rules(client) -> None:
    """콘솔 답은 NowView의 사전 검사를 거치지 않는다 — 기록 작업이 마지막 관문이다."""
    rid, sid = _received(client)
    base = f"/sc01/demo-runs/{rid}"
    # 배정한 사람이 그 역할이 아니면 422 (이름으로 와도 id로 와도 같다)
    r = client.post(f"{base}/answers/Approve_Dispatch", json={"prod": "최유나", "mat": "u-mat"})
    assert r.status_code == 422 and "생산 담당" in r.json()["detail"]
    r = client.post(f"{base}/answers/Approve_Dispatch", json={"prod": "김태오", "mat": "u-mat"})
    assert r.status_code == 200 and r.json() == {"prod_name": "김태오", "mat_name": "최유나"}
    # 의견·근거 없는 영업 검토 422, 기록할 결재가 아닌 노드 404
    r = client.post(f"{base}/answers/Approve_Sales", json={"run_id": "RUN-F01-001", "opinion": " "})
    assert r.status_code == 422
    assert client.post(f"{base}/answers/Task_Calc", json={}).status_code == 404
    # 답한 사람을 실어 보내면 그 사람으로 적는다(R1 이후의 길) — 모르는 이름은 422
    r = client.post(
        f"{base}/answers/Approve_DQ",
        json={"source_id": sid, "result": "확인완료", "answered_by": "홍길동"},
    )
    assert r.status_code == 422
