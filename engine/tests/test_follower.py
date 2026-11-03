"""
세계 따라가기(`app.follower`) — 회사 사이트가 기간계에 세계·시계·원천·명령을 남기고 NowView 일꾼이
따라간다(`docs/role-split.md` §5). 여기서는 사이트 대신 기간계 쌍둥이를 직접 부른다.

* 처음 보는 세계 → 그 id로 장면 1 데모 실행(사례·회차). 다시 돌아도 그대로다.
* 시각은 읽기만 한다 — 문서가 세계 시각을 따라가고, 엔진은 기간계 시계를 쓰지 않는다.
* 수신함의 원천은 한 번만 들인다. 초기화 회차가 바뀌면 장면 1은 S0, 장면 2~7 문서는 지운다.
* 명령은 결과를 한 번 적는다 — 앞 장면이 끝나지 않은 장면 열기는 409, 모르는 명령은 422.
* 일감 전에 그 세계의 시각을 먼저 따라간다(`Synced`).
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest

from app.company import engine_drives
from app.follower import Follower, Synced
from app.sc01.domain import DomainError
from app.sc01.process import Sc01Process
from app.sc01.store import SqliteSc01Store
from app.sc02.process import Sc02Process
from app.sc03.process import Sc03Process
from app.sc04.process import Sc04Process
from app.sc05.process import Sc05Process
from app.sc06.process import Sc06Process
from app.sc07.process import Sc07Process


def _store(prefix: str) -> SqliteSc01Store:
    return SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), prefix)


@pytest.fixture
def site_drives(monkeypatch):
    """운영처럼 — 회사 사이트가 몬다(엔진은 기간계 시계를 쓰지 않는다)."""
    monkeypatch.delenv("NOWVIEW_TEST_INPUTS", raising=False)
    assert not engine_drives()


@pytest.fixture
def scenes(site_drives):
    publish = lambda _: None  # noqa: E731
    s1 = Sc01Process(_store("sc01"), inline_agent=True, publish=publish)
    s2 = Sc02Process(_store("sc02"), s1, publish=publish)
    s3 = Sc03Process(_store("sc03"), s2, publish=publish)
    s4 = Sc04Process(_store("sc04"), s3, publish=publish)
    s5 = Sc05Process(_store("sc05"), s4, publish=publish)
    s6 = Sc06Process(_store("sc06"), s5, publish=publish)
    s7 = Sc07Process(_store("sc07"), s6, publish=publish)
    return {1: s1, 2: s2, 3: s3, 4: s4, 5: s5, 6: s6, 7: s7}


@pytest.fixture
def world(company_system):
    """사이트가 기간계에 만든 세계 — 쌍둥이를 직접 부른다."""
    rid = f"demo-{uuid.uuid4().hex[:8]}"
    company_system._call("POST", "/worlds", {"world_id": rid, "case_id": "BASE", "origin": "site"})
    return rid


def _follow(scenes, company, rid: str) -> Follower:
    """그 세계 하나만 따라간다(쌍둥이에는 다른 시험의 세계도 있다)."""
    f = Follower(company, scenes)
    summary = company.world(rid)
    f._follow(summary)
    return f


def test_new_world_becomes_a_demo_run_with_the_same_id(scenes, company_system, world) -> None:
    _follow(scenes, company_system, world)
    doc = scenes[1].get(world)
    assert doc["case_id"] == "BASE" and doc["world_generation"] == 1
    assert doc["bpm"]["executor"] == "center"
    # 다시 돌아도 새로 만들지 않는다
    _follow(scenes, company_system, world)
    assert scenes[1].store.history(world)[-1]["seq"] == 1


def test_clock_is_read_not_written(scenes, company_system, world) -> None:
    f = _follow(scenes, company_system, world)
    company_system._call("POST", f"/worlds/{world}/clock", {"at": "2027-06-16T10:00:00+09:00"})
    f._follow(company_system.world(world))
    assert scenes[1].get(world)["clock"] == "2027-06-16T10:00:00+09:00"
    # 엔진의 시각 쓰기는 기간계에 닿지 않는다 — 원본은 사이트가 옮긴 시각이다
    company_system.set_clock(world, "2027-06-20T10:00:00+09:00")
    assert company_system.world(world)["clock"] == "2027-06-16T10:00:00+09:00"
    # 뒤로 가는 세계 시각은 무시한다(문서는 뒤로 가지 않는다)
    company_system._call("POST", f"/worlds/{world}/clock", {"at": "2027-06-16T09:00:00+09:00"})
    f._follow(company_system.world(world))
    assert scenes[1].get(world)["clock"] == "2027-06-16T10:00:00+09:00"


def test_inbox_source_is_received_once(scenes, company_system, world) -> None:
    f = _follow(scenes, company_system, world)
    company_system._call("POST", f"/worlds/{world}/clock", {"at": "2027-06-16T09:00:00+09:00"})
    company_system._call("POST", f"/worlds/{world}/sim/customer-plans", {"fixture_id": "CP02"})
    f._follow(company_system.world(world))
    doc = scenes[1].get(world)
    (source,) = doc["sources"].values()
    assert source["company_doc_id"] == "DOC-0001" and source["received_at"].startswith("2027-06-16")
    # 엔진이 다시 떠서 본 번호를 잊어도 같은 원천을 두 번 들이지 않는다
    Follower(company_system, scenes)._follow(company_system.world(world))
    assert len(scenes[1].get(world)["sources"]) == 1


def test_world_reset_restarts_the_demo_run(scenes, company_system, world) -> None:
    f = _follow(scenes, company_system, world)
    company_system._call("POST", f"/worlds/{world}/sim/customer-plans", {"fixture_id": "CP02"})
    f._follow(company_system.world(world))
    # 장면 2 문서가 있었다고 치고(열려면 장면 1 인계가 필요하다) 지워지는지 본다
    scenes[2].store.insert(world, {"demo_run_id": world, "step": "D00", "clock": "2027-06-17"})
    company_system._call("POST", f"/worlds/{world}/reset", {"case_id": "EX08"})
    f._follow(company_system.world(world))
    doc = scenes[1].get(world)
    assert doc["world_generation"] == 2 and doc["case_id"] == "EX08" and doc["sources"] == {}
    assert scenes[2].store.load(world) is None


def test_commands_get_one_result(scenes, company_system, world) -> None:
    f = _follow(scenes, company_system, world)

    def post(scene: int, kind: str, body: dict | None = None) -> str:
        made = company_system._call(
            "POST",
            f"/worlds/{world}/commands",
            {"scene": scene, "kind": kind, "actor": "u-buy", "body": body or {}, "ref": kind},
        )
        return made["command_id"]

    opened = post(2, "open")
    unknown = post(2, "teleport")
    policy = post(4, "budget_policy", {"kind": "transfer"})
    f._follow(company_system.world(world))
    results = {c["command_id"]: c for c in company_system.commands(world, None)}
    assert results[opened]["state"] == "REJECTED" and results[opened]["status"] == 409
    assert "끝나지 않았다" in results[opened]["reason"]  # 앞 장면을 각본으로 끝내지 않는다
    assert results[unknown]["status"] == 422
    assert results[policy]["status"] == 404  # 장면 4가 열리지 않았다
    assert scenes[2].store.load(world) is None
    assert company_system.commands(world) == []  # 대기 명령이 남지 않는다


def test_operation_follows_the_world_clock_first(scenes, company_system, world) -> None:
    f = _follow(scenes, company_system, world)
    company_system._call("POST", f"/worlds/{world}/clock", {"at": "2027-06-16T11:00:00+09:00"})
    worker = Synced(scenes[1], f)
    with pytest.raises(DomainError):
        worker.operate(world, "no_such_operation", {}, external_run_id=None)
    assert scenes[1].get(world)["clock"] == "2027-06-16T11:00:00+09:00"


def test_operation_leaves_a_worker_log_with_its_approval(scenes, company_system, world) -> None:
    """기록 작업이 끝나면(성공·거절 모두) 그 결재와 일감 기록을 남긴다 — 자동 모드가 기다린다."""
    f = _follow(scenes, company_system, world)
    worker = Synced(scenes[1], f, 1)
    assert worker._approval_of["Record_Dispatch"] == "Approve_Dispatch"
    with pytest.raises(DomainError):
        worker.operate(
            world, "no_such_operation", {}, external_run_id="run_x", node_id="Record_Dispatch"
        )
    (entry,) = company_system._call("GET", f"/worlds/{world}/worker-log")
    assert entry["approval_node"] == "Approve_Dispatch" and entry["ok"] is False
    assert entry["run_id"] == "run_x" and entry["reason"]


def test_worlds_the_site_did_not_make_are_left_alone(scenes, company_system) -> None:
    """예전 엔진이 만든 세계·다른 엔진의 세계 — 같은 기간계를 써도 집지 않는다."""
    rid = f"demo-{uuid.uuid4().hex[:8]}"
    company_system._call("POST", "/worlds", {"world_id": rid})
    company_system._call("POST", f"/worlds/{rid}/sim/customer-plans", {"fixture_id": "CP02"})
    Follower(company_system, scenes)._follow(company_system.world(rid))
    assert scenes[1].store.load(rid) is None


def test_task_opens_at_the_time_of_the_record_before_it() -> None:
    """폴러가 결재를 늦게 읽어도 업무는 그 결재 앞 기록 작업의 처리 시각에 연다 — 결재마다."""
    from app.follower import PROGRESS_AT, sync_opened

    doc = {"demo_run_id": "demo-opened", "clock": "2027-06-16T11:30:00+09:00"}
    PROGRESS_AT["demo-opened"] = {
        "Record_Dispatch": "2027-06-16T11:00:00+09:00",
        "Record_Review": "2027-06-16T11:05:00+09:00",
    }
    before = {
        "apr_prod": ["Gw_Ops_Split", "Record_Dispatch", "Record_Sales"],
        "apr_fin": ["Record_Review", "Record_Dispatch"],
        "apr_new": ["Something_Else"],  # 모르는 노드뿐이면 지금 시각
    }
    seen: list[tuple[str, list[str]]] = []
    sync_opened(
        doc, ["apr_new", "apr_fin", "apr_prod"], before, lambda r: seen.append((doc["clock"], r))
    )
    assert seen == [
        ("2027-06-16T11:00:00+09:00", ["apr_prod"]),
        ("2027-06-16T11:05:00+09:00", ["apr_fin"]),
        ("2027-06-16T11:30:00+09:00", ["apr_new"]),
    ]
    assert doc["clock"] == "2027-06-16T11:30:00+09:00"
    PROGRESS_AT.pop("demo-opened")
