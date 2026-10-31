"""
테스트 고정물 — 두 저장 백엔드를 고르는 규칙, 같은 프로세스의 회사 시스템.

**회사 시스템은 진짜 시뮬레이터다**(`company-sim/`, 2026-10-31). 엔진의 회사 자료·원천 수신·원천
상태 쓰기는 회사 시스템 API를 지난다(`app/company.py`) — 시험은 시뮬레이터 앱을 같은 프로세스에 띄워
HTTP 대신 ASGI로 붙인다. 세계는 데모 실행 id라 시험끼리 섞이지 않는다.

**`REQUIRE_POSTGRES`가 켜져 있으면 건너뛰지 않고 실패한다.** CI에서 환경 변수 이름을
오타내면 Postgres 테스트가 전부 skip되는데, 초록색 체크만 보고는 "검증했다"와
"건너뛰었다"를 구분할 수 없다. 조용한 미검증이 가장 나쁘다.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def company_system(tmp_path_factory):
    """회사 시스템 시뮬레이터를 한 번 띄워 엔진의 기본 회사 클라이언트로 끼운다."""
    from autoparts_sim.main import build_app
    from autoparts_sim.store import WorldStore
    from fastapi.testclient import TestClient

    from app import company

    previous = os.environ.get("AUTOPARTS_SIM_AUTH")
    os.environ["AUTOPARTS_SIM_AUTH"] = "off"
    sim = build_app(WorldStore(tmp_path_factory.mktemp("company") / "sim.sqlite"))
    client = company.CompanyClient("http://autoparts-sim", client=TestClient(sim))
    company._override = client
    yield client
    company._override = None
    if previous is None:
        os.environ.pop("AUTOPARTS_SIM_AUTH", None)
    else:
        os.environ["AUTOPARTS_SIM_AUTH"] = previous


def postgres_url() -> str | None:
    return os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


def require_postgres() -> str:
    """Postgres URL을 돌려주거나, 없으면 건너뛴다(REQUIRE_POSTGRES면 실패)."""
    url = postgres_url()
    if url:
        return url
    if os.getenv("REQUIRE_POSTGRES"):
        pytest.fail("REQUIRE_POSTGRES가 켜져 있는데 TEST_DATABASE_URL이 없다")
    pytest.skip("TEST_DATABASE_URL이 없다 (Postgres 백엔드 검증 생략)")


class C15Calls:
    """
    Center 외부 작업(C15)의 흉내 — 서비스 태스크 호출(`OpCall`)을 일감(`LockedTask`)으로 바꿔
    **NowView 일꾼의 그 수행기**(`app.consumer.scene_service`)에 넣고, 결과를 부르는 쪽
    (`CenterServiceCaller`)처럼 돌려준다. `origin`은 `run`(서버 실행기) 또는 `test`(Studio)다 —
    Center가 올린 쪽을 인증해 붙이는 값이고, 일꾼은 그것으로 실행 위치를 가른다.
    """

    def __init__(self, process, *, origin: str = "run") -> None:
        self.process = process
        self.origin = origin
        self.services: dict = {}  # 토픽마다 하나 — 멱등 저장소가 일꾼처럼 이어진다

    def call(self, request):
        from chaeksas.contracts.external_task import LockedTask
        from chaeksas.core.services import OpOutcome, ServiceCallError

        task = LockedTask.model_validate(
            {
                "task_id": f"xt_{request.node_id}_{request.node_instance}_{request.attempt}",
                "topic": request.app_id,
                "operation": request.operation,
                "mode": request.mode,
                "origin": self.origin,
                "idempotency": {
                    "run_id": request.run_id,
                    "node_id": request.node_id,
                    "node_instance": request.node_instance,
                    "attempt": request.attempt,
                    "call_seq": request.call_seq,
                },
                "caller": {
                    "type": "studio" if self.origin == "test" else "server_runner",
                    "host": "test",
                    "bpm_process_id": request.bpm_process_id or "nowview",
                    "version": request.version or "0.0.0",
                },
                "input": dict(request.input),
                "lock_until": "2099-01-01T00:00:00Z",
                "deadline": "2099-01-01T00:00:00Z",
            }
        )
        from app.consumer import scene_service

        if request.app_id not in self.services:
            self.services[request.app_id] = scene_service(request.app_id, self.process)
        outcome = self.services[request.app_id].execute(task)
        if outcome.ok:
            from chaeksas.contracts.external_task import missing_outputs

            # Center가 `complete`에서 보는 것 — manifest의 필수 출력이 빠지면 422 `output_invalid`
            op = self.services[request.app_id].manifest.operation(request.operation)
            missing = missing_outputs(op, outcome.response.output)
            assert not missing, (request.operation, missing)
            return OpOutcome(output=dict(outcome.response.output))
        raise ServiceCallError(outcome.message, code=outcome.code, retryable=outcome.retryable)
