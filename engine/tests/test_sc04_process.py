"""
SC04 업무 흐름 — Chaeksas BPM 위에서 기본 시연(D401~D413)과 예외(E401~E408)·권한·버전·멱등을 잠근다.

검수 기준은 구현명세 17장 T401~T416이다. 시험 이름 옆에 대응 ID를 적었다. 끝난 문서는
통합가상데이터 v0.4의
장면 4 시트(기본 시연 종료 시점의 완성 레코드)와 대조한다 — 값을 시험에 옮겨 적지 않는다. 흐름은
내장 실행기로
돈다(같은 그림·같은 작업 함수). 바깥 실행은 `test_sc04_external.py`가 본다.
"""

from __future__ import annotations

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
from app.sc04 import demo, domain
from app.sc04.api import build_router
from app.sc04.process import PROCESS_PATH, Sc04Process
from app.sc04.seed import kst, load_seed
from app.sc04.view import topology, view
from app.store import build_postgres_backend

PREFIXES = ("sc01", "sc02", "sc03", "sc04")
TABLES = ", ".join(f"{p}_demo_run, {p}_history" for p in PREFIXES)
SEED = load_seed()


@pytest.fixture(params=["sqlite", "postgres"])
def proc(request) -> Iterator[Sc04Process]:
    """두 백엔드에서 같은 흐름 — 장면 1~4 저장소는 같은 DB의 다른 테이블이다."""
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
    p = Sc04Process(stores[3], Sc03Process(stores[2], sc02), publish=published.append)
    p.published = published  # type: ignore[attr-defined]
    try:
        yield p
    finally:
        if backend is not None:
            with backend.pool.connection() as conn:
                conn.execute(f"TRUNCATE {TABLES}")
            backend.close()


def play(proc: Sc04Process, case: str = "BASE", until: str | None = None) -> dict:
    """각본을 `until` 노드(또는 단계 코드·라벨 앞머리)를 실행한 직후까지."""
    doc = proc.create(case_id=case)
    for i, step in enumerate(demo.steps_for(case)):
        doc = demo.run_step(proc, doc["demo_run_id"], i)
        if until is not None and until in (step.node_id, step.code, step.label.split(" ")[0]):
            break
    return doc


def step_index(case: str, node_id: str) -> int:
    return next(i for i, s in enumerate(demo.steps_for(case)) if s.node_id == node_id)


def waiting(doc: dict) -> list[str]:
    return sorted(p["node_id"] for p in doc["bpm"]["snapshot"]["pendings"].values())


def answer(case: str, node_id: str) -> dict:
    return dict(demo.steps_for(case)[step_index(case, node_id)].answer)


# ─────────────────────────── 착수 (D400·D401 · T401·T414) ───────────────────────────


def test_d400_starts_from_handoff31_and_exposes_nothing_ahead(proc: Sc04Process) -> None:
    """T414 — 7/1 08:59에는 장면 3 인계만 보인다. 미래의 결과·보고·결정·승인·인수가 없다."""
    doc = proc.create()
    assert doc["review"]["state"] == "PENDING" and doc["bpm"] is None
    for key in (
        "results",
        "assumptions",
        "runs",
        "reports",
        "directives",
        "approvals",
        "assignments",
    ):
        assert doc[key] == {}, key
    for key in (
        "verification",
        "recommendation",
        "meeting",
        "decision",
        "approval_draft",
        "handoff",
    ):
        assert doc[key] is None, key
    assert doc["clock"] == "2027-07-01T08:59:00+09:00"
    b = doc["sc03"]
    assert b["handoff"]["handoff_id"] == "HANDOFF31"
    assert b["handoff"]["next_meeting"]["meeting_id"] == "MT41"
    assert [t["task_id"] for t in b["tasks"]] == ["AT31", "AT32", "AT33", "AT34"]
    assert [q["question_id"] for q in doc["followups"]] == ["Q31", "Q32"]
    assert sum(int(m["base"]) for m in doc["baseline"]) == 3299986680
    assert domain.statuses(doc) == {
        "review": "PENDING",
        "approval": None,
        "conditions": None,
        "risk": "OPEN",
        "forecast": "REVIEW_PENDING",
        "target": "UNCHANGED",
        "scene": "PENDING",
    }


def test_t401_start_twice_returns_the_same_result(proc: Sc04Process) -> None:
    """
    T401 — 같은 검토건의 재착수는 새 BPM 실행·이벤트 없이 같은 결과다. 경영관리 담당만 착수한다.
    """
    rid = proc.create()["demo_run_id"]
    with pytest.raises(DomainError) as exc:
        proc.start(rid, actor="u-fin-exec")
    assert exc.value.status == 403
    first = proc.start(rid, actor="u-fin")
    again = proc.start(rid, actor="u-fin")
    assert first["bpm"]["run_id"] == again["bpm"]["run_id"]
    assert len(again["audit"]) == len(first["audit"])
    assert waiting(again) == ["Submit_AT31", "Submit_AT32", "Submit_AT33", "Submit_AT34"]


def test_sc03_must_be_completed_base(proc: Sc04Process) -> None:
    """CT401 — 장면 3 완료(HANDOFF31)가 출발점이다. 다른 사례의 장면 3에서는 시작하지 않는다."""
    sc03 = proc.sc03.create(case_id="E32")
    with pytest.raises(DomainError) as exc:
        proc.create(sc01_demo_run_id=sc03["demo_run_id"])
    assert exc.value.status == 409


def test_unknown_case_is_422(proc: Sc04Process) -> None:
    with pytest.raises(DomainError) as exc:
        proc.create(case_id="E499")
    assert exc.value.status == 422


# ─────────────────────────── 기본 시연 끝 (D413 · T402·T410·T415·T416) ───────────────────────────


def test_base_demo_ends_in_sc04_completed_with_the_data_records(proc: Sc04Process) -> None:
    """
    D401~D413 — 완료 상태가 「SC04」 시트들의 완성 레코드와 같다: 실행과제 3개(책임·한도·두
    기한·인수 시각),
    조건·지시 3개(책임·확인자·기한·상태), 예산 구간, 인계 필드. 위험·전망·목표는 그대로다.
    """
    doc = play(proc)
    assert doc["review"]["state"] == "SC04_COMPLETED" and doc["bpm"]["state"] == "done"
    assert doc["clock"] == kst(SEED.by_id("SC04이벤트")["EV41-23"]["event_at_KST"])
    budget = SEED.by_id("SC04예산과제")
    for act in ("ACT41", "ACT42", "ACT43"):
        a, row = doc["assignments"][act], budget[act]
        assert a["owner"] == domain.ACCOUNTS[row["책임임원"]], act
        assert a["worker"] == domain.ACCOUNTS[row["실무담당"]], act
        assert int(a["budget"]) == row["승인한도"], act
        assert (a["plan_due"], a["completion_due"]) == (
            kst(row["계획제출_KST"]),
            kst(row["과제완료_KST"]),
        )
        assert a["decision"] == row["승인결정"] and a["state"] == row["인수상태"], act
        assert a["accepted_at"] == kst(row["인수시각_KST"]), act
        assert (a["approval_ref"], a["assignment_version"]) == (row["승인버전"], row["배정버전"])
    total = doc["assignments"]["TOTAL"]
    assert total["owner"] == domain.ACCOUNTS[budget["TOTAL"]["책임임원"]]
    assert total["accepted_at"] == kst(budget["TOTAL"]["인수시각_KST"])
    apr = doc["approvals"]["APR41-v1"]
    assert int(apr["total_budget"]) == budget["TOTAL"]["승인한도"]
    assert {k: int(v) for k, v in apr["budget_status"].items()} == {
        "planned": budget["TOTAL"]["미약정예정"],
        "committed": budget["TOTAL"]["기약정미집행"],
        "spent": budget["TOTAL"]["집행완료"],
        "headroom": budget["TOTAL"]["한도여력"],
    }
    for did, row in SEED.by_id("SC04조건지시").items():
        x = doc["directives"][did]
        assert x["owner"] == domain.ACCOUNTS[row["책임"]], did
        assert x["verifier"] == domain.ACCOUNTS[row["충족확인자"]], did
        assert x["collaborators"] == [domain.ACCOUNTS[c] for c in str(row["협조"]).split(";")], did
        assert x["due_at"] == kst(row["기한_KST"]), did
        assert x["responsibility_at"] == kst(row["인수시각_KST"]), did
        assert x["expected_effect"] is None, did  # 미산정 — 0이 아니다
    # 조건 책임 인수와 이행은 따로다(T410·E406) — CON41은 OPEN인 채로 완료한다
    con = doc["directives"]["CON41"]
    assert (con["responsibility"], con["fulfillment"]) == ("ACCEPTED", "OPEN")
    h = doc["handoff"]
    sheet = {r["field"]: r["value"] for r in SEED.rows("SC04인계")}
    assert h["handoff_id"] == sheet["handoff_id"] and h["review_id"] == sheet["review_id"]
    assert (h["approval"], h["decision"]) == (sheet["approval"], sheet["basis_report"])
    assert ";".join(a["target_id"] for a in h["actions"]) == sheet["actions"]
    assert [c["directive_id"] for c in h["conditions"]] == [sheet["open_condition"]]
    assert {d["directive_id"] for d in h["directives"]} == {
        sheet["support"],
        sheet["additional_work"],
    }
    assert h["state_snapshot"] == {
        "scene": sheet["scene_status"],
        "risk": sheet["risk_status"],
        "forecast": sheet["forecast_status"],
        "target": sheet["target_status"],
    }
    assert (
        h["financial_snapshot"].items()
        >= {
            "baseline": "3299986680",
            "target": "3477290000",
            "effect": "127800000",
            "gap": "49503320",
            "conditional_effect": "35600000",
            "gap_excl_conditional": "85103320",
            "normal_annual_reference": "357600000",
        }.items()
    )
    assert h["execution_gates"] == [
        {"target_id": "ACT41", "gate": "PLAN_AND_APPROVAL_REQUIRED"},
        {"target_id": "ACT42", "gate": "BLOCKED_BY_CON41"},
        {"target_id": "ACT43", "gate": "PLAN_AND_APPROVAL_REQUIRED"},
    ]
    assert h["detail_plan"] == "PLAN_PENDING"
    assert (
        domain.statuses(doc).items()
        >= {
            "review": "SC04_COMPLETED",
            "approval": "VALID",
            "conditions": "OPEN",
            "risk": "OPEN",
            "forecast": "REVIEW_PENDING",
            "target": "UNCHANGED",
        }.items()
    )
    assert all(t["status"] == "COMPLETED" for t in doc["tasks"].values())


def test_events_follow_the_sc04_event_sheet(proc: Sc04Process) -> None:
    """T414 — 23 이벤트가 순서·역할·시각대로 감사 이력에 남는다."""
    doc = play(proc)
    logged = {
        a["event_code"]: a for a in doc["audit"] if (a.get("event_code") or "").startswith("EV41")
    }
    rows = SEED.rows("SC04이벤트")
    assert list(logged) == [r["event_id"] for r in rows]
    for r in rows:
        a = logged[r["event_id"]]
        assert a["at"] == kst(r["event_at_KST"]), r["event_id"]
        assert a["actor"] == domain.ACCOUNTS[r["actor"]], r["event_id"]


def test_t402_report_is_frozen_and_decision_is_a_separate_version(proc: Sc04Process) -> None:
    """T402 — REP41-v1 137,200,000원, DEC41-v2 127,800,000원. 판단본은 원 보고본을 덮지 않는다."""
    doc = play(proc, until="Decide")
    rep, dec = doc["reports"]["REP41-v1"], doc["reports"]["DEC41-v2"]
    assert rep["status"] == "FROZEN" and rep["snapshot"]["effect"] == "137200000"
    assert rep["snapshot"]["gap"] == "40103320" and rep["snapshot"]["gap_before"] == "177303320"
    assert dec["status"] == "CONFIRMED" and dec["parent"] == "REP41-v1"
    assert dec["snapshot"]["effect"] == "127800000" and dec["snapshot"]["gap"] == "49503320"
    assert dec["changes"] == [
        {
            "alt_id": "ALT42",
            "field": "start",
            "label": "효과 시작",
            "before": "2027-08-01",
            "after": "2027-09-01",
        }
    ]
    assert doc["runs"][rep["run_id"]]["assumptions"][1]["start"] == "2027-08-01"
    assert doc["decision"]["approved_effect"] == "127800000"


def test_results_keep_writer_confirmer_and_exclusion(proc: Sc04Process) -> None:
    """
    AC402 — 작성자와 확인자는 따로다. AT33은 제외 결과(사유·근거)로 종결하고 과제를 만들지 않는다.
    Q31·Q32는 과거 상태를 보존하고 7월 후속 확인 이력만 더한다.
    """
    doc = play(proc, until="Verify_Effects")
    for rid, row in SEED.by_id("SC04분석결과").items():
        cur = doc["results"][rid]["versions"][-1]
        assert cur["submitted_by"] == domain.ACCOUNTS[row["작성자"]], rid
        assert cur["confirmation"]["by"] == domain.ACCOUNTS[row["확인자"]], rid
        assert cur["submitted_at"] == kst(row["제출시각_KST"]), rid
        assert cur["evidence_refs"] == str(row["근거"]).split(";"), rid
    res43 = doc["results"]["RES43"]["versions"][-1]
    assert res43["outcome"] == "EXCLUDED" and res43["reason"]
    causes = doc["results"]["RES44"]["versions"][-1]["causes"]
    assert sum(int(c["contribution"]) for c in causes) == 153939000  # CK402
    q31, q32 = doc["followups"]
    assert q31["state"] == "OPEN_FOLLOWUP" and len(q31["history"]) == 2
    assert "위험 해소를 뜻하지 않는다" in q31["history"][-1]["note"]
    assert len(q32["history"]) == 2


def test_only_the_department_writes_and_the_executive_confirms(proc: Sc04Process) -> None:
    """구현명세 2장 — 다른 부서 결과 제출 403, 실무자가 임원 확인 대신 403."""
    rid = play(proc, until="D401")["demo_run_id"]
    with pytest.raises(DomainError) as exc:
        proc.act(rid, "Submit_AT31", answer("BASE", "Submit_AT31"), actor="u-buy-lead")
    assert exc.value.status == 403
    proc.act(rid, "Submit_AT31", answer("BASE", "Submit_AT31"), actor="u-prod-lead")
    with pytest.raises(DomainError) as exc:
        proc.act(rid, "Confirm_AT31", answer("BASE", "Confirm_AT31"), actor="u-prod-lead")
    assert exc.value.status == 403


def test_rework_request_needs_a_new_version(proc: Sc04Process) -> None:
    """AC402 — 임원 보완 요청이면 같은 부서가 새 버전을 낸다. 기존 확인본을 덮지 않는다."""
    rid = play(proc, until="D401")["demo_run_id"]
    proc.act(rid, "Submit_AT31", answer("BASE", "Submit_AT31"), actor="u-prod-lead")
    doc = proc.act(
        rid,
        "Confirm_AT31",
        {"AT31확인": "보완요청", "AT31확인의견": "시범 품질 근거를 붙인다"},
        actor="u-prod-exec",
    )
    assert "Submit_AT31" in waiting(doc)
    doc = proc.act(rid, "Submit_AT31", answer("BASE", "Submit_AT31"), actor="u-prod-lead")
    versions = doc["results"]["RES41"]["versions"]
    assert [v["ref"] for v in versions] == ["RES41-v1", "RES41-v2"]
    assert versions[0]["confirmation"]["decision"] == "REWORK_REQUESTED"
    assert doc["assumptions"]["ALT41"]["version"] == 2


def test_exclusion_needs_a_reason(proc: Sc04Process) -> None:
    rid = play(proc, until="D401")["demo_run_id"]
    with pytest.raises(DomainError) as exc:
        proc.act(
            rid,
            "Submit_AT33",
            {**answer("BASE", "Submit_AT33"), "AT33제외사유": ""},
            actor="u-sales-lead",
        )
    assert exc.value.status == 422


# ─────────────────────────── 검증·추천·보고 (U402~U404) ───────────────────────────


@pytest.mark.parametrize(
    ("case", "owner", "code"),
    [
        ("E401", "u-prod-exec", "FIXED_COST_NOT_AVOIDABLE"),
        ("E402", "u-buy-exec", "DUPLICATE_NOT_REMOVED"),
    ],
)
def test_e401_e402_verify_blocks_then_the_owner_corrects(
    proc: Sc04Process, case: str, owner: str, code: str
) -> None:
    """
    T404·T405 — 검증이 막고 보고 확정이 제한된다. 그 안의 담당 임원만 보완한다 → 새 가정 버전 →
    재검증.
    """
    doc = play(proc, case, until="검증")
    assert waiting(doc) == ["Correct_Effects"]
    assert doc["verification"]["state"] == "VALIDATION_FAILED"
    assert doc["rework"][0]["items"][0]["code"] == code and doc["rework"][0]["owner"] == owner
    with pytest.raises(DomainError) as exc:
        proc.act(doc["demo_run_id"], "Correct_Effects", {"보완내용": "x"}, actor="u-fin-exec")
    assert exc.value.status == 403
    rid = doc["demo_run_id"]
    i = next(i for i, s in enumerate(demo.steps_for(case)) if s.node_id == "Correct_Effects")
    for j in range(i, i + 2):
        doc = demo.run_step(proc, rid, j)
    assert doc["verification"]["state"] == "VERIFIED"
    assert doc["rework"][0]["state"] == "RESOLVED"
    alt = doc["rework"][0]["alt_id"]
    assert doc["assumptions"][alt]["version"] == 2
    res = next(r for r in doc["results"].values() if alt in r["alts"])
    assert len(res["versions"]) == 2 and res["versions"][-1]["confirmation"]["by"] == owner
    run = doc["runs"][doc["verification"]["run_id"]]
    assert run["result"]["effect_total"] == "137200000"
    assert run["result"]["fixed_cost_monthly"] == "370000000"


def test_recommendation_needs_two_or_three_and_distinct_priorities(proc: Sc04Process) -> None:
    """CT404 — 2~3개, 우선순위는 1부터 겹치지 않게. 효과액 자동 정렬이 아니다(ALT42가 1순위)."""
    doc = play(proc, until="Verify_Effects")
    rid = doc["demo_run_id"]
    base = answer("BASE", "Recommend")
    with pytest.raises(DomainError) as exc:
        proc.act(
            rid, "Recommend", {**base, "추천ALT41": "제외", "추천ALT43": "제외"}, actor="u-fin-exec"
        )
    assert exc.value.status == 422
    with pytest.raises(DomainError) as exc:
        proc.act(rid, "Recommend", {**base, "ALT41우선순위": "1"}, actor="u-fin-exec")
    assert exc.value.status == 422
    doc = proc.act(rid, "Recommend", base, actor="u-fin-exec")
    assert domain.recommended(doc) == ["ALT42", "ALT41", "ALT43"]
    assert doc["recommendation"]["excluded"][0]["effect"] is None


def test_meeting_records_respect_roles(proc: Sc04Process) -> None:
    """AC407 — 질의·지시는 대표, 답변은 담당 임원. 참석자가 아니면 기록하지 못한다."""
    rid = play(proc, until="Report_Meeting")["demo_run_id"]
    with pytest.raises(DomainError) as exc:
        proc.meeting_record(
            rid, record_type="QUESTION", subject="", content="x", related="", actor="u-buy-exec"
        )
    assert exc.value.status == 403
    with pytest.raises(DomainError) as exc:
        proc.meeting_record(
            rid, record_type="ANSWER", subject="", content="x", related="", actor="u-ceo"
        )
    assert exc.value.status == 403
    with pytest.raises(DomainError) as exc:
        proc.meeting_record(
            rid, record_type="ANSWER", subject="", content="x", related="", actor="u-sales"
        )
    assert exc.value.status == 403


def test_records_follow_the_meeting_sheet(proc: Sc04Process) -> None:
    """SC04회의 — QA411~414의 시각·발언자·본문이 회의 기록에 그대로 남는다."""
    doc = play(proc, until="Draft_Decision")
    sheet = SEED.by_id("SC04회의")
    for r in doc["meeting"]["records"]:
        row = sheet[r["record_id"]]
        assert (r["event_at"], r["actor_id"], r["content"]) == (
            kst(row["시각_KST"]),
            domain.ACCOUNTS[row["발언·결정자"]],
            str(row["본문"]),
        )


def test_decision_change_needs_reason_and_executive(proc: Sc04Process) -> None:
    """구현명세 5장 — 시점·금액 변경에는 변경 사유와 현업 임원 확인이 필수다."""
    rid = play(proc, until="QA414")["demo_run_id"]
    base = answer("BASE", "Draft_Decision")
    for bad in ({"변경사유": ""}, {"변경확인임원": "정하윤"}, {"변경값": "2027-09-15"}):
        with pytest.raises(DomainError) as exc:
            proc.act(rid, "Draft_Decision", {**base, **bad}, actor="u-fin")
        assert exc.value.status == 422, bad


def test_t403_another_change_recalculates_in_a_new_draft(proc: Sc04Process) -> None:
    """
    T403 — 판단 초안에서 ALT42 9월 시작에 더해 ALT41 월량을 2,900으로 바꾸면 124,800,000원·부족
    52,503,320원(같은 계산 규칙). 확정 보고본(REP41-v1)은 그대로다. 폼은 한 칸씩이고 도메인은 여러
    칸을 받는다.
    """
    doc = play(proc, until="QA414")
    args = domain._decision_args(
        {"reason": "회의 질의 반영", "confirmed_by": "권태윤", "change_alt": "없음"}
    )
    args["changes"] = [
        {"alt_id": "ALT42", "field": "start", "value": "2027-09-01"},
        {"alt_id": "ALT41", "field": "monthly_qty", "value": "2900"},
    ]
    rid = domain.draft_decision(doc, SEED, args, by="u-fin")
    run = doc["runs"][doc["reports"][rid]["run_id"]]["result"]
    assert run["effect_total"] == "124800000" and run["periods"]["year"]["gap"] == "52503320"
    assert doc["reports"]["REP41-v1"]["snapshot"]["effect"] == "137200000"
    assert [c["after"] for c in doc["reports"][rid]["changes"]] == ["2027-09-01", 2900]


def test_only_the_ceo_decides_and_stale_decision_is_409(proc: Sc04Process) -> None:
    """구현명세 13장 — 대표만 결정한다. 화면이 본 판단본이 최신이 아니면 409."""
    doc = play(proc, until="Confirm_Decision")
    rid = doc["demo_run_id"]
    with pytest.raises(DomainError) as exc:
        proc.act(rid, "Decide", answer("BASE", "Decide"), actor="u-fin-exec")
    assert exc.value.status == 403
    with pytest.raises(DomainError) as exc:
        proc.act(
            rid, "Decide", answer("BASE", "Decide"), actor="u-ceo", expect={"report": "DEC41-v9"}
        )
    assert exc.value.status == 409


# ─────────────────────────── 승인·인수·종료 (U406~U408) ───────────────────────────


def test_t407_e404_missing_fields_block_finalize_without_partial_save(proc: Sc04Process) -> None:
    """
    T407 — 총괄 한도·계획기한이 비면 422 APPROVAL_INCOMPLETE, 승인서·회의록 모두 없다. 보완 뒤
    확정한다.
    """
    doc = play(proc, "E404", until="Draft_Approval")
    assert doc["approval_draft"]["missing"] == ["총괄 예산 한도 없음", "계획 제출기한 없음"]
    with pytest.raises(domain.PrerequisiteError) as exc:
        proc.act(
            doc["demo_run_id"],
            "Finalize_Approval",
            answer("BASE", "Finalize_Approval"),
            actor="u-ceo",
        )
    assert exc.value.code == "APPROVAL_INCOMPLETE" and len(exc.value.items) == 2
    doc = proc.get(doc["demo_run_id"])
    assert doc["approvals"] == {} and doc["minutes"] == {}
    doc = play_rest(proc, doc["demo_run_id"], "E404")
    assert doc["review"]["state"] == "SC04_COMPLETED"
    assert doc["approval_draft"]["version"] == 2 and doc["approval_draft"]["missing"] == []


def play_rest(proc: Sc04Process, rid: str, case: str) -> dict:
    doc = proc.get(rid)
    for i in range(doc.get("script_index", -1) + 1, len(demo.steps_for(case))):
        doc = demo.run_step(proc, rid, i)
    return doc


def test_t406_e403_hold_creates_no_action(proc: Sc04Process) -> None:
    """
    T406 — ALT43 보류: 실행과제 미생성, 승인 범위 효과 121,600,000원, 부족 55,703,320원. 판단본은
    그대로.
    """
    doc = play(proc, "E403")
    assert doc["review"]["state"] == "SC04_COMPLETED"
    assert "ACT43" not in doc["assignments"]
    assert doc["decision"]["items"]["ALT43"]["outcome"] == "HOLD"
    assert doc["handoff"]["financial_snapshot"]["effect"] == "121600000"
    assert doc["handoff"]["financial_snapshot"]["gap"] == "55703320"
    assert doc["reports"]["DEC41-v2"]["snapshot"]["effect"] == "127800000"
    assert {
        "alt_id": "ALT43",
        "decision": "HOLD",
        "reason": answer("E403", "Decide")["ALT43결정사유"],
    } in doc["handoff"]["excluded"]


def test_t408_two_of_three_blocks_completion_and_others_cannot_accept(proc: Sc04Process) -> None:
    """T408·E405 — 2/3 인수면 종료 422(미인수 과제 표시). 다른 책임자는 403. 반려는 사유 필수."""
    doc = play(proc, until="ACT42")
    rid = doc["demo_run_id"]
    with pytest.raises(DomainError) as exc:
        proc.act(rid, "Accept_ACT43", {"ACT43결정": "인수", "ACT43사유": ""}, actor="u-prod-exec")
    assert exc.value.status == 403
    with pytest.raises(DomainError) as exc:
        proc.act(rid, "Accept_ACT43", {"ACT43결정": "반려", "ACT43사유": ""}, actor="u-buy-exec")
    assert exc.value.status == 422
    with pytest.raises(domain.PrerequisiteError) as exc:
        proc.act(rid, "Complete_Scene", {"완료메모": "x"}, actor="u-fin")
    assert exc.value.code == "COMPLETION_BLOCKED"
    assert any(i.startswith("ACT43 현재 배정버전 미인수") for i in exc.value.items)
    assert any("DIR41" in i or "TOTAL" in i or "전체 책임" in i for i in exc.value.items)
    assert proc.get(rid)["handoff"] is None


def test_t409_e405_return_revise_and_old_version_is_409(proc: Sc04Process) -> None:
    """
    T409·E405 — 반려 → 보완(배정버전 2) → 구버전 인수는 409 → 새 버전 인수. 반려 이력은 그대로다.
    """
    doc = play(proc, "E405", until="Revise_ACT43")
    rid = doc["demo_run_id"]
    a = doc["assignments"]["ACT43"]
    assert a["assignment_version"] == 2 and [h["state"] for h in a["history"]] == [
        "ASSIGNED",
        "RETURNED",
        "ASSIGNED",
    ]
    with pytest.raises(DomainError) as exc:
        proc.act(
            rid,
            "Accept_ACT43",
            {"ACT43결정": "인수", "ACT43사유": ""},
            actor="u-buy-exec",
            expect={"assignment": 1},
        )
    assert exc.value.status == 409
    doc = play_rest(proc, rid, "E405")
    assert doc["review"]["state"] == "SC04_COMPLETED"
    assert doc["handoff"]["actions"][2]["assignment_version"] == 2


def test_register_twice_is_409(proc: Sc04Process) -> None:
    """T401 — 같은 승인으로 과제를 두 번 만들지 않는다."""
    doc = play(proc, until="Register_Actions")
    with pytest.raises(DomainError) as exc:
        domain.check_register(doc)
    assert exc.value.status == 409


def test_t411_budget_policy_lookup_creates_nothing(proc: Sc04Process) -> None:
    """
    T411·E407 — 전용 1백만원은 전체 책임 임원 승인, 총괄 19백만원은 대표 별도 승인. 거래·이력 없음.
    """
    doc = play(proc, until="Finalize_Approval")
    rid = doc["demo_run_id"]
    before = len(proc.get(rid)["audit"])
    a = proc.budget_policy(rid, {"kind": "transfer", "from": "ACT41", "amount": "1000000"})
    b = proc.budget_policy(
        rid, {"kind": "total", "amount": str(SEED.by_id("SC04예외")["E407-B"]["수치 기대값"])}
    )
    assert a["approver"] == "경영관리임원" and b["approver"] == "대표이사" and not b["allowed"]
    assert len(proc.get(rid)["audit"]) == before


def test_t412_e408_agent_failure_falls_back_to_manual(proc: Sc04Process) -> None:
    """T412 — Agent가 실패해도 계산·권한·기록은 그대로이고 사람이 진행한다."""
    doc = play(proc, "E408")
    assert doc["review"]["state"] == "SC04_COMPLETED"
    assert [o["status"] for o in doc["agent_outputs"].values()] == ["FAILED", "FAILED", "FAILED"]
    assert doc["handoff"]["financial_snapshot"]["effect"] == "127800000"


def test_agent_drafts_cite_only_inputs(proc: Sc04Process) -> None:
    """AC417 — 초안은 검증을 통과해야 나온다. 채택은 경영관리만 하고 원 초안은 그대로다."""
    doc = play(proc, until="Draft_Approval")
    outs = list(doc["agent_outputs"].values())
    assert [o["kind"] for o in outs] == ["AG41", "AG42", "AG43"]
    assert all(o["status"] == "SUCCEEDED" and not o["errors"] for o in outs)
    with pytest.raises(DomainError) as exc:
        proc.adopt(doc["demo_run_id"], outs[2]["output_id"], actor="u-ceo")
    assert exc.value.status == 403
    adopted = proc.adopt(doc["demo_run_id"], outs[2]["output_id"], actor="u-fin")
    assert adopted["agent_outputs"][outs[2]["output_id"]]["draft"] == outs[2]["draft"]


def test_t413_idempotency_key_replays_and_conflicts(proc: Sc04Process) -> None:
    """T413 — 같은 키·같은 본문은 최초 결과, 같은 키·다른 본문은 409."""
    doc = play(proc, until="Register_Actions")
    rid = doc["demo_run_id"]
    body = {"ACT41결정": "인수", "ACT41사유": ""}
    first = proc.act(rid, "Accept_ACT41", body, actor="u-prod-exec", idempotency_key="SC04-ACT41-1")
    again = proc.act(rid, "Accept_ACT41", body, actor="u-prod-exec", idempotency_key="SC04-ACT41-1")
    assert len(again["audit"]) == len(first["audit"])
    with pytest.raises(DomainError) as exc:
        proc.act(
            rid,
            "Accept_ACT41",
            {**body, "ACT41사유": "x"},
            actor="u-prod-exec",
            idempotency_key="SC04-ACT41-1",
        )
    assert exc.value.status == 409


def test_t414_clock_alone_does_not_approve_or_accept(proc: Sc04Process) -> None:
    """구현명세 16장 — 달력만 옮겨도 승인·인수가 생기지 않는다. 기한이 지난 업무에는 알림만."""
    rid = play(proc, until="D401")["demo_run_id"]
    doc = proc.set_clock(rid, "2027-07-14T09:00:00+09:00", actor="u-demo")
    assert doc["approvals"] == {} and doc["assignments"] == {}
    assert {a["target"] for a in doc["alerts"]} >= {"TASK-SUBMIT_AT31", "TASK-SUBMIT_AT34"}


def test_reset_returns_only_this_run_to_d400(proc: Sc04Process) -> None:
    doc = play(proc, until="Verify_Effects")
    rid = doc["demo_run_id"]
    doc = proc.reset(rid, actor="u-demo")
    assert doc["review"]["state"] == "PENDING" and doc["results"] == {} and doc["bpm"] is None
    assert proc.sc03.get(rid)["review"]["state"] == "SC03_COMPLETED"


def test_script_cannot_skip_and_rerun_is_harmless(proc: Sc04Process) -> None:
    rid = proc.create()["demo_run_id"]
    with pytest.raises(DomainError) as exc:
        demo.run_step(proc, rid, 2)
    assert exc.value.status == 409
    first = demo.run_step(proc, rid, 0)
    again = demo.run_step(proc, rid, 0)
    assert len(first["audit"]) == len(again["audit"])


def test_changes_are_published_on_the_sc04_channel(proc: Sc04Process) -> None:
    rid = play(proc, until="D401")["demo_run_id"]
    assert f"sc04:{rid}" in proc.published  # type: ignore[attr-defined]


def test_history_keeps_each_step_for_read_only_past(proc: Sc04Process) -> None:
    rid = play(proc, until="Submit_AT32")["demo_run_id"]
    entries = proc.store.history(rid)
    assert len(entries) >= 4
    first = proc.store.at(rid, entries[0]["seq"])
    assert first is not None and first["review"]["state"] == "PENDING"


# ─────────────────────────── BPMN ↔ 역할표 ───────────────────────────


def test_every_user_task_has_a_role_and_matching_assignees() -> None:
    """
    NODE_ROLES와 BPMN이 갈라지면 화면 역할 검사와 결재 담당자가 어긋난다(장면 1~3과 같은 그물).
    """
    process = read_process(Path(PROCESS_PATH).read_bytes())
    users = [n.id for n in process.all_nodes() if n.kind == "userTask"]
    assert sorted(users) == sorted(domain.NODE_ROLES)
    for node in process.all_nodes():
        if node.kind != "userTask":
            continue
        spec = domain.NODE_ROLES[node.id]
        assignees = node.prop("approval").assignees
        if isinstance(assignees, list):
            assert {u["role"] for u in USERS.values() if u["name"] in assignees} == {
                spec["role"]
            }, node.id
        elif spec["owner_of"] == "rework":
            assert assignees == "보완담당자명", node.id
        else:
            assert assignees == f"{spec['owner_of']}책임자", node.id


# ─────────────────────────── HTTP ───────────────────────────


def test_http_errors_and_shapes(proc: Sc04Process) -> None:
    app = FastAPI()
    app.include_router(build_router(proc, Hub()))
    client = TestClient(app)
    created = client.post("/sc04/demo-runs", json={"executor": "embedded"})
    assert created.status_code == 201
    body = created.json()
    rid = body["demoRunId"]
    assert body["status"]["risk"] == "OPEN" and body["completion"]["met"] is False
    assert client.get("/sc04/demo-runs/nope").status_code == 404
    assert client.post(f"/sc04/demo-runs/{rid}/start").status_code == 403
    ok = client.post(f"/sc04/demo-runs/{rid}/start", headers={"x-demo-actor": "u-fin"})
    assert ok.status_code == 200
    assert [w["nodeId"] for w in ok.json()["bpm"]["waiting"]][0] == "Submit_AT31"
    wrong = client.post(
        f"/sc04/demo-runs/{rid}/actions/Recommend",
        json={"answer": {}},
        headers={"x-demo-actor": "u-fin-exec"},
    )
    assert wrong.status_code == 409
    early = client.post(
        f"/sc04/demo-runs/{rid}/actions/Complete_Scene",
        json={"answer": {"완료메모": "x"}},
        headers={"x-demo-actor": "u-fin"},
    )
    assert early.status_code == 422
    detail = early.json()["detail"]
    assert detail["error_code"] == "COMPLETION_BLOCKED" and detail["blocking_items"]
    assert (
        client.post(
            f"/sc04/demo-runs/{rid}/budget-policy", json={"kind": "total", "amount": "1"}
        ).status_code
        == 409
    )
    script = client.get("/sc04/script", params={"case_id": "E405"}).json()
    assert [s["nodeId"] for s in script].count("Accept_ACT43") == 2
    topo = client.get("/sc04/process").json()
    assert {n["recordOf"] for n in topo["nodes"] if n["recordOf"]} >= {
        "Submit_AT31",
        "Verify_Effects",
        "Decide",
        "Accept_ACT42",
        "Complete_Scene",
    }
    shown = view(proc.get(rid))
    assert shown["scene"] == "SC04" and shown["reportId"] is None


def test_ts_topology_fixture_is_the_bpmn(proc: Sc04Process) -> None:
    """
    화면 테스트의 토폴로지 사본(`tests/fixtures/sc04-process.json`) = BPMN. BPMN을 고치면 실패한다
    — 다시
    만든다: `curl -s localhost:8077/sc04/process | python3 -m json.tool --indent 1`
    `> tests/fixtures/sc04-process.json`
    """
    fixture = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sc04-process.json"
    assert json.loads(fixture.read_text(encoding="utf-8")) == topology(proc.process)
