"""
장면 2(외주 단가 인상 검토)의 경영 기록 — 회사 시스템에 적는 판(`app/sc02/records.py`).

기본 시연 D00~D12 동안 적은 모든 판이 봉투·종류별 스키마(`docs/records/sc02/`)를 통과하고, 회사
기록이 엔진 문서와 같으며(사이트가 그것만으로 그린다), 회사가 받지 못하면 조작이 저장되지 않는다.
계약의 공통 몫은 `records_contract.py`.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from records_contract import check, every_version, example

from app.company import CompanyUnavailable
from app.sc01.process import Sc01Process
from app.sc01.store import SqliteSc01Store
from app.sc02 import demo
from app.sc02.process import Sc02Process
from app.sc02.records import KINDS, SCENE
from app.sc02.view import view


def _proc() -> Sc02Process:
    s1 = SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False))
    s2 = SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), "sc02")
    return Sc02Process(s2, Sc01Process(s1, inline_agent=True))


def _play(proc: Sc02Process, case: str) -> str:
    rid = proc.create(case_id=case)["demo_run_id"]
    for i in range(len(demo.steps_for(case))):
        demo.run_step(proc, rid, i)
    return rid


@pytest.fixture(scope="module")
def played() -> tuple[Sc02Process, str]:
    proc = _proc()
    return proc, _play(proc, "BASE")


def test_every_written_version_matches_the_schemas(played) -> None:
    proc, rid = played
    # 추가 협상지시(instruction)는 X01에만 있다 — 스키마는 두 시연의 판으로 본다
    x01 = _play(proc, "X01")
    versions = every_version(proc.company, rid, SCENE) + every_version(proc.company, x01, SCENE)
    assert len(versions) > 40
    assert check(SCENE, KINDS, versions) == []


def test_company_records_equal_the_engine_document(played) -> None:
    proc, rid = played
    latest = {r["kind"] + "/" + r["record_id"]: r for r in proc.company.records(rid, scene=SCENE)}
    assert latest["scene/SC02:SC02"]["state"] == "HANDED_OFF"
    # 본문은 화면 응답의 같은 칸 그대로다 — 사이트가 계산하지 않고 그린다
    v = json.loads(json.dumps(view(proc.get(rid)), ensure_ascii=False, default=str))
    run = next(r for r in v["runs"] if r["run_id"] == "RUN-APP01")
    assert latest["price_run/SC02:RUN-APP01"]["body"] == run
    assert latest["handoff/SC02:SC02"]["body"]["handoffCheck"] == v["handoffCheck"]
    assert latest["cost_version/SC02:C02-APP01"]["state"] == "REGISTERED_FUTURE"
    assert [d["body"]["step"] for d in proc.company.records(rid, kind="price_decision")] == [
        "TEAM",
        "EXEC",
        "CEO",
    ]
    assert latest["handoff/SC02:SC02"]["body"]["handoffCheck"]["met"] is True
    assert latest["issue/SC02:ISSUE-COST01"]["state"] == "OPEN"
    assert len(proc.company.records(rid, scene=SCENE, kind="task")) == 12
    assert example(proc.company, rid, SCENE) == []


def test_company_outage_keeps_the_operation_unsaved(monkeypatch) -> None:
    proc = _proc()
    rid = proc.create()["demo_run_id"]
    demo.run_step(proc, rid, 0)
    before = proc.get(rid)

    def down(*_a, **_k):
        raise CompanyUnavailable("회사 시스템에 닿지 않는다")

    monkeypatch.setattr(proc.company, "write_records", down)
    with pytest.raises(CompanyUnavailable):
        demo.run_step(proc, rid, 1)
    after = proc.get(rid)
    assert (
        after["audit"] == before["audit"] and after["company_records"] == before["company_records"]
    )
    monkeypatch.undo()
    demo.run_step(proc, rid, 1)  # 다시 하면 이어진다(같은 판을 다시 낸다)
    assert len(proc.get(rid)["audit"]) > len(before["audit"])


def test_reset_starts_the_scene_records_over(played) -> None:
    proc = _proc()
    rid = proc.create()["demo_run_id"]
    for i in range(3):
        demo.run_step(proc, rid, i)
    assert len(proc.company.records(rid, scene=SCENE)) > 5
    proc.reset(rid, actor="u-demo")
    after = proc.company.records(rid, scene=SCENE)
    assert {r["version"] for r in after} == {1}  # 앞 판은 지웠다 — 처음부터
    assert proc.company.records(rid, scene=1)  # 장면 1 기록은 그대로다
