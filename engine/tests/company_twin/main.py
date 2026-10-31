"""
회사 시스템 쌍둥이(엔진 시험 전용) — autopart1 기간계(`legacy/`)의 HTTP 계약
(`docs/worker-interfaces.md` §4.2)을 같은 프로세스에서 흉내 낸다. 원본은 autopart1 리포다.
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
    return {"world_id": world_id, "clock": S0_CLOCK, "seq": 0, "inbox": {}, "status_log": []}


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

    return app


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
