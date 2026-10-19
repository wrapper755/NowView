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
