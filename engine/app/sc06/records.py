"""
장면 6(과제 완료와 성과 실현 검토)의 경영 기록 — 회사 시스템에 적는 판(`app/records.py`, 스키마
`docs/records/sc06/`).

장면 6 화면은 문서 머리(`view.view`)와 조회 넷(U601 요약 · ACT42 차이 상세 · 근거 · U602 보고
요약)을 읽는다. 조회는 행위자에 따라 403이라 **검토건 담당(경영관리 담당)이 보는 응답 그대로**
적는다 — 회사 사이트는 사람마다 다른 권한을 다시 판정하지 않는다(보는 사람의 권한은 사이트 로그인
몫이다). 숫자는 규칙 계산(`calc`)이고 기대 효과의 기준인 공식 전망 FC51은 회사 기록에서 읽어
대조한 것이다. 회사 확정 기록에 적는 것은 없다.
"""

from __future__ import annotations

from typing import Any

from app.records import bpm_head, items, record, scoped

SCENE = 6
TITLE = "과제 완료와 성과 실현 검토"
#: 기록 종류 — 스키마 `docs/records/sc06/{kind}.schema.json`의 설명
KINDS = {
    "scene": (
        "장면 머리 — 시연 시각·보고본·산정 버전·적재 묶음·장면 5 결과·상태·알림·회사와 오간 것"
    ),
    "procedure": (
        "확인 절차 — 단계별 담당·계획 시각·확인 기록(CF61-*)·남는 사항·물러난 기록·확정 차단 사유"
    ),
    "review_summary": (
        "U601 요약 — 3과제의 기대·확인 효과·차이·완료 판단·Agent 후보(경영관리 담당의 조회)"
    ),
    "task_variance": (
        "ACT42 차이 상세 — 원인별 건수·실제 긴급비, 대표 주문 PO61-1103, AG62 초안과 사람 보정"
    ),
    "evidence": "근거 — 본문·작성/확인 이력(가상 증빙)",
    "performance_report": (
        "U602 보고 요약(RPT61) — 결론·운영 보완·추가 검토 발의·위험·확인 다섯 단계·다음 보고"
    ),
    "task": "업무 — 담당·기한·완료·이력",
}


def _read(fn, *args, **kwargs) -> dict | None:
    """조회 하나 — 아직 읽을 수 없으면(보고본 전 등) 기록하지 않는다."""
    from app.sc06 import domain

    try:
        return fn(*args, **kwargs)
    except domain.ReadError:
        return None


def records_of(doc: dict) -> list[dict[str, Any]]:
    """지금 문서의 장면 6 기록 전부(판 번호 없이)."""
    from app.sc06 import domain, view  # view가 process를 읽는다 — 순환을 피해 늦게 읽는다

    v = view.view(doc)
    reader = domain.ACCOUNTS["USR-FIN"]
    head = {
        k: v[k]
        for k in (
            "demoRunId",
            "caseId",
            "clock",
            "step",
            "reviewId",
            "reportVersion",
            "calculationVersion",
            "reportState",
            "sc05",
            "batch",
            "status",
            "executor",
            "companyLog",
        )
    }
    head["bpm"] = bpm_head(v["bpm"])
    state = v["status"].get("procedure")
    out = [record("scene", scoped(SCENE, "SC06"), state, TITLE, head)]
    if v["procedure"] is not None:
        out.append(record("procedure", scoped(SCENE, "RV61"), state, "확인 절차", v["procedure"]))
    summary = _read(domain.summary, doc, actor=reader)
    if summary is not None:
        out.append(
            record(
                "review_summary", scoped(SCENE, "RV61"), v["reportState"], "완료·성과 요약", summary
            )
        )
    variance = _read(domain.variance, doc, "ACT42", actor=reader)
    if variance is not None:
        out.append(record("task_variance", scoped(SCENE, "ACT42"), None, "ACT42 차이", variance))
    for evidence_id in sorted(doc["evidence"]):
        found = _read(domain.evidence, doc, evidence_id, actor=reader)
        if found is not None:
            out.append(record("evidence", scoped(SCENE, evidence_id), None, evidence_id, found))
    version = doc["report"]["report_version"]
    report = _read(domain.report, doc, version, actor=reader)
    if report is not None:
        out.append(
            record(
                "performance_report", scoped(SCENE, version), v["reportState"], "보고 요약", report
            )
        )
    out += items(SCENE, "task", v["tasks"], "task_id", "status", "type")
    return out


__all__ = ["KINDS", "SCENE", "TITLE", "records_of"]
