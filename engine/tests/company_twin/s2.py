"""
시나리오 2(OTD — 납기) 회사 자료와 세계 기록 — 장면 1 「납기 위험 조기 감지」·장면 2 「정형통제
실행과 주문별 분기」·장면 3 「잔여 납기 위험의 경영검토와 대응 합의」.

NowView `docs/platform.md`(공통 플랫폼)·`docs/s2/sc01.md`~`sc03.md`. 자료는
`seed/SYN-S2-SC03-v0.3.xlsx`(SC01~SC03 통합가상데이터 v0.3 — 앞 15개 시트는 v0.2와 값이 같다)의
**원천 칸만** 읽는다 — 파생 칸(마감판정·사용 가능 예정·착수차질·판정, 장면 2의 제안 착수·종료·
출하 준비·이용 정기차·여유, 장면 3의 대안비교·요약·결정인계)은 NowView 규칙 계산이 내고 시험이
대조한다.

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
* 장면 3 — 출하팀의 **기존 운송 문의**(원업무 W-TRAN-R, 담당 H04)와 사건 근거 원천(운송사 회신
  Q-R-v1 · 영업의 고객 소요 확인 CUST-R-v1). 원업무는 회사의 진행 중 업무라 NowView가 새로 만들지
  않고 참조만 한다(`GET /worlds/{w}/shipping-inquiries/{work_id}` — 담당·상태·받은 회신). 회신·고객
  확인은 (시연) `POST /worlds/{w}/sim/case-sources {fixture_id}`로 세계 시각에 들어온다 — 수신
  시각은 그때다. 같은 근거 id를 다시 보내면 기존 접수다. 시험은 `source_id`·`overrides`로 회신의
  새 판·변형(미회신 뒤 늦은 회신, 2대, 운임 변경)을 낸다. 팀장 전결 한도(AUTH-T1)는 불변 자료다.
  예약은 이 기간계에 없다 — 회신의 「가능」은 예약 확정이 아니다.

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
NAME = "SYN-S2-SC03-v0.3.xlsx"
DATASET = "SYN-S2-SC03-v0.3"
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
        **_scene3(wb),
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


#: 출하팀이 운송 문의를 시작한 시각 — SC03운송회신 머리글 문장(「11/4 09:10 문의 시작(기존 진행
#: 건)」)에만 있고 칸이 없다(구현용 보완 — 그 문장의 시각).
INQUIRY_STARTED = datetime(2026, 11, 4, 9, 10, tzinfo=KST).isoformat()
#: 근거 원천의 종류 — 운송사 회신(원업무에 붙는다)·영업의 고객 소요 확인
REPLY, CUSTOMER = "transport_reply", "customer_condition"
#: 시험이 회신 변형에 바꿀 수 있는 칸 — 수량·운임·시각만(근거 id·원업무는 못 바꾼다)
OVERRIDABLE = {
    "vehicles",
    "sets_per_vehicle",
    "extra_cost_per_vehicle",
    "departure",
    "arrival",
    "valid_until",
    "status_text",
    "qty",
    "promised_at",
}


def _int(value: Any) -> int | None:
    return None if value in (None, "") else int(value)


def _scene3(wb: Any) -> dict[str, Any]:
    """
    장면 3 원천 — SC03운송회신(운송사 회신 Q-R-v1 — 원업무·담당·예약 유효시각·가능 대수·대당 세트·
    대당 추가비·예상 출발·도착)과 SC03고객권한(영업의 고객 소요 확인 CUST-R-v1, 팀장 전결 기준
    AUTH-T1). 회신·고객 확인의 시각 칸은 **예정 시각**이다 — 실제 수신 시각은 시연이 보낸 세계
    시각이다. SC03업무연결·대안비교·요약·결정인계·인계는 NowView 결과와 대조하는 기대값이라 싣지
    않는다.
    """
    replies = [
        {
            "fixture_id": r["회신 ID"],
            "kind": REPLY,
            "work_id": r["원업무"],
            "commitment_id": r["약정"],
            "owner_role": r["담당"],
            "scheduled_at": _at(r["수신시각"]),
            "valid_until": _at(r["예약 유효시각"]),
            "vehicles": _int(r["가능 대수"]),
            "sets_per_vehicle": _int(r["대당 세트"]),
            "extra_cost_per_vehicle": _int(r["대당 추가비(원)"]),
            "departure": _at(r["예상 출발"]),
            "arrival": _at(r["예상 도착"]),
            "status_text": r["상태"],
        }
        for r in _rows(wb["SC03운송회신"])
    ]
    customer, authority = [], []
    for r in _rows(wb["SC03고객권한"]):
        if r["한도(원)"] in (None, ""):
            customer.append(
                {
                    "fixture_id": r["근거 ID"],
                    "kind": CUSTOMER,
                    "source": r["출처 / 확인자"],
                    "scheduled_at": _at(r["확인 시각"]),
                    "commitment_id": r["대상"],
                    "qty": _int(r["수량(세트)"]),
                    "promised_at": _at(r["약정시각"]),
                    "condition": r["적용 조건"],
                }
            )
        else:
            authority.append(
                {
                    "rule_id": r["근거 ID"],
                    "source": r["출처 / 확인자"],
                    "effective_at": _at(r["확인 시각"]),
                    "holder": r["대상"],
                    "limit": int(r["한도(원)"]),
                    "condition": r["적용 조건"],
                }
            )
    works = sorted({(x["work_id"], x["commitment_id"], x["owner_role"]) for x in replies})
    return {
        "shipping_inquiries": [
            {
                "work_id": w,
                "commitment_id": cid,
                "owner_role": owner,
                "started_at": INQUIRY_STARTED,
                "subject": "운송 차량 가능 여부 문의",
            }
            for w, cid, owner in works
        ],
        "case_sources": replies + customer,
        "authority": authority,
    }


def new_world() -> dict[str, Any]:
    """시나리오 2 세계의 변하는 기록 — 구매 개정 수신함·생산계획 저장소·장면 3 근거 원천."""
    return {"receipt_seq": 0, "receipts": {}, **new_plan(), **new_sources()}


def new_sources() -> dict[str, Any]:
    """장면 3 근거 원천(운송사 회신·고객 소요 확인)의 처음 — 아무것도 받지 않았다."""
    return {"case_source_seq": 0, "case_sources": {}}


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
    둔다), 장면 3부터면 장면 3 근거 원천을 비운다.
    """
    if w.get("scenario_id") != SCENARIO:
        return
    if scene <= 2:
        w.update(new_plan())
    if scene <= 3:
        w.update(new_sources())


def _plan(w: dict[str, Any]) -> dict[str, Any]:
    """이 칸 전에 만든 시나리오 2 세계는 읽을 때 채운다."""
    if "production_plan" not in w:
        w.update(new_plan())
    if "case_sources" not in w:
        w.update(new_sources())
    return w


def summary(w: dict[str, Any]) -> dict[str, Any]:
    """세계 요약에 더하는 칸 — NowView 일꾼이 수신함 번호를 보고 새 개정을 들인다."""
    return {
        "receipt_revisions": len(w.get("receipts", {})),
        "case_sources": len(w.get("case_sources", {})),
    }


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


class SourceBody(BaseModel):
    """
    장면 3 근거 원천 하나 — `fixture_id`는 자료의 근거(Q-R-v1·CUST-R-v1). (시험) `source_id`로 새 판
    (Q-R-v2 등)을, `overrides`로 회신 칸을 바꾼 변형을 낸다.
    """

    fixture_id: str
    source_id: str | None = None
    overrides: dict[str, Any] = {}


def _plan_view(w: dict[str, Any]) -> dict[str, Any]:
    p = _plan(w)["production_plan"]
    return {
        "version": p["version"],
        "rows": [p["rows"][k] for k in sorted(p["rows"])],
        "history": p["history"],
    }


def _source_summary(d: dict[str, Any]) -> dict[str, Any]:
    keys = ("doc_id", "seq", "fixture_id", "source_id", "kind", "registered_at")
    return {k: d[k] for k in keys}


def _inquiry(w: dict[str, Any], work_id: str) -> dict[str, Any] | None:
    """
    원업무 하나 — 담당·시작·상태와 받은 회신(수신 순). 시작 전 시각이면 아직 없는 업무다(시연
    시각에 아직 없는 결과는 노출하지 않는다). 예약은 이 업무의 상태가 아니다(`reserved`는 늘
    거짓).
    """
    found = next((i for i in master()["shipping_inquiries"] if i["work_id"] == work_id), None)
    if found is None:
        return None
    clock = datetime.fromisoformat(w["clock"])
    started = datetime.fromisoformat(found["started_at"])
    replies = sorted(
        (d for d in _plan(w)["case_sources"].values() if d.get("work_id") == work_id),
        key=lambda d: d["seq"],
    )
    return {
        **found,
        "state": "IN_PROGRESS" if clock >= started else "NOT_STARTED",
        "reserved": False,
        "replies": replies if clock >= started else [],
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

    @app.post("/worlds/{world_id}/sim/case-sources", status_code=201, dependencies=[Depends(auth)])
    def case_source_arrives(world_id: str, body: SourceBody) -> dict[str, Any]:
        """
        (시연) 장면 3 근거 원천이 들어왔다 — 운송사 회신은 원업무 W-TRAN-R에, 영업 확인은 고객
        조건으로. 수신·확인 시각은 세계 시각이다. 같은 근거 id는 기존 접수를 돌려준다.
        """
        found = next(
            (x for x in master()["case_sources"] if x["fixture_id"] == body.fixture_id), None
        )
        if found is None:
            known = ", ".join(x["fixture_id"] for x in master()["case_sources"])
            raise HTTPException(404, f"모르는 근거 원천: {body.fixture_id} (가능: {known})")
        bad = sorted(set(body.overrides) - OVERRIDABLE)
        if bad:
            raise HTTPException(422, f"바꿀 수 없는 칸: {', '.join(bad)}")
        source_id = body.source_id or body.fixture_id
        with store.lock():
            w = _plan(world(world_id))
            for d in w["case_sources"].values():
                if d["source_id"] == source_id:
                    return {**_source_summary(d), "created": False}
            w["case_source_seq"] = w.get("case_source_seq", 0) + 1
            doc_id = f"CS-{w['case_source_seq']:04d}"
            at_key = "received_at" if found["kind"] == REPLY else "confirmed_at"
            w["case_sources"][doc_id] = {
                **{k: v for k, v in found.items() if k != "scheduled_at"},
                **body.overrides,
                "doc_id": doc_id,
                "seq": w["case_source_seq"],
                "source_id": source_id,
                "registered_at": w["clock"],
                at_key: w["clock"],
            }
            store.put(w)
        return {**_source_summary(w["case_sources"][doc_id]), "created": True}

    @app.get("/worlds/{world_id}/case-sources/inbox", dependencies=[Depends(auth)])
    def case_source_inbox(world_id: str, after: int = 0) -> list[dict[str, Any]]:
        docs = sorted(_plan(world(world_id))["case_sources"].values(), key=lambda d: d["seq"])
        return [_source_summary(d) for d in docs if d["seq"] > after]

    @app.get("/worlds/{world_id}/case-sources", dependencies=[Depends(auth)])
    def case_sources(world_id: str) -> list[dict[str, Any]]:
        """받은 근거 원천 전부(수신 순) — NowView가 링크·비교 때 다시 읽는다."""
        return sorted(_plan(world(world_id))["case_sources"].values(), key=lambda d: d["seq"])

    @app.get("/worlds/{world_id}/case-sources/{doc_id}", dependencies=[Depends(auth)])
    def case_source(world_id: str, doc_id: str) -> dict[str, Any]:
        d = _plan(world(world_id))["case_sources"].get(doc_id)
        if d is None:
            raise HTTPException(404, f"없는 근거 원천 수신: {doc_id}")
        return d

    @app.get("/worlds/{world_id}/shipping-inquiries/{work_id}", dependencies=[Depends(auth)])
    def shipping_inquiry(world_id: str, work_id: str) -> dict[str, Any]:
        """출하팀의 기존 운송 문의(원업무) — 담당·상태·받은 회신. 읽기만 한다."""
        found = _inquiry(world(world_id), work_id)
        if found is None:
            raise HTTPException(404, f"없는 원업무: {work_id}")
        return found

    @app.get("/worlds/{world_id}/receipt-revisions/{doc_id}", dependencies=[Depends(auth)])
    def receipt(world_id: str, doc_id: str) -> dict[str, Any]:
        d = world(world_id).get("receipts", {}).get(doc_id)
        if d is None:
            raise HTTPException(404, f"없는 구매 개정 수신: {doc_id}")
        return d
