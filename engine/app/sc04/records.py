"""
장면 4(수익성 개선 대응안 검토와 실행 승인)의 경영 기록 — 회사 시스템에 적는 판
(`app/records.py`, 스키마 `docs/records/sc04/`).

본문은 NowView 장면 4 화면이 읽는 모양 그대로다(`view.view`의 같은 칸). 장면 4는 회사 확정
기록이 없다(실행 품의·예산 거래는 장면 5) — 분석 결과·검증·추천·보고/판단본·월간회의·대표 결정·
승인서·실행과제 배정·인계가 전부 경영 기록이다. 화면 상태 칸(`answerHere`·결재 대기 폼·
`historical`)은 싣지 않는다.
"""

from __future__ import annotations

from typing import Any

from app.records import bpm_head, items, record, scoped

SCENE = 4
TITLE = "수익성 개선 대응안 검토와 실행 승인"
#: 기록 종류 — 스키마 `docs/records/sc04/{kind}.schema.json`의 설명
KINDS = {
    "audit": "감사 이력 한 줄 — 누가·언제·무엇을(쌓이기만 한다)",
    "scene": (
        "장면 머리 — 시연 시각·상태 묶음·장면 3 결과 스냅샷·일정·기준 손익·인수율·완료 요건·알림"
    ),
    "improvement_review": "검토건(MR-2706-01) — 장면 4 상태·위험·전망·Target·착수/완료 시각",
    "analysis_result": "분석과제 결과(RES41~44) — 작성·확인·판(제출·보완) 이력(U401·U402)",
    "followup_question": "장면 3에서 넘어온 쟁점(Q31·Q32) — 담당·기한·처리·이력",
    "assumption": "대응안 가정(ALT41~43) — 물량·단가·시작월 등 규칙 계산의 입력",
    "effect_run": (
        "효과 계산 한 번 — 월별 대응안 효과·중복 제거·월 손익·잔여 부족. 숫자는 규칙 계산"
        "(U402·U403)"
    ),
    "verification": "경영관리 검증 — 계산·가정 해시·확인자·상태(U402)",
    "recommendation": "담당 임원 공동 추천(RCM41) — 대안별 추천·우선순위·효과·예산(U403)",
    "improvement_report": "보고본·판단본(REP41·DEC41) — 결론·스냅샷 숫자(U404)",
    "monthly_meeting": "월간회의(MT41) — 참석·질의/지시 기록(U405)",
    "directive": "조건·지원·지시(CON41·SUP41·DIR41) — 내용·책임·확인자·기한(U406·U407)",
    "ceo_decision": "대표 결정(REV41) — 대안별 승인/조건부/보류·승인 범위 효과·남는 부족(U405)",
    "approval_draft": "승인서 초안 — 책임·예산 한도·두 기한·조건·누락 항목(U406)",
    "execution_approval": "확정 승인서(APR41) — 판단본 해시·책임·예산·기한(U406)",
    "minutes": "회의록(MIN41) — 기록·결정·승인서 연결(U406)",
    "execution_assignment": (
        "실행과제 배정·인수(ACT41~43·SUP41·전체 책임) — 배정버전·인수/반려(U407)"
    ),
    "task": "업무 — 담당·기한·인수·완료·기한 초과·이력",
    "agent_draft": "AI 초안 — 검증을 통과한 응답만(거절 응답·입력 원문 없음)",
    "handoff": "장면 5 인계(HANDOFF41) — 인계 기록·완료 요건(U408)",
}


def records_of(doc: dict) -> list[dict[str, Any]]:
    """지금 문서의 장면 4 기록 전부(판 번호 없이)."""
    from app.sc04 import view  # view가 process를 읽는다 — 순환을 피해 늦게 읽는다

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
            "sc03",
            "schedule",
            "baseline",
            "reportId",
            "decisionId",
            "acceptance",
            "completion",
            "assumptionLog",
            "rework",
            "executor",
            "agentMode",
            "alerts",
        )
    }
    head["bpm"] = bpm_head(v["bpm"])
    out = [record("scene", scoped(SCENE, "SC04"), v["status"]["scene"], TITLE, head)]
    review = v["review"]
    if review is not None:
        out.append(
            record(
                "improvement_review",
                scoped(SCENE, review["review_id"]),
                review.get("state"),
                "개선 대응안 검토",
                review,
            )
        )
    out += items(SCENE, "analysis_result", v["results"], "result_id", "state", "task_id")
    out += items(SCENE, "followup_question", v["followups"], "question_id", "state", "question")
    out += items(SCENE, "assumption", v["assumptions"], "alt_id", None, "name")
    out += items(SCENE, "effect_run", v["runs"], "run_id", "kind", "run_id")
    single = (
        ("verification", "verification", "VERIFY", "state", "경영관리 검증"),
        ("recommendation", "recommendation", "RECOMMEND", None, "우선 실행안 추천"),
        ("monthly_meeting", "meeting", "MEETING", "state", "월간회의"),
        ("ceo_decision", "decision", "DECISION", None, "대표 결정"),
        ("approval_draft", "approvalDraft", "DRAFT", None, "승인서 초안"),
    )
    for kind, key, rid, state_key, title in single:
        body = v[key]
        if body is not None:
            state = None if state_key is None else body.get(state_key)
            out.append(record(kind, scoped(SCENE, rid), state, title, body))
    out += items(SCENE, "improvement_report", v["reports"], "report_id", "status", "report_id")
    out += items(SCENE, "directive", v["directives"], "directive_id", "responsibility", "content")
    out += items(SCENE, "execution_approval", v["approvals"], "approval_id", None, "approval_id")
    out += items(SCENE, "minutes", v["minutes"], "minutes_id", None, "minutes_id")
    out += items(SCENE, "execution_assignment", v["assignments"], "target_id", "state", "target_id")
    out += items(SCENE, "task", v["tasks"], "task_id", "status", "type")
    out += items(SCENE, "agent_draft", v["agentOutputs"], "output_id", "status", "kind")
    # 감사 이력은 한 줄이 기록 하나다 — 쌓이기만 하고 고치지 않아 판이 하나다. 인계 본문에 넣으면
    # 조작마다 이력 전체가 새 판이 되어 회사 기록이 제곱으로 불었다(엔진 시험 실측).
    out += items(SCENE, "audit", v["audit"], "seq", None, "action")
    out.append(
        record(
            "handoff",
            scoped(SCENE, "SC04"),
            "HANDED_OFF" if v["handoff"] else "PENDING",
            "장면 5 인계",
            {"handoff": v["handoff"], "completion": v["completion"]},
        )
    )
    return out


__all__ = ["KINDS", "SCENE", "TITLE", "records_of"]
