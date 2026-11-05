"""
공통 플랫폼 카탈로그 — 역할·업무 단위·위임 수준·실행 방식·상태 어휘(`docs/platform.md` §4).

업무설계서 v0.3 CP26·28·30과 시나리오 2 전체 업무연결설계 v0.2 「역할정의」·「업무조합」의
표를 코드로 둔다. 화면(회사 사이트)은 기록에 실린 이 값을 그대로 보인다 — 사이트에
사본을 두지 않는다.

* **사람·Agent·일반 시스템을 나눈다**(CP26) — 정해진 계산·저장을 모두 Agent로 표현하지 않는다. Y01은
  「시스템 자동처리(규칙 엔진)」이지 Agent가 아니다.
* **역할 수 ≠ Agent 수**다 — A03은 논리 역할이고 별도 Agent 구축을 뜻하지 않는다(역할정의 머리).
* 역할의 직위 배정은 제안이다(H03 Case 책임 등) — 구체 사용자 매핑은 구현명세에서 확정한다(Q03).
"""

from __future__ import annotations

from typing import Any

HUMAN, AGENT, SYSTEM = "human", "agent", "system"

#: 역할 — 역할정의 시트(시나리오 2). `label`이 왼쪽 목록 표시명이다.
ROLES: dict[str, dict[str, Any]] = {
    "H01": {"kind": HUMAN, "label": "구매 담당자", "title": "담당"},
    "H02": {"kind": HUMAN, "label": "생산계획 담당자", "title": "담당"},
    "H03": {"kind": HUMAN, "label": "생산관리 책임자", "title": "관리자"},
    "H04": {"kind": HUMAN, "label": "출하·물류 담당자", "title": "담당"},
    "H05": {"kind": HUMAN, "label": "생산총괄 임원", "title": "임원"},
    "H06": {"kind": HUMAN, "label": "관리 기준 책임자", "title": "기준 책임"},
    "H07": {"kind": HUMAN, "label": "Agent 운영 담당자", "title": "운영"},
    "A01": {"kind": AGENT, "label": "납기위험 분석 Agent", "title": None},
    "A02": {"kind": AGENT, "label": "생산계획 지원 Agent", "title": None},
    "A03": {"kind": AGENT, "label": "사건대응 계획 지원 Agent", "title": None},
    "Y01": {"kind": SYSTEM, "label": "시스템 자동처리 (규칙 엔진)", "title": None},
}

#: 재사용 업무 단위 U01~U09 — 업무조합 시트. 장면 2(N03A)의 수행계획 항목이 이 id를 참조한다.
UNITS: dict[str, dict[str, Any]] = {
    "U01": {"name": "통합 납기 영향 점검", "steps": ["N03", "N07"], "selection": "required"},
    "U02": {"name": "생산계획 변경안 작성", "steps": ["N04"], "selection": "conditional"},
    "U03": {"name": "생산계획 변경 확인", "steps": ["N05"], "selection": "required_if_change"},
    "U04": {"name": "확인 계획 반영과 재조회", "steps": ["N06"], "selection": "conditional"},
    "U05": {"name": "잔여 위험과 종료 판단", "steps": ["N07", "N08"], "selection": "required"},
    "U06": {"name": "운송 대안 사실 확인", "steps": ["N09"], "selection": "conditional"},
    "U07": {
        "name": "경영검토 준비와 대응 결정",
        "steps": ["N09", "N10"],
        "selection": "conditional",
    },
    "U08": {"name": "관찰과 후속 결과 연결", "steps": ["N08", "N11"], "selection": "required"},
    "U09": {"name": "기준 개선과 검증 적용", "steps": ["N12", "N16"], "selection": "optional"},
}

#: 위임 수준(CP28) — A 조회·분석·초안, B 사람 확인 후 반영, C 사전 조건 내 자동 실행
DELEGATION = {"A": "조회·분석·초안", "B": "사람 확인 후 확정 반영", "C": "사전 조건 내 자동 실행"}
#: 업무 단위의 위임 수준과 기본 수행 역할 — 시나리오 2 장면 2 수행계획(SC02수행계획 「담당」)의
#: U01~U05와 장면 3 수행계획 v2(상세화면구성 01 「역할과 권한」)의 U06·U07. U03·U07은 사람 확인·
#: 결정 그 자체라 위임 수준이 없다. U08·U09는 그 장면이 오면 정한다.
UNIT_PLAN: dict[str, dict[str, Any]] = {
    "U01": {"delegation": "A", "owner": ["A03", "Y01"]},
    "U02": {"delegation": "A", "owner": ["A02"]},
    "U03": {"delegation": None, "owner": ["H03"]},
    "U04": {"delegation": "B", "owner": ["Y01"]},
    "U05": {"delegation": "A", "owner": ["Y01", "A01"]},
    # 기존 운송 문의(원업무)를 참조해 회신을 연결·비교한다 — 원업무 담당은 H04 그대로다
    "U06": {"delegation": "A", "owner": ["H04", "A01"]},
    # 재보고가 있을 때만 활성 — 결정은 사람(H05)이다
    "U07": {"delegation": None, "owner": ["H03", "H05"]},
}

#: 역할의 직위 배정(가안 — 구현명세 Q03 「구체 사용자 매핑」 전). 결재 담당자 이름
#: (`chk:approval.assignees`)과 시험이 맞춰 본다.
#: * H03 생산관리 책임자(관리자) = 회사 명단의 생산팀장. 장면 3의 「담당 팀장」(AUTH-T1 전결 한도의
#:   주인, 재보고하는 사람)도 H03으로 둔다.
#: * H04 출하·물류 담당자 = 「출하담당」 — 명단에 출하 직원이 없어 역할명을 이름으로 더했다(인명을
#:   지어내지 않는다, 장면 7 「운영담당」과 같다).
#: * H05 생산총괄 임원 = 회사 명단의 생산임원.
HOLDERS: dict[str, list[str]] = {"H03": ["배정훈"], "H04": ["출하담당"], "H05": ["권태윤"]}

#: 실행 방식(F05) — 화면이 구분해 보인다. 가상자료 재현을 실제 AI 호출로 표시하지 않는다.
EXECUTION_MODES = {
    "live_agent": "실제 Agent",
    "rule": "규칙 처리",
    "prepared": "준비된 결과",
    "mock": "모의 연계",
}

#: 위험 상태(업무설계서 §7) — 자료 부족은 미평가. 업무 상태와 다르다.
RISK_STATES = {
    "UNEVALUATED": "미평가",
    "WATCH": "주의",
    "RISK": "위험",
    "ACCEPTABLE": "허용 범위",
    "OBSERVE": "관찰",
}

#: Case 상태(업무설계서 §7·T02)
CASE_STATES = {
    "RECEIVED": "접수",
    "ANALYZING": "분석 중",
    "ANALYZED": "영향 분석 완료",
    "CONTROL": "정형통제",
    "AWAITING_CONFIRM": "확인 대기",
    "REVIEW": "경영검토",
    "FOLLOW_UP": "후속 조치",
    "CLOSED": "종료",
}

#: Agent·도구 실행 상태(T13)
RUN_STATES = {
    "WAITING": "대기",
    "RUNNING": "실행 중",
    "AWAITING_CONFIRM": "확인 대기",
    "SUCCEEDED": "성공",
    "FAILED": "실패",
    "PARTIAL": "부분 성공",
    "STOPPED": "중지",
}


def role(role_id: str) -> dict[str, Any]:
    """역할 하나 — 기록에 싣는 모양(id·구분·표시명·직위)."""
    found = ROLES[role_id]
    return {"role_id": role_id, **found}


__all__ = [
    "AGENT",
    "CASE_STATES",
    "DELEGATION",
    "EXECUTION_MODES",
    "HOLDERS",
    "HUMAN",
    "RISK_STATES",
    "ROLES",
    "RUN_STATES",
    "SYSTEM",
    "UNITS",
    "UNIT_PLAN",
    "role",
]
