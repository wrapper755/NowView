"""
회사 시스템 쌍둥이(엔진 시험 전용) — Company1 기간계(`legacy/`)의 HTTP 계약
(`docs/worker-interfaces.md` §4.2)을 같은 프로세스에서 흉내 낸다. 원본은 Company1 리포다.
"""

from __future__ import annotations

import hmac
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from company_twin import seed
from company_twin.store import WorldStore

KST = ZoneInfo("Asia/Seoul")
#: 기준 시점 S0 — 2027-06-15 18:00(실적 컷오프 다음 저녁, NowView SC01 S0와 같다).
S0_CLOCK = datetime(2027, 6, 15, 18, 0, tzinfo=KST).isoformat()
STATUSES = {"VERIFIED", "NEEDS_INFO"}
#: 원가 버전 등록에서 같은 버전인지 가르는 칸 — 등록자·시각·ref는 다시 와도 같은 등록이다.
COST_VERSION_FIELDS = (
    "cost_version_id",
    "parent_cost_version",
    "part_id",
    "supplier_id",
    "old_price",
    "new_price",
    "effective_from",
    "models",
    "approved_proposal",
)


class NewWorld(BaseModel):
    world_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")


class ClockBody(BaseModel):
    at: str


class FixtureBody(BaseModel):
    fixture_id: str


class StatusBody(BaseModel):
    status: str
    by: str
    opinion: str = ""
    evidence: str = ""
    ref: str  # 멱등 — 같은 ref로 다시 오면 다시 적지 않는다(BPM 실행·노드)


class ExecutionRequestBody(BaseModel):
    """실행 품의의 상태 하나(상신·현업 승인·예산 승인·반려) — 회사 전자결재의 품의 기록이다."""

    request_id: str
    version: int
    task_id: str
    scope: str  # ONEOFF(일회성 준비비) · OPERATING(운영지원비)
    amount: str
    reason: str = ""
    approval_ref: str = ""
    state: str
    by: str
    at: str  # 업무 시각(그 결재가 난 시각) — 기록 시각은 세계 시각이다
    note: str = ""
    ref: str  # 멱등 — 같은 ref로 다시 오면 다시 적지 않는다


class BudgetTxnBody(BaseModel):
    """예산 원장 거래 한 줄 — 약정(COMMIT)·정산(SETTLE). 금액은 원 단위 정수 글이다."""

    txn_id: str
    task_id: str
    scope: str
    request_ref: str
    at: str
    type: str
    commitment_delta: str
    paid_delta: str
    pnl_cost: str
    evidence: str = ""
    ref: str


class ForecastBody(BaseModel):
    """공식 전망 게시 — 대표 승인본을 회사의 공식 전망으로 건다. 앞 공식본은 이력이다."""

    forecast_id: str
    run_id: str
    parent_official: str | None = None
    cutoff: str
    annual: str
    months: list[dict[str, Any]]
    approved_at: str
    approved_by: str
    published_at: str
    published_by: str
    ref: str


class CostVersionBody(BaseModel):
    """승인된 단가를 원가 버전으로 등록한다 — C01은 그대로 두고 부품값 몫만 바꾼 새 버전이다."""

    cost_version_id: str
    parent_cost_version: str
    part_id: str
    supplier_id: str
    old_price: str
    new_price: str
    effective_from: str
    models: list[dict[str, Any]]
    approved_proposal: str
    request_doc_id: str | None = None
    registered_by: str
    note: str = ""
    ref: str


class RecordBody(BaseModel):
    """
    경영 기록 한 판 — 봉투는 공통, 본문(`body`)은 종류별 스키마다(주인은 NowView
    `docs/records/`). 기간계는 봉투만 검사한다 — 본문을 다시 해석하지 않는다.
    """

    kind: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    record_id: str = Field(min_length=1, max_length=120)
    version: int = Field(ge=1)
    scene: int = Field(ge=1, le=99)
    state: str | None = None
    at: str  # 업무 시각(그 기록이 생긴 시각) — 기록 시각은 세계 시각이다
    by: str | None = None
    title: str = ""
    body: dict[str, Any]
    ref: str  # 멱등 — 같은 ref·같은 내용이면 다시 적지 않는다


class RecordsReset(BaseModel):
    scene: int = Field(ge=1, le=99)


def _auth_dependency():
    key = os.getenv("COMPANY_TWIN_KEY") or ""
    off = os.getenv("COMPANY_TWIN_AUTH", "").lower() == "off"
    if not key and not off:
        raise RuntimeError("COMPANY_TWIN_KEY가 없다 — 끄려면 COMPANY_TWIN_AUTH=off를 명시한다")

    def check(authorization: str | None = Header(default=None)) -> None:
        if off:
            return
        given = (authorization or "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(given, key):
            raise HTTPException(401, "회사 시스템 키가 없거나 틀렸다")

    return check


def _new_world(world_id: str) -> dict[str, Any]:
    return {
        "world_id": world_id,
        "clock": S0_CLOCK,
        "seq": 0,
        "inbox": {},
        "status_log": [],
        **_new_purchase(),
        **_new_execution(),
        **_new_records(),
    }


def _new_purchase() -> dict[str, Any]:
    """장면 2의 세계 기록 — 이 칸이 생기기 전에 만든 세계는 읽을 때 채운다(`_purchase`)."""
    return {"price_seq": 0, "price_requests": {}, "price_status_log": [], "cost_versions": {}}


def _purchase(w: dict[str, Any]) -> dict[str, Any]:
    for k, v in _new_purchase().items():
        w.setdefault(k, v)
    return w


def _new_execution() -> dict[str, Any]:
    """장면 5의 세계 기록 — 실행 품의·예산 원장·공식 전망. 옛 세계는 읽을 때 채운다."""
    return {"execution_requests": {}, "budget_ledger": [], "forecasts": {}, "official": None}


def _execution(w: dict[str, Any]) -> dict[str, Any]:
    for k, v in _new_execution().items():
        w.setdefault(k, v)
    return w


def _new_records() -> dict[str, Any]:
    """경영 기록(NowView 일꾼이 적는다, role-split §3). 옛 세계는 읽을 때 채운다."""
    return {"records": {}, "records_seq": 0}


def _records(w: dict[str, Any]) -> dict[str, Any]:
    for k, v in _new_records().items():
        w.setdefault(k, v)
    return w


#: 예산 원장 거래에서 같은 거래인지 가르는 칸
TXN_FIELDS = (
    "txn_id",
    "task_id",
    "scope",
    "request_ref",
    "at",
    "type",
    "commitment_delta",
    "paid_delta",
    "pnl_cost",
)
#: 경영 기록에서 같은 판인지 가르는 칸 — 기록 시각·ref는 다시 와도 같은 판이다.
RECORD_FIELDS = ("kind", "record_id", "version", "scene", "state", "at", "by", "title", "body")
#: 공식 전망에서 같은 판인지 가르는 칸
FORECAST_FIELDS = ("forecast_id", "run_id", "parent_official", "cutoff", "annual", "approved_at")


def build_app(store: WorldStore) -> FastAPI:
    data = seed.load()
    app = FastAPI(
        title="autoparts 회사 시스템 시뮬레이터",
        version="0.1.0",
        description="가상 자동차 부품사의 회사 자료·확정 기록 — NowView 일꾼이 읽고 적는다",
    )
    auth = _auth_dependency()

    def world(world_id: str) -> dict[str, Any]:
        found = store.get(world_id)
        if found is None:
            raise HTTPException(404, f"없는 세계: {world_id}")
        return found

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "company": "autoparts",
            "worlds": store.count(),
            "auth": "off" if os.getenv("COMPANY_TWIN_AUTH", "").lower() == "off" else "key",
        }

    # ───────────── 불변 기록 ─────────────

    @app.get("/company/org/users", dependencies=[Depends(auth)])
    def users() -> list[dict[str, str]]:
        return data.users

    @app.get("/company/master", dependencies=[Depends(auth)])
    def master() -> dict[str, Any]:
        return {"customers": ["CUS-HK"], "plants": ["ULS"], "models": data.models}

    @app.get("/company/versions", dependencies=[Depends(auth)])
    def versions() -> list[dict[str, Any]]:
        return data.versions

    @app.get("/company/plans/{version}", dependencies=[Depends(auth)])
    def plan(version: str) -> dict[str, Any]:
        if version not in data.plans:
            raise HTTPException(404, f"없는 계획 버전: {version}")
        return {"version": version, "rows": data.plans[version]}

    @app.get("/company/actuals", dependencies=[Depends(auth)])
    def actuals() -> dict[str, Any]:
        return {"rows": data.actuals}

    @app.get("/company/costs/{version}", dependencies=[Depends(auth)])
    def costs(version: str) -> dict[str, Any]:
        if version not in data.costs:
            raise HTTPException(404, f"없는 원가 버전: {version}")
        return {"version": version, "rows": data.costs[version]}

    @app.get("/company/fixed-costs/{version}", dependencies=[Depends(auth)])
    def fixed_costs(version: str) -> dict[str, Any]:
        if version not in data.fixed_costs:
            raise HTTPException(404, f"없는 고정비 버전: {version}")
        return {"version": version, "rows": data.fixed_costs[version]}

    @app.get("/company/customer-plans/{plan_id}", dependencies=[Depends(auth)])
    def baseline_plan(plan_id: str) -> dict[str, Any]:
        """기준 시점에 이미 받아 확인한 원천(CP01) — 변경 비교의 직전 원천이다."""
        if plan_id not in seed.BASELINE_PLANS:
            raise HTTPException(404, f"기준 원천이 아니다: {plan_id}")
        return {
            "customer_plan_id": plan_id,
            "status": "VERIFIED",
            "rows": data.customer_plans[plan_id],
        }

    # ───────────── 세계 ─────────────

    @app.post("/worlds", status_code=201, dependencies=[Depends(auth)])
    def create_world(body: NewWorld) -> dict[str, Any]:
        """세계를 만든다 — 이미 있으면 그대로 돌려준다(멱등)."""
        with store.lock():
            found = store.get(body.world_id)
            if found is None:
                found = _new_world(body.world_id)
                store.put(found)
        return {"world_id": found["world_id"], "clock": found["clock"]}

    @app.post("/worlds/{world_id}/reset", dependencies=[Depends(auth)])
    def reset(world_id: str) -> dict[str, Any]:
        with store.lock():
            world(world_id)
            fresh = _new_world(world_id)
            store.put(fresh)
        return {"world_id": world_id, "clock": fresh["clock"]}

    @app.get("/worlds/{world_id}/clock", dependencies=[Depends(auth)])
    def get_clock(world_id: str) -> dict[str, str]:
        return {"at": world(world_id)["clock"]}

    @app.post("/worlds/{world_id}/clock", dependencies=[Depends(auth)])
    def set_clock(world_id: str, body: ClockBody) -> dict[str, str]:
        try:
            at = datetime.fromisoformat(body.at)
        except ValueError as e:
            raise HTTPException(422, f"시각 형식이 아니다: {body.at}") from e
        with store.lock():
            w = world(world_id)
            w["clock"] = at.isoformat()
            store.put(w)
        return {"at": w["clock"]}

    @app.post(
        "/worlds/{world_id}/sim/customer-plans", status_code=201, dependencies=[Depends(auth)]
    )
    def customer_sends(world_id: str, body: FixtureBody) -> dict[str, Any]:
        """
        고객이 생산계획 원천을 보냈다 — 세계 시각에 수신함에 들어온다. 같은 내용을 다시 보내면
        기존 접수다.
        """
        if body.fixture_id not in seed.FIXTURES:
            raise HTTPException(
                404, f"모르는 시연 원천: {body.fixture_id} (가능: {', '.join(seed.FIXTURES)})"
            )
        plan_id, rows = seed.fixture_rows(body.fixture_id)
        with store.lock():
            w = world(world_id)
            for d in w["inbox"].values():
                if d["fixture_id"] == body.fixture_id and d["rows"] == rows:
                    return {**_summary(d), "created": False}
            w["seq"] += 1
            doc_id = f"DOC-{w['seq']:04d}"
            earlier = sorted(w["inbox"].values(), key=lambda d: d["seq"])
            corrects = next(
                (d["doc_id"] for d in reversed(earlier) if d["customer_plan_id"] == plan_id), None
            )
            w["inbox"][doc_id] = {
                "doc_id": doc_id,
                "seq": w["seq"],
                "fixture_id": body.fixture_id,
                "customer_plan_id": plan_id,
                "received_at": w["clock"],
                "corrects": corrects,
                "status": "RECEIVED",
                "rows": rows,
            }
            store.put(w)
        return {**_summary(w["inbox"][doc_id]), "created": True}

    @app.get("/worlds/{world_id}/customer-plans/inbox", dependencies=[Depends(auth)])
    def inbox(world_id: str, after: int = 0) -> list[dict[str, Any]]:
        """받은 원천(수신 순서). `after`보다 뒤의 것만 — NowView가 마지막으로 본 번호를 넘긴다."""
        docs = sorted(world(world_id)["inbox"].values(), key=lambda d: d["seq"])
        return [_summary(d) for d in docs if d["seq"] > after]

    @app.get("/worlds/{world_id}/customer-plans/{doc_id}", dependencies=[Depends(auth)])
    def customer_plan(world_id: str, doc_id: str) -> dict[str, Any]:
        d = world(world_id)["inbox"].get(doc_id)
        if d is None:
            raise HTTPException(404, f"없는 원천: {doc_id}")
        return d

    @app.post("/worlds/{world_id}/customer-plans/{doc_id}/status", dependencies=[Depends(auth)])
    def set_status(world_id: str, doc_id: str, body: StatusBody) -> dict[str, Any]:
        """원천 확인 결정 — 회사의 확정 기록. 같은 `ref`가 다시 오면 다시 적지 않는다."""
        if body.status not in STATUSES:
            raise HTTPException(
                422, f"모르는 상태: {body.status} (가능: {', '.join(sorted(STATUSES))})"
            )
        with store.lock():
            w = world(world_id)
            d = w["inbox"].get(doc_id)
            if d is None:
                raise HTTPException(404, f"없는 원천: {doc_id}")
            done = next((e for e in w["status_log"] if e["ref"] == body.ref), None)
            if done is not None:
                if done["doc_id"] != doc_id or done["status"] != body.status:
                    raise HTTPException(409, f"같은 ref로 다른 결정이 이미 있다: {body.ref}")
                return {**_summary(d), "recorded": False}
            d["status"] = body.status
            w["status_log"].append(
                {
                    "ref": body.ref,
                    "doc_id": doc_id,
                    "status": body.status,
                    "by": body.by,
                    "opinion": body.opinion,
                    "evidence": body.evidence,
                    "at": w["clock"],
                }
            )
            store.put(w)
        return {**_summary(d), "recorded": True}

    # ───────────── 구매 (장면 2) ─────────────

    @app.get("/company/purchase/master", dependencies=[Depends(auth)])
    def purchase_master() -> dict[str, Any]:
        """부품·공급사·부품 구성(BOM)·현행 구매 단가 — 불변 기록."""
        p = seed.load_purchase()
        return {"parts": p.parts, "suppliers": p.suppliers, "bom": p.bom, "prices": p.prices}

    @app.post(
        "/worlds/{world_id}/sim/price-requests", status_code=201, dependencies=[Depends(auth)]
    )
    def supplier_sends(world_id: str, body: FixtureBody) -> dict[str, Any]:
        """
        공급사가 단가 인상 요청 공문을 보냈다 — 세계 시각에 구매 수신함에 들어온다. 같은 내용을 다시
        보내면 기존 접수다.
        """
        if body.fixture_id not in seed.PRICE_REQUEST_FIXTURES:
            raise HTTPException(
                404,
                f"모르는 시연 요청: {body.fixture_id} "
                f"(가능: {', '.join(seed.PRICE_REQUEST_FIXTURES)})",
            )
        content = seed.price_request(body.fixture_id)
        with store.lock():
            w = _purchase(world(world_id))
            for d in w["price_requests"].values():
                if d["fixture_id"] == body.fixture_id and d["items"] == content["items"]:
                    return {**_request_summary(d), "created": False}
            w["price_seq"] += 1
            doc_id = f"PRQ-{w['price_seq']:04d}"
            earlier = sorted(w["price_requests"].values(), key=lambda d: d["seq"])
            corrects = next(
                (
                    d["doc_id"]
                    for d in reversed(earlier)
                    if d["request_id"] == content["request_id"]
                ),
                None,
            )
            w["price_requests"][doc_id] = {
                "doc_id": doc_id,
                "seq": w["price_seq"],
                "fixture_id": body.fixture_id,
                **content,
                "received_at": w["clock"],
                "corrects": corrects,
                "status": "RECEIVED",
            }
            store.put(w)
        return {**_request_summary(w["price_requests"][doc_id]), "created": True}

    @app.get("/worlds/{world_id}/price-requests/inbox", dependencies=[Depends(auth)])
    def price_inbox(world_id: str, after: int = 0) -> list[dict[str, Any]]:
        docs = sorted(_purchase(world(world_id))["price_requests"].values(), key=lambda d: d["seq"])
        return [_request_summary(d) for d in docs if d["seq"] > after]

    @app.get("/worlds/{world_id}/price-requests/status-log", dependencies=[Depends(auth)])
    def price_status_log(world_id: str) -> list[dict[str, Any]]:
        """요청 원문 확인 결정 기록(적힌 순서)."""
        return _purchase(world(world_id))["price_status_log"]

    @app.get("/worlds/{world_id}/price-requests/{doc_id}", dependencies=[Depends(auth)])
    def price_request(world_id: str, doc_id: str) -> dict[str, Any]:
        d = _purchase(world(world_id))["price_requests"].get(doc_id)
        if d is None:
            raise HTTPException(404, f"없는 요청: {doc_id}")
        return d

    @app.post("/worlds/{world_id}/price-requests/{doc_id}/status", dependencies=[Depends(auth)])
    def set_price_status(world_id: str, doc_id: str, body: StatusBody) -> dict[str, Any]:
        """요청 원문 확인 결정 — 구매의 접수 기록. 같은 `ref`가 다시 오면 다시 적지 않는다."""
        if body.status not in STATUSES:
            raise HTTPException(
                422, f"모르는 상태: {body.status} (가능: {', '.join(sorted(STATUSES))})"
            )
        with store.lock():
            w = _purchase(world(world_id))
            d = w["price_requests"].get(doc_id)
            if d is None:
                raise HTTPException(404, f"없는 요청: {doc_id}")
            done = next((e for e in w["price_status_log"] if e["ref"] == body.ref), None)
            if done is not None:
                if done["doc_id"] != doc_id or done["status"] != body.status:
                    raise HTTPException(409, f"같은 ref로 다른 결정이 이미 있다: {body.ref}")
                return {**_request_summary(d), "recorded": False}
            d["status"] = body.status
            w["price_status_log"].append(
                {
                    "ref": body.ref,
                    "doc_id": doc_id,
                    "status": body.status,
                    "by": body.by,
                    "opinion": body.opinion,
                    "evidence": body.evidence,
                    "at": w["clock"],
                }
            )
            store.put(w)
        return {**_request_summary(d), "recorded": True}

    @app.get("/worlds/{world_id}/cost-versions", dependencies=[Depends(auth)])
    def cost_versions(world_id: str) -> list[dict[str, Any]]:
        """
        등록된 원가 버전(등록 순서). 상태는 세계 시각에서 읽는다 — 적용일 전이면 REGISTERED_FUTURE,
        적용일부터 EFFECTIVE(적용일 도래는 새 승인이 아니다).
        """
        w = _purchase(world(world_id))
        docs = sorted(w["cost_versions"].values(), key=lambda d: d["seq"])
        return [{**d, "status": _cost_status(d, w["clock"])} for d in docs]

    @app.post("/worlds/{world_id}/cost-versions", dependencies=[Depends(auth)])
    def register_cost_version(world_id: str, body: CostVersionBody) -> dict[str, Any]:
        """
        승인 단가의 원가 버전 등록 — 회사의 확정 기록. 같은 버전·같은 내용이면 기존 등록을
        돌려준다(COST-02). 같은 버전 id에 다른 내용은 409 — 바꾸려면 새 승인·새 버전이다.
        """
        record = body.model_dump()
        with store.lock():
            w = _purchase(world(world_id))
            found = w["cost_versions"].get(body.cost_version_id)
            if found is not None:
                if any(found[k] != record[k] for k in COST_VERSION_FIELDS):
                    raise HTTPException(
                        409, f"같은 원가 버전에 다른 내용이 이미 있다: {body.cost_version_id}"
                    )
                return {**found, "status": _cost_status(found, w["clock"]), "recorded": False}
            found = {**record, "seq": len(w["cost_versions"]) + 1, "registered_at": w["clock"]}
            w["cost_versions"][body.cost_version_id] = found
            store.put(w)
        return {**found, "status": _cost_status(found, w["clock"]), "recorded": True}

    @app.post("/worlds/{world_id}/purchase/reset", dependencies=[Depends(auth)])
    def reset_purchase(world_id: str) -> dict[str, Any]:
        """장면 2의 세계 기록만 처음으로 — 고객계획 수신함·원천 상태(장면 1)는 그대로 둔다."""
        with store.lock():
            w = world(world_id)
            w.update(_new_purchase())
            store.put(w)
        return {"world_id": world_id, "clock": w["clock"]}

    # ───────────── 장면 5 — 실행 품의 · 예산 원장 · 공식 전망 ─────────────

    @app.get("/worlds/{world_id}/execution-requests", dependencies=[Depends(auth)])
    def execution_requests(world_id: str) -> list[dict[str, Any]]:
        """실행 품의(상신 순서) — 지금 상태와 상태 이력. 반려 뒤 고친 품의는 새 판(version)이다."""
        w = _execution(world(world_id))
        return sorted(w["execution_requests"].values(), key=lambda d: d["seq"])

    @app.post("/worlds/{world_id}/execution-requests", dependencies=[Depends(auth)])
    def record_execution_request(world_id: str, body: ExecutionRequestBody) -> dict[str, Any]:
        """
        품의 상태 하나를 적는다(상신 → 현업 승인 → 예산 승인, 또는 반려). 같은 ref는
        다시 적지 않는다.
        판(version)이 지금보다 낮으면 409 — 지난 판의 결재가 새 판을 덮지 않는다.
        """
        with store.lock():
            w = _execution(world(world_id))
            found = w["execution_requests"].get(body.request_id)
            if found is not None and any(h["ref"] == body.ref for h in found["history"]):
                return {**found, "recorded": False}
            if found is not None and body.version < found["version"]:
                raise HTTPException(
                    409,
                    f"{body.request_id} v{body.version}은 지난 판이다(지금 v{found['version']})",
                )
            if found is None:
                found = {
                    "request_id": body.request_id,
                    "seq": len(w["execution_requests"]) + 1,
                    "history": [],
                }
                w["execution_requests"][body.request_id] = found
            found.update(
                version=body.version,
                task_id=body.task_id,
                scope=body.scope,
                amount=body.amount,
                reason=body.reason or found.get("reason", ""),
                approval_ref=body.approval_ref,
                state=body.state,
            )
            found["history"].append(
                {
                    "ref": body.ref,
                    "version": body.version,
                    "state": body.state,
                    "by": body.by,
                    "at": body.at,
                    "note": body.note,
                    "recorded_at": w["clock"],
                }
            )
            store.put(w)
        return {**found, "recorded": True}

    @app.get("/worlds/{world_id}/budget-ledger", dependencies=[Depends(auth)])
    def budget_ledger(world_id: str) -> dict[str, Any]:
        """
        예산 원장(적은 순서)과 범위별 합계 — 약정 잔액(약정증감 합)·집행(집행증감 합)·손익비용.
        한도·잔여 판정은 NowView 규칙 계산이다(여기는 원장만 둔다).
        """
        w = _execution(world(world_id))
        totals: dict[str, dict[str, int]] = {}
        for t in w["budget_ledger"]:
            s = totals.setdefault(t["scope"], {"committed": 0, "paid": 0, "pnl_cost": 0})
            s["committed"] += int(t["commitment_delta"])
            s["paid"] += int(t["paid_delta"])
            s["pnl_cost"] += int(t["pnl_cost"])
        return {"transactions": w["budget_ledger"], "totals": totals}

    @app.post("/worlds/{world_id}/budget-ledger", dependencies=[Depends(auth)])
    def record_budget_txn(world_id: str, body: BudgetTxnBody) -> dict[str, Any]:
        """원장 한 줄 — 같은 거래 id·같은 내용은 기존 줄, 다른 내용은 409(정정 거래로 고친다)."""
        record = body.model_dump()
        with store.lock():
            w = _execution(world(world_id))
            found = next((t for t in w["budget_ledger"] if t["txn_id"] == body.txn_id), None)
            if found is not None:
                if any(found[k] != record[k] for k in TXN_FIELDS):
                    raise HTTPException(409, f"같은 거래 id에 다른 내용이 이미 있다: {body.txn_id}")
                return {**found, "recorded": False}
            found = {**record, "seq": len(w["budget_ledger"]) + 1, "recorded_at": w["clock"]}
            w["budget_ledger"].append(found)
            store.put(w)
        return {**found, "recorded": True}

    @app.get("/worlds/{world_id}/forecasts", dependencies=[Depends(auth)])
    def forecasts(world_id: str) -> dict[str, Any]:
        """게시된 공식 전망(게시 순서)과 지금 공식본."""
        w = _execution(world(world_id))
        docs = sorted(w["forecasts"].values(), key=lambda d: d["seq"])
        return {"official": w["official"], "forecasts": docs}

    @app.post("/worlds/{world_id}/forecasts", dependencies=[Depends(auth)])
    def publish_forecast(world_id: str, body: ForecastBody) -> dict[str, Any]:
        """
        공식 전망 게시 — 지금 공식본을 이 판으로 바꾼다. 같은 판·같은 내용은 기존 게시,
        같은 id에 다른
        내용은 409(공식본은 고치지 않고 새 판으로). 목표(Target)는 바꾸지 않는다 — 전망만이다.
        """
        record = body.model_dump()
        with store.lock():
            w = _execution(world(world_id))
            found = w["forecasts"].get(body.forecast_id)
            if found is not None:
                if any(found[k] != record[k] for k in FORECAST_FIELDS):
                    raise HTTPException(
                        409, f"같은 전망 판에 다른 내용이 이미 있다: {body.forecast_id}"
                    )
                return {**found, "official": w["official"], "recorded": False}
            found = {**record, "seq": len(w["forecasts"]) + 1, "recorded_at": w["clock"]}
            w["forecasts"][body.forecast_id] = found
            w["official"] = body.forecast_id
            store.put(w)
        return {**found, "official": w["official"], "recorded": True}

    @app.post("/worlds/{world_id}/execution/reset", dependencies=[Depends(auth)])
    def reset_execution(world_id: str) -> dict[str, Any]:
        """장면 5의 세계 기록만 처음으로 — 장면 1·2 기록은 그대로 둔다."""
        with store.lock():
            w = world(world_id)
            w.update(_new_execution())
            store.put(w)
        return {"world_id": world_id, "clock": w["clock"]}

    # ───────────── 경영 기록 — 봉투 공통, 본문은 종류별 스키마(NowView docs/records/) ─────────────

    def _latest(r: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in r.items() if k != "history"} | {"history_count": len(r["history"])}

    @app.get("/worlds/{world_id}/records", dependencies=[Depends(auth)])
    def list_records(
        world_id: str, scene: int | None = None, kind: str | None = None, state: str | None = None
    ) -> list[dict[str, Any]]:
        """각 기록의 최신 판(처음 적은 순서). 지난 판은 단건 조회의 history에 있다."""
        w = _records(world(world_id))
        found = sorted(w["records"].values(), key=lambda r: r["seq"])
        return [
            _latest(r)
            for r in found
            if (scene is None or r["scene"] == scene)
            and (kind is None or r["kind"] == kind)
            and (state is None or r["state"] == state)
        ]

    @app.get("/worlds/{world_id}/records/{kind}/{record_id}", dependencies=[Depends(auth)])
    def get_record(world_id: str, kind: str, record_id: str) -> dict[str, Any]:
        r = _records(world(world_id))["records"].get(f"{kind}/{record_id}")
        if r is None:
            raise HTTPException(404, f"없는 기록: {kind}/{record_id}")
        return r

    @app.post("/worlds/{world_id}/records", dependencies=[Depends(auth)])
    def write_record(world_id: str, body: RecordBody) -> dict[str, Any]:
        """
        기록 한 판을 적는다. 같은 ref·같은 내용은 기존 판(`recorded: false`), 같은 ref에 다른
        내용은 409. 새 판(version이 더 크다)이면 앞 판을 history로 옮긴다 — 지우지 않는다.
        지난 판이거나 같은 판에 다른 ref면 409(지난 결재가 새 기록을 덮지 않는다).
        """
        record = body.model_dump()
        key = f"{body.kind}/{body.record_id}"
        with store.lock():
            w = _records(world(world_id))
            found = w["records"].get(key)
            if found is not None:
                for past in [found, *found["history"]]:
                    if past["ref"] == body.ref:
                        if any(past[k] != record[k] for k in RECORD_FIELDS):
                            raise HTTPException(
                                409, f"같은 ref에 다른 내용이 이미 있다: {body.ref}"
                            )
                        return {**_latest(found), "recorded": False}
                if body.version <= found["version"]:
                    raise HTTPException(
                        409,
                        f"{key} v{body.version}은 지난 판이다(지금 v{found['version']})",
                    )
                prior = {k: v for k, v in found.items() if k != "history"}
                found = {
                    **record,
                    "seq": found["seq"],
                    "recorded_at": w["clock"],
                    "history": [*found["history"], prior],
                }
            else:
                w["records_seq"] += 1
                found = {
                    **record,
                    "seq": w["records_seq"],
                    "recorded_at": w["clock"],
                    "history": [],
                }
            w["records"][key] = found
            store.put(w)
        return {**_latest(found), "recorded": True}

    @app.post("/worlds/{world_id}/records/reset", dependencies=[Depends(auth)])
    def reset_records(world_id: str, body: RecordsReset) -> dict[str, Any]:
        """(시연) 그 장면의 기록만 처음으로 — 다른 장면 기록과 회사 자료는 그대로다."""
        with store.lock():
            w = _records(world(world_id))
            before = len(w["records"])
            w["records"] = {k: r for k, r in w["records"].items() if r["scene"] != body.scene}
            store.put(w)
        return {"world_id": world_id, "removed": before - len(w["records"])}

    return app


def _request_summary(d: dict[str, Any]) -> dict[str, Any]:
    return {
        k: d[k]
        for k in (
            "doc_id",
            "seq",
            "fixture_id",
            "request_id",
            "supplier_id",
            "received_at",
            "corrects",
            "status",
        )
    }


def _cost_status(d: dict[str, Any], clock: str) -> str:
    today = datetime.fromisoformat(clock).date().isoformat()
    return "EFFECTIVE" if today >= d["effective_from"] else "REGISTERED_FUTURE"


def _summary(d: dict[str, Any]) -> dict[str, Any]:
    return {
        k: d[k]
        for k in (
            "doc_id",
            "seq",
            "fixture_id",
            "customer_plan_id",
            "received_at",
            "corrects",
            "status",
        )
    }
