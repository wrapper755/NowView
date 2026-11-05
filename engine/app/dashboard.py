"""
회사 대시보드 — 회사·세계(시연 회차)·업무별 운영 현황(`GET /companies/{회사}/dashboard`).

NowView 웹에 남은 회사 화면은 이것 하나다(2026-11-03 4단계, `docs/role-split.md`). 업무 판단
화면·해설·업무 설명은 회사 사이트(`/work/{회차}/sc0N`)에 있고 대시보드는 그리로 잇는다. 업무마다
싣는 것:

* **BPM 진행** — 실행 상태, 지나온 결재 수 / 그림의 결재 수, 지금 열린 결재(제목·역할).
* **일꾼 일감** — 회사 시스템의 일감 기록(`worker-log`, 사이트 자동 모드가 읽는 것과 같다).
  엔진 메모리의 최근 일감(관리자 모드)은 다시 뜨면 비고 토픽·실행 id까지 있어 공개하지 않는다.
* **핵심 지표** — 숫자는 규칙 계산 그대로다. 회사 시스템에 적는 경영 기록
  (`app/sc0N/records.py`의 `records_of`)에서 고르기만 한다 — 대시보드와 회사 사이트가 같은
  숫자를 보인다. 아직 없으면 `null`(미산출)이다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from app.companies import SCENE_WORKS

log = logging.getLogger("nowview.dashboard")

Record = dict[str, Any]
Metric = dict[str, Any]


def _latest(found: list[Record], kind: str, record_id: str | None = None) -> Record | None:
    """그 종류의 마지막 기록 — `records_of`는 문서 순서(`domain.ordered`)로 낸다."""
    rows = [
        r for r in found if r["kind"] == kind and (record_id is None or r["record_id"] == record_id)
    ]
    return rows[-1]["body"] if rows else None


def _dig(body: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(body, dict):
            return None
        body = body.get(key)
    return body


def _krw(label: str, value: Any, *, signed: bool = False) -> Metric:
    shown = None if value is None else str(value)
    return {"label": label, "kind": "krw", "value": shown, "signed": signed}


def _text(label: str, value: Any) -> Metric:
    return {"label": label, "kind": "text", "value": None if value is None else str(value)}


def _sc01(found: list[Record]) -> list[Metric]:
    board = _latest(found, "dashboard") or {}
    year = _dig(board, "totals", "연간") or {}
    shown = board.get("review") or board.get("approved")
    return [
        _krw(f"연간 공장관리손익 ({shown or '전망'})", _dig(year, shown or "", "mgmtProfit")),
        _krw("목표 대비", _dig(board, "gaps", "연간", "targetGap"), signed=True),
        _krw("이번 사건 영향", _dig(board, "gaps", "연간", "eventImpact"), signed=True),
    ]


def _sc02(found: list[Record]) -> list[Metric]:
    run = _latest(found, "price_run") or {}
    return [
        _krw("12개월 원가 증가", _dig(run, "result", "next12", "increase")),
        _krw("협상 감소", _dig(run, "result", "comparison", "reduction")),
    ]


def _sc03(found: list[Record]) -> list[Metric]:
    year = _dig(_latest(found, "analysis_run"), "result", "periods", "year") or {}
    return [
        _krw("통합 손익 (연간)", year.get("combined")),
        _krw("목표 대비 부족", year.get("total_gap")),
    ]


def _sc04(found: list[Record]) -> list[Metric]:
    snapshot = _dig(_latest(found, "handoff"), "handoff", "financial_snapshot") or {}
    effect = snapshot.get("effect")
    if effect is None:
        effect = _dig(_latest(found, "effect_run"), "result", "periods", "year", "effect")
    return [
        _krw("개선 효과 (연간)", effect),
        _krw("남는 부족", snapshot.get("gap")),
    ]


def _sc05(found: list[Record]) -> list[Metric]:
    run = _latest(found, "forecast_run") or {}
    return [
        _krw("전망 손익 (연간)", run.get("annual")),
        _krw("남는 부족", run.get("gap")),
    ]


def _sc06(found: list[Record]) -> list[Metric]:
    totals = _dig(_latest(found, "review_summary"), "totals") or {}
    return [
        _krw("Q4 기대 효과", totals.get("expected_krw")),
        _krw("확인 효과", totals.get("actual_krw")),
        _krw("차이", totals.get("variance_krw"), signed=True),
    ]


def _sc07(found: list[Record]) -> list[Metric]:
    state = _dig(_latest(found, "application"), "state") or {}
    return [_text("적용 상태", state.get("label") or state.get("state"))]


def _s2sc01(found: list[Record]) -> list[Metric]:
    board = _latest(found, "dashboard") or {}
    kpi = board.get("kpi") or {}
    kri = board.get("kri") or {}
    rate = kpi.get("otd")
    shown = None if rate is None else f"{float(rate) * 100:.0f}%"
    return [
        _text(f"납기준수율 ({_dig(kpi, 'period', 'label') or '마감기간'})", shown),
        _text(
            "OTD 목표", None if kpi.get("target") is None else f"{float(kpi['target']) * 100:.0f}%"
        ),
        _text("공급 경보", None if not board else f"{kri.get('alerts', 0)}건"),
        _text("영향 납기약정", None if not board else f"{kri.get('affected_commitments', 0)}건"),
    ]


METRICS: dict[int, Callable[[list[Record]], list[Metric]]] = {
    1: _sc01,
    2: _sc02,
    3: _sc03,
    4: _sc04,
    5: _sc05,
    6: _sc06,
    7: _sc07,
    21: _s2sc01,
}


def _records(scene: int, proc: Any, doc: dict) -> list[Record]:
    from app.sc01 import records as r1
    from app.sc02 import records as r2
    from app.sc03 import records as r3
    from app.sc04 import records as r4
    from app.sc05 import records as r5
    from app.sc06 import records as r6
    from app.sc07 import records as r7

    if scene == 1:
        return r1.records_of(doc, proc.seed)
    if scene == 21:
        from app.s2.sc01 import records as s21

        return s21.records_of(doc, proc.master())
    return {2: r2, 3: r3, 4: r4, 5: r5, 6: r6, 7: r7}[scene].records_of(doc)


def _approvals(proc: Any) -> set[str]:
    return {n.id for n in proc.process.all_nodes() if n.kind == "userTask"}


def work(scene: int, proc: Any, doc: dict | None) -> dict[str, Any]:
    """업무 하나 — 장면 문서가 없으면 시작 전(`none`)이다."""
    head: dict[str, Any] = {"scene": scene, "work": SCENE_WORKS[scene]}
    if doc is None:
        empty: dict[str, Any] = {"progress": None, "waiting": [], "metrics": []}
        return {**head, "state": "none", "clock": None, **empty}
    approvals = _approvals(proc)
    bpm = doc.get("bpm") or {}
    visited = set(bpm.get("visited") or [])
    found: list[Record] = []
    try:
        found = _records(scene, proc, doc)
        metrics = METRICS[scene](found)
    except Exception:  # 지표는 부수적이다 — 한 업무의 문서가 낡아도 대시보드 전체가 죽지 않게
        log.exception("장면 %s 지표를 짓지 못했다 (%s)", scene, doc.get("demo_run_id"))
        metrics = []
    if scene == 21:
        return {**head, **_s2_runs(doc), "metrics": metrics, "board": _latest(found, "dashboard")}
    waiting = [
        {"nodeId": w.get("node_id"), "title": w.get("title")}
        for w in bpm.get("waiting") or []
        if w.get("node_id") in approvals
    ]
    return {
        **head,
        "state": bpm.get("state") or "not_started",
        "clock": doc.get("clock"),
        "progress": {"approvals": len(approvals), "passed": len(visited & approvals)},
        "waiting": waiting,
        "metrics": metrics,
    }


def _s2_runs(doc: dict) -> dict[str, Any]:
    """
    시나리오 2 장면 1 — 개정 하나 = 실행 하나라 실행이 여럿이다. 결재가 없다(조회만). 흐름 끝은
    장면 2 인계가
    났을 때다.
    """
    runs = [r["run"] for r in doc.get("receipts", {}).values()]
    state = "not_started"
    if doc.get("handoff"):
        state = "done"
    elif any(r.get("state") == "running" for r in runs) or runs:
        state = "running"
    return {
        "state": state,
        "clock": doc.get("clock"),
        "progress": {"approvals": 0, "passed": 0, "runs": len(runs)},
        "waiting": [],
    }


def worker_entries(rows: list[dict[str, Any]], scene: int, limit: int = 5) -> dict[str, Any]:
    """그 장면의 일감 기록 — 건수·실패 수·최근 몇 건(새것이 앞)."""
    mine = [r for r in rows if r.get("scene") == scene]
    return {
        "count": len(mine),
        "failed": sum(1 for r in mine if not r.get("ok")),
        "recent": [
            {
                "at": r.get("at"),
                "operation": r.get("operation"),
                "ok": bool(r.get("ok")),
                "reason": r.get("reason"),
            }
            for r in reversed(mine[-limit:])
        ],
    }
