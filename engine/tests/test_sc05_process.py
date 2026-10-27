"""
SC05 업무 흐름 — Chaeksas BPM 위에서 기본 시연(D501~D518)과 예외(X501~X509)·권한·버전·멱등을 잠근다.

검수 기준은 구현명세 20·21장 T501~T532다. 시험 이름 옆에 대응 ID를 적었다. 끝난 문서는
통합가상데이터 v0.5의 장면 5
시트(기본 시연 종료 시점의 기대값)와 대조한다 — 값을 시험에 옮겨 적지 않는다. 흐름은 내장 실행기로
돈다(같은 그림·같은
작업 함수). 바깥 실행은 `test_sc05_external.py`가 본다.
"""

from __future__ import annotations

import copy
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from chaeksas.contracts.bpmn_ext import read_process
from conftest import require_postgres
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.events import Hub
from app.sc01.domain import USERS, DomainError
from app.sc01.process import Sc01Process
from app.sc01.store import PostgresSc01Store, SqliteSc01Store
from app.sc02.process import Sc02Process
from app.sc03.process import Sc03Process
from app.sc04.process import Sc04Process
from app.sc05 import demo, domain
from app.sc05.api import build_router
from app.sc05.process import PROCESS_PATH, Sc05Process
from app.sc05.seed import kst, load_seed
from app.sc05.view import topology, view
from app.store import build_postgres_backend

PREFIXES = ("sc01", "sc02", "sc03", "sc04", "sc05")
TABLES = ", ".join(f"{p}_demo_run, {p}_history" for p in PREFIXES)
SEED = load_seed()


@pytest.fixture(params=["sqlite", "postgres"])
def proc(request) -> Iterator[Sc05Process]:
    """두 백엔드에서 같은 흐름 — 장면 1~5 저장소는 같은 DB의 다른 테이블이다."""
    backend = None
    if request.param == "postgres":
        backend = build_postgres_backend(require_postgres())
        stores = [PostgresSc01Store(backend.pool, p) for p in PREFIXES]
        with backend.pool.connection() as conn:
            conn.execute(f"TRUNCATE {TABLES}")
    else:
        stores = [
            SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), p)
            for p in PREFIXES
        ]
    published: list[str] = []
    sc02 = Sc02Process(stores[1], Sc01Process(stores[0], inline_agent=True))
    sc04 = Sc04Process(stores[3], Sc03Process(stores[2], sc02))
    p = Sc05Process(stores[4], sc04, publish=published.append)
    p.published = published  # type: ignore[attr-defined]
    try:
        yield p
    finally:
        if backend is not None:
            with backend.pool.connection() as conn:
                conn.execute(f"TRUNCATE {TABLES}")
            backend.close()


def play(
    proc: Sc05Process, case: str = "BASE", until: str | None = None, rid: str | None = None
) -> dict:
    """각본을 `until` 노드(또는 단계 코드)를 실행한 직후까지. `rid`가 있으면 그 실행을 이어 간다."""
    doc = proc.create(case_id=case) if rid is None else proc.get(rid)
    for i, step in enumerate(demo.steps_for(case)):
        if i <= doc.get("script_index", -1):
            continue
        doc = demo.run_step(proc, doc["demo_run_id"], i)
        if until is not None and until in (step.node_id, step.code):
            break
    return doc


def play_before(proc: Sc05Process, node_id: str, case: str = "BASE") -> dict:
    """그 노드 바로 앞 단계까지."""
    steps = demo.steps_for(case)
    stop = next(i for i, s in enumerate(steps) if s.node_id == node_id)
    doc = proc.create(case_id=case)
    for i in range(stop):
        doc = demo.run_step(proc, doc["demo_run_id"], i)
    return doc


def answer(node_id: str, case: str = "BASE") -> dict:
    return dict(next(s for s in demo.steps_for(case) if s.node_id == node_id).answer)


def waiting(doc: dict) -> list[str]:
    return sorted(p["node_id"] for p in doc["bpm"]["snapshot"]["pendings"].values())


@pytest.fixture(scope="module")
def finished() -> dict:
    """기본 시연을 끝까지 한 번 — 끝난 문서 대조용(SQLite)."""
    stores = [
        SqliteSc01Store(sqlite3.connect(":memory:", check_same_thread=False), p) for p in PREFIXES
    ]
    sc02 = Sc02Process(stores[1], Sc01Process(stores[0], inline_agent=True))
    p = Sc05Process(stores[4], Sc04Process(stores[3], Sc03Process(stores[2], sc02)))
    return play(p)


# ─────────────────────────── 착수 (D500·D501 · T528) ───────────────────────────


def test_d500_starts_from_handoff41_and_exposes_nothing_ahead(proc: Sc05Process) -> None:
    """T528 — 7/13 10:00에는 HANDOFF41만 유효하다. 미래의 계획·조건·품의·주문·FC50·근거가 없다."""
    doc = proc.create()
    assert doc["clock"] == "2027-07-13T10:00:00+09:00" and doc["bpm"] is None
    for key in (
        "plans",
        "requests",
        "customer_plans",
        "changes",
        "orders",
        "operating_plans",
        "runs",
        "forecasts",
        "evidence",
    ):
        assert doc[key] == {}, key
    assert (
        doc["ledger"] == []
        and doc["official"] is None
        and doc["start"] is None
        and doc["handoff"] is None
    )
    assert {c["state"] for c in doc["conditions"].values()} == {"OPEN"}
    b = doc["sc04"]
    assert b["handoff"]["handoff_id"] == "HANDOFF41" and b["approval"]["approval_id"] == "APR41-v1"
    assert b["handoff"]["decision"] == "DEC41-v2"
    assert b["handoff"]["financial_snapshot"]["effect"] == "127800000"
    assert (b["actions"]["ACT42"]["budget"], b["actions"]["ACT42"]["owner"]) == (
        "6000000",
        "u-buy-exec",
    )
    st = domain.statuses(doc)
    assert (st["scene"], st["operation"], st["official"], st["risk"], st["target"]) == (
        "PENDING",
        "WAIT",
        None,
        "OPEN",
        "UNCHANGED",
    )
    shown = view(doc)
    assert shown["startCheck"] is None and shown["forecasts"] == [] and shown["orders"] == []


def test_start_twice_returns_the_same_result(proc: Sc05Process) -> None:
    """
    장면 중복 생성 금지 — 같은 장면의 재착수는 새 실행·이벤트를 만들지 않는다. 착수 ≠ 조건 충족.
    """
    doc = play(proc, until="D501")
    rid = doc["demo_run_id"]
    assert domain.statuses(doc)["scene"] == "PLAN_PENDING" and waiting(doc) == ["Draft_Plan"]
    again = proc.start(rid, actor="u-fin")
    assert again["bpm"]["run_id"] == doc["bpm"]["run_id"]
    assert sum(1 for a in again["audit"] if a["action"] == "scene_started") == 1
    assert again["conditions"]["CON41"]["state"] == "OPEN"
    with pytest.raises(DomainError) as other:
        proc.start(rid, actor="u-buy-lead")
    assert other.value.status == 403


def test_unknown_case_is_422(proc: Sc05Process) -> None:
    with pytest.raises(DomainError) as exc:
        proc.create(case_id="X999")
    assert exc.value.status == 422


# ─────────────────────────── 기본 시연 = 데이터 (T501·T520·T532) ───────────────────────────


def test_t501_base_demo_ends_in_sc05_completed(finished: dict) -> None:
    """T532 — FC51 공식, SC05 완료, Risk OPEN, Target 유지, ACT42 운영 추적, DIR41 효과 NULL."""
    h = finished["handoff"]
    assert h["handoff_id"] == "HANDOFF51" and h["source_handoff"] == "HANDOFF41"
    assert h["state_snapshot"] == {
        "scene": "SC05_COMPLETED",
        "forecast": "PUBLISHED",
        "target": "UNCHANGED",
        "risk": "OPEN",
    }
    assert h["forecast"]["official"] == "FC51" and h["forecast"]["parent"] == "FC50"
    fs = h["financial_snapshot"]
    assert (fs["target"], fs["forecast"], fs["gap"]) == ("3477290000", "3428986680", "48303320")
    assert (fs["effect"], fs["effect_closed"], fs["effect_remaining"]) == (
        "129000000",
        "37200000",
        "91800000",
    )
    assert h["operation"] == {
        "ACT41": "OPERATING_MONITORING",
        "ACT42": "OPERATING_MONITORING",
        "ACT43": "OPERATING",
    }
    assert h["completed_at"] == kst(SEED.by_id("SC05인계")["HANDOFF51"]["확인_KST"])
    assert h["completed_by"] == "u-fin-exec"
    st = domain.statuses(finished)
    assert (st["scene"], st["official"], st["risk"], st["target"]) == (
        "SC05_COMPLETED",
        "FC51",
        "OPEN",
        "UNCHANGED",
    )


def test_plans_follow_the_plan_sheet(finished: dict) -> None:
    """SC05계획 — 확정자·확정시각·확인자·확인시각·예산·효과 개시·기한. 배경 PL52·PL53 포함."""
    for r in SEED.rows("SC05계획"):
        p = finished["plans"][r["plan_id"]]
        assert (p["confirmed_by"], p["confirmed_at"]) == (
            domain.ACCOUNTS[r["확정자"]],
            kst(r["확정_KST"]),
        ), r["plan_id"]
        assert (p["verified_by"], p["verified_at"]) == (
            domain.ACCOUNTS[r["확인자"]],
            kst(r["확인_KST"]),
        ), r["plan_id"]
        assert (p["budget"], p["effect_start"], p["due_at"]) == (
            str(r["승인예산"]),
            r["효과개시"].date().isoformat(),
            kst(r["과제기한"]),
        ), r["plan_id"]
    assert (
        finished["plan_pointer"] == "PL51-v2"
        and finished["plans"]["PL51-v2"]["parent"] == "PL51-v1"
    )


def test_activities_keep_the_sheet_and_add_human_cooperation_and_cost(finished: dict) -> None:
    """
    SC05활동 — 담당·시작·완료·선행·완료 기준은 데이터 그대로, 협조·비용은 사람이 채웠다(AG51
    수정본).
    """
    for pid in ("PL51-v1", "PL51-v2"):
        acts = {a["activity_id"]: a for a in finished["plans"][pid]["activities"]}
        for r in (x for x in SEED.rows("SC05활동") if x["plan_id"] == pid):
            a = acts[str(r["activity_id"])]
            assert (a["owner"], a["start"], a["end"], a["completion"]) == (
                domain.ACCOUNTS[r["담당"]],
                r["시작일"].date().isoformat(),
                r["완료계획일"].date().isoformat(),
                r["완료기준·변경내용"],
            ), (pid, a["activity_id"])
        assert all(a["cooperation"] and a["cost"] is not None for a in acts.values())
        assert (
            sum(int(a["cost"]) for a in acts.values()) == 2000000
        )  # 승인 한도 6백만원 안, 활동을 두 번 세지 않는다
    diff = finished["plans"]["PL51-v2"]["diff"]
    assert next(d for d in diff if d.get("activity_id") == "03")["after"]["start"] == "2027-08-19"
    assert [d["kept"] for d in diff if "scope" in d] == [True, True, True]


def test_conditions_and_requests_follow_the_sheet(finished: dict) -> None:
    """SC05조건품의 — CON41·SUP41 최종 확인자·시각, REQ51·OP51·REQ52·REQ53 승인 단계 시각."""
    rows = SEED.by_id("SC05조건품의")
    for cid in ("CON41", "SUP41"):
        c, r = finished["conditions"][cid], rows[cid]
        assert (c["state"], c["confirmed_by"], c["confirmed_at"]) == (
            r["상태"],
            domain.ACCOUNTS[r["최종확인자"]],
            kst(r["최종확인_KST"]),
        )
    for rid in ("REQ51", "OP51", "REQ52", "REQ53"):
        q, r = finished["requests"][rid], rows[rid]
        assert (q["state"], q["amount"]) == ("APPROVED", str(r["금액"])), rid
        hist = {h["state"]: (h["at"], h["by"]) for h in q["history"]}
        assert hist["SUBMITTED"] == (kst(r["상신·이행_KST"]), domain.ACCOUNTS[r["작성·이행자"]]), (
            rid
        )
        assert hist["FUNCTION_APPROVED"] == (
            kst(r["1차확인_KST"]),
            domain.ACCOUNTS[r["1차확인자"]],
        ), rid
        assert hist["APPROVED"] == (kst(r["최종확인_KST"]), domain.ACCOUNTS[r["최종확인자"]]), rid


def test_ledger_and_budget_follow_the_sheets(finished: dict) -> None:
    """
    SC05예산원장 8건(id·시각·약정·집행·손익) · SC05예산 — 일회성 집행 7백만원, 약정 0, 사용가능
    11백만원(T508).
    """
    got = {t["txn_id"]: t for t in finished["ledger"]}
    assert sorted(got) == sorted(str(t["txn_id"]) for t in SEED.rows("SC05예산원장"))
    for t in SEED.rows("SC05예산원장"):
        g = got[str(t["txn_id"])]
        assert (g["at"], g["type"], g["commitment_delta"], g["paid_delta"], g["pnl_cost"]) == (
            kst(t["발생_KST"]),
            t["유형"],
            str(t["약정증감"]),
            str(t["집행증감"]),
            str(t["손익비용"]),
        ), t["txn_id"]
    total = domain.budget_status(finished)["total"]
    assert (total["paid"], total["commitment"], total["available"]) == ("7000000", "0", "11000000")


def test_changes_and_orders_follow_the_sheets(finished: dict) -> None:
    """
    SC05변경공유 6건(접수·공유·확인·대행) · SC05구매표본 60건(수량·긴급·추가비·발주·처리·승인).
    """
    for r in SEED.rows("SC05변경공유"):
        c = finished["changes"][r["change_id"]]
        assert (c["received_at"], c["shared_at"], c["ack_at"]) == (
            kst(r["접수_KST"]),
            kst(r["공유_KST"]),
            kst(r["구매확인_KST"]),
        )
        assert (c["ack_by"], c["delegate"], c["decision"]) == (
            domain.ACCOUNTS[r["확인자"]],
            bool(r["대행여부"]),
            r["대응"],
        )
    for r in SEED.rows("SC05구매표본"):
        o = finished["orders"][r["order_id"]]
        assert (o["qty"], o["urgent"], o["extra"], o["ordered_at"], o["recorded_at"]) == (
            r["수량"],
            bool(r["긴급여부"]),
            str(r["추가비합계"]),
            kst(r["발주_KST"]),
            kst(r["처리기록_KST"]),
        ), r["order_id"]
        assert (o["approver"], o["approved_at"]) == (
            domain.ACCOUNTS.get(r["긴급승인자"] or "", None),
            kst(r["긴급승인_KST"]),
        ), r["order_id"]
        assert (o["late"], o["quality"], o["result_status"]) == (
            r["납기이상"],
            r["품질이상"],
            r["확인상태"],
        )


def test_t511_normal_response_keeps_inventory_and_order_times(finished: dict) -> None:
    """T511 — CH51 재고 80 + 기발주 120 근거, 14시 발주·15시 처리기록 구분, 추가비 0."""
    c = finished["changes"]["CH51"]
    assert (c["response"]["inventory"], c["response"]["open_orders"]) == (80, 120)
    o = finished["orders"]["PO51-001"]
    assert (o["ordered_at"][11:16], o["recorded_at"][11:16], o["extra"]) == ("14:00", "15:00", "0")
    lines = finished["customer_plans"]["CP51"]["lines"]
    assert len(lines) == 5 and all(ln["month_diff"] == 0 for ln in lines)


def test_observation_and_operating_plans_follow_the_sheets(finished: dict) -> None:
    """
    T515·T517·T519 — 초기 결과(60건·9,785개·5건·6M·8.2M) · SC05운영계획(확정·확인 시각과 사람).
    """
    o = finished["observation"]
    assert (o["orders"], o["qty"], o["urgent"], o["extra_cost"], o["net"]) == (
        60,
        9785,
        5,
        "6000000",
        "8200000",
    )
    assert (o["one_off_august"], o["support"]) == (
        "2000000",
        "200000",
    )  # 8월 일회성은 9월 순개선에서 다시 빼지 않는다
    assert o["ack"]["delayed"] == 1 and o["changes"] == 6
    assert (o["confirmed_by"], o["confirmed_at"]) == (
        "u-buy-exec",
        kst(SEED.by_id("SC05이벤트")["EV51-37"]["발생_KST"]),
    )
    for r in SEED.rows("SC05운영계획"):
        p = finished["operating_plans"][r["plan_id"]]
        assert (p["owner_confirm"]["by"], p["owner_confirm"]["at"]) == (
            domain.ACCOUNTS[r["확정자"]],
            kst(r["확정_KST"]),
        )
        assert (
            p["management_verify"]["at"] == kst(r["경영관리확인_KST"]) and p["state"] == "VERIFIED"
        )
    assert finished["operating_plans"]["OPL51"]["assumptions"]["urgent"] == {
        "2027-10-01": 4,
        "2027-11-01": 3,
        "2027-12-01": 3,
    }


def test_forecast_versions_follow_the_sheet(finished: dict) -> None:
    """
    SC05전망버전 — FC50(9/6 승인) · FC51-D(같은 RUN51) · FC51(10/6 10:00 승인, 10:05 게시). 버전
    행을 합산하지 않는다.
    """
    rows = SEED.by_id("SC05전망버전")
    fc = finished["forecasts"]
    assert fc["FC50"]["approved_at"] == kst(rows["FC50"]["대표승인_KST"]) and fc["FC50"][
        "annual"
    ] == str(rows["FC50"]["연간손익"])
    d = fc["FC51-D"]
    assert d["run_id"] == fc["FC51"]["run_id"] == "RUN51" and d["drafted_at"] == kst(
        rows["FC51-D"]["작성_KST"]
    )
    assert max(c["at"] for c in d["confirmations"].values()) == kst(rows["FC51-D"]["부서확인_KST"])
    assert fc["FC51"]["approved_at"] == kst(rows["FC51"]["대표승인_KST"]) and fc["FC51"][
        "annual"
    ] == str(rows["FC51"]["연간손익"])
    assert fc["FC51"]["published_at"] == kst(SEED.by_id("SC05이벤트")["EV51-48"]["발생_KST"])
    run = finished["runs"]["RUN51"]
    assert (
        run["basis_includes_action_effects"] is False and run["reconciliation"]["residual"] == "0"
    )
    assert len(finished["shares"]) == 1


def test_followups_follow_the_handoff_sheet(finished: dict) -> None:
    """
    SC05인계 — FUP51~53·DIR41·RISK51 담당·기한. DIR41 효과는 미산정(NULL)이고 Risk는 새로 만들지
    않는다.
    """
    got = {f["followup_id"]: f for f in finished["followups"]}
    for r in SEED.rows("SC05인계"):
        if r["id"] == "HANDOFF51":
            continue
        f = got[r["id"]]
        assert (f["owner"], f["due_at"]) == (domain.ACCOUNTS[r["담당"]], kst(r["후속기한_KST"])), r[
            "id"
        ]
    assert got["DIR41"]["state"] == "FOLLOWUP_REQUIRED" and "expected_effect" not in got["DIR41"]


def test_events_follow_the_sc05_event_sheet(finished: dict) -> None:
    """
    SC05이벤트 — 시연 행은 감사 이력의 같은 코드·시각·사람, 배경 행은 원천에서 그 시각에 들어온
    기록.
    """
    audit = {}
    for a in finished["audit"]:
        if a["event_code"] and a["event_code"].startswith("EV51-"):
            audit.setdefault(a["event_code"], a)
    for r in SEED.rows("SC05이벤트"):
        if r["demo_id"] == "BACKGROUND" or r["actor"] == "AGENT":
            continue
        a = audit[r["event_id"]]
        assert (a["at"], a["actor"]) == (kst(r["발생_KST"]), domain.ACCOUNTS[r["actor"]]), r[
            "event_id"
        ]
    ev = SEED.by_id("SC05이벤트")
    alert = next(a for a in finished["alerts"] if a["target"] == "CH54")
    assert alert["at"] == kst(ev["EV51-35"]["발생_KST"]) and "u-buy-exec" in alert["to"]
    hist = {(h["state"]): h["at"] for h in finished["operation"]["ACT42"]["history"]}
    assert hist["OPERATING_MONITORING"] == kst(ev["EV51-36"]["발생_KST"])
    assert finished["operation"]["ACT41"]["started_at"] == kst(ev["EV51-08"]["발생_KST"])
    assert finished["directive_log"][0]["at"] == kst(ev["EV51-09"]["발생_KST"])


def test_agent_outputs_are_proposals_and_humans_decide(finished: dict) -> None:
    """SC05Agent — 원 제안과 사람 수정·검토가 따로 남는다. Agent는 승인하지 않는다(REPLAY 표시)."""
    status = {o["kind"]: o["review_status"] for o in finished["agent_outputs"].values()}
    for r in SEED.rows("SC05Agent"):
        assert status[r["agent_run"]] == r["상태"], r["agent_run"]
    assert {o["mode"] for o in finished["agent_outputs"].values()} == {"REPLAY"}
    ag51 = next(o for o in finished["agent_outputs"].values() if o["kind"] == "AG51")
    assert all(a["cost"] is None for a in ag51["draft"]["activities"])  # 원 제안 그대로


# ─────────────────────────── 착수 요건 (T505·T506 · SC05착수조건) ───────────────────────────


@pytest.mark.parametrize("gate", ["GT51", "GT52", "GT53", "GT54", "GT55"])
def test_start_checkpoints_follow_the_sheet(proc: Sc05Process, gate: str) -> None:
    """
    SC05착수조건 — 요건마다 0/1, 8/20 15:10 모두 충족해도 적용일 전에는 READY · 착수
    불가(CK519·CK520).
    """
    r = SEED.by_id("SC05착수조건")[gate]
    at = kst(r["기준_KST"])
    doc = proc.create()
    for i, step in enumerate(demo.steps_for("BASE")):
        if step.at > at or (step.node_id == "Start_Operation"):
            break
        doc = demo.run_step(proc, doc["demo_run_id"], i)
    if doc["clock"] < at:
        doc = proc.set_clock(doc["demo_run_id"], at, actor="u-demo")
    check = domain.start_requirements(doc)
    ok = {i["id"]: i["ok"] for i in check["items"]}
    for key, col in (
        ("plan_confirmed", "계획확정"),
        ("plan_verified", "관리확인"),
        ("CON41", "CON41"),
        ("SUP41", "SUP41"),
        ("REQ51", "REQ51"),
        ("OP51", "OP51"),
    ):
        assert ok[key] == bool(r[col]), (gate, key)
    assert check["ready"] == r["준비상태"]
    assert ("START_ALLOWED" if check["start_allowed"] else "NOT_YET") == r["착수허용"]


def test_t505_x501_conditions_alone_do_not_allow_start(proc: Sc05Process) -> None:
    """
    X501·T505 — 조건만 완료, 품의 미승인에서 착수 → 422 START_BLOCKED. 대기가 아니어도 요건을 먼저
    본다.
    """
    doc = play(proc, until="Verify_SUP41")
    rid = doc["demo_run_id"]
    with pytest.raises(domain.PrerequisiteError) as exc:
        proc.act(
            rid,
            "Start_Operation",
            answer("Start_Operation") | {"착수계획버전": "PL51-v2"},
            actor="u-buy-exec",
        )
    assert exc.value.code == "START_BLOCKED"
    assert any("REQ51" in i for i in exc.value.items) and any("OP51" in i for i in exc.value.items)
    after = proc.get(rid)
    assert after["start"] is None and after["plans"]["PL51-v2"]["state"] == "CONFIRMED"


def test_t506_all_ready_on_8_20_still_waits_for_9_1(proc: Sc05Process) -> None:
    """T506 — 8/20 15:10 모든 요건 충족(READY)이어도 9/1 09:00 전에는 착수 불가."""
    doc = play(proc, until="Budget_OP51")
    with pytest.raises(domain.PrerequisiteError) as exc:
        proc.act(doc["demo_run_id"], "Start_Operation", {"착수확인": "착수"}, actor="u-buy-exec")
    assert exc.value.items == ["적용일 9/1 09:00 미도래"]
    assert domain.operation_state(doc, "ACT42") == "WAIT"


# ─────────────────────────── 계획 (T502·T503·T504·T507) ───────────────────────────


def test_t502_roles_are_checked(proc: Sc05Process) -> None:
    """
    T502 — 임원 아닌 계획 확정 403, 경영관리 임원의 대표 승인 403, 다른 부서 가정 확인 대행 403.
    """
    doc = play(proc, until="Coordinate_Plan")
    rid = doc["demo_run_id"]
    with pytest.raises(DomainError) as lead:
        proc.act(rid, "Confirm_Plan", answer("Confirm_Plan"), actor="u-buy-lead")
    assert lead.value.status == 403
    later = play(proc, until="Submit_Forecast", rid=rid)
    with pytest.raises(DomainError) as cfo:
        proc.act(
            later["demo_run_id"], "Approve_Forecast", answer("Approve_Forecast"), actor="u-fin-exec"
        )
    assert cfo.value.status == 403


def test_t503_missing_fields_save_but_block_confirmation(proc: Sc05Process) -> None:
    """
    T503 — 비용 미입력·순환이 있어도 초안은 저장되고 확정은 422 PLAN_INCOMPLETE. 비용 0은 누락이
    아니다.
    """
    doc = play(proc, until="D501")
    rid = doc["demo_run_id"]
    doc = demo.run_step(proc, rid, 1)  # AG51
    text = answer("Draft_Plan")["계획활동"].splitlines()
    cells = text[1].split(" | ")
    cells[7] = ""  # 02 비용 미입력
    text[1] = " | ".join(cells)
    cyc = text[0].split(" | ")
    cyc[5] = "06"  # 01 ← 06 ← … ← 01 순환
    text[0] = " | ".join(cyc)
    proc.set_clock(rid, "2027-07-14T10:00:00+09:00", actor="u-demo")
    doc = proc.act(
        rid,
        "Draft_Plan",
        answer("Draft_Plan") | {"계획활동": "\n".join(text), "계획초안출처": ""},
        actor="u-buy-lead",
    )
    plan = doc["plans"]["PL51-v1"]
    problems = domain.plan_problems(doc, plan)
    assert "활동 02 비용 누락" in problems and "선행 관계에 순환이 있다" in problems
    assert not any("활동 01 비용" in p for p in problems)  # 0원은 확인된 0
    proc.act(rid, "Coordinate_Plan", answer("Coordinate_Plan"), actor="u-prod-exec")
    with pytest.raises(domain.PrerequisiteError) as exc:
        proc.act(rid, "Confirm_Plan", answer("Confirm_Plan"), actor="u-buy-exec")
    assert (
        exc.value.code == "PLAN_INCOMPLETE"
        and proc.get(rid)["plans"]["PL51-v1"]["state"] == "COORDINATED"
    )


def test_t504_v1_stays_effective_until_v2_is_verified(proc: Sc05Process) -> None:
    """T504 — 변경안 확인 전에는 v1이 유효, 확인 뒤 한 번 교체. 미확정 변경안은 착수를 막는다."""
    doc = play(proc, until="Confirm_Change")
    assert doc["plan_pointer"] == "PL51-v1" and doc["plans"]["PL51-v2"]["state"] == "CONFIRMED"
    assert any("미확정 변경안 PL51-v2" in b for b in domain.start_requirements(doc)["blocking"])
    doc = play(proc, until="Verify_Change", rid=doc["demo_run_id"])
    assert (
        doc["plan_pointer"] == "PL51-v2"
        and doc["plans"]["PL51-v1"]["management_check"] == "VERIFIED"
    )
    assert domain.unresolved_change(doc) is None
    assert sum(1 for a in doc["audit"] if a["action"] == "plan_verified") == 2


def test_t507_x502_out_of_scope_change_is_held(proc: Sc05Process) -> None:
    """
    X502·T507 — 총괄 한도 초과 변경안은 별도 승인 필요(시행 보류). APR41-v1·기존 계획은 그대로다.
    """
    doc = play(proc, case="X502", until="X502")
    v2 = doc["plans"]["PL51-v2"]
    assert v2["state"] == "NEEDS_SEPARATE_APPROVAL" and any(
        "총괄 한도" in p for p in v2["scope_problems"]
    )
    assert doc["plan_pointer"] == "PL51-v1" and waiting(doc) == ["Request_Change"]
    done = play(proc, case="X502", rid=doc["demo_run_id"])
    assert done["plans"]["PL51-v2"]["state"] == "SUPERSEDED" and done["plan_pointer"] == "PL51-v3"
    assert done["handoff"]["financial_snapshot"]["forecast"] == "3428986680"


# ─────────────────────────── 예산·변경 대응 (T509·T512·T513) ───────────────────────────


def test_t509_request_over_the_task_budget_is_blocked(proc: Sc05Process) -> None:
    """T509 — 과제 한도(6백만원)를 넘는 품의는 422 BUDGET_EXCEEDED. 약정이 생기지 않는다."""
    doc = play(proc, until="Verify_SUP41")
    with pytest.raises(domain.PrerequisiteError) as exc:
        proc.act(
            doc["demo_run_id"],
            "Submit_REQ51",
            answer("Submit_REQ51") | {"REQ51요청액": "7000000"},
            actor="u-buy-lead",
        )
    assert exc.value.code == "BUDGET_EXCEEDED"
    assert proc.get(doc["demo_run_id"])["requests"].get("REQ51") is None


def test_t512_x504_urgent_order_cannot_execute_before_approval(proc: Sc05Process) -> None:
    """X504·T512 — 긴급 기안 뒤 승인 전 실행 기록은 422. 승인 뒤 120만원 추가비로 실행된다."""
    doc = play_before(proc, "Approve_Urgent")
    with pytest.raises(domain.PrerequisiteError) as exc:
        domain.check(doc, "execute_order", {"ordered_at": "2027-09-10T11:00:00+09:00"})
    assert exc.value.code == "URGENT_NOT_APPROVED"
    assert doc["orders"]["PO51-010"]["state"] == "URGENT_SUBMITTED"


def test_t513_urgent_limit_boundary(proc: Sc05Process) -> None:
    """T513 — 추가비 2백만원은 구매 임원 전결, 2백만원+1원은 상위 전결 전 차단."""
    doc = play_before(proc, "Approve_Urgent")
    for extra, ok in ((2000000, True), (2000001, False)):
        trial = copy.deepcopy(doc)
        o = trial["orders"]["PO51-010"]
        o.update(transport=str(extra - 300000), extra=str(extra))
        args = {"decision": "승인", "additional_cost": str(extra), "impacts": "납기 준수"}
        if ok:
            domain.check(trial, "approve_urgent", args)
        else:
            with pytest.raises(domain.PrerequisiteError) as exc:
                domain.check(trial, "approve_urgent", args)
            assert "상위 전결" in str(exc.value)


def test_delegate_ack_needs_the_common_standard(proc: Sc05Process) -> None:
    """지정 대행(USR-BUY2)은 CON41 충족 뒤에만 구매 확인을 한다 — 임원 권한은 없다."""
    doc = play_before(proc, "Ack_Change")
    domain.check_actor(doc, "Ack_Change", "u-buy")
    with pytest.raises(DomainError):
        domain.check_actor(doc, "Approve_Urgent", "u-buy")
    trial = copy.deepcopy(doc)
    trial["conditions"]["CON41"]["state"] = "EVIDENCE_READY"
    with pytest.raises(DomainError) as exc:
        domain.ack_change(trial, {}, by="u-buy")
    assert exc.value.status == 403


# ─────────────────────────── 결과·전망 (T516·T518·T521~T527) ───────────────────────────


def test_t516_x509_duplicate_and_unknown_cost_block_result(proc: Sc05Process) -> None:
    """
    X509·T516 — 원천의 중복 주문 행·긴급 추가비 미확인은 노출되고 결과 확정은 422 RESULT_INCOMPLETE.
    """
    doc = play_before(proc, "Confirm_Observation")
    rid = doc["demo_run_id"]
    trial = copy.deepcopy(proc.get(rid))
    trial["orders"]["PO51-018"]["extra"] = None
    trial["source_issues"].append(
        {
            "kind": "DUPLICATE_ORDER",
            "order_id": "PO51-002",
            "row": dict(trial["orders"]["PO51-002"]),
        }
    )
    obs = domain.observation(trial)
    assert (
        obs["duplicates"] == ["PO51-002"]
        and obs["unknown_cost"] == ["PO51-018"]
        and obs["extra_cost"] is None
    )
    with pytest.raises(domain.PrerequisiteError) as exc:
        domain.check(trial, "confirm_observation", {"decision": "확인"})
    assert exc.value.code == "RESULT_INCOMPLETE"


def test_t518_results_before_the_month_close_are_unconfirmed(proc: Sc05Process) -> None:
    """
    T518·T528 — 9/30 18:00 전에는 납기·품질이 미확인(정상 0건이 아니다)이고 결과 확정이 막힌다.
    """
    doc = play(proc, until="D512")
    obs = domain.observation(doc)
    assert obs["late"] is None and obs["unconfirmed_results"] == obs["orders"]
    assert doc["official"] == "FC50"  # 9/6 배경 승인 뒤
    with pytest.raises(domain.PrerequisiteError):
        domain.check(doc, "confirm_observation", {"decision": "확인"})


def test_t521_x506_readding_the_approved_effect_is_redone(proc: Sc05Process) -> None:
    """
    X506·T521 — 종전 공식본 + 승인효과 검토안은 대사 실패로 남고 다시 작성한다. FC50은 그대로다.
    """
    doc = play(proc, case="X506", until="X506")
    bad = doc["forecasts"]["FC51-D"]
    assert not doc["runs"][bad["run_id"]]["valid"] and waiting(doc) == ["Draft_Forecast"]
    assert doc["official"] == "FC50"
    done = play(proc, case="X506", rid=doc["demo_run_id"])
    assert (
        done["forecasts"]["FC51-D"]["state"] == "STALE"
        and done["forecasts"]["FC51-D2"]["state"] == "PUBLISHED"
    )
    assert done["forecasts"]["FC51"]["run_id"] == "RUN52"


def test_t522_fixed_cost_saving_is_blocked(proc: Sc05Process) -> None:
    """T522 — 외주 조정 고정비 절감 입력은 막힌다(절감 0, 월 370백만원 유지)."""
    doc = play(proc, until="Confirm_OPL51")
    with pytest.raises(domain.PrerequisiteError):
        proc.act(
            doc["demo_run_id"],
            "Confirm_OPL52",
            answer("Confirm_OPL52") | {"OPL52고정비절감": "1"},
            actor="u-prod-exec",
        )


def test_t523_x505_missing_department_blocks_submission(proc: Sc05Process) -> None:
    """
    X505·T523 — 부서 확인 하나가 빠지면 대표 승인 요청은 422 FORECAST_INVALID. FC50은 공식본으로
    남는다.
    """
    doc = play(proc, until="Confirm_FC_PROD")
    with pytest.raises(domain.PrerequisiteError) as exc:
        proc.act(
            doc["demo_run_id"], "Submit_Forecast", answer("Submit_Forecast"), actor="u-fin-exec"
        )
    assert exc.value.code == "FORECAST_INVALID" and any("SALES" in i for i in exc.value.items)
    assert proc.get(doc["demo_run_id"])["official"] == "FC50"


def test_t524_x507_ceo_return_keeps_fc50(proc: Sc05Process) -> None:
    """
    X507·T524 — 반려하면 검토안 RETURNED, FC50·Target 불변. 보완 검토안을 새로 만들어 승인한다.
    """
    doc = play(proc, case="X507", until="X507")
    assert doc["forecasts"]["FC51-D"]["state"] == "RETURNED" and doc["official"] == "FC50"
    assert doc["scene"]["target"] == "UNCHANGED" and waiting(doc) == ["Draft_Forecast"]
    done = play(proc, case="X507", rid=doc["demo_run_id"])
    assert (
        done["forecasts"]["FC51"]["review_ref"] == "FC51-D2"
        and done["forecasts"]["FC51-D"]["state"] == "RETURNED"
    )


def test_t525_x508_november_four(proc: Sc05Process) -> None:
    """X508·T525 — 새 RUN의 연간 3,427,786,680원·부족 49,503,320원. 마감 Actual은 그대로다."""
    doc = play(proc, case="X508")
    fs = doc["handoff"]["financial_snapshot"]
    assert (fs["forecast"], fs["gap"], fs["effect_closed"]) == (
        "3427786680",
        "49503320",
        "37200000",
    )


def test_t526_change_after_approval_makes_a_new_run(proc: Sc05Process) -> None:
    """T526 — 게시 뒤 입력이 바뀌면 새 RUN·새 검토본(FC52-D). 기존 FC51은 그대로다."""
    doc = play(proc, until="Publish_Forecast")
    trial = copy.deepcopy(doc)
    out = domain.draft_forecast(
        trial, SEED, {"method": "마감 실적+잔여 전망", "reasons": "11월 가정 재검토"}, by="u-fin"
    )
    assert out["forecast_id"] == "FC52-D" and out["run_id"] == "RUN52"
    assert trial["forecasts"]["FC51"] == doc["forecasts"]["FC51"] and trial["official"] == "FC51"


def test_t527_publish_retry_is_idempotent(proc: Sc05Process) -> None:
    """
    T527 — 게시 응답이 유실돼 같은 멱등키로 다시 보내면 FC51·공유 기록이 각 1건이다. 게시 전엔
    FC50이 공식본.
    """
    doc = play(proc, until="Approve_Forecast")
    rid = doc["demo_run_id"]
    assert doc["official"] == "FC50" and doc["forecasts"]["FC51-D"]["state"] == "APPROVED"
    proc.set_clock(rid, "2027-10-06T10:05:00+09:00", actor="u-demo")
    body = answer("Publish_Forecast")
    first = proc.act(rid, "Publish_Forecast", body, actor="u-fin", idempotency_key="pub-1")
    again = proc.act(rid, "Publish_Forecast", body, actor="u-fin", idempotency_key="pub-1")
    assert again["official"] == "FC51" and len(again["shares"]) == len(first["shares"]) == 1
    with pytest.raises(DomainError) as conflict:
        proc.act(
            rid,
            "Publish_Forecast",
            {"게시대상": "다른 대상"},
            actor="u-fin",
            idempotency_key="pub-1",
        )
    assert conflict.value.status == 409


def test_t528_clock_alone_does_not_approve_or_start(proc: Sc05Process) -> None:
    """
    T528 — 시계를 10/6으로 옮겨도 계획·조건·착수·전망은 생기지 않는다. 배경 원천만 시각대로
    들어온다.
    """
    doc = play(proc, until="D501")
    doc = proc.set_clock(doc["demo_run_id"], "2027-10-06T16:00:00+09:00", actor="u-demo")
    assert doc["plans"].keys() == {"PL52-v1", "PL53-v1"} and doc["start"] is None
    assert doc["official"] == "FC50" and "FC51" not in doc["forecasts"]
    assert doc["operation"]["ACT42"]["state"] == "WAIT"  # 착수 전이라 운영 인계가 들어오지 않는다
    assert {"REQ52", "REQ53"} == set(doc["requests"])
    assert not any(
        t["request_ref"] in ("REQ51", "OP51") for t in doc["ledger"]
    )  # 승인 전 약정·집행 없음


def test_t530_agent_failure_falls_back_to_manual(proc: Sc05Process) -> None:
    """T530 — Agent가 실패해도 수동으로 진행한다. 실패 초안은 인용하지 않고 권한은 그대로다."""
    doc = play(proc, until="D501")
    rid = doc["demo_run_id"]
    stored, version = proc.store.load(rid)
    stored["agent_mode"] = "fail"
    proc.store.save(rid, stored, version, "test")
    doc = demo.run_step(proc, rid, 1)
    assert [o["status"] for o in doc["agent_outputs"].values()] == ["FAILED"]
    doc = demo.run_step(proc, rid, 2)
    assert (
        doc["plans"]["PL51-v1"]["agent_ref"] is None and doc["plans"]["PL51-v1"]["state"] == "DRAFT"
    )


def test_t531_missing_followup_owner_blocks_completion(proc: Sc05Process) -> None:
    """
    T531 — 후속 담당·기한이 빠지면 422 COMPLETION_BLOCKED이고 HANDOFF51은 부분 생성되지 않는다.
    """
    doc = play_before(proc, "Complete_Scene")
    rid = doc["demo_run_id"]
    lines = answer("Complete_Scene")["후속목록"].splitlines()
    cells = lines[0].split(" | ")
    cells[2] = ""
    lines[0] = " | ".join(cells)
    with pytest.raises(domain.PrerequisiteError) as exc:
        proc.act(
            rid,
            "Complete_Scene",
            {"후속목록": "\n".join(lines), "완료메모": ""},
            actor="u-fin-exec",
        )
    assert exc.value.code == "COMPLETION_BLOCKED" and any("FUP51" in i for i in exc.value.items)
    after = proc.get(rid)
    assert after["handoff"] is None and after["followups"] == []


def test_idempotency_and_script_guards(proc: Sc05Process) -> None:
    """멱등키 재요청은 상태를 바꾸지 않고, 각본은 건너뛸 수 없고, 지난 단계 재실행은 무해하다."""
    doc = play(proc, until="D501")
    rid = doc["demo_run_id"]
    with pytest.raises(DomainError) as skip:
        demo.run_step(proc, rid, 5)
    assert skip.value.status == 409
    assert demo.run_step(proc, rid, 0)["script_index"] == 0


def test_reset_returns_only_this_run_to_d500(proc: Sc05Process) -> None:
    doc = play(proc, until="Verify_Plan")
    doc = proc.reset(doc["demo_run_id"], actor="u-demo")
    assert doc["plans"] == {} and doc["scene"]["started_at"] is None and doc["step"] == "D500"
    assert any(a["action"] == "demo_run_reset" for a in doc["audit"])


def test_changes_are_published_and_history_keeps_steps(proc: Sc05Process) -> None:
    doc = play(proc, until="Draft_Plan")
    rid = doc["demo_run_id"]
    assert f"sc05:{rid}" in proc.published  # type: ignore[attr-defined]
    history = proc.store.history(rid)
    assert len(history) >= 4 and proc.store.at(rid, history[0]["seq"])["plans"] == {}


# ─────────────────────────── BPMN ↔ 역할표 · HTTP ───────────────────────────


def test_every_user_task_has_a_role_and_matching_assignees() -> None:
    """
    NODE_ROLES와 BPMN이 갈라지면 화면 역할 검사와 결재 담당자가 어긋난다. 구매 확인은 지정 대행도
    담당이다.
    """
    process = read_process(Path(PROCESS_PATH).read_bytes())
    users = [n.id for n in process.all_nodes() if n.kind == "userTask"]
    assert sorted(users) == sorted(domain.NODE_ROLES)
    for node in process.all_nodes():
        if node.kind != "userTask":
            continue
        spec = domain.NODE_ROLES[node.id]
        assignees = node.prop("approval").assignees
        roles = {u["role"] for u in USERS.values() if u["name"] in assignees}
        extra = {USERS[d]["role"] for d in domain.DELEGATES.get(node.id, ())}
        assert roles == {spec["role"], *extra}, node.id


def test_http_errors_and_shapes(proc: Sc05Process) -> None:
    app = FastAPI()
    app.include_router(build_router(proc, Hub()))
    client = TestClient(app)
    created = client.post("/sc05/demo-runs", json={"executor": "embedded"})
    assert created.status_code == 201
    body = created.json()
    rid = body["demoRunId"]
    assert (
        body["status"]["risk"] == "OPEN" and body["completion"] is None and body["scene"] == "SC05"
    )
    assert client.get("/sc05/demo-runs/nope").status_code == 404
    assert client.post(f"/sc05/demo-runs/{rid}/start").status_code == 403
    ok = client.post(f"/sc05/demo-runs/{rid}/start", headers={"x-demo-actor": "u-fin"})
    assert ok.status_code == 200 and [w["nodeId"] for w in ok.json()["bpm"]["waiting"]] == [
        "Draft_Plan"
    ]
    early = client.post(
        f"/sc05/demo-runs/{rid}/actions/Start_Operation",
        json={"answer": {"착수확인": "착수"}},
        headers={"x-demo-actor": "u-buy-exec"},
    )
    assert early.status_code == 422 and early.json()["detail"]["error_code"] == "START_BLOCKED"
    check = client.get(f"/sc05/demo-runs/{rid}/start-check").json()
    assert check["ready"] == "WAIT" and not check["start_allowed"]
    done = client.post(
        f"/sc05/demo-runs/{rid}/actions/Complete_Scene",
        json={"answer": {"후속목록": "FUP51 | ACT42 | 문지후 | 2027-10-29T16:00:00+09:00 | 점검"}},
        headers={"x-demo-actor": "u-fin-exec"},
    )
    assert done.status_code == 422 and done.json()["detail"]["error_code"] == "COMPLETION_BLOCKED"
    agent = client.post(
        f"/sc05/demo-runs/{rid}/agent-drafts",
        json={"kind": "AG51"},
        headers={"x-demo-actor": "u-buy-lead"},
    )
    out = agent.json()["agentOutputs"][0]
    assert out["status"] == "SUCCEEDED" and out["mode"] == "REPLAY"
    reviewed = client.post(
        f"/sc05/demo-runs/{rid}/agent-outputs/{out['output_id']}/review",
        json={"note": "검토"},
        headers={"x-demo-actor": "u-buy-lead"},
    )
    assert reviewed.json()["agentOutputs"][0]["review_status"] == "REVIEWED"
    script = client.get("/sc05/script", params={"case_id": "X507"}).json()
    assert [s["nodeId"] for s in script].count("Approve_Forecast") == 2
    topo = client.get("/sc05/process").json()
    assert {n["recordOf"] for n in topo["nodes"] if n["recordOf"]} >= {
        "Draft_Plan",
        "Start_Operation",
        "Complete_Scene",
    }


def test_ts_topology_fixture_is_the_bpmn(proc: Sc05Process) -> None:
    """
    화면 테스트의 토폴로지 사본(`tests/fixtures/sc05-process.json`) = BPMN. BPMN을 고치면 실패한다 —
    다시 만든다:
    `curl -s localhost:8077/sc05/process | python3 -m json.tool --indent 1 >
    tests/fixtures/sc05-process.json`
    """
    fixture = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sc05-process.json"
    assert json.loads(fixture.read_text(encoding="utf-8")) == topology(proc.process)
