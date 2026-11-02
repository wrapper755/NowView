"""
C15 일꾼(`app/consumer.py`) — Center가 NowView를 부르지 않고 일감을 쌓아 두면 엔진이 가져간다
(Chaeksas ADR-0102).

* **manifest ↔ 그림** — 일꾼이 Center에 올리는 작업 목록이 여섯 장면 그림의 서비스 호출을 다
  덮는다. 빠지면 Center가 올리기를 422 `operation_not_found`로 막는다.
* **가짜 Center와 한 바퀴** — 승인 없는 일꾼(Chaeksas ADR-0121): 환경의 토큰으로 바로
  manifest 올리기 → 가져가기 → `complete`/`fail`. 들이기(요청 코드)를 부르지 않는다. 실행
  위치는 일감의 `origin`이고 거절 사유가 `fail` 글로 간다. 토큰이 없으면 뜨지 않고 사유를 남긴다.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time

import httpx
import pytest
from chaeksas.contracts.bpmn_ext import read_process
from chaeksas.service_kit import TokenFile

from app.consumer import ConsumerHost, manifest_of, scene_service
from app.sc01.process import PROCESS_PATH as SC01_PATH
from app.sc01.process import Sc01Process
from app.sc01.store import SqliteSc01Store
from app.sc02.process import PROCESS_PATH as SC02_PATH
from app.sc03.process import PROCESS_PATH as SC03_PATH
from app.sc04.process import PROCESS_PATH as SC04_PATH
from app.sc05.process import PROCESS_PATH as SC05_PATH
from app.sc06.process import PROCESS_PATH as SC06_PATH

DRAWINGS = {
    "external": [SC01_PATH, SC02_PATH, SC03_PATH, SC04_PATH],
    "nowview-sc05": [SC05_PATH],
    "nowview-sc06": [SC06_PATH],
}


@pytest.mark.parametrize("topic", sorted(DRAWINGS))
def test_manifest_covers_every_service_call_of_the_drawings(topic: str) -> None:
    """그림의 서비스 호출마다 manifest에 그 작업이 있고, 그림이 넘기는 입력이 필수 입력을 덮는다."""
    manifest = manifest_of(topic)
    assert manifest.app_id == topic
    for path in DRAWINGS[topic]:
        process = read_process(path.read_bytes())
        for node in process.of_kind("serviceTask"):
            call = node.prop("serviceCall")
            assert call.app_id == topic, node.id
            op = manifest.operation(call.operation)
            assert op is not None and op.supports("deterministic"), (node.id, call.operation)
            # 그림이 꺼내는 출력이 manifest에 있다 — 없으면 변수가 비어 다음 노드가 틀린다
            produced = set((op.output_schema or {}).get("properties") or {})
            assert set(call.output.values()) <= produced, (
                node.id,
                set(call.output.values()) - produced,
            )
            required = set((op.input_schema or {}).get("required") or [])
            assert required <= set(call.input), (node.id, required - set(call.input))
            # 일감에서 데모 실행을 찾는 열쇠 — 그림이 늘 싣는다
            assert "demo_run_id" in call.input, node.id


# ─────────────────────────── 가짜 Center
# ───────────────────────────

TOKEN = "consumer-token-0123456789"
RUN = "run_20270616_090000_c3c3c3"


class FakeCenter:
    """C15의 일꾼 쪽 엔드포인트만 — manifest·가져가기·끝내기. 들이기 요청은 세기만 한다."""

    def __init__(self) -> None:
        self.enroll_calls = 0
        self.extensions: list[tuple[str, str]] = []
        self.manifests: list[str] = []
        self.queue: list[dict] = []
        self.finished: dict[str, tuple[str, dict]] = {}
        self.done = threading.Event()

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/api/v1/consumers/enroll"):
            self.enroll_calls += 1
            return httpx.Response(404, json={"code": "not_found", "message": path, "detail": {}})
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"code": "token_invalid", "message": "", "detail": {}})
        if path == "/api/v1/consumers/self/extension":
            definition = json.loads(request.content)["definition"]
            self.extensions.append((definition["id"], definition["version"]))
            return httpx.Response(201, json={})
        if path == "/api/v1/consumers/self/manifest":
            self.manifests.append(json.loads(request.content)["app_id"])
            return httpx.Response(200, json={})
        if path == "/api/v1/consumers/fetch":
            asked = json.loads(request.content)
            tasks = [t for t in self.queue if t["topic"] in asked["topics"]][: asked["max_tasks"]]
            self.queue = [t for t in self.queue if t not in tasks]
            if not tasks:
                time.sleep(0.02)  # 롱폴링 대신 — 빈 바퀴가 CPU를 태우지 않게
            return httpx.Response(200, json={"tasks": tasks})
        found = re.fullmatch(r"/api/v1/consumers/tasks/(\w+)/(complete|fail)", path)
        if found:
            self.finished[found.group(1)] = (found.group(2), json.loads(request.content))
            self.done.set()
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"code": "not_found", "message": path, "detail": {}})

    def put(self, task_id: str, operation: str, origin: str, run: str, **input) -> None:
        self.done.clear()
        self.queue.append(
            {
                "task_id": task_id,
                "topic": "external",
                "operation": operation,
                "mode": "deterministic",
                "origin": origin,
                "idempotency": {
                    "run_id": run,
                    "node_id": "Task_Validate",
                    "node_instance": 1,
                    "attempt": 1,
                    "call_seq": 1,
                },
                "caller": {"type": "studio", "host": "t", "bpm_process_id": "company1.sc01"},
                "input": input,
                "lock_until": "2099-01-01T00:00:00Z",
                "deadline": "2099-01-01T00:00:00Z",
            }
        )

    def wait(self, task_id: str) -> tuple[str, dict]:
        deadline = time.monotonic() + 5
        while task_id not in self.finished and time.monotonic() < deadline:
            self.done.wait(0.05)
        return self.finished[task_id]


def _until(check, seconds: float = 5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        found = check()
        if found:
            return found
        time.sleep(0.02)
    raise AssertionError("기다린 상태가 오지 않았다")


@pytest.fixture
def proc(tmp_path) -> Sc01Process:
    db = sqlite3.connect(str(tmp_path / "sc01.sqlite"), check_same_thread=False)
    return Sc01Process(SqliteSc01Store(db), inline_agent=True)


def test_consumer_takes_tasks_with_its_token_and_reports_reasons(proc: Sc01Process) -> None:
    """
    승인 없는 일꾼 — 환경의 토큰으로 들이기 없이 manifest를 올리고 일감을 가져간다. Studio 일감
    (`origin: test`)이 Studio 데모 실행을 묶고, 서버 실행 일감(`run`)은 사유와 함께 `fail`이다.
    """
    center = FakeCenter()
    host = ConsumerHost(
        center_url="http://center",
        services=[scene_service("external", proc)],
        tokens=TokenFile(path=None, env_value=TOKEN),
        client=httpx.Client(base_url="http://center", transport=httpx.MockTransport(center.handle)),
    )
    host.start()
    try:
        _until(lambda: host.describe()["state"] == "running")
        _until(lambda: center.manifests == ["external"])
        # 확장 정의는 manifest보다 먼저, 일꾼 토큰으로 올린다 — 콘솔 등록·들이기가 없다
        assert center.extensions == [("external", "0.4.0")]
        assert center.enroll_calls == 0

        rid = proc.create(executor="studio")["demo_run_id"]
        sid = proc.receive(rid, "CP02", actor="u-sales")["sources"]["SRC02"]["source_id"]
        center.put("xt_1", "validate_customer_plan", "test", RUN, demo_run_id=rid, source_id=sid)
        verdict, body = center.wait("xt_1")
        assert verdict == "complete", body
        assert body["output"] == {"passed": True, "error_count": 0}
        doc = proc.get(rid)
        assert doc["bpm"]["external_run_id"] == RUN

        other = proc.create(executor="studio")["demo_run_id"]
        proc.receive(other, "CP02", actor="u-sales")
        # 다른 실행의 일감 — 같은 멱등 칸에 다른 본문이면 일꾼이 `idempotency_conflict`로 막는다
        center.put(
            "xt_2",
            "validate_customer_plan",
            "run",
            "run_20270616_091500_d4d4d4",
            demo_run_id=other,
            source_id="SRC02",
        )
        verdict, body = center.wait("xt_2")
        assert verdict == "fail"
        assert body["code"] == "conflict" and body["retryable"] is False
        assert "Center 서버 실행에서 왔는데" in body["message"]
        assert proc.get(other)["bpm"]["external_run_id"] is None
    finally:
        host.stop()


def test_consumer_stays_off_without_a_center(proc: Sc01Process) -> None:
    """Center 주소가 없으면 뜨지 않는다 — 내장 시험·로컬 화면만 쓸 때."""
    host = ConsumerHost(
        center_url=None,
        services=[scene_service("external", proc)],
        tokens=TokenFile(path=None, env_value=TOKEN),
    )
    host.start()
    assert host.describe()["state"] == "off"


def test_consumer_stays_off_without_a_token(proc: Sc01Process) -> None:
    """토큰이 없으면 들이기를 청하지 않고 꺼진 채 사유를 남긴다 — 승인 대기는 없다."""
    host = ConsumerHost(
        center_url="http://center",
        services=[scene_service("external", proc)],
        tokens=TokenFile(path=None, env_value=None),
    )
    host.start()
    found = host.describe()
    assert found["state"] == "off" and "app.worker_file" in found["problem"]


def test_worker_file(tmp_path, monkeypatch) -> None:
    """
    설치가 Center 키 셋(일꾼·연동용·대리 답용)을 짓고 Center 폴더(ADR-0122)에 **해시만** 쓴다.
    원문은 엔진의 보관 파일(0600)에만 있고 엔진은 거기서 읽는다 — 환경 변수가 있으면 그것이
    이긴다. 다시 돌려도 키는 그대로이고 `--rotate`만 바꾼다.
    """
    import hashlib

    from app.config import default_config
    from app.worker_file import center_key, ensure_keys, load_keys, write_folder

    store = tmp_path / "secret" / "keys.json"
    monkeypatch.setenv("NOWVIEW_CONSUMER_DIR", str(store.parent))
    for name in ("WORKER_CONSUMER_TOKEN", "CHAEKSAS_INTEGRATION_KEY", "CHAEKSAS_RELAY_KEY"):
        monkeypatch.delenv(name, raising=False)
    keys = ensure_keys()
    assert set(keys) == {"worker", "integration", "relay"} and len(set(keys.values())) == 3
    for token in keys.values():
        assert token.startswith("chk_ctr_") and len(token) == len("chk_ctr_") + 40
    assert store.stat().st_mode & 0o777 == 0o600
    assert ensure_keys() == keys and load_keys() == keys
    assert center_key("relay") == keys["relay"]
    monkeypatch.setenv("CHAEKSAS_RELAY_KEY", "from-env")
    assert center_key("relay") == "from-env"
    assert ensure_keys(rotate=True)["worker"] != keys["worker"]
    keys = load_keys()

    folder = tmp_path / "consumers"
    topics = list(default_config().topics)
    assert topics == ["external"]
    paths = write_folder(folder, keys, topics)
    sha = {kind: hashlib.sha256(token.encode()).hexdigest() for kind, token in keys.items()}
    assert {p.name for p in paths} == {
        "worker.consumer.json", "nowview-integration.key.json", "nowview-relay.key.json"
    }
    assert json.loads((folder / "worker.consumer.json").read_text("utf-8")) == {
        "name": "worker", "topics": ["external"], "token_sha256": sha["worker"],
    }
    for kind in ("integration", "relay"):
        assert json.loads((folder / f"nowview-{kind}.key.json").read_text("utf-8")) == {
            "name": f"nowview-{kind}", "type": kind, "token_sha256": sha[kind],
        }
    written = "".join(p.read_text("utf-8") for p in paths)
    assert not any(token in written for token in keys.values())
