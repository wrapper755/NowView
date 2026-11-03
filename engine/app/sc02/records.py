"""
장면 2(외주 단가 인상 검토)의 경영 기록 — 회사 시스템에 적는 판(`app/records.py`, 스키마
`docs/records/sc02/`).

본문은 NowView 장면 2 화면이 읽는 모양 그대로다(`view.view`의 같은 칸). 회사 확정 기록(요청
확인 상태·원가 버전 C02-APP01)은 지금처럼 구매 기록에도 적는다 — 여기 것은 경영 기록이다(요청
분석·협상·기안·결재·인계). 화면 상태 칸(`answerHere`·결재 대기 폼·`historical`)은 싣지 않는다 —
결재는 Center에 있고 회사 사이트 결재 화면이 그린다.
"""

from __future__ import annotations

from typing import Any

from app.records import bpm_head, items, record, scoped

SCENE = 2
TITLE = "외주 단가 인상 검토"
#: 기록 종류 — 스키마 `docs/records/sc02/{kind}.schema.json`의 설명
KINDS = {
    "audit": "감사 이력 한 줄 — 누가·언제·무엇을(쌓이기만 한다)",
    "scene": (
        "장면 머리 — 시연 시각·장면 상태 묶음·장면 1 결과 스냅샷·실행 위치·근거 목록·"
        "알림·회사와 오간 것"
    ),
    "price_request": "단가 인상 요청 사본 — 원문 확인 결정·검사 오류·외부 협상기한(이력 포함)(U21)",
    "purchase_report": "구매 팀장 보고 — 요약·필요성·협상 방향(U21)",
    "price_version": "가격 버전 — 요청안·협상안·기안안·승인안 각각의 단가·적용일(U22)",
    "price_run": (
        "단가 영향 분석 한 번 — 기간별(잔여·12개월·Q3) 원가·손익 연결·승인선 판정. 숫자는 규칙 계산"
        "(U22)"
    ),
    "negotiation": "협상 기록 — 차수·결과·합의 단가·미해결 사항(U23)",
    "proposal": "기안 — 판(v1·v2)·단가·적용일·차이 사유·결재선·대표 대상 판정(U24)",
    "price_decision": "결재 한 단계 — 팀장·임원·대표의 결정·의견·시각(U25)",
    "instruction": "추가 협상지시(X01) — 사유·조건·담당·기한",
    "cost_version": "원가 버전 등록(C02-APP01) — 승인 단가·적용일·적용 상태(U26)",
    "issue": "원가 상승 이슈(ISSUE-COST01) — 위험·열림·분석별 이력",
    "review_link": "상위 검토건(MR-2706-01) 연결 — 장면 1 물량 감소·장면 2 원가 상승 묶음(U27)",
    "task": "업무 — 담당·기한·인수·완료·기한 초과·이력",
    "agent_draft": "AI 초안 — 검증을 통과한 응답만(거절 응답·입력 원문 없음)",
    "handoff": "경영관리 인계 — 인계 기록·완료 조건·인계 이력(U27)",
}


def records_of(doc: dict) -> list[dict[str, Any]]:
    """지금 문서의 장면 2 기록 전부(판 번호 없이)."""
    from app.sc02 import view  # view가 process를 읽는다 — 순환을 피해 늦게 읽는다

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
            "sc01",
            "executor",
            "selectedRunId",
            "selectedProvisional",
            "evidence",
            "agentMode",
            "alerts",
            "companyLog",
        )
    }
    head["bpm"] = bpm_head(v["bpm"])
    out = [record("scene", scoped(SCENE, "SC02"), v["status"]["scene"], TITLE, head)]
    req = v["request"]
    if req is not None:
        out.append(
            record(
                "price_request",
                scoped(SCENE, req["request_id"]),
                req.get("status"),
                f"{req['supplier_name']} 단가 인상 요청",
                req,
            )
        )
    rep = v["report"]
    if rep is not None:
        out.append(
            record("purchase_report", scoped(SCENE, rep["report_id"]), None, "구매 보고", rep)
        )
    out += items(SCENE, "price_version", v["priceVersions"], "version_id", "kind", "version_id")
    out += items(SCENE, "price_run", v["runs"], "run_id", "status", "run_id")
    out += items(
        SCENE, "negotiation", v["negotiations"], "negotiation_id", "outcome", "negotiation_id"
    )
    out += items(SCENE, "proposal", v["proposals"], "proposal_key", "status", "proposal_id")
    out += items(SCENE, "price_decision", v["decisions"], "decision_id", "decision", "step")
    ins = v["instruction"]
    if ins is not None:
        out.append(
            record("instruction", scoped(SCENE, ins["instruction_id"]), None, "추가 협상지시", ins)
        )
    out += items(
        SCENE, "cost_version", v["costVersions"], "cost_version_id", "status", "cost_version_id"
    )
    issue = v["issue"]
    if issue is not None:
        out.append(
            record(
                "issue", scoped(SCENE, issue["issue_id"]), issue["status"], "원가 상승 이슈", issue
            )
        )
    review = v["review"]
    if review is not None:
        out.append(
            record(
                "review_link", scoped(SCENE, review["review_id"]), None, "상위 검토건 연결", review
            )
        )
    out += items(SCENE, "task", v["tasks"], "task_id", "status", "type")
    out += items(SCENE, "agent_draft", v["agentOutputs"], "output_id", "status", "kind")
    # 감사 이력은 한 줄이 기록 하나다 — 쌓이기만 하고 고치지 않아 판이 하나다. 인계 본문에 넣으면
    # 조작마다 이력 전체가 새 판이 되어 회사 기록이 제곱으로 불었다(엔진 시험 실측).
    out += items(SCENE, "audit", v["audit"], "seq", None, "action")
    out.append(
        record(
            "handoff",
            scoped(SCENE, "SC02"),
            "HANDED_OFF" if v["handoff"] else "PENDING",
            "경영관리 인계",
            {
                "handoff": v["handoff"],
                "handoffCheck": v["handoffCheck"],
                "handoffHistory": v["handoffHistory"],
            },
        )
    )
    return out


__all__ = ["KINDS", "SCENE", "TITLE", "records_of"]
