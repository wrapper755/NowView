"""
SC06 HTTP 경계 — `/sc06/*`. Next의 `/api/engine/sc06/*`가 그대로 중계한다(BFF).

기본 시연 서비스는 **읽기 전용이고 멱등이다**(구현명세 10장) — 조회가 확인·승인·과제 등록 이력을
만들지 않는다.
모든 응답에 `review_id`·`report_version`·`calculation_version`·`as_of`·`data_status`를 싣는다.
오류는 `error_code`를
함께 낸다: 403 ACCESS_DENIED(근거·금액을 싣지 않는다) · 404 NOT_FOUND · 409 VERSION_MISMATCH.
행위자는 `X-Demo-Actor`
헤더다 — 신뢰 경계가 아니다(5.4).

경로는 구현명세 10장의 제안에 데모 실행을 앞에 붙였다(`/demo-runs/{id}/reviews/RV61/summary` …) —
데모 실행끼리는 서로
보지 않는다(DATA-05).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.sc01.domain import DomainError
from app.sc06 import domain
from app.sc06.process import Sc06Process


class CreateBody(BaseModel):
    #: 이어 갈 데모 실행(장면 1~5와 같은 id). 없으면 장면 1부터 새로 만들어 장면 5 완료까지 돌린다.
    sc01_demo_run_id: str | None = Field(default=None, alias="sc01DemoRunId")
    case_id: str = Field(default="BASE", alias="caseId")
    #: 장면 1~5를 새로 돌려야 할 때의 실행 위치 — center(기본) | studio. 장면 6 자신은 BPM을 돌지
    # 않는다.
    executor: str = "center"
    model_config = {"populate_by_name": True}


def build_router(process: Sc06Process) -> APIRouter:
    r = APIRouter(prefix="/sc06", tags=["sc06"])

    def guard(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except domain.ReadError as exc:
            raise HTTPException(
                status_code=exc.status, detail={"message": str(exc), "error_code": exc.code}
            ) from exc
        except DomainError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc

    def meta(doc: dict) -> dict[str, Any]:
        """
        문서 머리 — 화면이 장면 6이 열렸는지·어느 보고본인지를 안다. 숫자는 조회 서비스로 받는다.
        """
        return {
            "scene": "SC06",
            "demoRunId": doc["demo_run_id"],
            "caseId": doc["case_id"],
            "clock": doc["clock"],
            "reviewId": domain.REVIEW_ID,
            "reportVersion": doc["report"]["report_version"],
            "calculationVersion": doc["report"]["calculation_version"],
            "reportState": doc["report"]["state"],
            "sc05": {
                k: doc["sc05"][k] for k in ("handoff_id", "official", "annual", "target", "gap")
            },
            "batch": doc["batch"],
        }

    @r.get("/cases")
    def cases() -> list[dict[str, str]]:
        return [{"caseId": k, "label": v} for k, v in domain.CASES.items()]

    @r.post("/demo-runs", status_code=201)
    def create(body: CreateBody) -> dict[str, Any]:
        return meta(
            guard(
                process.create,
                sc01_demo_run_id=body.sc01_demo_run_id,
                case_id=body.case_id,
                executor=body.executor,
            )
        )

    @r.get("/demo-runs/{demo_run_id}")
    def get(demo_run_id: str) -> dict[str, Any]:
        return meta(guard(process.get, demo_run_id))

    @r.get("/demo-runs/{demo_run_id}/reviews/{review_id}/summary")
    def summary(
        demo_run_id: str,
        review_id: str,
        report_version: str | None = None,
        x_demo_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        guard(domain.check_review, review_id)
        doc = guard(process.get, demo_run_id)
        return guard(domain.summary, doc, actor=x_demo_actor, report_version=report_version)

    @r.get("/demo-runs/{demo_run_id}/reviews/{review_id}/tasks/{task_id}/variance")
    def variance(
        demo_run_id: str,
        review_id: str,
        task_id: str,
        report_version: str | None = None,
        x_demo_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        guard(domain.check_review, review_id)
        doc = guard(process.get, demo_run_id)
        return guard(
            domain.variance, doc, task_id, actor=x_demo_actor, report_version=report_version
        )

    @r.get("/demo-runs/{demo_run_id}/evidence/{evidence_id}")
    def evidence(
        demo_run_id: str,
        evidence_id: str,
        report_version: str | None = None,
        x_demo_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        doc = guard(process.get, demo_run_id)
        return guard(
            domain.evidence, doc, evidence_id, actor=x_demo_actor, report_version=report_version
        )

    @r.get("/demo-runs/{demo_run_id}/reports/{report_version}")
    def report(
        demo_run_id: str, report_version: str, x_demo_actor: str | None = Header(default=None)
    ) -> dict[str, Any]:
        doc = guard(process.get, demo_run_id)
        return guard(domain.report, doc, report_version, actor=x_demo_actor)

    return r
