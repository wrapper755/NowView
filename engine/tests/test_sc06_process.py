"""
SC06 적재 · 확인 절차(BPM) · 조회 서비스 — 장면 5 인계에서 RV61을 여는 길, 확인 절차(담당 임원 확인
→ 종합 → 결론 → 확정 → 대표 보고)를 내장 실행기로 끝까지 돌린 문서가 SC06보고 시트와 같은지, 결재
규칙(담당 403 · 확정 요건 422 · 재확인·보완 고리), 조회 계약(구현명세 10장)과 오류·권한(AT61-13),
조회가 이력을 만들지 않는 것(AT61-09), 보고 결말(AT61-14). **SQLite·Postgres 양쪽**이다(장면 1~5
저장소와 같은 DB의 다른 테이블).
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
from app.sc04.process import Sc04Process
from app.sc05 import demo as sc05_demo
from app.sc05.process import Sc05Process
from app.sc06 import confirm, demo, domain
from app.sc06.api import build_router
from app.sc06.process import PROCESS_PATH, Sc06Process
from app.sc06.view import topology
from app.store import build_postgres_backend

PREFIXES = ("sc01", "sc02", "sc03", "sc04", "sc05", "sc06")
TABLES = ", ".join(f"{p}_demo_run, {p}_history" for p in PREFIXES)
RV = "/sc06/demo-runs/{rid}/reviews/RV61"


@pytest.fixture(params=["sqlite", "postgres"])
def proc(request) -> Iterator[Sc06Process]:
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
    sc02 = Sc02Process(stores[1], Sc01Process(stores[0], inline_agent=True))
    sc05 = Sc05Process(stores[4], Sc04Process(stores[3], Sc03Process(stores[2], sc02)))
    try:
        yield Sc06Process(stores[5], sc05)
    finally:
        if backend is not None:
            with backend.pool.connection() as conn:
                conn.execute(f"TRUNCATE {TABLES}")
            backend.close()


@pytest.fixture
def client(proc: Sc06Process) -> TestClient:
    app = FastAPI()
    app.include_router(build_router(proc, Hub()))
    return TestClient(app)


def opened(client: TestClient) -> str:
    """
    적재하고 확인 절차를 각본으로 끝까지(대표 보고) — 조회 계약은 보고가 끝난 시점(1/14 11:00)이다.
    """
    r = client.post("/sc06/demo-runs", json={"executor": "embedded"})
    assert r.status_code == 201, r.text
    rid = r.json()["demoRunId"]
    for i in range(len(demo.steps_for())):
        step = client.post(f"/sc06/demo-runs/{rid}/script/{i}")
        assert step.status_code == 200, step.text
    return rid


def reported(proc: Sc06Process) -> dict:
    doc = proc.create()
    for i in range(len(demo.steps_for())):
        doc = demo.run_step(proc, doc["demo_run_id"], i)
    return doc


def get(client: TestClient, path: str, actor: str | None = "u-fin", **params):
    headers = {"x-demo-actor": actor} if actor else {}
    return client.get(path, headers=headers, params=params)


# ─────────────────────────── 적재 ───────────────────────────


def test_opening_runs_scene5_to_handoff51_then_loads_rv61(proc: Sc06Process) -> None:
    """
    장면 5가 없으면 장면 1부터 각본을 실제로 돌려 HANDOFF51까지 간 뒤 적재한다. 같은 데모 실행 id다.
    적재 직후는 **확인 전**이다 — 숫자는 있고 보고본은 DRAFT, 확인 기록은 없다.
    """
    doc = proc.create()
    rid = doc["demo_run_id"]
    sc05 = proc.sc05.get(rid)
    assert sc05["handoff"]["handoff_id"] == "HANDOFF51" and sc05["official"] == "FC51"
    assert doc["clock"] == confirm.START_AT and doc["report"]["report_version"] == "RPT61-v1"
    assert doc["report"]["state"] == "DRAFT" and doc["report_records"] == {}
    assert doc["calculations"]["CALC61-v1"]["totals"]["actual_krw"] == 87_000_000
    assert doc["batch"]["seed_id"] == "SYN-SC06-v0.6" and len(doc["batch"]["sha256"]) == 64
    assert doc["batch"]["counts"]["orders"] == 180 and doc["batch"]["problems"] == []
    # 다시 열어도 다시 적재하지 않는다(동일 키 중복 생성 없음)
    again = proc.create(sc01_demo_run_id=rid)
    assert again["created_at"] == doc["created_at"]
    assert len(proc.store.history(rid)) == 1


def test_opening_after_a_partial_scene5_finishes_it_first(proc: Sc06Process) -> None:
    """장면 5가 도중이면 남은 각본을 실행해 완료까지 간다 — 지름길로 「완료됨」을 만들지 않는다."""
    sc05 = proc.sc05.create(executor="embedded")
    rid = sc05["demo_run_id"]
    for i in range(3):
        sc05_demo.run_step(proc.sc05, rid, i)
    doc = proc.create(sc01_demo_run_id=rid)
    assert proc.sc05.get(rid)["handoff"] is not None and doc["demo_run_id"] == rid


def test_unknown_case_is_refused(proc: Sc06Process) -> None:
    """예외 X61-*는 시험 fixture로만 적재한다 — 시연 사례로 열지 않는다."""
    with pytest.raises(DomainError) as err:
        proc.create(case_id="X61-01")
    assert err.value.status == 422


# ─────────────────────────── 조회 계약 (구현명세 10장) ───────────────────────────


def test_summary_contract(client: TestClient) -> None:
    """U601 — 모든 응답의 문맥 칸, 3과제·합계, 완료 판단, Agent 요약(AG61·63)."""
    rid = opened(client)
    r = get(client, RV.format(rid=rid) + "/summary", report_version="RPT61-v1")
    assert r.status_code == 200, r.text
    s = r.json()
    for key in ("review_id", "report_version", "calculation_version", "as_of", "data_status"):
        assert s[key] is not None, key
    assert (s["review_id"], s["report_version"], s["as_of"], s["data_status"]) == (
        "RV61",
        "RPT61-v1",
        "2028-01-14T11:00:00+09:00",
        "COMPLETE",
    )
    assert [t["task_id"] for t in s["tasks"]] == ["ACT41", "ACT42", "ACT43"]
    act42 = s["tasks"][1]
    assert act42["focus"] and act42["performance"] == "일부 기대 미달"
    assert act42["activity_judgment"] == "COMPLETION_CONFIRMED"
    assert {
        k: act42[k] for k in ("expected_krw", "actual_krw", "variance_krw", "calculation_status")
    } == {
        "expected_krw": 30_600_000,
        "actual_krw": 25_800_000,
        "variance_krw": -4_800_000,
        "calculation_status": "CONFIRMED",
    }
    assert s["totals"]["actual_krw"] == 87_000_000 and s["newer_calculation"] is None
    assert [a["run_id"] for a in s["agent"]] == ["AG61", "AG63"]
    assert all(a["mode"] == "REPLAY" and a["state"] == "HUMAN_REVIEWED" for a in s["agent"])
    assert s["data_close"] == "2028-01-07T18:00:00+09:00"


def test_variance_contract(client: TestClient) -> None:
    """
    AT61-03·04 — 원인별 건수·비용(실제 긴급비), 대표 주문 PO61-1103: 대행 10:00 확인 · 요구 11/14 ·
    정상 11/16, AG62.
    """
    rid = opened(client)
    v = get(client, RV.format(rid=rid) + "/tasks/ACT42/variance").json()
    assert {g["cause"]: (g["count"], g["actual_urgent_cost_krw"]) for g in v["cause_groups"]} == {
        "INTERNAL": (4, 4_800_000),
        "SUPPLY": (9, 10_800_000),
        "MIXED": (1, 1_200_000),
    }
    assert v["cause_total"] == {"count": 14, "actual_urgent_cost_krw": 16_800_000}
    assert v["variance_krw"] == -4_800_000
    assert v["order"]["order_id"] == "PO61-1103" and v["order"]["approver"]["account"] == "EX-BUY"
    assert v["order"]["approved_at"] <= v["order"]["ordered_at"]
    ch = v["change"]
    assert (ch["shared_at"], ch["confirmed_at"]) == (
        "2027-11-12T09:20:00+09:00",
        "2027-11-12T10:00:00+09:00",
    )
    assert (ch["required_at"], ch["supply_at"]) == (
        "2027-11-14T09:00:00+09:00",
        "2027-11-16T09:00:00+09:00",
    )
    assert (ch["confirm_minutes"], ch["cause"]) == (40, "SUPPLY")
    ag = v["agent"]
    assert (
        ag["run_id"] == "AG62"
        and ag["candidate_cause"] == "INTERNAL"
        and ag["state"] == "HUMAN_REVIEWED"
    )
    assert "대행 로그 미결합" in ag["input_scope"] and ag["reviewed_by"]["account"] == "USR-BUY"
    assert ag["reviewed_at"] == "2028-01-10T11:00:00+09:00"
    assert len(v["urgent_orders"]) == 14 and v["evidence"] == ["E61-1103"]


def test_evidence_contract(client: TestClient) -> None:
    """근거 본문·작성/확인 이력 — 가상 증빙이다. E61-1103 작성자는 대행 USR-BUY2다."""
    rid = opened(client)
    e = get(client, f"/sc06/demo-runs/{rid}/evidence/E61-1103").json()
    assert e["virtual"] and e["written_by"]["account"] == "USR-BUY2" and "대행" in e["body"]
    assert e["checked_by"]["account"] == "EX-BUY" and e["report_version"] == "RPT61-v1"


def test_report_contract(client: TestClient) -> None:
    """
    U602 · AT61-14 — 결론·확인 다섯 단계(같은 버전)·후속 FUP61·PROP61·FUP62·RISK61·다음 보고
    2/11·연간 FC51 그대로.
    """
    rid = opened(client)
    rep = get(client, f"/sc06/demo-runs/{rid}/reports/RPT61-v1").json()
    assert rep["state"] == "REPORTED" and rep["problems"] == []
    assert [c["record_id"] for c in rep["confirmations"]] == [
        "CF61-P",
        "CF61-B",
        "CF61-F",
        "CF61-R",
        "CF61-M",
    ]
    assert {c["version"] for c in rep["confirmations"]} == {"RPT61-v1"}
    assert rep["confirmations"][3]["actor"]["account"] == "USR-CFO"
    assert "87.0백만원" in rep["conclusion"]["content"]
    assert rep["conclusion"]["actor"]["account"] == "USR-FIN"
    assert [f["followup_id"] for f in rep["followups"]] == ["FUP61", "PROP61", "FUP62", "RISK61"]
    prop = rep["followups"][1]
    assert (
        prop["state"] == "PROPOSED"
        and prop["effect"]["krw"] is None
        and prop["budget"]["krw"] is None
    )
    assert rep["next_review"] == "2028-02-11T10:00:00+09:00" and rep["risk"]["state"] == "OPEN"
    assert rep["annual"] == {
        "official": "FC51",
        "annual": "3428986680",
        "target": "3477290000",
        "gap": "48303320",
    }
    assert rep["quarter_profit"]["quarter"]["profit"] == 902_868_880
    assert (
        rep["judgment"]["judgment_state"] == "REVIEWABLE"
        and rep["judgment"]["collection_state"] == "PARTIAL"
    )


# ─────────────────────────── 오류 · 권한 · 멱등 (AT61-09·13) ───────────────────────────


def test_access_denied_without_reader_role(client: TestClient) -> None:
    """
    AT61-13 — 검토건 밖의 역할(영업)·헤더 없음은 403 ACCESS_DENIED. 오류에 근거·금액을 싣지 않는다.
    """
    rid = opened(client)
    for path in (
        RV.format(rid=rid) + "/summary",
        RV.format(rid=rid) + "/tasks/ACT42/variance",
        f"/sc06/demo-runs/{rid}/evidence/E61-1103",
        f"/sc06/demo-runs/{rid}/reports/RPT61-v1",
    ):
        for actor in ("u-sales", None):
            r = get(client, path, actor=actor)
            assert r.status_code == 403, path
            detail = r.json()["detail"]
            assert detail["error_code"] == "ACCESS_DENIED"
            assert "000" not in detail["message"] and "대행" not in detail["message"]


def test_version_and_not_found(client: TestClient) -> None:
    """
    409 VERSION_MISMATCH(다른 보고 버전) · 404 NOT_FOUND(검토건·근거·데모 실행 없음, ACT41 상세).
    """
    rid = opened(client)
    r = get(client, RV.format(rid=rid) + "/summary", report_version="RPT61-v2")
    assert r.status_code == 409 and r.json()["detail"]["error_code"] == "VERSION_MISMATCH"
    assert get(client, f"/sc06/demo-runs/{rid}/reports/RPT61-v2").status_code == 409
    for path in (
        f"/sc06/demo-runs/{rid}/reviews/RV99/summary",
        f"/sc06/demo-runs/{rid}/evidence/DOC99",
        RV.format(rid=rid) + "/tasks/ACT41/variance",
        RV.format(rid="nope") + "/summary",
    ):
        r = get(client, path)
        assert r.status_code == 404, path
        assert r.json()["detail"]["error_code"] == "NOT_FOUND"


def test_reads_are_idempotent_and_record_nothing(client: TestClient, proc: Sc06Process) -> None:
    """
    AT61-09·13 — 왕복·새로고침 조회가 확인·승인·과제 등록 이력을 만들지 않는다. 문서·이력·감사가
    그대로다.
    """
    rid = opened(client)
    before = proc.store.load(rid)
    seen = len(proc.store.history(rid))
    paths = [
        RV.format(rid=rid) + "/summary",
        RV.format(rid=rid) + "/tasks/ACT42/variance",
        f"/sc06/demo-runs/{rid}/evidence/DOC61-JDG",
        f"/sc06/demo-runs/{rid}/reports/RPT61-v1",
    ]
    first = [get(client, p).json() for p in paths]
    for _ in range(2):
        assert [get(client, p).json() for p in paths] == first
    after = proc.store.load(rid)
    assert after == before and len(proc.store.history(rid)) == seen
    assert after[0]["audit"] == before[0]["audit"]
    assert after[0]["report"]["state"] == "REPORTED"
    assert after[0]["followups"]["PROP61"]["state"] == "PROPOSED"


def test_scene5_studio_run_is_not_driven(proc: Sc06Process) -> None:
    """장면 5가 Studio 시험 실행이면 각본이 답할 수 없다 — Studio에서 끝낸 뒤 연다(409)."""
    sc05 = proc.sc05.create(executor="embedded")
    proc.sc05.reset(sc05["demo_run_id"], actor="u-demo", executor="studio")
    with pytest.raises(DomainError) as err:
        proc.create(sc01_demo_run_id=sc05["demo_run_id"])
    assert err.value.status == 409


def test_unloaded_demo_run_is_404_for_meta(client: TestClient, proc: Sc06Process) -> None:
    """화면은 장면 6을 저절로 열지 않는다 — 없으면 404를 받고 「장면 6 열기」를 묻는다."""
    sc05 = proc.sc05.create(executor="embedded")
    r = client.get(f"/sc06/demo-runs/{sc05['demo_run_id']}")
    assert r.status_code == 404 and r.json()["detail"]["error_code"] == "NOT_FOUND"


def test_reader_roles_cover_the_review_participants() -> None:
    """
    확인·판단·보고에 나오는 계정은 모두 볼 수 있다(USR-FIN·CFO·CEO·BUY·BUY2·PROD·EX-BUY·EX-PROD).
    """
    for account in (
        "USR-FIN",
        "USR-CFO",
        "USR-CEO",
        "USR-BUY",
        "USR-BUY2",
        "USR-PROD",
        "EX-BUY",
        "EX-PROD",
    ):
        assert domain.ACCOUNTS[account] in domain.READERS, account
    assert "u-sales" not in domain.READERS and "u-sales-exec" not in domain.READERS


# ─────────────────────────── 확인 절차 (BPM · 업무설계표 S11~S13) ───────────────────────────


def test_confirmation_procedure_reproduces_the_sc06_report_sheet(proc: Sc06Process) -> None:
    """
    각본(SC06보고의 글)으로 착수 → 담당 임원 확인 2 → 종합 → 결론 → 확정 → 대표 보고를 끝까지 돌리면
    확인 기록 일곱 건이 시트와 같다(행위자·시각·상태·글·근거). 보고본이 산정 CALC61-v1에 묶이고
    문제가 없다.
    """
    doc = reported(proc)
    assert doc["bpm"]["state"] == "done" and "End" in doc["bpm"]["visited"]
    assert doc["report"]["state"] == "REPORTED" and doc["report"]["problems"] == []
    assert doc["report"]["calculation_version"] == "CALC61-v1"
    assert doc["report"]["finalized_at"] == "2028-01-13T17:00:00+09:00"
    assert doc["clock"] == "2028-01-14T11:00:00+09:00"
    fields = ("version", "step", "actor", "at", "state", "content", "refs")
    assert set(doc["report_records"]) == set(doc["schedule"])
    for record_id, planned in doc["schedule"].items():
        got = doc["report_records"][record_id]
        assert {f: got[f] for f in fields} == {f: planned[f] for f in fields}, record_id
    tasks = sorted(doc["tasks"].values(), key=lambda t: t["seq"])
    assert [t["assigned_to"] for t in tasks] == [s["user"] for s in confirm.NODE_ROLES.values()]
    assert all(t["status"] == "COMPLETED" and not t["opened_late"] for t in tasks)
    # 보고 확정 ≠ 과제 실행 승인 ≠ 위험 종결 — 후속·위험·FC51은 그대로다
    assert doc["risk"]["state"] == "OPEN" and doc["followups"]["PROP61"]["state"] == "PROPOSED"


def test_only_the_assignee_answers_each_approval(proc: Sc06Process) -> None:
    """결재마다 그 담당만 — 다른 임원·시연관리자는 403(입력은 그대로, 대기도 그대로)."""
    rid = proc.create()["demo_run_id"]
    demo.run_step(proc, rid, 0)
    answer = demo.steps_for()[1].answer
    for actor in ("u-buy-exec", "u-fin-exec", "u-demo"):
        with pytest.raises(DomainError) as err:
            proc.act(rid, "Confirm_Prod", answer, actor=actor)
        assert err.value.status == 403, actor
    with pytest.raises(DomainError) as starter:
        proc.start(proc.create()["demo_run_id"], actor="u-prod-exec")
    assert starter.value.status == 403
    assert proc.get(rid)["report_records"] == {}


def test_finalize_is_blocked_when_the_conclusion_numbers_differ(proc: Sc06Process) -> None:
    """
    CT611 — 결론의 「…백만원」이 산정과 다르면 확정이 422 REPORT_INVALID와 남은 항목이다(아무것도
    남기지 않는다). 보완 요청으로 결론을 다시 쓰면 앞 결론은 이력에 남고 확정된다.
    """
    rid = proc.create()["demo_run_id"]
    steps = demo.steps_for()
    for i in range(4):
        demo.run_step(proc, rid, i)
    wrong = steps[4].answer["보고결론"].replace("87.0백만원", "88.0백만원")
    proc.act(rid, "Draft_Conclusion", {"보고결론": wrong, "결론근거": ""}, actor="u-fin")
    with pytest.raises(confirm.PrerequisiteError) as blocked:
        proc.act(rid, "Finalize_Report", steps[5].answer, actor="u-fin-exec")
    assert blocked.value.code == "REPORT_INVALID"
    assert any("88.0" in item for item in blocked.value.items)
    doc = proc.get(rid)
    assert doc["report"]["state"] == "DRAFT" and "CF61-R" not in doc["report_records"]
    proc.act(
        rid,
        "Finalize_Report",
        {"확정결정": "보완요청", "확정내용": "결론 숫자가 산정과 다르다", "남는사항": ""},
        actor="u-fin-exec",
    )
    doc = proc.get(rid)
    assert "TXT61" not in doc["report_records"]
    assert doc["record_history"][-1]["content"] == wrong
    assert [p["node_id"] for p in doc["bpm"]["snapshot"]["pendings"].values()] == [
        "Draft_Conclusion"
    ]
    proc.act(rid, "Draft_Conclusion", steps[4].answer, actor="u-fin")
    proc.act(rid, "Finalize_Report", steps[5].answer, actor="u-fin-exec")
    assert proc.get(rid)["report"]["state"] == "FINALIZED"


def test_reconfirm_request_sends_both_owner_confirmations_back(proc: Sc06Process) -> None:
    """
    종합 확인의 재확인 요청 — 두 담당 임원 확인이 이력으로 가고 다시 열린다. 종합은 둘이 끝나야
    한다.
    """
    rid = proc.create()["demo_run_id"]
    steps = demo.steps_for()
    for i in range(3):
        demo.run_step(proc, rid, i)
    proc.act(
        rid,
        "Review_Finance",
        {"종합결정": "재확인요청", "종합내용": "ACT42 확인 범위에 JDG61 미비를 적는다"},
        actor="u-fin-exec",
    )
    doc = proc.get(rid)
    assert doc["report_records"] == {}
    assert [h["record_id"] for h in doc["record_history"]] == ["CF61-F", "CF61-P", "CF61-B"]
    waiting = sorted(p["node_id"] for p in doc["bpm"]["snapshot"]["pendings"].values())
    assert waiting == ["Confirm_Buy", "Confirm_Prod"]
    assert {t["task_id"] for t in doc["tasks"].values() if t["status"] != "COMPLETED"} == {
        "TASK-CONFIRM_PROD-2",
        "TASK-CONFIRM_BUY-2",
    }
    proc.act(rid, "Confirm_Prod", steps[1].answer, actor="u-prod-exec")
    with pytest.raises(DomainError) as early:
        proc.precheck(proc.get(rid), "Review_Finance", steps[3].answer, "u-fin-exec")
    assert early.value.status == 409
    proc.act(rid, "Confirm_Buy", steps[2].answer, actor="u-buy-exec")
    proc.act(rid, "Review_Finance", steps[3].answer, actor="u-fin-exec")
    assert proc.get(rid)["report_records"]["CF61-F"]["state"] == "CONFIRMED"


def test_reset_returns_to_before_confirmation_and_keeps_the_load(proc: Sc06Process) -> None:
    """
    초기화는 확인 절차만 되돌린다 — 적재(숫자·근거)는 같다. 지난 확인 기록은 이력 테이블에 남는다.
    """
    doc = reported(proc)
    rid = doc["demo_run_id"]
    with pytest.raises(DomainError) as role:
        proc.reset(rid, actor="u-fin")
    assert role.value.status == 403
    back = proc.reset(rid, actor="u-demo", executor="embedded")
    assert back["report"]["state"] == "DRAFT" and back["report_records"] == {}
    assert back["scene_info"]["started_at"] is None and back["bpm"] is None
    assert (
        back["calculations"]["CALC61-v1"]["calculation_hash"]
        == (doc["calculations"]["CALC61-v1"]["calculation_hash"])
    )
    assert any(h["report"]["state"] == "REPORTED" for h in _snapshots(proc, rid))
    assert reported_again(proc, rid)["report"]["state"] == "REPORTED"


def _snapshots(proc: Sc06Process, rid: str) -> list[dict]:
    return [proc.store.at(rid, h["seq"]) for h in proc.store.history(rid)]


def reported_again(proc: Sc06Process, rid: str) -> dict:
    doc = proc.get(rid)
    for i in range(len(demo.steps_for())):
        doc = demo.run_step(proc, rid, i)
    return doc


def test_every_user_task_has_a_role_and_matching_assignees() -> None:
    """NODE_ROLES와 BPMN이 갈라지면 화면 역할 검사와 결재 담당자가 어긋난다."""
    process = read_process(PROCESS_PATH.read_bytes())
    users = [n.id for n in process.all_nodes() if n.kind == "userTask"]
    assert sorted(users) == sorted(confirm.NODE_ROLES)
    for node_id in users:
        assignees = process.node(node_id).prop("approval").assignees
        assert assignees == [USERS[confirm.NODE_ROLES[node_id]["user"]]["name"]], node_id


def test_http_procedure_routes(client: TestClient) -> None:
    """착수·결재·각본은 장면 1~5와 같은 경로다. 결재 폼 칸의 기본값은 데이터의 확인 기록이다."""
    r = client.post("/sc06/demo-runs", json={"executor": "embedded"})
    rid = r.json()["demoRunId"]
    assert r.json()["status"]["procedure"] == "PENDING"
    started = client.post(f"/sc06/demo-runs/{rid}/start", headers={"x-demo-actor": "u-fin"})
    assert started.status_code == 200, started.text
    head = started.json()
    assert head["status"]["procedure"] == "CONFIRMING" and head["answerHere"]
    waiting = {w["nodeId"]: w for w in head["bpm"]["waiting"]}
    assert set(waiting) == {"Confirm_Prod", "Confirm_Buy"}
    prod = {f["key"]: f.get("default") for f in waiting["Confirm_Prod"]["fields"]}
    assert prod == {"생산확인내용": "ACT41 완료·Q4 효과 확인", "생산확인근거": "DOC61-PROD"}
    denied = client.post(
        f"/sc06/demo-runs/{rid}/actions/Confirm_Prod",
        json={"answer": {"생산확인내용": "x", "생산확인근거": "y"}},
        headers={"x-demo-actor": "u-buy-exec"},
    )
    assert denied.status_code == 403
    for i in range(1, 5):
        assert client.post(f"/sc06/demo-runs/{rid}/script/{i}").status_code == 200
    blocked = client.post(
        f"/sc06/demo-runs/{rid}/actions/Finalize_Report",
        json={"answer": {"확정결정": "확정", "확정내용": "확정", "남는사항": ""}},
        headers={"x-demo-actor": "u-fin-exec"},
    )
    assert blocked.status_code == 422
    assert [
        s["recordId"] for s in client.get(f"/sc06/demo-runs/{rid}").json()["procedure"]["steps"]
    ] == [
        "CF61-P",
        "CF61-B",
        "CF61-F",
        "TXT61",
        "CF61-R",
        "CF61-M",
    ]
    topo = client.get("/sc06/process").json()
    assert {n["recordOf"] for n in topo["nodes"] if n["recordOf"]} == set(confirm.NODE_ROLES)
    assert [s["code"] for s in client.get("/sc06/script").json()] == [
        "D601",
        "D602",
        "D603",
        "D604",
        "D605",
        "D606",
        "D607",
    ]


def test_ts_topology_fixture_is_the_bpmn(proc: Sc06Process) -> None:
    """
    화면 테스트의 토폴로지 사본(`tests/fixtures/sc06-process.json`) = BPMN. BPMN을 고치면 실패한다 —
    다시 만든다: `curl -s localhost:8077/sc06/process | python3 -m json.tool --indent 1 >
    tests/fixtures/sc06-process.json`
    """
    fixture = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sc06-process.json"
    assert json.loads(fixture.read_text(encoding="utf-8")) == topology(proc.process)
