"""
장면 3(수익성 변동의 통합 분석과 수시 경영검토)의 경영 기록 — 회사 시스템에 적는 판
(`app/sc03/records.py`).

기본 시연 D30~D41 동안 적은 모든 판이 봉투·종류별 스키마(`docs/records/sc03/`)를 통과하고, 회사
기록이 엔진 화면 응답과 같으며(사이트가 그것만으로 그린다), 회사가 받지 못하면 조작이 저장되지
않는다. 계약의 공통 몫은 `records_contract.py`.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from records_contract import check, every_version, example

from app.company import CompanyUnavailable
from app.sc01.process import Sc01Process
from app.sc01.store import SqliteSc01Store
from app.sc02.process import Sc02Process
from app.sc03 import demo
from app.sc03.process import Sc03Process
from app.sc03.records import KINDS, SCENE
from app.sc03.view import view


def _proc() -> Sc03Process:
    s1, s2, s3 = (
        SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), p)
        for p in ("sc01", "sc02", "sc03")
    )
    return Sc03Process(s3, Sc02Process(s2, Sc01Process(s1, inline_agent=True)))


def _play(proc: Sc03Process, case: str = "BASE") -> str:
    rid = proc.create(case_id=case)["demo_run_id"]
    for i in range(len(demo.steps_for(case))):
        demo.run_step(proc, rid, i)
    return rid


@pytest.fixture(scope="module")
def played() -> tuple[Sc03Process, str]:
    proc = _proc()
    return proc, _play(proc)


def test_every_written_version_matches_the_schemas(played) -> None:
    proc, rid = played
    versions = every_version(proc.company, rid, SCENE)
    assert len(versions) > 60
    assert check(SCENE, KINDS, versions) == []


def test_company_records_equal_the_engine_document(played) -> None:
    proc, rid = played
    latest = {r["kind"] + "/" + r["record_id"]: r for r in proc.company.records(rid, scene=SCENE)}
    assert latest["scene/SC03:SC03"]["state"] == "SC03_COMPLETED"
    # 본문은 화면 응답의 같은 칸 그대로다 — 사이트가 계산하지 않고 그린다
    v = json.loads(json.dumps(view(proc.get(rid)), ensure_ascii=False, default=str))
    run = latest["analysis_run/SC03:RUN-SC03-01"]["body"]
    assert run == v["runs"][0]
    year = run["result"]["periods"]["year"]
    assert (year["combined"], year["existing_gap"], year["total_gap"]) == (
        "3299986680",
        "153939000",
        "177303320",
    )
    assert latest["handoff/SC03:SC03"]["body"]["completion"] == v["completion"]
    assert latest["meeting_decision/SC03:REV31"]["state"] == "CONDITIONAL_ACCEPT"
    tasks = proc.company.records(rid, scene=SCENE, kind="analysis_task")
    assert [(t["record_id"], t["state"]) for t in tasks] == [
        (f"SC03:AT3{i}", "ACCEPTED") for i in range(1, 5)
    ]
    assert len(proc.company.records(rid, scene=SCENE, kind="task")) == 18
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
