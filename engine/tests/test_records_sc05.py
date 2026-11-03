"""
장면 5의 경영 기록 — 회사 시스템에 적는 판(`app/sc05/records.py`).

기본 시연 동안 적은 모든 판이 봉투·종류별 스키마(`docs/records/sc05/`)를 통과하고, 회사 기록이
엔진 화면 응답과 같으며(사이트가 그것만으로 그린다), 회사가 받지 못하면 조작이 저장되지 않는다.
계약의 공통 몫은 `records_contract.py`, 장면 잇기는 `records_chain.py`.
"""

from __future__ import annotations

import json

import pytest
from records_chain import chain
from records_contract import check, every_version, example

from app.company import CompanyUnavailable
from app.sc05 import demo
from app.sc05.records import KINDS, SCENE
from app.sc05.view import view


def _start(proc) -> str:
    return proc.create(case_id="BASE")["demo_run_id"]


@pytest.fixture(scope="module")
def played():
    proc = chain(SCENE)
    rid = _start(proc)
    for i in range(len(demo.steps_for("BASE"))):
        demo.run_step(proc, rid, i)
    return proc, rid


def test_every_written_version_matches_the_schemas(played) -> None:
    proc, rid = played
    versions = every_version(proc.company, rid, SCENE)
    assert len(versions) > 10
    assert check(SCENE, KINDS, versions) == []


def test_company_records_equal_the_engine_document(played) -> None:
    proc, rid = played
    latest = {r["kind"] + "/" + r["record_id"]: r for r in proc.company.records(rid, scene=SCENE)}
    # 본문은 화면 응답의 같은 칸 그대로다 — 사이트가 계산하지 않고 그린다
    v = json.loads(json.dumps(view(proc.get(rid)), ensure_ascii=False, default=str))
    assert latest["scene/SC05:SC05"]["state"] == "SC05_COMPLETED"
    run = latest["forecast_run/SC05:RUN51"]["body"]
    assert run == v["runs"][0]
    assert (run["annual"], run["gap"]) == ("3428986680", "48303320")
    assert latest["forecast/SC05:FC51"]["state"] == "PUBLISHED"
    assert latest["purchase_orders/SC05:ORDERS"]["body"]["orders"] == v["orders"]
    assert latest["handoff/SC05:SC05"]["body"]["completion"] == v["completion"]
    assert len(proc.company.records(rid, scene=SCENE, kind="task")) == 46
    assert example(proc.company, rid, SCENE) == []


def test_company_outage_keeps_the_operation_unsaved(monkeypatch) -> None:
    proc = chain(SCENE)
    rid = _start(proc)
    demo.run_step(proc, rid, 0)
    before = proc.get(rid)

    def down(*_a, **_k):
        raise CompanyUnavailable("회사 시스템에 닿지 않는다")

    monkeypatch.setattr(proc.company, "write_records", down)
    with pytest.raises(CompanyUnavailable):
        demo.run_step(proc, rid, 1)
    after = proc.get(rid)
    assert after["audit"] == before["audit"]
    assert after["company_records"] == before["company_records"]
    monkeypatch.undo()
    demo.run_step(proc, rid, 1)  # 다시 하면 이어진다(같은 판을 다시 낸다)
    assert proc.get(rid)["company_records"] != before["company_records"]
