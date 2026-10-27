"""
SC06 적재와 조회 서비스 — 장면 5 인계에서 RV61을 여는 길, 조회 계약(구현명세 10장)과
오류·권한(AT61-13), 조회가 이력을
만들지 않는 것(AT61-09), 보고 결말(AT61-14). **SQLite·Postgres 양쪽**이다(장면 1~5 저장소와 같은
DB의 다른 테이블).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from conftest import require_postgres
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.sc01.domain import DomainError
from app.sc01.process import Sc01Process
from app.sc01.store import PostgresSc01Store, SqliteSc01Store
from app.sc02.process import Sc02Process
from app.sc03.process import Sc03Process
from app.sc04.process import Sc04Process
from app.sc05 import demo as sc05_demo
from app.sc05.process import Sc05Process
from app.sc06 import domain
from app.sc06.api import build_router
from app.sc06.process import Sc06Process
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
    app.include_router(build_router(proc))
    return TestClient(app)


def opened(client: TestClient) -> str:
    r = client.post("/sc06/demo-runs", json={"executor": "embedded"})
    assert r.status_code == 201, r.text
    return r.json()["demoRunId"]


def get(client: TestClient, path: str, actor: str | None = "u-fin", **params):
    headers = {"x-demo-actor": actor} if actor else {}
    return client.get(path, headers=headers, params=params)


# ─────────────────────────── 적재 ───────────────────────────


def test_opening_runs_scene5_to_handoff51_then_loads_rv61(proc: Sc06Process) -> None:
    """
    장면 5가 없으면 장면 1부터 각본을 실제로 돌려 HANDOFF51까지 간 뒤 적재한다. 같은 데모 실행 id다.
    """
    doc = proc.create()
    rid = doc["demo_run_id"]
    sc05 = proc.sc05.get(rid)
    assert sc05["handoff"]["handoff_id"] == "HANDOFF51" and sc05["official"] == "FC51"
    assert (
        doc["clock"] == "2028-01-14T11:00:00+09:00"
        and doc["report"]["report_version"] == "RPT61-v1"
    )
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
    assert after == before and len(proc.store.history(rid)) == 1
    assert [a["action"] for a in after[0]["audit"]] == ["sc06_loaded"]
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
