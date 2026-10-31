"""
C15 일꾼(`app/consumer.py`) — Center가 NowView를 부르지 않고 일감을 쌓아 두면 엔진이 가져간다
(Chaeksas ADR-0102).

* **manifest ↔ 그림** — 일꾼이 Center에 올리는 작업 목록이 여섯 장면 그림의 서비스 호출을 다
  덮는다. 빠지면 Center가 올리기를 422 `operation_not_found`로 막는다.
* **가짜 Center와 한 바퀴** — 들이기 요청(요청 코드) → 관리자 승인(봉한 토큰) → manifest 올리기 →
  가져가기 → `complete`/`fail`. 실행 위치는 일감의 `origin`이고 거절 사유가 `fail` 글로 간다.
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
from chaeksas.contracts.enrollment import request_code, seal
from chaeksas.service_kit import TokenFile

from app.consumer import ConsumerHost, manifest_of, scene_service
from app.sc01.process import INTAKE_PATH, Sc01Process
from app.sc01.process import PROCESS_PATH as SC01_PATH
from app.sc01.store import SqliteSc01Store
from app.sc02.process import PROCESS_PATH as SC02_PATH
from app.sc03.process import PROCESS_PATH as SC03_PATH
from app.sc04.process import PROCESS_PATH as SC04_PATH
from app.sc05.process import PROCESS_PATH as SC05_PATH
from app.sc06.process import PROCESS_PATH as SC06_PATH

DRAWINGS = {
    "nowview": [SC01_PATH, INTAKE_PATH],
    "nowview-sc02": [SC02_PATH],
    "nowview-sc03": [SC03_PATH],
    "nowview-sc04": [SC04_PATH],
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
ENROLLMENT = "enr_" + "a" * 32
RUN = "run_20270616_090000_c3c3c3"


class FakeCenter:
    """C15의 일꾼 쪽 엔드포인트만 — 들이기·manifest·가져가기·끝내기."""

    def __init__(self) -> None:
        self.public_key: str | None = None
        self.enrolled: dict | None = None
        self.approved = False
        self.manifests: list[str] = []
        self.queue: list[dict] = []
        self.finished: dict[str, tuple[str, dict]] = {}
        self.done = threading.Event()

    def code(self) -> str:
        assert self.public_key
        return request_code(self.public_key, ENROLLMENT)

    def status(self) -> dict:
        body = {
            "enrollment_id": ENROLLMENT,
            "state": "approved" if self.approved else "pending",
            "code": self.code(),
            "expires_at": "2099-01-01T00:00:00Z",
        }
        if self.approved:
            sealed = seal(self.public_key, TOKEN, salt=ENROLLMENT)
            body["sealed_key"] = sealed.to_json_dict()
        return body

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/consumers/enroll":
            self.enrolled = json.loads(request.content)
            self.public_key = self.enrolled["public_key"]
            return httpx.Response(200, json=self.status())
        if path == f"/api/v1/consumers/enroll/{ENROLLMENT}":
            return httpx.Response(200, json=self.status())
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"code": "token_invalid", "message": "", "detail": {}})
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
                "topic": "nowview",
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
                "caller": {"type": "studio", "host": "t", "bpm_process_id": "autoparts.sc01"},
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


def test_consumer_enrolls_then_takes_tasks_and_reports_reasons(proc: Sc01Process, tmp_path) -> None:
    """
    처음에는 토큰이 없어 들이기를 청하고 요청 코드를 `/health`에 보인다 — 관리자가 같은 코드를
    승인하면 봉한 토큰을 열어 파일에 두고, manifest를 올리고, 일감을 가져간다. Studio 일감
    (`origin: test`)이 Studio 데모 실행을 묶고, 서버 실행 일감(`run`)은 사유와 함께 `fail`이다.
    """
    center = FakeCenter()
    host = ConsumerHost(
        center_url="http://center",
        services=[scene_service("nowview", proc)],
        tokens=TokenFile(path=tmp_path / "consumer" / "consumer-token.json"),
        client=httpx.Client(base_url="http://center", transport=httpx.MockTransport(center.handle)),
        enroll_every_s=0.05,
    )
    host.start()
    try:
        code = _until(lambda: host.describe()["requestCode"] or host.describe()["problem"])
        assert code == center.code() and host.describe()["state"] == "enrolling"
        assert center.enrolled["topics"] == ["nowview"]
        center.approved = True
        _until(lambda: host.describe()["state"] == "running")
        assert host.tokens.token() == TOKEN  # 원문은 토큰 파일에만 있다
        _until(lambda: center.manifests == ["nowview"])

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


def test_consumer_stays_off_without_a_center(proc: Sc01Process, tmp_path) -> None:
    """Center 주소가 없으면 뜨지 않는다 — 내장 시험·로컬 화면만 쓸 때."""
    host = ConsumerHost(
        center_url=None,
        services=[scene_service("nowview", proc)],
        tokens=TokenFile(path=tmp_path / "t.json"),
    )
    host.start()
    assert host.describe()["state"] == "off"
