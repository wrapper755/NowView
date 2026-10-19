"""
HTTP 경계의 계약 — **생성은 즉시 돌아오고 진행은 배경에서 한다.**

다른 테스트들은 `InstanceStore`와 그래프를 직접 쓴다. 여기서만 엔드포인트를 거치는데,
운영에서 터진 것이 바로 그 경계였기 때문이다(CLAUDE.md 5.4): LLM 모드의 생성이 요청
안에서 Agent 3개를 돌려 120초를 넘고, Cloudflare가 약 100초에 끊어 **524 + 고아
인스턴스**가 됐다. 엔진은 끝까지 돌아 인스턴스를 남기는데 클라이언트가 id를 못 받는다.

**`TestClient`는 배경 작업이 끝난 뒤에 반환한다.** 그래서 "생성이 배경을 기다리지
않는다"는 응답 **본문**으로 확인한다 — 본문은 배경이 돌기 전에 만들어진 것이라
`status`가 `created`이고 `runs`가 비어 있다. 진행 결과는 그 다음 조회로 본다.
"""

from __future__ import annotations

import pytest
from conftest import spec_with
from fastapi.testclient import TestClient

from app import main
from app.agents import AgentContractError, make_runner
from app.instances import InstanceStore, snapshot
from app.store import build_sqlite_backend


@pytest.fixture
def client(tmp_path, monkeypatch):
    """
    앱의 모듈 전역 store를 격리된 파일 SQLite로 갈아 끼운다.

    `:memory:`는 쓸 수 없다 — 배경 작업이 **다른 스레드**에서 돌고 in-memory DB는
    연결마다 따로이므로 진행 결과가 보이지 않는다.
    """
    backend = build_sqlite_backend(str(tmp_path / "api.sqlite"))
    monkeypatch.setattr(
        main,
        "store",
        InstanceStore(backend, runner_factory=lambda mode: make_runner(mode)),
    )
    try:
        # 컨텍스트 매니저로 써야 startup이 돈다 — 알림 허브가 루프를 잡는 지점이다.
        with TestClient(main.app) as c:
            yield c
    finally:
        backend.close()


def _create(client, *, cross_functional: bool = True, **extra):
    body = {
        "spec": spec_with(cross_functional).model_dump(mode="json"),
        "agentMode": "mock",
        **extra,
    }
    response = client.post("/instances", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_returns_before_advancing(client):
    """
    **응답에 Agent 산출물이 없다.** 있으면 요청이 진행을 기다렸다는 뜻이고, 그러면
    LLM 모드에서 다시 프록시 타임아웃에 걸린다.
    """
    created = _create(client)

    assert created["status"] == "created"
    assert created["runs"] == []
    assert created["pendingApproval"] is None
    # id는 즉시 온다 — 이것이 고아를 막는 핵심이다. 화면이 여기에 붙어 놓고 SSE로 받는다.
    assert created["instanceId"].startswith("inst-")


def test_background_advance_reaches_first_human_wait(client):
    """생성 요청이 기다리지 않았을 뿐, 진행은 실제로 끝까지 간다."""
    instance_id = _create(client)["instanceId"]

    after = client.get(f"/instances/{instance_id}").json()

    assert after["status"] == "waiting"
    assert after["pendingApproval"]["nodeId"] == "review"
    assert after["failure"] is None
    # 배경이 정말로 Agent를 돌렸다 — 응답 시점에는 비어 있던 것이다.
    assert [run["nodeId"] for run in after["runs"]] == ["sensing", "rca", "simulate"]


def test_advance_false_creates_without_running(client):
    """`advance: false`면 아무것도 돌지 않는다 — 진행 지점이 생기지 않는다."""
    instance_id = _create(client, advance=False)["instanceId"]

    after = client.get(f"/instances/{instance_id}").json()

    assert after["status"] == "created"
    assert after["runs"] == []


def test_resume_before_first_wait_is_409(client):
    """
    배경 진행이 끝나기 전에 재개를 부르면 멈춰 있지 않으므로 409다.

    `advance: false`로 그 상태를 재현한다. **`advance: false`만으로는 524를 고칠 수
    없다는 근거이기도 하다** — 진행시킬 경로가 없다.
    """
    instance_id = _create(client, advance=False)["instanceId"]

    response = client.post(f"/instances/{instance_id}/resume", json={"payload": {}})

    assert response.status_code == 409


def test_progress_notifications_never_report_done_while_running(client, monkeypatch):
    """
    **노드마다 알리는 동안 `done`이 새어 나가면 안 된다.**

    노드 사이에서는 체크포인트의 `next`가 비어 있어 스냅샷이 `done`으로 파생된다.
    운영에서 실제로 SSE가 중간에 `status=done`을 한 번 보냈고 그래프는 계속 돌고
    있었다 — 화면은 그것을 "종료"로 읽는다.

    알림이 나갈 때마다 그 순간의 스냅샷을 모아 두고, 마지막 하나(진행이 끝난 뒤의
    것)를 뺀 전부가 `done`이 아님을 본다.
    """
    seen: list[str] = []
    real_publish = main.notifier.publish

    def spy(instance_id: str) -> None:
        try:
            seen.append(snapshot(main.store.get(instance_id))["status"])
        except KeyError:
            pass
        real_publish(instance_id)

    monkeypatch.setattr(main.notifier, "publish", spy)

    created = _create(client)
    final = client.get(f"/instances/{created['instanceId']}").json()

    assert final["status"] == "waiting", final["status"]
    # 진행 중에 관찰된 상태에 `done`이 없다. `created`·`running`만 나와야 한다.
    assert seen, "알림이 한 번도 나가지 않았다 — 스파이가 안 걸렸다"
    assert "done" not in seen, seen
    assert set(seen) <= {"created", "running", "waiting"}, seen


def test_background_failure_is_reported_on_snapshot(client, monkeypatch):
    """
    **배경 실패를 조용히 넘기지 않는다.**

    응답이 이미 끝났으니 502를 던질 곳이 없다. 인스턴스에 남기지 않으면 화면은
    진행 중인 인스턴스와 구분할 수 없어 영원히 기다린다.
    """

    class Failing:
        def run(self, *args, **kwargs):
            raise AgentContractError("Agent가 스키마를 지키지 않았다 (테스트)")

    monkeypatch.setattr(main.store, "_runner_factory", lambda mode: Failing())

    # 생성 자체는 성공한다 — 실패는 배경에서 일어난다.
    created = _create(client)
    after = client.get(f"/instances/{created['instanceId']}").json()

    assert after["failure"] is not None
    assert "스키마" in after["failure"]
    # 사람 대기에 닿지 못했다 — 실패를 대기로 위장하지 않는다.
    assert after["pendingApproval"] is None
    assert after["status"] != "waiting"
