"""
장면 5(결정 실행과 계획 갱신)의 경영 기록 — 회사 시스템에 적는 판(`app/records.py`, 스키마
`docs/records/sc05/`).

본문은 NowView 장면 5 화면이 읽는 모양 그대로다(`view.view`의 같은 칸). 실행 품의·예산 원장·공식
전망은 지금처럼 회사 확정 기록에도 적는다(`_sync_company` — 기간계
`execution-requests`·`budget-ledger`· `forecasts`). 여기 것은 경영 기록이다 — 상세
계획·협조·조건·착수·생산 변경·구매 대응·초기 결과· 운영계획·전망 산정·후속 책임·근거, 그리고
화면이 함께 읽는 품의·원장·전망의 사본. 화면 상태 칸 (`answerHere`·결재 대기 폼·`historical`)은
싣지 않는다.
"""

from __future__ import annotations

from typing import Any

from app.records import bpm_head, items, record, scoped

SCENE = 5
TITLE = "결정 실행과 계획 갱신"
#: 기록 종류 — 스키마 `docs/records/sc05/{kind}.schema.json`의 설명
KINDS = {
    "audit": "감사 이력 한 줄 — 누가·언제·무엇을(쌓이기만 한다)",
    "scene": (
        "장면 머리 — 시연 시각·상태 묶음·장면 4 결과 스냅샷·일정·설정·유효 계획·공식 전망·"
        "착수/완료 요건·예산 요약·초기 결과·알림·회사와 오간 것"
    ),
    "execution_plan": "상세 실행계획(PL51-v1·v2 …) — 활동·예산·효과 시작·기한·확정/확인(U502)",
    "collaboration": "협조 확인 — 계획 버전·부서·내용·담당(U502)",
    "condition": "승인 조건·지원(CON41·SUP41) — 책임·확인자·기한·근거·이력(U503)",
    "execution_request": (
        "실행 품의(REQ51·OP51 …)의 사본 — 범위·금액·승인 이력(U503, 원본은 회사 품의)"
    ),
    "budget_txn": "예산 원장 한 줄의 사본 — 약정·정산·손익 비용(U503, 원본은 회사 원장)",
    "action_start": "운영 착수(START51) — 계획 버전·조건·품의·요건(U503)",
    "action_operation": "과제 운영 상태(ACT41~43) — 담당·상태·이력",
    "customer_plan": "고객 생산계획 변경 원문(CP51·CP52 …) — 도착 시각·변경 줄(U504)",
    "production_change": "생산 변경 공유·구매 확인 — 공유/확인 분, 대행, 정상·긴급 판단(U504)",
    "purchase_orders": "구매 주문 표본(9월) — 주문별 수량·긴급·추가비(U505)",
    "operating_plan": "월간 운영계획(OPL51~53) — 잔여 계획·가정·확인(U506)",
    "forecast_run": (
        "Rolling 산정 한 번(RUN51) — 마감+잔여 월별 효과·손익·종전 공식본 대비 대사. 숫자는"
        " 규칙 계산(U507)"
    ),
    "forecast": (
        "전망 버전(FC50·FC51-D·FC51 …) — 월별 손익·연간·상태·승인/게시(U507, 공식본 원본은 회사)"
    ),
    "followup": "후속 책임(FUP51~53·DIR41·RISK51) — 담당·기한·내용(U508)",
    "evidence": "근거 문서 — 종류·연결 대상·작성/확인(가상 증빙)",
    "task": "업무 — 담당·기한·인수·완료·기한 초과·이력",
    "agent_draft": "AI 초안(AG51~58) — 고정 초안 재생(REPLAY)·사람 검토 기록",
    "handoff": "후속 책임 인계(HANDOFF51) — 인계 기록·완료 요건(U508)",
}


def records_of(doc: dict) -> list[dict[str, Any]]:
    """지금 문서의 장면 5 기록 전부(판 번호 없이)."""
    from app.sc05 import view  # view가 process를 읽는다 — 순환을 피해 늦게 읽는다

    v = view.view(doc)
    head = {
        k: v[k]
        for k in (
            "demoRunId",
            "caseId",
            "caseLabel",
            "clock",
            "step",
            "status",
            "sc04",
            "sceneInfo",
            "schedule",
            "settings",
            "planPointer",
            "official",
            "reviewForecastId",
            "forecastBlocking",
            "sourceIssues",
            "startCheck",
            "completion",
            "budget",
            "observation",
            "observationPreview",
            "shares",
            "directiveLog",
            "executor",
            "agentMode",
            "alerts",
            "companyLog",
        )
    }
    head["bpm"] = bpm_head(v["bpm"])
    out = [record("scene", scoped(SCENE, "SC05"), v["status"]["scene"], TITLE, head)]
    out += items(SCENE, "execution_plan", v["plans"], "plan_id", "state", "plan_id")
    out += items(SCENE, "collaboration", v["collaborations"], "collab_id", None, "kind")
    out += items(SCENE, "condition", v["conditions"], "condition_id", "state", "content")
    out += items(SCENE, "execution_request", v["requests"], "request_id", "state", "reason")
    out += items(SCENE, "budget_txn", v["ledger"], "txn_id", "type", "txn_id")
    if v["start"] is not None:
        out.append(
            record(
                "action_start", scoped(SCENE, v["start"]["start_id"]), None, "운영 착수", v["start"]
            )
        )
    out += items(SCENE, "action_operation", v["operation"], "task_id", "state", "task_id")
    out += items(SCENE, "customer_plan", v["customerPlans"], "plan_ref", None, "plan_ref")
    out += items(SCENE, "production_change", v["changes"], "change_id", "decision", "change_id")
    if v["orders"]:
        out.append(
            record(
                "purchase_orders",
                scoped(SCENE, "ORDERS"),
                None,
                f"구매 주문 {len(v['orders'])}건",
                {"orders": v["orders"]},
            )
        )
    out += items(SCENE, "operating_plan", v["operatingPlans"], "plan_id", "state", "plan_id")
    out += items(SCENE, "forecast_run", v["runs"], "run_id", None, "run_id")
    out += items(SCENE, "forecast", v["forecasts"], "forecast_id", "state", "forecast_id")
    out += items(SCENE, "followup", v["followups"], "followup_id", "state", "content")
    out += items(SCENE, "evidence", v["evidence"], "evidence_id", None, "type")
    out += items(SCENE, "task", v["tasks"], "task_id", "status", "type")
    out += items(SCENE, "agent_draft", v["agentOutputs"], "output_id", "status", "kind")
    # 감사 이력은 한 줄이 기록 하나다 — 쌓이기만 하고 고치지 않아 판이 하나다. 인계 본문에 넣으면
    # 조작마다 이력 전체가 새 판이 되어 회사 기록이 제곱으로 불었다(엔진 시험 실측).
    out += items(SCENE, "audit", v["audit"], "seq", None, "action")
    out.append(
        record(
            "handoff",
            scoped(SCENE, "SC05"),
            "HANDED_OFF" if v["handoff"] else "PENDING",
            "후속 책임 인계",
            {"handoff": v["handoff"], "completion": v["completion"]},
        )
    )
    return out


__all__ = ["KINDS", "SCENE", "TITLE", "records_of"]
