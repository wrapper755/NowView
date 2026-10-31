"""
회사 시스템 시뮬레이터 API — NowView 일꾼이 기대는 계약(`docs/worker-interfaces.md` §3.2).

* 불변 기록은 원천 시트 그대로다(행 수·버전·누락 null).
* 세계는 서로 보지 않는다 — 수신함·상태·시각이 세계마다 따로다. 초기화는 그 세계만 S0로.
* 고객 원천 수신은 같은 내용이면 기존 접수, 상태 쓰기는 같은 ref면 다시 적지 않는다.
* 키가 없으면 401, 서버에 키가 없으면 기동하지 않는다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from autoparts_sim.main import build_app
from autoparts_sim.store import WorldStore

KEY = "sim-test-key"


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("AUTOPARTS_SIM_KEY", KEY)
    monkeypatch.delenv("AUTOPARTS_SIM_AUTH", raising=False)
    app = build_app(WorldStore(tmp_path / "sim.sqlite"))
    return TestClient(app, headers={"authorization": f"Bearer {KEY}"})


def test_immutable_records(client: TestClient) -> None:
    users = client.get("/company/org/users").json()
    assert {"user_id": "u-sales", "name": "이도윤", "role": "영업담당"} in users
    assert client.get("/company/master").json()["models"] == ["A-a", "A-b", "A-c", "A-d", "A-e"]
    t01 = client.get("/company/plans/T01").json()["rows"]
    assert len(t01) == 60 and {"period", "model_id", "quantity"} <= set(t01[0])
    assert client.get("/company/plans/F02").status_code == 404  # 검토 전망은 NowView가 만든다
    assert [v["version_id"] for v in client.get("/company/versions").json()] == [
        "T01",
        "CP01",
        "F01",
        "C01",
    ]
    c01 = client.get("/company/costs/C01").json()["rows"]
    assert isinstance(c01[0]["unit_cm"], str)  # 금액은 문자열 DECIMAL
    assert client.get("/company/fixed-costs/FC01").json()["rows"]
    assert client.get("/company/actuals").json()["rows"][0]["cutoff_date"]
    cp01 = client.get("/company/customer-plans/CP01").json()
    assert cp01["status"] == "VERIFIED" and len(cp01["rows"]) == 15
    assert client.get("/company/customer-plans/CP02").status_code == 404  # 고객이 보내야 생긴다


def test_world_inbox_status_and_clock(client: TestClient) -> None:
    assert client.post("/worlds", json={"world_id": "demo-a"}).status_code == 201
    client.post("/worlds", json={"world_id": "demo-b"})
    assert client.get("/worlds/demo-a/clock").json()["at"] == "2027-06-15T18:00:00+09:00"
    client.post("/worlds/demo-a/clock", json={"at": "2027-06-16T09:00:00+09:00"})
    sent = client.post("/worlds/demo-a/sim/customer-plans", json={"fixture_id": "CP02"}).json()
    assert (
        sent["created"]
        and sent["doc_id"] == "DOC-0001"
        and sent["received_at"].startswith("2027-06-16T09:00")
    )
    again = client.post("/worlds/demo-a/sim/customer-plans", json={"fixture_id": "CP02"}).json()
    assert again == {**sent, "created": False}
    assert client.get("/worlds/demo-b/customer-plans/inbox").json() == []  # 세계는 서로 보지 않는다

    doc = client.get("/worlds/demo-a/customer-plans/DOC-0001").json()
    b7 = next(r for r in doc["rows"] if r["model_id"] == "A-b" and r["period"] == "2027-07-01")
    assert b7["quantity"] == 8800
    missing = client.post("/worlds/demo-a/sim/customer-plans", json={"fixture_id": "EX02"}).json()
    rows = client.get(f"/worlds/demo-a/customer-plans/{missing['doc_id']}").json()["rows"]
    assert (
        next(r for r in rows if r["model_id"] == "A-b" and r["period"] == "2027-07-01")["quantity"]
        is None
    )
    assert missing["corrects"] == "DOC-0001"
    assert [
        d["doc_id"] for d in client.get("/worlds/demo-a/customer-plans/inbox?after=1").json()
    ] == [missing["doc_id"]]

    body = {
        "status": "VERIFIED",
        "by": "이도윤",
        "opinion": "확인",
        "evidence": "CP02",
        "ref": "run-1:Approve_DQ",
    }
    first = client.post("/worlds/demo-a/customer-plans/DOC-0001/status", json=body).json()
    assert first["recorded"] and first["status"] == "VERIFIED"
    assert (
        client.post("/worlds/demo-a/customer-plans/DOC-0001/status", json=body).json()["recorded"]
        is False
    )
    clash = client.post(
        "/worlds/demo-a/customer-plans/DOC-0001/status", json={**body, "status": "NEEDS_INFO"}
    )
    assert clash.status_code == 409

    client.post("/worlds/demo-a/reset")
    assert client.get("/worlds/demo-a/customer-plans/inbox").json() == []
    assert client.get("/worlds/demo-a/clock").json()["at"] == "2027-06-15T18:00:00+09:00"


def test_unknown_world_and_fixture(client: TestClient) -> None:
    assert client.get("/worlds/none/clock").status_code == 404
    client.post("/worlds", json={"world_id": "w"})
    assert (
        client.post("/worlds/w/sim/customer-plans", json={"fixture_id": "EX99"}).status_code == 404
    )


def test_key_is_required(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOPARTS_SIM_KEY", KEY)
    monkeypatch.delenv("AUTOPARTS_SIM_AUTH", raising=False)
    bare = TestClient(build_app(WorldStore(tmp_path / "s.sqlite")))
    assert bare.get("/health").status_code == 200
    assert bare.get("/company/master").status_code == 401
    monkeypatch.delenv("AUTOPARTS_SIM_KEY")
    with pytest.raises(RuntimeError):
        build_app(WorldStore(tmp_path / "t.sqlite"))
