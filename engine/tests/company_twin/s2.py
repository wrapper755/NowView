"""
시나리오 2(OTD — 납기) 회사 자료와 세계 기록 — 장면 1 「납기 위험 조기 감지」.

NowView `docs/platform.md`(공통 플랫폼)·`docs/s2/sc01.md`. 자료는
`seed/SYN-S2-SC01-v0.1.xlsx`(통합가상데이터 v0.1)의 **원천 칸만** 읽는다 — 파생
칸(마감판정·사용 가능 예정·착수차질·판정)은 NowView 규칙 계산이 내고 시험이 대조한다.

* `GET /company/s2/master` — 불변 회사 자료: 납기약정(M04·M05 — 10월 마감 100건 +
  11월 시연 8건, 미래 인수는 `null`), 생산 소요(주문영향의 원천 칸 — 약정 × 부품·
  세트당 소요·추가 가용재고·기존 조립 착수·정기차 마감, M28), 배경 부품 입고 예정
  (모델별 별도 발주의 최신 단일 예정), 구매 개정 원천(발주행 PO-P-01의 개정 0·1·2).
* `POST /worlds/{w}/sim/receipt-revisions {fixture_id}` — (시연) 구매시스템에 개정이
  등록됐다. 세계 시각에 수신함에 들어간다. 같은 개정을 다시 보내면 기존 접수다
  (사이트 자동 모드가 「이미 보냈나」를 이것으로 본다).
* `GET /worlds/{w}/receipt-revisions/inbox?after=` · `…/receipt-revisions/{doc_id}`.

이 파일은 NowView 엔진 시험의 기간계 쌍둥이(`engine/tests/company_twin/s2.py`)에
**그대로** 복사한다 — 자료 위치를 두 자리에서 찾는다(`_workbook`).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

KST = timezone(timedelta(hours=9))
SCENARIO = "s2"
NAME = "SYN-S2-SC01-v0.1.xlsx"
#: 시나리오 2 회차의 처음 시각 — 최초 입고예정(P-v0) 등록 전. 시연은 11/2 → 11/3 →
#: 11/4 09:00 개정을 차례로 보낸다.
S0_CLOCK = datetime(2026, 11, 2, 8, 0, tzinfo=KST).isoformat()


#: 납기약정의 역할 — 마감(10월 실적) · 대표(S·R) · 배경(c·d·e, F04 demo_data_role)
ROLES = {"마감": "closed", "대표": "representative", "배경": "background"}


def _workbook() -> Path:
    here = Path(__file__).resolve()
    for root in (here.parents[1], here.parents[2]):  # 기간계 `legacy/seed/` · 쌍둥이 `engine/seed/`
        if (root / "seed" / NAME).exists():
            return root / "seed" / NAME
    raise FileNotFoundError(f"시나리오 2 자료가 없다: {NAME}")


def _at(value: Any) -> str | None:
    """
    엑셀 날짜(원천 현지 시각, 시간대 없음) → KST ISO. 빈칸은 None(0이나 지금으로
    지어내지 않는다).
    """
    if value is None or value == "":
        return None
    if not isinstance(value, datetime):
        raise ValueError(f"시각 칸이 날짜가 아니다: {value!r}")
    return value.replace(tzinfo=KST).isoformat()


def _rows(ws: Any) -> list[dict[str, Any]]:
    """4행이 머리, 5행부터 자료 — 첫 칸이 빈 행에서 멈춘다."""
    header = [c.value for c in ws[4]]
    out = []
    for row in ws.iter_rows(min_row=5, values_only=True):
        if row[0] is None:
            break
        out.append(dict(zip(header, row, strict=False)))
    return out


def _lot(lot: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in lot.items() if k != "source"}


@lru_cache(maxsize=1)
def master() -> dict[str, Any]:
    from openpyxl import load_workbook

    wb = load_workbook(_workbook(), data_only=True)
    commitments = [
        {
            "order_id": r["주문 ID"],
            "commitment_id": r["약정 ID"],
            "model": r["모델"],
            "plant": r["공장"],
            "product": r["제품"],
            "demo_role": ROLES[r["역할"]],
            "qty": int(r["약정수량"]),
            "promised_at": _at(r["고객 약정시각"]),
            "accepted_qty": None if r["인수수량"] in (None, "") else int(r["인수수량"]),
            "accepted_at": _at(r["실제 인수시각"]),
        }
        for r in _rows(wb["납기약정"])
    ]
    demand = [
        {
            "commitment_id": r["약정 ID"],
            "model": r["모델"],
            "part_id": r["소요 부품"],
            "per_set": int(r["세트당 소요"]),
            "extra_stock": int(r["추가 가용재고"]),
            "assembly_start": _at(r["기존 조립착수"]),
            "truck_cutoff": _at(r["정기차 마감"]),
        }
        for r in _rows(wb["주문영향"])
    ]
    lots = [
        {
            "lot_id": r["입고분 ID"],
            "source": r["원천 개정"],
            "part_id": r["부품"],
            "qty": int(r["예정수량"]),
            "planned_at": _at(r["입고 예정"]),
            "inspection_min": int(r["검수(분)"]),
        }
        for r in _rows(wb["입고분"])
    ]
    revisions = []
    for r in _rows(wb["입고개정"]):
        rid = r["원천 개정"]
        revisions.append(
            {
                "fixture_id": rid,
                "revision_id": rid,
                "po_line": r["발주행"],
                "revision_no": int(rid.rsplit("-v", 1)[1]),
                "scheduled_registration": _at(r["등록시각"]),
                "lots": [_lot(lot) for lot in lots if lot["source"] == rid],
            }
        )
    fixtures = {r["fixture_id"] for r in revisions}
    background = [
        {"po_line": lot["source"], **_lot(lot)} for lot in lots if lot["source"] not in fixtures
    ]
    return {
        "dataset_version": "SYN-S2-SC01-v0.1",
        "commitments": commitments,
        "demand": demand,
        "background_lots": background,
        "revisions": revisions,
    }


def new_world() -> dict[str, Any]:
    """시나리오 2 세계의 변하는 기록 — 구매 개정 수신함."""
    return {"receipt_seq": 0, "receipts": {}}


def summary(w: dict[str, Any]) -> dict[str, Any]:
    """세계 요약에 더하는 칸 — NowView 일꾼이 수신함 번호를 보고 새 개정을 들인다."""
    return {"receipt_revisions": len(w.get("receipts", {}))}


class ReceiptBody(BaseModel):
    fixture_id: str


def _doc_summary(d: dict[str, Any]) -> dict[str, Any]:
    keys = ("doc_id", "seq", "fixture_id", "revision_id", "po_line", "revision_no", "registered_at")
    return {k: d[k] for k in keys}


def mount(
    app: FastAPI,
    *,
    store: Any,
    world: Callable[[str], dict[str, Any]],
    auth: Callable[..., None],
) -> None:
    """시나리오 2 경로를 기간계 앱에 붙인다(기간계와 쌍둥이가 같은 함수를 쓴다)."""

    @app.get("/company/s2/master", dependencies=[Depends(auth)])
    def s2_master() -> dict[str, Any]:
        return master()

    @app.post(
        "/worlds/{world_id}/sim/receipt-revisions", status_code=201, dependencies=[Depends(auth)]
    )
    def purchase_registers(world_id: str, body: ReceiptBody) -> dict[str, Any]:
        """구매시스템에 입고예정 개정이 등록됐다 — 등록 시각은 세계 시각이다."""
        found = next((r for r in master()["revisions"] if r["fixture_id"] == body.fixture_id), None)
        if found is None:
            known = ", ".join(r["fixture_id"] for r in master()["revisions"])
            raise HTTPException(404, f"모르는 구매 개정: {body.fixture_id} (가능: {known})")
        with store.lock():
            w = world(world_id)
            w.setdefault("receipts", {})
            for d in w["receipts"].values():
                if d["fixture_id"] == body.fixture_id:
                    return {**_doc_summary(d), "created": False}
            w["receipt_seq"] = w.get("receipt_seq", 0) + 1
            doc_id = f"RCV-{w['receipt_seq']:04d}"
            w["receipts"][doc_id] = {
                "doc_id": doc_id,
                "seq": w["receipt_seq"],
                "fixture_id": body.fixture_id,
                "revision_id": found["revision_id"],
                "po_line": found["po_line"],
                "revision_no": found["revision_no"],
                "registered_at": w["clock"],
                "lots": found["lots"],
            }
            store.put(w)
        return {**_doc_summary(w["receipts"][doc_id]), "created": True}

    @app.get("/worlds/{world_id}/receipt-revisions/inbox", dependencies=[Depends(auth)])
    def receipt_inbox(world_id: str, after: int = 0) -> list[dict[str, Any]]:
        docs = sorted(world(world_id).get("receipts", {}).values(), key=lambda d: d["seq"])
        return [_doc_summary(d) for d in docs if d["seq"] > after]

    @app.get("/worlds/{world_id}/receipt-revisions/{doc_id}", dependencies=[Depends(auth)])
    def receipt(world_id: str, doc_id: str) -> dict[str, Any]:
        d = world(world_id).get("receipts", {}).get(doc_id)
        if d is None:
            raise HTTPException(404, f"없는 구매 개정 수신: {doc_id}")
        return d
