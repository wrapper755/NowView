"""
장면 시작의 배경 진행(`app.preparation`) — 시작 요청이 오래 걸리면 202와 준비 상태를
돌려주고 배경에서 앞 장면을 끝까지 잇는다. Center 실행이면 장면 3 시작이 약 7분이라
BFF·Cloudflare가 끊었다(로컬 실측).

장면 2(장면 1을 내장 각본으로 인계까지)로 본다 — 다섯 장면의 시작이 같은 도우미를 쓴다.
기다림을 0으로 두면 내장 실행도 「아직」이 된다.
"""

from __future__ import annotations

import sqlite3
import threading
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.events import Hub
from app.preparation import Preparations
from app.sc01.domain import DomainError
from app.sc01.process import Sc01Process
from app.sc01.store import SqliteSc01Store
from app.sc02.api import build_router
from app.sc02.process import Sc02Process


def _proc() -> Sc02Process:
    s1 = SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False))
    s2 = SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), "sc02")
    return Sc02Process(s2, Sc01Process(s1, inline_agent=True), publish=lambda _: None)


def _client(proc: Sc02Process, wait_s: float) -> TestClient:
    app = FastAPI()
    app.include_router(build_router(proc, Hub(), preparations=Preparations(wait_s=wait_s)))
    return TestClient(app)


def _until_done(client: TestClient, rid: str) -> dict:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        state = client.get(f"/sc02/demo-runs/{rid}/preparation").json()
        if state["state"] != "running":
            return state
        time.sleep(0.2)
    raise AssertionError("준비가 끝나지 않았다")


def test_slow_start_answers_202_and_finishes_in_the_background() -> None:
    proc = _proc()
    client = _client(proc, wait_s=0)
    r = client.post("/sc02/demo-runs", json={"executor": "embedded"})
    assert r.status_code == 202, r.text
    body = r.json()
    rid = body["demoRunId"]
    assert body["preparing"] is True and body["scene"] == "sc02" and body["state"] == "running"
    # 장면 1 실행은 응답 전에 만들었다 — 화면이 준비 상태를 물을 id가 있다
    assert proc.sc01.store.load(rid) is not None
    assert _until_done(client, rid)["state"] == "done"
    got = client.get(f"/sc02/demo-runs/{rid}")
    assert got.status_code == 200 and got.json()["step"] == "D00"
    # 다시 시작하면 문서가 이미 있으니 곧바로 201
    again = client.post("/sc02/demo-runs", json={"sc01DemoRunId": rid, "executor": "embedded"})
    assert again.status_code == 201 and again.json()["demoRunId"] == rid


def test_progress_reads_the_previous_scene_step() -> None:
    proc = _proc()
    gate = threading.Event()
    original = proc._finish_sc01

    def slow(rid: str):
        gate.wait(10)
        return original(rid)

    proc._finish_sc01 = slow  # type: ignore[method-assign]
    client = _client(proc, wait_s=0)
    rid = client.post("/sc02/demo-runs", json={"executor": "embedded"}).json()["demoRunId"]
    state = client.get(f"/sc02/demo-runs/{rid}/preparation").json()
    assert state["preparing"] is True
    # 장면 1은 만들어졌고 아직 시작 전이다 — 진행 표시가 그 단계를 읽는다
    assert [p["scene"] for p in state["progress"]] == ["sc01"]
    assert state["progress"][0]["step"] == proc.sc01.get(rid)["step"]
    # 같은 시작이 겹치면 진행 중인 것을 함께 기다린다 — 새로 돌리지 않는다
    second = client.post("/sc02/demo-runs", json={"sc01DemoRunId": rid, "executor": "embedded"})
    assert second.status_code == 202 and second.json()["startedAt"] == state["startedAt"]
    gate.set()
    assert _until_done(client, rid)["state"] == "done"


def test_quick_start_still_answers_201() -> None:
    client = _client(_proc(), wait_s=60)
    r = client.post("/sc02/demo-runs", json={"executor": "embedded"})
    assert r.status_code == 201 and r.json()["step"] == "D00"


def test_background_failure_keeps_reason_and_status() -> None:
    proc = _proc()
    # 첫 응답(202)이 나간 뒤에 실패하게 한다 — 기다림 0이어도 스레드가 먼저 끝나면 곧바로 409다
    gate = threading.Event()

    def refuse(rid: str):
        gate.wait(10)
        raise DomainError("장면 1 F02가 통합 데이터와 다르다", 409)

    proc._finish_sc01 = refuse  # type: ignore[method-assign]
    client = _client(proc, wait_s=0)
    first = client.post("/sc02/demo-runs", json={"executor": "embedded"})
    assert first.status_code == 202
    rid = first.json()["demoRunId"]
    gate.set()
    state = _until_done(client, rid)
    assert state["state"] == "failed" and state["status"] == 409
    assert "F02" in state["error"] and state["preparing"] is False
    # 기다리는 안에 실패하면 그 상태 코드 그대로다
    sync = _client(proc, wait_s=10).post(
        "/sc02/demo-runs", json={"sc01DemoRunId": rid, "executor": "embedded"}
    )
    assert sync.status_code == 409


def test_unknown_case_is_refused_before_creating_anything() -> None:
    proc = _proc()
    r = _client(proc, wait_s=0).post("/sc02/demo-runs", json={"caseId": "NOPE"})
    assert r.status_code == 422
    assert proc.sc01.store.load("anything") is None


def test_preparation_unknown_to_this_engine_is_404() -> None:
    r = _client(_proc(), wait_s=0).get("/sc02/demo-runs/demo-nope/preparation")
    assert r.status_code == 404
