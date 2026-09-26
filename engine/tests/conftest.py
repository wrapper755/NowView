"""
테스트 고정물 — 시나리오 1(수익성 하락)의 실제 토폴로지를 쓴다.

지어낸 그래프로 시험하면 실제 명세의 문제를 못 잡는다. 실제로 `op-control`에
나가는 엣지가 없다는 것이 여기서 드러났다.
"""

from __future__ import annotations

import pytest

from app.agents import make_runner
from app.instances import InstanceStore
from app.spec import ProcessSpec

#: `lib/mock-data/bpm-process.ts`에서 추출한 토폴로지.
SCENARIO_1 = {
    "scenario_id": "scn-profitability",
    "subject": "파워트레인 가동률 임계치 이탈 대응",
    "risk_id": "risk-utilization",
    "kri": {"label": "설비 가동률", "value": "82.1%", "threshold": "85.0%"},
    "nodes": [
        {"id": "start", "kind": "start", "label": "KRI 임계치 이탈 감지"},
        {"id": "sensing", "kind": "agent-task", "label": "실적 편차·선행 리스크 수집",
         "agent_id": "agent-sensing"},
        {"id": "rca", "kind": "agent-task", "label": "다차원 원인 분석",
         "agent_id": "agent-rca"},
        {"id": "gw-escalate", "kind": "gateway", "label": "부서 간 조정 필요?"},
        {"id": "op-control", "kind": "user-task", "label": "현업 단위 사전 통제",
         "actor": "생산본부 김상현"},
        {"id": "simulate", "kind": "agent-task", "label": "대응 대안 3안 시뮬레이션",
         "agent_id": "agent-simulation"},
        {"id": "review", "kind": "user-task", "label": "Management Review",
         "actor": "경영진 (CFO)"},
        {"id": "action", "kind": "user-task", "label": "실행 과제 변환·배포",
         "actor": "사업기획팀 정하윤"},
        {"id": "rolling", "kind": "service-task", "label": "Forecast 즉시 갱신"},
        {"id": "evolution", "kind": "agent-task", "label": "KRI 임계치·룰 개선",
         "agent_id": "agent-evolution"},
        {"id": "end", "kind": "end", "label": "루프 종료"},
    ],
    "edges": [
        {"id": "e1", "source": "start", "target": "sensing"},
        {"id": "e2", "source": "sensing", "target": "rca"},
        {"id": "e3", "source": "rca", "target": "gw-escalate"},
        {"id": "e4", "source": "simulate", "target": "review"},
        {"id": "e5", "source": "review", "target": "action"},
        {"id": "e6", "source": "action", "target": "rolling"},
        {"id": "e7", "source": "rolling", "target": "evolution"},
        {"id": "e8", "source": "evolution", "target": "end"},
    ],
    "agents": [
        {"id": "agent-sensing", "name": "Risk Sensing Agent", "role": "편차·선행 리스크 수집",
         "capability": "실적/외부 데이터"},
        {"id": "agent-rca", "name": "Root Cause Agent", "role": "다차원 원인 분석",
         "capability": "물량·단가·원가"},
        {"id": "agent-simulation", "name": "Simulation Agent", "role": "대안 시뮬레이션",
         "capability": "손익 영향"},
        {"id": "agent-evolution", "name": "Evolution Agent", "role": "룰 개선",
         "capability": "임계치 백테스트"},
    ],
    "gateways": [
        {"node_id": "gw-escalate", "flag": "crossFunctional",
         "when_true": "simulate", "when_false": "op-control"},
    ],
    "decision_node_id": "review",
    "alternatives": [
        {"id": "alt-1", "title": "전장 물량 이관", "recommended": True},
        {"id": "alt-2", "title": "보전비 이연", "recommended": False},
        {"id": "alt-3", "title": "CR 협상 강화", "recommended": False},
    ],
    "decision_rules": {"rationale_min_length": 10},
}


def spec_with(cross_functional: bool) -> ProcessSpec:
    """
    `rca` Agent가 "부서 간 조정 필요"를 어떻게 판정하는지에 따라 경로가 갈린다.
    **명세는 한 벌이고 플래그만 다르다** — 그게 이 그래프가 진짜 분기라는 증거다.
    """
    data = {
        **SCENARIO_1,
        "agent_outputs": [
            {"agent_id": "agent-sensing", "node_id": "sensing",
             "output": "가동률 82.1%, 3개월 연속 하락 확인.",
             "sources": [{"label": "MES 가동 로그", "quality": "complete"}],
             "duration": "4분 12초", "confidence": "high"},
            {"agent_id": "agent-rca", "node_id": "rca",
             "output": "물량 감소가 갭의 68%를 설명한다.",
             "sources": [{"label": "수주 이력", "quality": "partial",
                          "caveat": "9월 일부 품번 미확정"}],
             "duration": "11분 04초", "confidence": "medium",
             "confidence_note": "9월 수주 데이터에 결손이 있다.",
             "flags": {"crossFunctional": cross_functional}},
            {"agent_id": "agent-simulation", "node_id": "simulate",
             "output": "1안 +18억 / 2안 +12억 / 3안 +9억 손익 영향 산출 완료.",
             "sources": [{"label": "표준원가", "quality": "complete"}],
             "duration": "6분 38초", "confidence": "high"},
            {"agent_id": "agent-evolution", "node_id": "evolution",
             "output": "가동률 KRI 임계치 85% → 87% 상향 제안.",
             "sources": [{"label": "백테스트", "quality": "complete"}],
             "duration": "3분 20초", "confidence": "high"},
        ],
    }
    return ProcessSpec.model_validate(data)


@pytest.fixture
def store() -> InstanceStore:
    return InstanceStore(":memory:", runner_factory=lambda mode: make_runner(mode))
