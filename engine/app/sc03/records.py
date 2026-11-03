"""
장면 3(수익성 변동의 통합 분석과 수시 경영검토)의 경영 기록 — 회사 시스템에 적는 판
(`app/records.py`, 스키마 `docs/records/sc03/`).

본문은 NowView 장면 3 화면이 읽는 모양 그대로다(`view.view`의 같은 칸). 원가 버전 C02-APP01은 회사
구매 기록에서 읽어 대조만 한다 — 여기 것은 경영 기록이다(통합 분석·보고 버전·부서 확인·쟁점·회의·
결론·분석과제·인계). 화면 상태 칸(`answerHere`·결재 대기 폼·`historical`)은 싣지 않는다.
"""

from __future__ import annotations

from typing import Any

from app.records import bpm_head, items, record, scoped

SCENE = 3
TITLE = "수익성 변동의 통합 분석과 수시 경영검토"
#: 기록 종류 — 스키마 `docs/records/sc03/{kind}.schema.json`의 설명
KINDS = {
    "audit": "감사 이력 한 줄 — 누가·언제·무엇을(쌓이기만 한다)",
    "scene": (
        "장면 머리 — 시연 시각·상태 묶음·장면 2 결과 스냅샷·일정·인수율·완료 요건·"
        "알림·회사와 오간 것"
    ),
    "profit_review": "상위 검토건(MR-2706-01) — 상태·결론·위험·전망·Target과 물량·원가 이슈 연결",
    "analysis_run": (
        "통합 분석 한 번 — 기간별 손익(물량·단가 효과, 기존·전체 부족)·모델별·검증. "
        "숫자는 규칙 계산(U32)"
    ),
    "review_report": "보고 버전 — 초안(v0)·확정(v1)·재검토, 핵심 숫자와 근거 기준(U32·U34)",
    "dept_confirmation": "부서 확인 요청과 회신 — 영업·구매·생산의 상태·회신·확인 사실(U33)",
    "fact": "확인된 사실 — 부서·분류·근거·확인자(U33)",
    "question": "쟁점 — 미확인·이견, 차단 여부·담당·기한·처리 방향·판단 이력(U33)",
    "meeting": "회의(MT31) — 안건·참석·질의/답변 기록(U34)",
    "candidate": "개선 후보 — 메커니즘·제약·포함/제외 판단과 사유·연결 과제(U35)",
    "meeting_decision": "회의 결론(REV31) — 결론·조건·남은 쟁점(U35)",
    "minutes": "회의록 — 포함/제외 후보·과제·다음 회의(U35)",
    "analysis_task": "분석과제(AT31~34) — 질문·산출물·책임자·협업·기한·배정버전·인수(U36)",
    "task": "업무 — 담당·기한·인수·완료·기한 초과·이력",
    "agent_draft": "AI 초안 — 검증을 통과한 응답만(거절 응답·입력 원문 없음)",
    "handoff": "장면 4 인계(HANDOFF31) — 인계 기록·완료 요건(U37)",
}


def records_of(doc: dict) -> list[dict[str, Any]]:
    """지금 문서의 장면 3 기록 전부(판 번호 없이)."""
    from app.sc03 import view  # view가 process를 읽는다 — 순환을 피해 늦게 읽는다

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
            "sc02",
            "schedule",
            "latestRunId",
            "currentDraftId",
            "frozenReportId",
            "freezeProblems",
            "acceptance",
            "delayed",
            "revisions",
            "executor",
            "agentMode",
            "alerts",
            "companyLog",
        )
    }
    head["bpm"] = bpm_head(v["bpm"])
    out = [record("scene", scoped(SCENE, "SC03"), v["status"]["scene"], TITLE, head)]
    review = v["review"]
    if review is not None:
        out.append(
            record(
                "profit_review",
                scoped(SCENE, review["review_id"]),
                review.get("state"),
                "수익성 통합 검토",
                review,
            )
        )
    out += items(SCENE, "analysis_run", v["runs"], "run_id", "status", "run_id")
    out += items(SCENE, "review_report", v["reports"], "report_id", "status", "report_id")
    if v["confirmation"] is not None:
        body = {
            "confirmation": v["confirmation"],
            "departments": v["departments"],
            "replies": v["replies"],
        }
        done = all(d["state"] == "RESPONDED" for d in v["departments"])
        out.append(
            record(
                "dept_confirmation",
                scoped(SCENE, "CONFIRM"),
                "RESPONDED" if done else "REQUESTED",
                "부서 확인",
                body,
            )
        )
    out += items(SCENE, "fact", v["facts"], "fact_id", "state", "statement")
    out += items(SCENE, "question", v["questions"], "question_id", "state", "question")
    out += items(SCENE, "meeting", v["meetings"], "meeting_id", "state", "subject")
    out += items(SCENE, "candidate", v["candidates"], "candidate_id", "decision", "candidate")
    decision = v["decision"]
    if decision is not None:
        out.append(
            record(
                "meeting_decision",
                scoped(SCENE, decision["decision_id"]),
                decision.get("outcome"),
                "회의 결론",
                decision,
            )
        )
    out += items(SCENE, "minutes", v["minutes"], "minutes_id", "outcome", "minutes_id")
    out += items(SCENE, "analysis_task", v["assignments"], "task_id", "state", "title")
    out += items(SCENE, "task", v["tasks"], "task_id", "status", "type")
    out += items(SCENE, "agent_draft", v["agentOutputs"], "output_id", "status", "kind")
    # 감사 이력은 한 줄이 기록 하나다 — 쌓이기만 하고 고치지 않아 판이 하나다. 인계 본문에 넣으면
    # 조작마다 이력 전체가 새 판이 되어 회사 기록이 제곱으로 불었다(엔진 시험 실측).
    out += items(SCENE, "audit", v["audit"], "seq", None, "action")
    out.append(
        record(
            "handoff",
            scoped(SCENE, "SC03"),
            "HANDED_OFF" if v["handoff"] else "PENDING",
            "장면 4 인계",
            {"handoff": v["handoff"], "completion": v["completion"]},
        )
    )
    return out


__all__ = ["KINDS", "SCENE", "TITLE", "records_of"]
