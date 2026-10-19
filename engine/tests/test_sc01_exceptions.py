"""
SC01 예외 경로 — EX03 정정본, EX07 기한 초과, AT13 멱등키.

정정은 "새 계산을 만든다"보다 **무엇을 지우지 않는가**가 핵심이다(WF-02·03): 이전 실행·이전
인계·이전 인수는 이력으로 남고, 완료된 업무는 다시 쓰지 않고 재검토 업무를 새로 만들며, 이미
인수한 업무는 새 근거에 대한 재확인이 끝나야 최신 인계가 성립한다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from conftest import require_postgres

from app.sc01 import demo
from app.sc01.domain import DomainError
from app.sc01.process import Sc01Process
from app.sc01.store import PostgresSc01Store, SqliteSc01Store
from app.sc01.view import view
from app.store import build_postgres_backend

OK_DQ = {"확인결과": "확인완료", "확인의견": "정정본 확인", "확인근거": "SRC03 원본"}
SALES = {"영업의견": "정정본 반영 — 감소폭이 줄었다", "영업근거": "RUN-F03-001"}


def jsonb_order(value):
    """JSONB처럼 객체 키를 (바이트 길이, 바이트) 순으로 다시 놓는다 — 넣은 순서가 사라진다."""
    if isinstance(value, dict):
        keys = sorted(value, key=lambda k: (len(k.encode()), k.encode()))
        return {k: jsonb_order(value[k]) for k in keys}
    if isinstance(value, list):
        return [jsonb_order(v) for v in value]
    return value


class JsonbLikeStore(SqliteSc01Store):
    """읽을 때 JSONB처럼 키 순서를 바꾸는 SQLite — Postgres 없이도 순서 의존을 잡는다."""

    def load(self, demo_run_id):
        found = super().load(demo_run_id)
        return (jsonb_order(found[0]), found[1]) if found else None

    def at(self, demo_run_id, seq):
        doc = super().at(demo_run_id, seq)
        return jsonb_order(doc) if doc else None


@pytest.fixture(params=["sqlite", "jsonb-like", "postgres"])
def proc(request) -> Iterator[Sc01Process]:
    """
    세 저장소에서 같은 흐름을 돈다. Postgres JSONB는 키를 길이·바이트 순으로 다시 놓는다 —
    운영계에서 업무 목록 순서가 바뀐 것으로 드러났다. jsonb-like는 그것을 Postgres 없이 재현한다.
    """
    backend = None
    if request.param == "postgres":
        backend = build_postgres_backend(require_postgres())
        store = PostgresSc01Store(backend.pool)
        with backend.pool.connection() as conn:
            conn.execute("TRUNCATE sc01_demo_run, sc01_history")
    else:
        cls = JsonbLikeStore if request.param == "jsonb-like" else SqliteSc01Store
        store = cls(sqlite3.connect(":memory:", check_same_thread=False))
    try:
        yield Sc01Process(store, inline_agent=True)
    finally:
        if backend is not None:
            with backend.pool.connection() as conn:
                conn.execute("TRUNCATE sc01_demo_run, sc01_history")
            backend.close()


def play(proc: Sc01Process, until: int | None = None) -> dict:
    doc = proc.create()
    last = len(demo.BASE) - 1 if until is None else until
    for i in range(last + 1):
        doc = demo.run_step(proc, doc["demo_run_id"], i)
    return doc


def waiting(doc: dict) -> set[str]:
    return {p["node_id"] for p in doc["bpm"]["snapshot"]["pendings"].values()}


def b7(doc: dict, run_id: str) -> dict:
    return next(
        r
        for r in doc["calc_runs"][run_id]["results"]
        if r["model_id"] == "A-b" and r["period"] == "2027-07-01"
    )


# ─────────────────────────── EX03 정정본 ───────────────────────────


def correct_after_handoff(proc: Sc01Process) -> tuple[str, dict]:
    doc = play(proc)
    rid = doc["demo_run_id"]
    proc.set_clock(rid, "2027-06-17T09:00:00+09:00", actor="u-demo")
    doc = proc.receive(rid, "CP03", actor="u-sales")
    return rid, doc


def test_correction_after_handoff_keeps_the_old_handoff_as_history(proc) -> None:
    """WF-03 — 끝난 인계는 역사로 남고 최신 run의 장면은 다시 ACTIVE다."""
    _, doc = correct_after_handoff(proc)
    assert doc["scene"] == "ACTIVE" and doc["handoff"] is None
    assert doc["handoff_history"][0]["run_id"] == "RUN-F02-001"
    assert len(doc["bpm_history"]) == 1 and doc["bpm_history"][0]["state"] == "done"
    assert doc["sources"]["SRC03"]["corrects"] == "SRC02"
    assert doc["sources"]["SRC02"]["status"] == "VERIFIED"  # 이전 원천은 그대로


def test_a_completed_task_is_not_rewritten(proc) -> None:
    """WF-03 — 완료된 TASK-DQ를 다시 쓰지 않고 연결된 재검토 업무 TASK-DQ-2를 만든다."""
    _, doc = correct_after_handoff(proc)
    assert doc["tasks"]["TASK-DQ"]["status"] == "COMPLETED"
    dq2 = doc["tasks"]["TASK-DQ-2"]
    assert dq2["reopens"] == "TASK-DQ" and dq2["status"] == "ASSIGNED"
    assert dq2["source_id"] == "SRC03"


def test_correction_is_judged_against_the_approved_prior(proc) -> None:
    """EX03 — 새 run RUN-F03-001. 공식 비교는 F01(9,500 → 9,000: 500·1천만원·중요)."""
    rid, _ = correct_after_handoff(proc)
    proc.act(rid, "Approve_DQ", OK_DQ, actor="u-sales")
    doc = proc.act(rid, "Confirm_Calc", {}, actor="u-sales")
    r = b7(doc, "RUN-F03-001")
    assert (r["prior"], r["latest"]) == (9500, 9000)
    assert r["metrics"]["M01"]["value"] == "500"
    assert r["metrics"]["KRI02"]["value"] == "10000000" and r["risk"] == "CRITICAL"
    assert b7(doc, "RUN-F02-001")["latest"] == 8800  # 이전 결과는 보존
    assert doc["issues"]["ISSUE-B07"]["runs"] == ["RUN-F01-001", "RUN-F02-001", "RUN-F03-001"]
    assert set(doc["issues"]) == {"ISSUE-A07", "ISSUE-B07"}  # 새 이슈 없음
    assert doc["forecasts"]["F03"]["approval"] == "UNDER_REVIEW"
    # Agent도 새 run에 대해 다시 쓴다
    assert any(o["run_id"] == "RUN-F03-001" for o in doc["agent_outputs"].values())


def test_accepted_tasks_need_reconfirmation_on_the_new_run(proc) -> None:
    """WF-02 — 이미 인수한 업무에는 새 근거를 붙이고 재확인을 요청한다. 재확인 전에는 인계 불가."""
    rid, _ = correct_after_handoff(proc)
    proc.act(rid, "Approve_DQ", OK_DQ, actor="u-sales")
    proc.act(rid, "Confirm_Calc", {}, actor="u-sales")
    proc.act(rid, "Approve_Sales", SALES, actor="u-sales-lead")
    doc = proc.act(
        rid,
        "Approve_Dispatch",
        {"생산담당자": "u-prod", "자재담당자": "u-mat", "배정사유": "정정 반영 재검토"},
        actor="u-sales-lead",
    )
    prod = doc["tasks"]["TASK-PROD"]
    assert prod["status"] == "IN_PROGRESS" and prod["reconfirm"] is True
    assert prod["runs"] == ["RUN-F02-001", "RUN-F03-001"]
    assert "TASK-PROD-2" not in doc["tasks"]  # 활성 업무는 하나뿐(WF-02)

    doc = proc.act(
        rid,
        "Approve_Review",
        {"경영관리담당자": "u-fin", "검토요청사유": "정정 반영"},
        actor="u-sales-lead",
    )
    doc = proc.act(rid, "Accept_PROD", {}, actor="u-prod")
    doc = proc.act(rid, "Accept_MAT", {}, actor="u-mat")
    assert doc["scene"] == "ACTIVE"  # FIN 재확인 전
    reasons = doc and proc.get(rid)
    from app.sc01.domain import handoff_conditions

    check = handoff_conditions(reasons, "RUN-F03-001")
    assert check["accepted"] == {"PROD": True, "MAT": True, "FIN": False}
    assert any("재확인 대기" in r for r in check["reasons"])

    doc = proc.act(rid, "Accept_FIN", {}, actor="u-fin")
    assert doc["scene"] == "HANDED_OFF" and doc["handoff"]["run_id"] == "RUN-F03-001"
    prod = doc["tasks"]["TASK-PROD"]
    # 이전 인수 이력은 지우지 않는다 — 두 run에 대한 확인이 모두 남는다.
    assert [a["run_id"] for a in prod["acks"]] == ["RUN-F02-001", "RUN-F03-001"]
    assert prod["accepted_at"] == "2027-06-16T11:30:00+09:00"


def test_correction_before_review_supersedes_the_running_flow(proc) -> None:
    """검토 대기 중에 정정본이 오면 진행 중이던 실행을 취소하고 새 실행으로 다시 간다."""
    doc = play(proc, until=2)
    rid = doc["demo_run_id"]
    doc = proc.receive(rid, "CP03", actor="u-sales")
    assert doc["bpm_history"][0]["state"] == "cancelled"
    assert waiting(doc) == {"Approve_DQ"}
    sales = doc["tasks"]["TASK-SALES"]
    assert sales["status"] == "ASSIGNED" and "새 계산 대기" in sales["history"][-1]["note"]
    proc.act(rid, "Approve_DQ", OK_DQ, actor="u-sales")
    doc = proc.act(rid, "Confirm_Calc", {}, actor="u-sales")
    # 같은 활성 업무가 새 근거로 이어진다 — 새 영업 검토 업무가 생기지 않는다.
    assert doc["tasks"]["TASK-SALES"]["run_id"] == "RUN-F03-001"
    assert "TASK-SALES-2" not in doc["tasks"]


# ─────────────────────────── EX07 기한 초과 ───────────────────────────


def test_ex07_overdue_alerts_once_per_task_and_deadline(proc) -> None:
    """미인수 상태로 6/17 18시를 넘기면 담당자와 기능별 검토자에게 알린다. 중복 알림은 없다."""
    doc = play(proc, until=5)  # PROD·MAT·FIN 배정, 아무도 인수 안 함
    rid = doc["demo_run_id"]
    doc = proc.set_clock(rid, "2027-06-17T18:30:00+09:00", actor="u-demo")
    alerts = {a["task_id"]: a for a in doc["alerts"]}
    assert set(alerts) == {"TASK-PROD", "TASK-MAT"}  # FIN 기한은 6/18, DQ·SALES는 완료
    assert alerts["TASK-PROD"]["to"] == ["u-prod", "u-plant"]
    assert alerts["TASK-PROD"]["unaccepted"] is True
    assert doc["tasks"]["TASK-PROD"]["status"] == "ASSIGNED"  # 시계는 인수를 실행하지 않는다

    doc = proc.set_clock(rid, "2027-06-18T19:00:00+09:00", actor="u-demo")
    assert [a["task_id"] for a in doc["alerts"]] == ["TASK-PROD", "TASK-MAT", "TASK-FIN"]
    assert doc["scene"] == "ACTIVE"  # 인계 완료 차단


# ─────────────────────────── AT13 멱등키 ───────────────────────────


def test_same_key_same_body_runs_once(proc) -> None:
    doc = play(proc, until=4)
    rid = doc["demo_run_id"]
    first = proc.act(
        rid, "Accept_PROD", {"생산인수의견": "착수"}, actor="u-prod", idempotency_key="k-1"
    )
    again = proc.act(
        rid, "Accept_PROD", {"생산인수의견": "착수"}, actor="u-prod", idempotency_key="k-1"
    )  # 타임아웃 뒤 재시도 — 409가 아니라 지금 상태
    assert again["tasks"]["TASK-PROD"] == first["tasks"]["TASK-PROD"]
    assert sum(a["action"] == "task_accepted" for a in again["audit"]) == 1


def test_same_key_different_body_is_a_conflict(proc) -> None:
    doc = play(proc, until=4)
    rid = doc["demo_run_id"]
    proc.act(rid, "Accept_PROD", {"생산인수의견": "착수"}, actor="u-prod", idempotency_key="k-2")
    with pytest.raises(DomainError) as e:
        proc.act(rid, "Accept_MAT", {}, actor="u-mat", idempotency_key="k-2")
    assert e.value.status == 409


def test_an_old_format_document_still_works(proc) -> None:
    """Agent·정정 이전에 저장된 데모 실행도 계속 조작할 수 있다."""
    doc = play(proc, until=4)
    rid = doc["demo_run_id"]
    old, version = proc.store.load(rid)
    for task in old["tasks"].values():
        for key in ("runs", "acks", "reconfirm", "reopens"):
            task.pop(key)
    for key in ("agent_outputs", "alerts", "agent_mode"):
        old.pop(key)
    proc.store.save(rid, old, version, "old-format")
    doc = proc.act(rid, "Accept_PROD", {}, actor="u-prod")
    assert doc["tasks"]["TASK-PROD"]["status"] == "IN_PROGRESS"


# ─────────────────────────── 순서 (JSONB) ───────────────────────────


def test_order_follows_creation_not_storage(proc) -> None:
    """
    업무·계산·초안·원천은 **만든 순서**로 나온다 — 저장소가 키 순서를 바꿔도. 마지막이 최신이라는
    가정을 화면이 쓰므로(최신 계산·최신 원천) 순서가 틀리면 엉뚱한 결과를 최신으로 보인다.
    """
    rid, _ = correct_after_handoff(proc)
    proc.act(rid, "Approve_DQ", OK_DQ, actor="u-sales")
    proc.act(rid, "Confirm_Calc", {}, actor="u-sales")
    shown = view(proc.get(rid))
    assert [t["task_id"] for t in shown["tasks"]] == [
        "TASK-DQ",
        "TASK-SALES",
        "TASK-PROD",
        "TASK-MAT",
        "TASK-FIN",
        "TASK-DQ-2",
        "TASK-SALES-2",
    ]
    assert [r["run_id"] for r in shown["calcRuns"]] == ["RUN-F01-001", "RUN-F02-001", "RUN-F03-001"]
    assert shown["latestRunId"] == "RUN-F03-001"
    assert [s["source_id"] for s in shown["sources"]] == ["SRC02", "SRC03"]
    assert [o["output_id"] for o in shown["agentOutputs"]] == ["AGT-001", "AGT-002"]


def test_old_documents_get_their_order_back() -> None:
    """순번(`seq`) 이전에 저장된 문서 — 키 순서가 섞였어도 id·배정 시각으로 되살린다."""
    from app.sc01.domain import upgrade

    store = SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False))
    proc = Sc01Process(store, inline_agent=True)
    rid, _ = correct_after_handoff(proc)
    proc.act(rid, "Approve_DQ", OK_DQ, actor="u-sales")
    doc = proc.act(rid, "Confirm_Calc", {}, actor="u-sales")
    for name in ("sources", "forecasts", "calc_runs", "agent_outputs", "tasks"):
        for record in doc[name].values():
            record.pop("seq", None)
    shown = view(upgrade(jsonb_order(doc)))
    assert [t["task_id"] for t in shown["tasks"]][:5] == [
        "TASK-DQ",
        "TASK-SALES",
        "TASK-MAT",
        "TASK-PROD",
        "TASK-FIN",
    ]  # 같은 시각(11:00)의 생산·자재는 id 순으로 — 원래 순서는 알 수 없다
    assert shown["latestRunId"] == "RUN-F03-001"
    assert [s["source_id"] for s in shown["sources"]] == ["SRC02", "SRC03"]
