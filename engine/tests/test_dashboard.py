"""
회사 대시보드(`GET /companies/{회사}/dashboard`, `app/dashboard.py`).

장면 1~7 기본 시연을 끝까지 돌린 뒤 업무마다 BPM 진행·핵심 지표가 통합가상데이터의 숫자와 같은지
본다 — 지표는 회사에 적는 경영 기록에서 고른다(사이트와 같은 숫자). 세계는 엔진이 따라가는 것만
보이고, 일꾼 일감은 회사 시스템의 일감 기록에서 그 장면 것만 센다.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from records_chain import chain

from app import dashboard
from app.companies import Settings, build_router
from app.company import CompanyUnavailable
from app.config import ConfigStore
from app.sc07 import demo
from app.store import build_sqlite_backend


@pytest.fixture(scope="module")
def played():
    """장면 7까지 끝낸 데모 실행 — 장면 7을 열면 앞 장면을 각본으로 끝까지 돈다."""
    p7 = chain(7)
    rid = p7.create(executor="embedded")["demo_run_id"]
    for i in range(len(demo.steps_for())):
        demo.run_step(p7, rid, i)
    procs = {7: p7}
    for n in range(7, 1, -1):
        procs[n - 1] = getattr(procs[n], f"sc0{n - 1}")
    return procs, rid


def _metrics(procs, rid: str, scene: int) -> dict[str, str | None]:
    doc = procs[scene].store.load(rid)[0]
    return {m["label"]: m["value"] for m in dashboard.work(scene, procs[scene], doc)["metrics"]}


def test_metrics_are_the_rule_results(played) -> None:
    procs, rid = played
    assert _metrics(procs, rid, 1) == {
        "연간 공장관리손익 (F02)": "3309351000",
        "목표 대비": "-167939000",
        "이번 사건 영향": "-14000000",
    }
    assert _metrics(procs, rid, 2) == {"12개월 원가 증가": "18817440", "협상 감소": "12544960"}
    assert _metrics(procs, rid, 3) == {
        "통합 손익 (연간)": "3299986680",
        "목표 대비 부족": "177303320",
    }
    assert _metrics(procs, rid, 4) == {"개선 효과 (연간)": "127800000", "남는 부족": "49503320"}
    assert _metrics(procs, rid, 5) == {"전망 손익 (연간)": "3428986680", "남는 부족": "48303320"}
    assert _metrics(procs, rid, 6) == {
        "Q4 기대 효과": "91800000",
        "확인 효과": "87000000",
        "차이": "-4800000",
    }
    assert _metrics(procs, rid, 7) == {"적용 상태": "운영 설정 반영 확인"}


def test_progress_counts_approvals_of_the_drawing(played) -> None:
    procs, rid = played
    for scene, proc in procs.items():
        work = dashboard.work(scene, proc, proc.store.load(rid)[0])
        assert work["state"] == "done", scene
        assert work["waiting"] == []
        progress = work["progress"]
        # 갈래가 있는 그림(장면 2·7의 종료 여럿)은 기본 시연이 모든 결재를 지나지 않는다
        assert 0 < progress["passed"] <= progress["approvals"], scene
    assert dashboard.work(6, procs[6], None) == {
        "scene": 6,
        "work": "완료·성과 검토",
        "state": "none",
        "clock": None,
        "progress": None,
        "waiting": [],
        "metrics": [],
    }


def test_worker_entries_are_per_scene_newest_first() -> None:
    rows = [
        {"scene": 1, "operation": "assess_supply_risk", "ok": True, "reason": None, "at": "a"},
        {"scene": 2, "operation": "screen_price_request", "ok": True, "reason": None, "at": "b"},
        {"scene": 1, "operation": "record_plan_review", "ok": False, "reason": "거절", "at": "c"},
    ]
    assert dashboard.worker_entries(rows, 1) == {
        "count": 2,
        "failed": 1,
        "recent": [
            {"at": "c", "operation": "record_plan_review", "ok": False, "reason": "거절"},
            {"at": "a", "operation": "assess_supply_risk", "ok": True, "reason": None},
        ],
    }


class _System:
    def __init__(self, worlds, log=None, down: bool = False) -> None:
        self._worlds, self._log, self._down = worlds, log or [], down

    def worlds(self):
        if self._down:
            raise CompanyUnavailable("회사 시스템에 닿지 않는다")
        return self._worlds

    def worker_log_entries(self, world_id: str):
        return [r for r in self._log if r["world"] == world_id]


def _client(tmp_path, system, procs) -> TestClient:
    settings = Settings(ConfigStore(build_sqlite_backend(str(tmp_path / "engine.sqlite"))))
    app = FastAPI()
    app.include_router(build_router(settings, None, None, None, {"company1": system}, procs))
    return TestClient(app)


def test_dashboard_shows_followed_worlds_and_the_scene_log(played, tmp_path) -> None:
    procs, rid = played
    worlds = [
        {"world_id": "demo-old", "origin": "engine", "generation": 1, "reset_at": None},
        {"world_id": rid, "origin": "site", "generation": 1, "reset_at": "2026-11-03T13:38+09:00"},
        # 이 엔진이 따라가지 않는 세계(다른 엔진의 것) — 보이지 않는다
        {"world_id": "demo-elsewhere", "case_id": "BASE", "generation": 1, "clock": None},
    ]
    log = [{"world": rid, "scene": 3, "operation": "open_profit_review", "ok": True, "at": "x"}]
    procs[1].create(demo_run_id="demo-old")  # 엔진이 따라가지만 사이트가 만들지 않은 예전 세계
    client = _client(tmp_path, _System(worlds, log), procs)
    body = client.get("/companies/company1/dashboard").json()
    # 사이트가 만든 세계가 앞이다(회사 시스템은 id 순서로 준다)
    assert [w["worldId"] for w in body["worlds"]] == [rid, "demo-old"]
    assert body["world"] == rid and body["problem"] is None
    assert body["company"]["id"] == "company1" and "siteUrl" in body["company"]
    assert [w["scene"] for w in body["works"]] == [1, 2, 3, 4, 5, 6, 7]
    assert [w["worker"]["count"] for w in body["works"]] == [0, 0, 1, 0, 0, 0, 0]
    # 따라가지 않는 세계를 고르면 사유와 함께 맨 앞 세계다
    other = client.get("/companies/company1/dashboard", params={"world": "demo-elsewhere"}).json()
    assert other["world"] == rid and "따라가는 세계가 아니다" in other["problem"]
    assert client.get("/companies/nope/dashboard").status_code == 404


def test_dashboard_without_the_company_system_says_why(played, tmp_path) -> None:
    procs, _ = played
    body = _client(tmp_path, _System([], down=True), procs).get("/companies/company1/dashboard")
    assert body.status_code == 200
    data = body.json()
    assert data["worlds"] == [] and data["world"] is None
    assert "닿지 않는다" in data["problem"]
    assert all(w["state"] == "none" for w in data["works"])
