"""
장면 1의 경영 기록 — 회사 시스템에 적는 판(`app/sc01/records.py`, `docs/role-split.md` §3).

* 기본 시연을 끝까지 돌리는 동안 적은 **모든 판**(최신·지난 판)이 봉투·종류별 스키마
  (`docs/records/`)를 통과한다 — 회사 사이트가 같은 스키마로 읽는다.
* 바뀌지 않은 기록은 새 판을 만들지 않는다. 회사가 받지 못하면 그 조작은 저장되지 않는다(503).
* 사이트 시험이 쓰는 예시(`docs/records/sc01/examples/base-end.json`)도 같은 스키마를 통과하고, 지금
  엔진이 적는 기록 목록과 같다. 다시 만들려면 `NOWVIEW_WRITE_RECORD_EXAMPLES=1 uv run pytest
  tests/test_sc01_records.py`.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import require_postgres
from jsonschema import Draft202012Validator

from app.company import CompanyUnavailable
from app.sc01 import demo
from app.sc01.process import Sc01Process
from app.sc01.store import PostgresSc01Store, SqliteSc01Store
from app.store import build_postgres_backend

DOCS = Path(__file__).resolve().parents[2] / "docs" / "records"
EXAMPLE = DOCS / "sc01" / "examples" / "base-end.json"


def _validator(path: Path) -> Draft202012Validator:
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))


ENVELOPE = _validator(DOCS / "envelope.schema.json")
KINDS = {
    p.name.removesuffix(".schema.json"): _validator(p) for p in DOCS.glob("sc01/*.schema.json")
}


def problems(record: dict) -> list[str]:
    envelope = {k: record[k] for k in ENVELOPE.schema["properties"]}
    found = [f"봉투: {e.message}" for e in ENVELOPE.iter_errors(envelope)]
    kind = KINDS.get(record["kind"])
    if kind is None:
        return [*found, f"스키마 없는 종류: {record['kind']}"]
    for e in kind.iter_errors(record["body"]):
        found.append(f"{record['kind']}/{record['record_id']} {list(e.path)}: {e.message}")
    return found


@pytest.fixture(params=["sqlite", "postgres"])
def proc(request) -> Iterator[Sc01Process]:
    backend = None
    if request.param == "postgres":
        backend = build_postgres_backend(require_postgres())
        store = PostgresSc01Store(backend.pool)
        _truncate(backend)
    else:
        store = SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False))
    try:
        yield Sc01Process(store, publish=lambda _c: None, inline_agent=True)
    finally:
        if backend is not None:
            _truncate(backend)
            backend.close()


def _truncate(backend) -> None:
    with backend.pool.connection() as conn:
        conn.execute("TRUNCATE sc01_demo_run, sc01_history")


def play(proc: Sc01Process, until: int | None = None) -> dict:
    doc = proc.create()
    last = len(demo.BASE) - 1 if until is None else until
    for i in range(last + 1):
        doc = demo.run_step(proc, doc["demo_run_id"], i)
    return doc


def every_version(proc: Sc01Process, world: str) -> list[dict]:
    out = []
    for r in proc.company.records(world):
        full = proc.company.record(world, r["kind"], r["record_id"])
        out.extend([full, *full["history"]])
    return out


def test_every_written_version_matches_the_schemas(proc: Sc01Process) -> None:
    doc = play(proc)
    versions = every_version(proc, doc["demo_run_id"])
    assert len(versions) > 20
    assert [p for r in versions for p in problems(r)] == []
    latest = {(r["kind"], r["record_id"]): r for r in proc.company.records(doc["demo_run_id"])}
    assert set(KINDS) == {k for k, _ in latest}  # 스키마마다 적힌 기록이 있다
    # 회사 기록이 엔진 문서와 같다 — 사이트가 이것만으로 그린다
    assert latest[("scene", "SC01")]["state"] == "HANDED_OFF"
    b07 = latest[("issue", "ISSUE-B07")]
    assert b07["state"] == "OPEN" and b07["body"]["risk"] == "CRITICAL"
    run = latest[("calc_run", "RUN-F02-001")]["body"]
    b7 = next(r for r in run["results"] if r["model_id"] == "A-b" and r["period"] == "2027-07-01")
    assert b7["metrics"]["M01"]["value"] == "700"  # 감소 물량(대분) — 엑셀 SC01검증과 같다
    assert b7["metrics"]["M03"]["value"] == "-14000000" and b7["risk"] == "CRITICAL"
    assert latest[("handoff", "SC01")]["body"]["handoffCheck"]["met"] is True
    totals = latest[("dashboard", "UI01")]["body"]["totals"]
    assert set(totals) >= {"연간", "Q3", "7월"} and totals["연간"]["F02"]["mgmtProfit"]
    # 쓰는 동안 바뀌지 않은 기록은 판이 하나다 — F02 전망은 만들어진 뒤 그대로다
    assert latest[("forecast", "F02")]["version"] == 1
    assert latest[("calc_run", "RUN-F01-001")]["version"] == 1


def test_company_outage_keeps_the_operation_unsaved(proc: Sc01Process, monkeypatch) -> None:
    doc = play(proc, until=1)
    before = proc.get(doc["demo_run_id"])

    def down(*_a, **_k):
        raise CompanyUnavailable("회사 시스템에 닿지 않는다")

    monkeypatch.setattr(proc.company, "write_records", down)
    with pytest.raises(CompanyUnavailable):
        demo.run_step(proc, doc["demo_run_id"], 2)
    after = proc.get(doc["demo_run_id"])
    assert after["step"] == before["step"] and after["company_records"] == before["company_records"]
    monkeypatch.undo()
    demo.run_step(proc, doc["demo_run_id"], 2)  # 다시 하면 그대로 이어진다(같은 판을 다시 낸다)
    assert proc.get(doc["demo_run_id"])["step"] != before["step"]


def _normalized(records: list[dict], world: str) -> list[dict]:
    text = json.dumps(records, ensure_ascii=False)
    text = text.replace(world, "demo-example")
    # 실제 시각(Agent 초안의 요청·완료)은 예시마다 달라진다
    real = r'"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+\+00:00)"'
    text = re.sub(real, '"2026-11-03T00:00:00+00:00"', text)
    text = re.sub(r'"AGX-[0-9a-f]{12}"', '"AGX-example"', text)  # Agent 실행 id
    text = re.sub(r"apr_run_[0-9a-z_]+?_(?=[A-Z])", "apr_run_example_", text)
    return json.loads(text)


def test_site_example_matches_what_the_engine_writes(proc: Sc01Process) -> None:
    doc = play(proc)
    world = doc["demo_run_id"]
    listed = proc.company.records(world)
    latest = [proc.company.record(world, r["kind"], r["record_id"]) for r in listed]
    for r in latest:
        r.pop("history")
    now = _normalized(latest, world)
    if os.getenv("NOWVIEW_WRITE_RECORD_EXAMPLES"):
        EXAMPLE.parent.mkdir(parents=True, exist_ok=True)
        EXAMPLE.write_text(json.dumps(now, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    saved = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert [p for r in saved for p in problems(r)] == []
    assert [(r["kind"], r["record_id"], r["version"]) for r in saved] == [
        (r["kind"], r["record_id"], r["version"]) for r in now
    ], "예시가 낡았다 — NOWVIEW_WRITE_RECORD_EXAMPLES=1로 다시 만든다"
