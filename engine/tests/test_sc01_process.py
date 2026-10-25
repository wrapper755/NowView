"""
SC01 업무 흐름 — Chaeksas BPM 위에서 기본 시연(EV01~EV07)과 업무 규칙을 잠근다.

검수 기준은 구현명세 13장 AT 표다. 각 테스트 이름 옆에 대응하는 AT/요구사항 ID를 적었다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from conftest import require_postgres

from app.sc01 import demo
from app.sc01.domain import DomainError, due_at, parse_at
from app.sc01.process import Sc01Process
from app.sc01.store import PostgresSc01Store, SqliteSc01Store
from app.store import build_postgres_backend


@pytest.fixture(params=["sqlite", "postgres"])
def proc(request) -> Iterator[Sc01Process]:
    """두 백엔드에서 같은 흐름을 돌린다 — JSON(TEXT vs JSONB)과 잠금 쓰기가 백엔드마다 다르다."""
    published: list[str] = []
    backend = None
    if request.param == "postgres":
        backend = build_postgres_backend(require_postgres())
        store = PostgresSc01Store(backend.pool)
        _truncate_sc01(backend)
    else:
        store = SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False))
    p = Sc01Process(store, publish=published.append, inline_agent=True)
    p.published = published  # type: ignore[attr-defined]
    try:
        yield p
    finally:
        if backend is not None:
            _truncate_sc01(backend)
            backend.close()


def _truncate_sc01(backend) -> None:
    with backend.pool.connection() as conn:
        conn.execute("TRUNCATE sc01_demo_run, sc01_history")


def play(proc: Sc01Process, until: int | None = None) -> dict:
    doc = proc.create()
    last = len(demo.BASE) - 1 if until is None else until
    for i in range(last + 1):
        doc = demo.run_step(proc, doc["demo_run_id"], i)
    return doc


def pending_nodes(doc: dict) -> set[str]:
    return {p["node_id"] for p in doc["bpm"]["snapshot"]["pendings"].values()}


def result(doc: dict, run_id: str, model: str, month: int) -> dict:
    return next(
        r
        for r in doc["calc_runs"][run_id]["results"]
        if r["model_id"] == model and r["period"] == f"2027-{month:02d}-01"
    )


# ─────────────────────────── 기본 시연 ───────────────────────────


def test_s0_shows_only_the_approved_forecast(proc: Sc01Process) -> None:
    """AT01 — F01 기본. CP02·F02 없음. a·b 7월 관심 이슈만 열려 있다."""
    doc = proc.create()
    assert doc["sources"] == {} and doc["forecasts"] == {}
    assert doc["bpm"] is None
    assert {i: x["risk"] for i, x in doc["issues"].items()} == {
        "ISSUE-A07": "ATTENTION",
        "ISSUE-B07": "ATTENTION",
    }


def test_ev01_receive_creates_the_source_and_the_dq_task(proc: Sc01Process) -> None:
    """AT02 — 15행 수신, 자동 검증 통과, TASK-DQ 배정(기한 6/17 18시)."""
    doc = play(proc, until=0)
    src = doc["sources"]["SRC02"]
    assert len(src["rows"]) == 15 and src["errors"] == [] and src["status"] == "RECEIVED"
    assert pending_nodes(doc) == {"Approve_DQ"}
    dq = doc["tasks"]["TASK-DQ"]
    assert dq["assigned_to"] == "u-sales" and dq["status"] == "ASSIGNED"
    assert dq["due_at"] == "2027-06-17T18:00:00+09:00"


def test_ev03_calculation_raises_b07_to_critical(proc: Sc01Process) -> None:
    """AT03·AT04·UI04-05 — 새 run, b 중요, 기존 ISSUE-B07에 연결(새 이슈 없음), a 관심 유지."""
    doc = play(proc, until=2)
    assert doc["sources"]["SRC02"]["status"] == "VERIFIED"
    assert doc["sources"]["SRC02"]["verified_by"] == "u-sales"
    assert doc["forecasts"]["F02"]["approval"] == "UNDER_REVIEW"
    b = result(doc, "RUN-F02-001", "A-b", 7)
    assert (b["metrics"]["M01"]["value"], b["metrics"]["KRI01"]["value"]) == ("700", "0.07368421")
    assert b["metrics"]["KRI02"]["value"] == "14000000" and b["risk"] == "CRITICAL"
    assert set(doc["issues"]) == {"ISSUE-A07", "ISSUE-B07"}
    b07 = doc["issues"]["ISSUE-B07"]
    assert [h["risk"] for h in b07["history"]] == ["ATTENTION", "CRITICAL"]
    assert b07["runs"] == ["RUN-F01-001", "RUN-F02-001"]
    assert doc["issues"]["ISSUE-A07"]["risk"] == "ATTENTION"
    assert pending_nodes(doc) == {"Approve_Sales"}
    assert doc["tasks"]["TASK-SALES"]["run_id"] == "RUN-F02-001"


def test_critical_routes_to_both_ops_and_review(proc: Sc01Process) -> None:
    """UI04-03 — 중요면 현업 검토와 경영 검토가 함께 열린다."""
    doc = play(proc, until=3)
    assert pending_nodes(doc) == {"Approve_Dispatch", "Approve_Review"}
    assert doc["tasks"]["TASK-SALES"]["status"] == "COMPLETED"


def test_prod_and_mat_are_separate_tasks(proc: Sc01Process) -> None:
    """AT08·UI05-01 — 생산·자재는 별도 업무, 각자 담당·기한."""
    doc = play(proc, until=4)
    prod, mat = doc["tasks"]["TASK-PROD"], doc["tasks"]["TASK-MAT"]
    assert (prod["assigned_to"], mat["assigned_to"]) == ("u-prod", "u-mat")
    assert prod["assigned_at"] == "2027-06-16T11:00:00+09:00"
    assert prod["due_at"] == mat["due_at"] == "2027-06-17T18:00:00+09:00"


def test_fin_has_the_two_day_deadline(proc: Sc01Process) -> None:
    doc = play(proc, until=5)
    fin = doc["tasks"]["TASK-FIN"]
    assert fin["assigned_at"] == "2027-06-16T11:05:00+09:00"
    assert fin["due_at"] == "2027-06-18T18:00:00+09:00"


def test_no_handoff_before_fin_is_accepted(proc: Sc01Process) -> None:
    """AT08 — PROD·MAT 인수만으로는 인계되지 않는다."""
    doc = play(proc, until=7)
    assert doc["scene"] == "ACTIVE" and doc["handoff"] is None
    assert pending_nodes(doc) == {"Accept_FIN"}


def test_full_base_run_hands_off_without_resolving_anything(proc: Sc01Process) -> None:
    """AT09·UI06-02 — 인계 완료. F02는 검토 중, B07은 열린 중요, 후속 업무는 진행 중."""
    doc = play(proc)
    assert doc["scene"] == "HANDED_OFF"
    assert doc["handoff"] == {"run_id": "RUN-F02-001", "at": "2027-06-16T11:45:00+09:00"}
    assert doc["bpm"]["state"] == "done"
    assert doc["forecasts"]["F02"]["approval"] == "UNDER_REVIEW"
    assert doc["issues"]["ISSUE-B07"]["status"] == "OPEN"
    assert doc["issues"]["ISSUE-B07"]["risk"] == "CRITICAL"
    status = {t: x["status"] for t, x in doc["tasks"].items()}
    assert status == {
        "TASK-DQ": "COMPLETED",
        "TASK-SALES": "COMPLETED",
        "TASK-PROD": "IN_PROGRESS",
        "TASK-MAT": "IN_PROGRESS",
        "TASK-FIN": "IN_PROGRESS",
    }
    assert [a["action"] for a in doc["audit"]].count("SCENE_HANDED_OFF") == 1


def test_every_change_is_audited_with_actor_and_time(proc: Sc01Process) -> None:
    """AT15 — 각 상태 변경에 행위자·시각이 있다."""
    doc = play(proc)
    assert all(a["actor"] and a["at"] for a in doc["audit"])
    accepted = [a for a in doc["audit"] if a["action"] == "task_accepted"]
    assert {(a["actor"], a["at"]) for a in accepted} == {
        ("u-prod", "2027-06-16T11:30:00+09:00"),
        ("u-mat", "2027-06-16T11:30:00+09:00"),
        ("u-fin", "2027-06-16T11:45:00+09:00"),
    }


def test_each_change_is_kept_in_history_and_published(proc: Sc01Process) -> None:
    doc = play(proc)
    history = proc.store.history(doc["demo_run_id"])
    assert history[0]["event"] == "S0"
    assert proc.store.at(doc["demo_run_id"], 1)["scene"] == "READY"  # 지난 시점은 그대로 남는다
    assert proc.published and set(proc.published) == {f"sc01:{doc['demo_run_id']}"}  # type: ignore[attr-defined]


# ─────────────────────────── 멱등·권한 ───────────────────────────


def test_rerunning_a_step_creates_nothing(proc: Sc01Process) -> None:
    """AT10 — 지난 단계 재실행·같은 원천 재수신은 업무·이슈를 중복 생성하지 않는다."""
    doc = play(proc, until=4)
    again = demo.run_step(proc, doc["demo_run_id"], 2)
    assert again["tasks"] == doc["tasks"] and again["issues"] == doc["issues"]
    same = proc.receive(doc["demo_run_id"], "CP02", actor="u-sales")
    assert list(same["sources"]) == ["SRC02"]


def test_only_the_assignee_can_accept(proc: Sc01Process) -> None:
    """AT13 — 비담당 인수 403. 역할이 같아도 배정된 사람이 아니면 안 된다."""
    doc = play(proc, until=5)
    with pytest.raises(DomainError) as e:
        proc.act(doc["demo_run_id"], "Accept_PROD", {}, actor="u-mat")
    assert e.value.status == 403


def test_the_sales_lead_must_review(proc: Sc01Process) -> None:
    doc = play(proc, until=2)
    with pytest.raises(DomainError) as e:
        proc.act(
            doc["demo_run_id"], "Approve_Sales", {"영업의견": "x", "영업근거": "y"}, actor="u-sales"
        )
    assert e.value.status == 403


def test_review_needs_human_opinion_and_evidence(proc: Sc01Process) -> None:
    """UI04-02 — 의견·근거 없이 검토 완료 불가."""
    doc = play(proc, until=2)
    with pytest.raises(DomainError) as e:
        proc.act(
            doc["demo_run_id"],
            "Approve_Sales",
            {"영업의견": " ", "영업근거": "y"},
            actor="u-sales-lead",
        )
    assert e.value.status == 422
    assert proc.get(doc["demo_run_id"])["reviews"] == {}  # 거절된 조작은 아무것도 남기지 않는다


def test_dispatch_needs_real_assignees(proc: Sc01Process) -> None:
    """UI05-02 — 담당이 없거나 역할이 다르면 배정하지 않는다."""
    doc = play(proc, until=3)
    with pytest.raises(DomainError, match="생산 담당"):
        proc.act(
            doc["demo_run_id"],
            "Approve_Dispatch",
            {"생산담당자": "u-mat", "자재담당자": "u-mat", "배정사유": "x"},
            actor="u-sales-lead",
        )


def test_a_stale_write_is_refused(proc: Sc01Process) -> None:
    """ERR-04 — 다른 쪽이 먼저 쓴 뒤의 쓰기는 409."""
    doc = proc.create()
    _, version = proc.store.load(doc["demo_run_id"])
    proc.set_clock(doc["demo_run_id"], "2027-06-16T08:00:00+09:00", actor="u-demo")
    from app.sc01.store import StaleWrite

    with pytest.raises(StaleWrite):
        proc.store.save(doc["demo_run_id"], doc, version, "stale")


def test_clock_moves_forward_only_and_never_acts(proc: Sc01Process) -> None:
    doc = play(proc, until=5)
    moved = proc.set_clock(doc["demo_run_id"], "2027-06-18T09:00:00+09:00", actor="u-demo")
    assert moved["tasks"]["TASK-PROD"]["status"] == "ASSIGNED"  # 시각 이동은 인수를 실행하지 않는다
    with pytest.raises(DomainError):
        proc.set_clock(doc["demo_run_id"], "2027-06-17T09:00:00+09:00", actor="u-demo")


def test_reset_restores_s0_and_keeps_the_audit(proc: Sc01Process) -> None:
    """AT14 — 현재 데모 실행만 S0로. 다른 실행은 그대로."""
    doc = play(proc)
    other = play(proc, until=2)
    reset = proc.reset(doc["demo_run_id"], actor="u-demo")
    assert reset["scene"] == "READY" and reset["sources"] == {} and reset["bpm"] is None
    assert reset["audit"][-1]["action"] == "demo_run_reset"
    assert proc.get(other["demo_run_id"])["sources"]["SRC02"]["status"] == "VERIFIED"


# ─────────────────────────── 보완 경로 (EX02 → 정정) ───────────────────────────


def test_missing_quantity_blocks_until_corrected(proc: Sc01Process) -> None:
    """EX02·AT11 — 누락은 확인 완료를 막고, 정정본이 오면 새 원천으로 다시 검증한다."""
    doc = proc.create()
    rid = doc["demo_run_id"]
    doc = proc.receive(rid, "EX02", actor="u-sales")
    src = doc["sources"]["SRC02"]
    assert src["status"] == "NEEDS_INFO" and src["errors"][0]["code"] == "MISSING"

    with pytest.raises(DomainError) as e:  # 확인 완료는 막힌다
        proc.act(
            rid,
            "Approve_DQ",
            {"확인결과": "확인완료", "확인의견": "x", "확인근거": "y"},
            actor="u-sales",
        )
    assert e.value.status == 409

    doc = proc.act(
        rid,
        "Approve_DQ",
        {"확인결과": "보완요청", "확인의견": "b 7월 누락", "확인근거": "SRC02"},
        actor="u-sales",
    )
    assert pending_nodes(doc) == set() and doc["tasks"]["TASK-DQ"]["status"] == "NEEDS_INFO"
    assert doc["calc_runs"].keys() == {"RUN-F01-001"}  # 계산·판정 보류

    first_due = doc["tasks"]["TASK-DQ"]["due_at"]
    proc.set_clock(rid, "2027-06-17T10:00:00+09:00", actor="u-demo")
    doc = proc.receive(rid, "CP02", actor="u-sales")  # 정정본
    assert (
        doc["sources"]["SRC03"]["errors"] == [] and doc["sources"]["SRC03"]["corrects"] == "SRC02"
    )
    assert doc["sources"]["SRC02"]["status"] == "NEEDS_INFO"  # 이전 원천은 보존
    dq = doc["tasks"]["TASK-DQ"]
    assert dq["status"] == "ASSIGNED" and dq["source_id"] == "SRC03"
    # 보완 후 재배정돼도 최초 배정 시각과 기한은 보존한다(설계서 1.9) — 시계를 옮긴 뒤에도 그대로다.
    assert dq["due_at"] == first_due == "2027-06-17T18:00:00+09:00"
    assert dq["assigned_at"] == "2027-06-15T18:00:00+09:00"


def test_below_threshold_change_still_goes_to_ops_only(proc: Sc01Process) -> None:
    """EX01·UI04-04 — 기준 이내여도 현업 검토는 간다. 경영 검토는 자동으로 열리지 않는다."""
    doc = proc.create()
    rid = doc["demo_run_id"]
    proc.receive(rid, "EX01", actor="u-sales")
    proc.act(
        rid,
        "Approve_DQ",
        {"확인결과": "확인완료", "확인의견": "x", "확인근거": "y"},
        actor="u-sales",
    )
    doc = proc.act(rid, "Confirm_Calc", {}, actor="u-sales")
    assert result(doc, "RUN-F02-001", "A-c", 7)["risk"] == "NORMAL"
    doc = proc.act(
        rid,
        "Approve_Sales",
        {"영업의견": "소폭 변경", "영업근거": "RUN-F02-001"},
        actor="u-sales-lead",
    )
    assert pending_nodes(doc) == {"Approve_Dispatch"}


def test_deadline_rules() -> None:
    """WF-04 — 18시 이후·주말 배정은 다음 영업일이 기준일이다."""
    assert (
        due_at(parse_at("2027-06-16T09:00:00+09:00"), 1).isoformat() == "2027-06-17T18:00:00+09:00"
    )
    assert (
        due_at(parse_at("2027-06-16T19:00:00+09:00"), 1).isoformat() == "2027-06-18T18:00:00+09:00"
    )
    assert (
        due_at(parse_at("2027-06-18T10:00:00+09:00"), 1).isoformat() == "2027-06-21T18:00:00+09:00"
    )
    assert (
        due_at(parse_at("2027-06-19T10:00:00+09:00"), 2).isoformat() == "2027-06-23T18:00:00+09:00"
    )


# ───────────── 바깥 실행 — Chaeksas가 그림을 돌리고 NowView는 작업으로만 듣는다 (N1) ─────────────


class _ExternalCalls:
    """Studio·서버 실행기의 HTTP 어댑터 흉내 — 행위자 없이 `operate`만 부른다."""

    def __init__(self, proc: Sc01Process) -> None:
        self.proc = proc

    def call(self, request):
        from chaeksas.core.services import OpOutcome, ServiceCallError

        # 확장 정의가 본문에 `{{run_id}}`·`{{node_id}}`를 싣는 것과 같다(N2).
        args = dict(request.input)
        try:
            out = self.proc.operate(
                args.pop("demo_run_id"),
                request.operation,
                args,
                external_run_id=request.run_id,
                node_id=request.node_id,
            )
        except DomainError as exc:
            # 어댑터는 4xx의 본문을 버리고 상태 코드만 말한다(`http_adapter.AdapterCaller.call`).
            raise ServiceCallError(
                f"{request.app_id}.{request.operation}이 {exc.status}를 돌려줬다",
                code="http_error",
                status=exc.status,
            ) from exc
        return OpOutcome(output=out)


def _run_external(proc: Sc01Process, rid: str, sid: str, run_id: str):
    from chaeksas.core.engine import Engine, RunEnv, State
    from chaeksas.core.run_log import RunLog

    engine = Engine()
    run = engine.start(
        proc.process,
        run_id=run_id,
        log=RunLog(run_id=run_id),
        env=RunEnv(services=_ExternalCalls(proc)),
        executor="server_runner",
        inputs={"데모실행ID": rid, "원천ID": sid},
        now=parse_at(proc.get(rid)["clock"]),
    )
    answers = {s.node_id: s.answer for s in demo.BASE if s.node_id}
    while engine.run_until_blocked(run) is State.WAITING:
        for p in list(run.pendings.values()):
            # Center는 담당자만 답하게 한다 — 그 결재의 담당자(이름)가 답한다(ADR-0081)
            engine.answer(run, p.request_id, answers[p.node_id], answered_by=p.assignees[0])
    return run


def test_external_run_reaches_handoff_through_record_tasks(proc: Sc01Process) -> None:
    """
    Studio 시험 실행에서 확인완료 뒤 계산이 409로 막혔다(2026-10-25). 결정 기록 작업이 생긴 뒤에는
    바깥 실행만으로 인계까지 간다 — 업무는 기록될 때 늦게 열리고, 답한 사람은 결재 변수로 와서
    짐작 없이 적힌다(R1). 내장 BPM은 그 데모 실행에서 돌지 않는다(N2).
    """
    from chaeksas.core.engine import State

    rid = proc.create(executor="studio")["demo_run_id"]
    sid = proc.receive(rid, "CP02", actor="u-sales")["sources"]["SRC02"]["source_id"]
    assert proc.get(rid)["bpm"]["snapshot"] is None  # 내장 실행이 시작되지 않았다

    run = _run_external(proc, rid, sid, "run_20270616_090000_e0e0e0")
    assert run.state is State.DONE

    after = proc.get(rid)
    assert after["scene"] == "HANDED_OFF"
    assert after["sources"][sid]["status"] == "VERIFIED"
    bpm = after["bpm"]
    assert (bpm["executor"], bpm["external_run_id"], bpm["state"], bpm["snapshot"]) == (
        "studio",
        "run_20270616_090000_e0e0e0",
        "done",
        None,
    )
    assert {"Approve_DQ", "Confirm_Calc", "Accept_FIN", "Task_Handoff"} <= set(bpm["visited"])
    late = {t["type"]: t["opened_late"] for t in after["tasks"].values() if t.get("opened_late")}
    # 업무는 전부 기록 시점에 늦게 열렸다 — 대기를 여는 내장 실행이 없다.
    assert set(late) == {"DQ", "SALES", "PROD", "MAT", "FIN"}
    recorded = {
        a["detail"]["node_id"]: a["actor"]
        for a in after["audit"]
        if a["action"] == "answer_recorded"
    }
    assert recorded == {
        "Approve_DQ": "u-sales",
        "Approve_Sales": "u-sales-lead",
        "Approve_Dispatch": "u-sales-lead",
        "Approve_Review": "u-sales-lead",
        "Accept_PROD": "u-prod",
        "Accept_MAT": "u-mat",
        "Accept_FIN": "u-fin",
    }
    [calc] = [a for a in after["audit"] if a["action"] == "calculation_requested"]
    assert calc["actor"] == "u-sales"
    assert not [a for a in after["audit"] if a["detail"].get("guessed")]


def test_correction_supersedes_the_external_run_and_links_the_next(proc: Sc01Process) -> None:
    """
    EX03 — 인계 뒤 정정본이 오면 바깥 실행을 이력으로 옮긴다. 그 실행의 남은 호출은 409이고, 다음에
    오는 새 실행이 묶인다. 「같은 데모 실행에 다른 run_id는 409」의 유일한 예외다.
    """
    from chaeksas.core.engine import State

    rid = proc.create(executor="studio")["demo_run_id"]
    proc.receive(rid, "CP02", actor="u-sales")
    first = "run_20270616_090000_f1f1f1"
    assert _run_external(proc, rid, "SRC02", first).state is State.DONE

    doc = proc.receive(rid, "CP03", actor="u-sales")
    assert doc["bpm"]["external_run_id"] is None and doc["scene"] == "ACTIVE"
    assert [(h["run_id"], h["executor"], h["state"]) for h in doc["bpm_history"]] == [
        (first, "studio", "superseded")
    ]
    with pytest.raises(DomainError) as stale:
        proc.operate(rid, "validate_source", {"source_id": "SRC03"}, external_run_id=first)
    assert stale.value.status == 409 and "대체된 실행" in str(stale.value)

    second = "run_20270616_100000_f2f2f2"
    assert _run_external(proc, rid, "SRC03", second).state is State.DONE
    after = proc.get(rid)
    assert after["bpm"]["external_run_id"] == second and after["scene"] == "HANDED_OFF"
    linked = [a["detail"]["run_id"] for a in after["audit"] if a["action"] == "external_run_linked"]
    assert linked == [first, second]


def test_rejected_record_returns_to_the_same_approval_then_fix_request_continues(
    proc: Sc01Process,
) -> None:
    """
    Center 콘솔 답은 NowView 사전 검사를 거치지 않는다 — 검증 오류가 남은 원천을 확인완료하면 기록
    작업이 409였고 실행이 실패로 끝났다. 이제 오류 경계가 같은 결재로 되돌린다(N1). 거절은 감사
    이력에 사유와 함께 남고 업무 효과는 없다. 그다음 보완 요청 → 정정본으로 바로잡으면 인계까지
    간다.
    """
    from chaeksas.core.engine import Engine, RunEnv, State
    from chaeksas.core.run_log import RunLog

    rid = proc.create(executor="center")["demo_run_id"]
    sid = proc.receive(rid, "EX02", actor="u-sales")["sources"]["SRC02"]["source_id"]

    engine, run_id = Engine(), "run_20270616_090000_b0b0b0"
    run = engine.start(
        proc.process,
        run_id=run_id,
        log=RunLog(run_id=run_id),
        env=RunEnv(services=_ExternalCalls(proc)),
        executor="server_runner",
        inputs={"데모실행ID": rid, "원천ID": sid},
        now=parse_at(proc.get(rid)["clock"]),
    )

    def answer(node_id: str, values: dict) -> None:
        [pending] = [p for p in run.pendings.values() if p.node_id == node_id]
        engine.answer(run, pending.request_id, values, answered_by="콘솔")

    dq = {"확인의견": "콘솔에서 확인", "확인근거": "원본 대조"}
    assert engine.run_until_blocked(run) is State.WAITING
    assert run.variables["검증통과"] is False  # EX02 — 필수값 누락
    answer("Approve_DQ", {"확인결과": "확인완료", **dq})

    # 실패로 끝나지 않고 같은 결재가 다시 열린다. 결재가 보이는 `error_message`에는 어댑터가 본문을
    # 버려 상태 코드만 남는다 — 사유는 NowView 감사 이력에 있다.
    assert engine.run_until_blocked(run) is State.WAITING
    assert [p.node_id for p in run.pendings.values()] == ["Approve_DQ"]
    assert "record_dq_review이 409를 돌려줬다" in run.variables["error_message"]
    after = proc.get(rid)
    assert after["sources"][sid]["status"] != "VERIFIED"
    [rejected] = [a for a in after["audit"] if a["action"] == "answer_rejected"]
    assert rejected["detail"]["node_id"] == "Approve_DQ" and rejected["detail"]["status"] == 409
    assert "검증 오류" in rejected["detail"]["reason"]
    # 거절된 답은 「기록」도 업무도 남기지 않는다.
    assert not [a for a in after["audit"] if a["action"] == "answer_recorded"]
    assert not after["tasks"]

    answer("Approve_DQ", {"확인결과": "보완요청", **dq})
    assert engine.run_until_blocked(run) is State.WAITING
    assert run.variables["error_message"] is None  # 기록이 성공하면 낡은 사유를 비운다
    assert proc.get(rid)["sources"][sid]["status"] == "NEEDS_INFO"

    fixed = proc.receive(rid, "CP02", actor="u-sales")
    new_sid = max(fixed["sources"], key=lambda s: fixed["sources"][s]["seq"])
    engine.deliver(run, "원천정정", payload={"원천ID": new_sid})
    answers = {s.node_id: s.answer for s in demo.BASE if s.node_id}
    while engine.run_until_blocked(run) is State.WAITING:
        for p in list(run.pendings.values()):
            engine.answer(run, p.request_id, answers[p.node_id], answered_by="콘솔")
    assert run.state is State.DONE
    done = proc.get(rid)
    assert done["scene"] == "HANDED_OFF" and done["sources"][new_sid]["status"] == "VERIFIED"
    # 콘솔 답은 관리자 계정 이름으로 온다 — 마스터 밖이라도 거절하지 않고 그 이름으로 적는다(R1)
    recorded = [a for a in done["audit"] if a["action"] == "answer_recorded"]
    assert recorded and all(
        a["actor"] == "콘솔" and a["detail"]["outside_master"] for a in recorded
    )
    assert done["bpm"]["external_run_id"] == run_id
