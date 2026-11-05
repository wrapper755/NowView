"""
시나리오 2(OTD — 납기) 회사 자료와 세계 기록 — 장면 1 「납기 위험 조기 감지」·장면 2 「정형통제
실행과 주문별 분기」.

NowView `docs/platform.md`(공통 플랫폼)·`docs/s2/sc01.md`·`docs/s2/sc02.md`. 자료는
`seed/SYN-S2-SC02-v0.2.xlsx`(SC01·SC02 통합가상데이터 v0.2 — 앞 7개 시트는 v0.1과 값이 같다)의
**원천 칸만** 읽는다 — 파생 칸(마감판정·사용 가능 예정·착수차질·판정, 장면 2의 제안 착수·종료·
출하 준비·이용 정기차·여유)은 NowView 규칙 계산이 내고 시험이 대조한다.

* `GET /company/s2/master` — 불변 회사 자료: 납기약정(M04·M05 — 10월 마감 100건 +
  11월 시연 8건, 미래 인수는 `null`), 생산 소요(주문영향의 원천 칸 — 약정 × 부품·
  세트당 소요·추가 가용재고·기존 조립 착수·정기차 마감, M28), 배경 부품 입고 예정
  (모델별 별도 발주의 최신 단일 예정), 구매 개정 원천(발주행 PO-P-01의 개정 0·1·2).
* `POST /worlds/{w}/sim/receipt-revisions {fixture_id}` — (시연) 구매시스템에 개정이
  등록됐다. 세계 시각에 수신함에 들어간다. 같은 개정을 다시 보내면 기존 접수다
  (사이트 자동 모드가 「이미 보냈나」를 이것으로 본다).
* `GET /worlds/{w}/receipt-revisions/inbox?after=` · `…/receipt-revisions/{doc_id}`.
* 장면 2 — 생산계획 저장소(M20·M21 「기간계(데모 저장)」). 회차마다 원계획 PROD-V1(11/5 약정 8건의
  기존 조립 착수)에서 시작한다. `GET /worlds/{w}/production-plan`은 **저장된 값을 다시 읽는다** —
  NowView는 반영한 뒤 이것으로 대조한다(화면 초안 복사는 대조가 아니다, 구현명세 §2).
  `POST /worlds/{w}/production-plan/apply`는 주문 한 행을 실행키로 반영한다(같은 키는 다시 적지
  않는다 — 응답이 유실돼 다시 와도 이중 반영이 없다). 기준 원계획 버전이 지금과 다르면 409.
* (시연·시험) `POST /worlds/{w}/sim/production-plan/revise` — 다른 사람이 원계획을 고쳤다(T04).
  `POST /worlds/{w}/sim/production-plan/faults` — 저장소가 한 주문의 수량을 다르게 남긴다(T07).

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
NAME = "SYN-S2-SC02-v0.2.xlsx"
DATASET = "SYN-S2-SC02-v0.2"
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
        "dataset_version": DATASET,
        "commitments": commitments,
        "demand": demand,
        "background_lots": background,
        "revisions": revisions,
        **_scene2(wb, commitments, demand),
    }


def line_of(model: str) -> str:
    """
    모델별 최종 조립라인 id — 자료는 「모델별 최종 조립라인」이라고만 하고 id가 없다(구현용 보완).
    """
    return f"ULS-A-{model}"


def _scene2(wb: Any, commitments: list[dict], demand: list[dict]) -> dict[str, Any]:
    """
    장면 2 원천 — SC02생산안의 원천 칸(입고분·확보수량·모델별 빈 라인 시간·조립·준비 시간)과
    SC02정기차(허용 약정·차수·마감·출발·예상 도착), 원계획 PROD-V1(11/5 약정 8건). 제안 착수·종료·
    자재 사용 칸은 파생이라 싣지 않는다. 원계획의 조립 종료는 자료에 없어 `None`이다(0이 아니다).
    """
    model = {c["commitment_id"]: c["model"] for c in commitments}
    qty = {c["commitment_id"]: c["qty"] for c in commitments}
    production = [
        {
            "commitment_id": r["약정"],
            "lot_id": r["입고분"],
            "secured_qty": int(r["확보수량"]),
            "line_id": line_of(model[r["약정"]]),
            "window_start": _at(r["빈 시간 시작"]),
            "window_end": _at(r["빈 시간 종료"]),
            "assembly_min": None if r["조립(분)"] in (None, "") else int(r["조립(분)"]),
            "prep_min": None if r["준비(분)"] in (None, "") else int(r["준비(분)"]),
        }
        for r in _rows(wb["SC02생산안"])
    ]
    trucks = [
        {
            "truck_id": r["차량편"],
            "commitment_id": r["대상 약정"],
            "seq": int(r["차수"]),
            "cutoff": _at(r["접수 마감"]),
            "departure": _at(r["출발"]),
            "arrival": _at(r["예상 도착"]),
        }
        for r in _rows(wb["SC02정기차"])
    ]
    plan = [
        {
            "commitment_id": d["commitment_id"],
            "model": model[d["commitment_id"]],
            "line_id": line_of(model[d["commitment_id"]]),
            "qty": qty[d["commitment_id"]],
            "start": d["assembly_start"],
            "end": None,
        }
        for d in demand
    ]
    return {
        "production": production,
        "trucks": trucks,
        "production_plan": {"version": "PROD-V1", "rows": plan},
    }


def new_world() -> dict[str, Any]:
    """시나리오 2 세계의 변하는 기록 — 구매 개정 수신함·생산계획 저장소."""
    return {"receipt_seq": 0, "receipts": {}, **new_plan()}


def new_plan() -> dict[str, Any]:
    """생산계획 저장소의 처음 — 원계획 PROD-V1, 반영 0건(실행키 없음)."""
    first = master()["production_plan"]
    rows = {r["commitment_id"]: {**r, "version": first["version"]} for r in first["rows"]}
    return {
        "production_plan": {"version": first["version"], "rows": rows, "history": []},
        "plan_applies": {},
        "plan_faults": {},
    }


def rewind(w: dict[str, Any], scene: int) -> None:
    """
    「장면 N부터 다시」(N ≥ 2) — 장면 2부터면 생산계획을 원계획으로(수신함은 장면 1 몫이라
    둔다).
    """
    if w.get("scenario_id") == SCENARIO and scene <= 2:
        w.update(new_plan())


def _plan(w: dict[str, Any]) -> dict[str, Any]:
    """이 칸 전에 만든 시나리오 2 세계는 읽을 때 채운다."""
    if "production_plan" not in w:
        w.update(new_plan())
    return w


def summary(w: dict[str, Any]) -> dict[str, Any]:
    """세계 요약에 더하는 칸 — NowView 일꾼이 수신함 번호를 보고 새 개정을 들인다."""
    return {"receipt_revisions": len(w.get("receipts", {}))}


class ReceiptBody(BaseModel):
    fixture_id: str


class PlanRow(BaseModel):
    commitment_id: str
    qty: int
    start: str
    end: str
    line_id: str


class ApplyBody(BaseModel):
    """주문 한 행의 반영 — 실행키는 run·확인 ID·대상 약정을 포함한다(구현명세 §3 U04)."""

    execution_key: str
    approval_id: str
    base_version: str
    target_version: str
    row: PlanRow


class ReviseBody(BaseModel):
    reason: str = "다른 담당자가 원계획을 고쳤다"


class FaultBody(BaseModel):
    commitment_id: str
    qty: int


def _plan_view(w: dict[str, Any]) -> dict[str, Any]:
    p = _plan(w)["production_plan"]
    return {
        "version": p["version"],
        "rows": [p["rows"][k] for k in sorted(p["rows"])],
        "history": p["history"],
    }


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

    @app.get("/worlds/{world_id}/production-plan", dependencies=[Depends(auth)])
    def production_plan(world_id: str) -> dict[str, Any]:
        """저장된 생산계획을 다시 읽는다 — 버전·약정별 수량·착수·종료·반영 확인 ID·실행키."""
        return _plan_view(world(world_id))

    @app.post(
        "/worlds/{world_id}/production-plan/apply", status_code=201, dependencies=[Depends(auth)]
    )
    def apply_plan_row(world_id: str, body: ApplyBody) -> dict[str, Any]:
        """
        확인된 주문 한 행을 반영한다. 같은 실행키는 다시 적지 않고 처음 결과를 돌려준다(이중 반영
        금지). 기준 원계획 버전이 지금 버전과 다르면 409 — 같은 확인이 이미 올린 버전이면 잇는다
        (부분 반영 뒤 남은 주문).
        """
        with store.lock():
            w = _plan(world(world_id))
            done = w["plan_applies"].get(body.execution_key)
            if done is not None:
                return {**done, "created": False}
            p = w["production_plan"]
            ours = p["version"] == body.target_version and any(
                r.get("approval_id") == body.approval_id for r in p["rows"].values()
            )
            if p["version"] != body.base_version and not ours:
                raise HTTPException(
                    409,
                    f"원계획 버전이 바뀌었다: 기준 {body.base_version} · 지금 {p['version']}",
                )
            cid = body.row.commitment_id
            if cid not in p["rows"]:
                raise HTTPException(404, f"원계획에 없는 약정: {cid}")
            fault = w["plan_faults"].get(cid)
            stored = {
                **p["rows"][cid],
                **body.row.model_dump(),
                "qty": body.row.qty if fault is None else fault["qty"],
                "version": body.target_version,
                "approval_id": body.approval_id,
                "execution_key": body.execution_key,
                "applied_at": w["clock"],
            }
            p["rows"][cid] = stored
            if p["version"] != body.target_version:
                p["history"].append(
                    {"from": p["version"], "to": body.target_version, "at": w["clock"]}
                )
                p["version"] = body.target_version
            result = {
                "execution_key": body.execution_key,
                "commitment_id": cid,
                "version": body.target_version,
                "applied_at": w["clock"],
            }
            w["plan_applies"][body.execution_key] = result
            store.put(w)
        return {**result, "created": True}

    @app.post("/worlds/{world_id}/sim/production-plan/revise", dependencies=[Depends(auth)])
    def revise_plan(world_id: str, body: ReviseBody) -> dict[str, Any]:
        """(시연·시험) 다른 담당자가 원계획을 고쳤다 — 버전만 바뀐다(T04 이전 확인 무효)."""
        with store.lock():
            w = _plan(world(world_id))
            p = w["production_plan"]
            new = f"{p['version']}.{len(p['history']) + 1}"
            p["history"].append(
                {"from": p["version"], "to": new, "at": w["clock"], "reason": body.reason}
            )
            p["version"] = new
            store.put(w)
        return _plan_view(w)

    @app.post("/worlds/{world_id}/sim/production-plan/faults", dependencies=[Depends(auth)])
    def plan_fault(world_id: str, body: FaultBody) -> dict[str, Any]:
        """(시험) 저장소가 그 약정의 반영 수량을 다르게 남긴다 — 재조회가 잡는다(T07)."""
        with store.lock():
            w = _plan(world(world_id))
            w["plan_faults"][body.commitment_id] = {"qty": body.qty}
            store.put(w)
        return {"faults": w["plan_faults"]}

    @app.get("/worlds/{world_id}/receipt-revisions/{doc_id}", dependencies=[Depends(auth)])
    def receipt(world_id: str, doc_id: str) -> dict[str, Any]:
        d = world(world_id).get("receipts", {}).get(doc_id)
        if d is None:
            raise HTTPException(404, f"없는 구매 개정 수신: {doc_id}")
        return d
