"""
장면 7(실제 경험을 관리모델 개선으로 연결)의 경영 기록 — 회사 시스템에 적는 판(`app/records.py`,
스키마 `docs/records/sc07/`).

장면 7 화면(U701)은 문서 머리(`view.view`)와 조회 넷(개선 전후 · 검증 · 적용 · 근거)을 읽는다.
조회는 행위자에 따라 403이라 **경영관리 담당이 보는 응답 그대로** 적는다. 검증 관측값·적용
상태(ST703~707)는 규칙 계산이다. 회사 확정 기록에 적는 것은 없다(Agent 설정은 NowView 기록이다 —
2026-11-02 사용자 결정).
"""

from __future__ import annotations

from typing import Any

from app.records import bpm_head, items, record, scoped

SCENE = 7
TITLE = "실제 경험을 관리모델 개선으로 연결"
#: 기록 종류 — 스키마 `docs/records/sc07/{kind}.schema.json`의 설명
KINDS = {
    "scene": (
        "장면 머리 — 시연 시각·개선건·버전 묶음·적재 묶음·장면 6 보고본·상태 배지·회사와 오간 것"
    ),
    "procedure": "확인·적용 절차 — 검증 실행·확인 단계(CF71·CF72)·설정 반영·후속 점검·이력·거절",
    "improvement": (
        "U701 보기 A — 개선 사유·기존 검토(AG62 원본·제한 입력)·개선한 검토 방식·기준·절차"
    ),
    "verification": (
        "U701 보기 B 왼쪽 — 검증 세트 TS71-v1, TC701 상세·TC702~708 요약(규칙으로 다시 계산)"
    ),
    "application": (
        "U701 보기 B 오른쪽 — 범위·버전·확인 이력·설정 반영·다섯 조건·운영 실행(미확인)·후속 점검"
    ),
    "evidence": "근거 — SC07근거 EV71~78·장면 6 대표 사례 E61-1103(화면 조회)",
    "task": "업무 — 담당·기한·완료·이력",
}


def _read(fn, *args, **kwargs) -> dict | None:
    from app.sc07 import domain

    try:
        return fn(*args, **kwargs)
    except domain.ReadError:
        return None


def records_of(doc: dict) -> list[dict[str, Any]]:
    """지금 문서의 장면 7 기록 전부(판 번호 없이)."""
    from app.sc07 import domain, view  # view가 process를 읽는다 — 순환을 피해 늦게 읽는다

    v = view.view(doc)
    reader = domain.ACCOUNTS["USR-FIN"]
    head = {
        k: v[k]
        for k in (
            "demoRunId",
            "caseId",
            "clock",
            "step",
            "improvementId",
            "applicationId",
            "datasetVersion",
            "versionBundle",
            "sc06",
            "batch",
            "status",
            "executor",
            "companyLog",
        )
    }
    head["bpm"] = bpm_head(v["bpm"])
    state = v["status"].get("procedure")
    out = [record("scene", scoped(SCENE, "SC07"), state, TITLE, head)]
    if v["procedure"] is not None:
        out.append(
            record("procedure", scoped(SCENE, "IMP71"), state, "확인·적용 절차", v["procedure"])
        )
    for kind, fn, rid, title, state_of in (
        ("improvement", domain.improvement, "IMP71", "개선 전후", lambda _f: None),
        ("verification", domain.verification, "IMP71", "검증", lambda f: f["summary"]["state"]),
        ("application", domain.application, "AP71", "적용", lambda f: f["state"]["state"]),
    ):
        found = _read(fn, doc, actor=reader)
        if found is not None:
            out.append(record(kind, scoped(SCENE, rid), state_of(found), title, found))
    ids = sorted(doc["evidence"])
    s6 = (doc.get("sc06") or {}).get("evidence")
    if s6:
        ids.append(s6["evidence_id"])
    for evidence_id in ids:
        found = _read(domain.evidence, doc, evidence_id, actor=reader)
        if found is not None:
            out.append(record("evidence", scoped(SCENE, evidence_id), None, evidence_id, found))
    out += items(SCENE, "task", v["tasks"], "task_id", "status", "type")
    return out


__all__ = ["KINDS", "SCENE", "TITLE", "records_of"]
