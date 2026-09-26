/**
 * 시나리오 3 — 기존 사업과 신사업 간 투자 배분.
 *
 * 기획안 4.1이 "전사 관점: 기존 사업과 신사업 간 자원 배분, 손익구조 변화, 투자·운영계획의
 * 조정"을 경영 고민으로 들었는데 시나리오 1·2가 모두 사업부 단위 편차 시정이라 이 축이
 * 비어 있었다.
 *
 * **앞 둘과 다른 점은 결정의 성격이다.** 1·2번은 "무엇을 고칠 것인가"였고 이번은
 * "한정된 재원을 어디에 둘 것인가"다 — 어느 대안을 골라도 다른 쪽이 준다. 그래서
 * 대안마다 비용이 0일 수 없고, 회수 기간이 조치형 대안보다 길다.
 *
 * 구조는 그대로 재사용한다. 노드 종류·상태 파생·Agent 실행 기록 형식이 모두 같고,
 * Portfolio Agent 하나만 추가된다.
 */

import type { BpmProcessInstance } from "@/lib/types/bpm";

const MAIN_LANE_Y = 0;
const BRANCH_LANE_Y = 170;

export const allocationProcess: BpmProcessInstance = {
  id: "proc-2026-0928-allocation",
  subject: "신사업 투자회수 지연에 따른 재원 배분 재검토",
  riskId: "risk-newbiz-roi",
  kri: { label: "신사업 투자회수율", value: "58.0%", threshold: "75.0%" },
  startedAt: "2026-09-28 10:00",

  sequence: [
    "start",
    "sensing",
    "rca",
    "gw-escalate",
    "simulate",
    "review",
    "action",
    "rolling",
    "evolution",
    "end",
  ],
  // 전사 배분 결정을 기다리는 지점에서 시작한다 (sequence 인덱스 5).
  defaultStepIndex: 5,

  nodes: [
    {
      id: "start",
      kind: "start",
      label: "투자회수율 임계 이탈",
      stage: "risk-sensing",
      position: { x: 0, y: MAIN_LANE_Y + 10 },
      outcome: "누적 투자 대비 회수 58.0% (임계 75%) — 자동 착수",
      duration: "즉시",
    },
    {
      id: "sensing",
      kind: "agent-task",
      label: "투자·회수 실적 수집",
      actor: "Risk Sensing Agent",
      agentId: "agent-sensing",
      stage: "risk-sensing",
      position: { x: 100, y: MAIN_LANE_Y },
      outcome: "전장 누적 투자 840억 대비 누적 회수 487억, 계획 대비 17%p 미달",
      duration: "4분 48초",
    },
    {
      id: "rca",
      kind: "agent-task",
      label: "회수 지연 원인 분해",
      actor: "Portfolio Agent",
      agentId: "agent-portfolio",
      stage: "risk-sensing",
      position: { x: 296, y: MAIN_LANE_Y },
      outcome: "주 원인: 양산 시점 이동(기여도 46%) · 부 원인: 초기 수율 미달, 단가 협상 지연",
      duration: "9분 12초",
    },
    {
      id: "gw-escalate",
      kind: "gateway",
      label: "전사 배분 판단 필요?",
      stage: "operation-control",
      position: { x: 492, y: MAIN_LANE_Y + 12 },
      outcome: "사업부 권한을 넘는 재원 이동 → 전사 경영 검토로 에스컬레이션",
      // 배분 안건은 판정 대상이 "부서 간 조정"이 아니라 "전사 재원 이동"이다 —
      // 물음이 다르면 플래그도 다르다. 같은 이름을 쓰면 Agent가 엉뚱한 판정을 한다.
      decision: {
        flag: "companyWideAllocation",
        whenTrue: "simulate",
        whenFalse: "op-control",
      },
    },
    {
      id: "op-control",
      kind: "user-task",
      label: "사업부 내 집행 조정",
      actor: "전장 사업부",
      stage: "operation-control",
      position: { x: 470, y: BRANCH_LANE_Y },
    },
    {
      id: "simulate",
      kind: "agent-task",
      label: "배분 대안 3안 시뮬레이션",
      actor: "Simulation Agent",
      agentId: "agent-simulation",
      stage: "management-review",
      position: { x: 628, y: MAIN_LANE_Y },
      outcome: "전장 증액 / 기존 사업 구조 개선 / 조건부 분할 — 손익·회수 기간 산출 완료",
      duration: "13분 26초",
    },
    {
      id: "review",
      kind: "user-task",
      label: "전사 재원 배분 결정",
      actor: "경영진 (CEO 주재)",
      stage: "management-review",
      position: { x: 824, y: MAIN_LANE_Y },
      outcome: "배분안 검토 중 — 어느 안을 골라도 반대편 재원이 줄어든다",
    },
    {
      id: "action",
      kind: "user-task",
      label: "투자·운영계획 반영",
      actor: "재무팀",
      stage: "management-action",
      position: { x: 1020, y: MAIN_LANE_Y },
    },
    {
      id: "rolling",
      kind: "service-task",
      label: "Forecast·Plan 동시 조정",
      actor: "Rolling Plan Engine",
      stage: "rolling-plan",
      position: { x: 1216, y: MAIN_LANE_Y },
    },
    {
      id: "evolution",
      kind: "agent-task",
      label: "투자 심의 기준 개선",
      actor: "Evolution Agent",
      agentId: "agent-evolution",
      stage: "management-evolution",
      position: { x: 1412, y: MAIN_LANE_Y },
    },
    {
      id: "end",
      kind: "end",
      label: "루프 종료",
      stage: "management-evolution",
      position: { x: 1608, y: MAIN_LANE_Y + 10 },
    },
  ],

  edges: [
    { id: "e-start-sensing", source: "start", target: "sensing" },
    { id: "e-sensing-rca", source: "sensing", target: "rca" },
    { id: "e-rca-gw", source: "rca", target: "gw-escalate" },
    {
      id: "e-gw-simulate",
      source: "gw-escalate",
      target: "simulate",
      sourceHandle: "main",
      label: "예",
    },
    {
      id: "e-gw-op",
      source: "gw-escalate",
      target: "op-control",
      sourceHandle: "branch",
      label: "아니오",
    },
    { id: "e-simulate-review", source: "simulate", target: "review" },
    { id: "e-review-action", source: "review", target: "action" },
    { id: "e-action-rolling", source: "action", target: "rolling" },
    { id: "e-rolling-evolution", source: "rolling", target: "evolution" },
    { id: "e-evolution-end", source: "evolution", target: "end" },
  ],

  agents: [
    {
      id: "agent-sensing",
      name: "Risk Sensing Agent",
      role: "실적 편차 및 선행 리스크 감지",
      capability: "MES·ERP 시계열 수집, KRI 임계치 비교",
    },
    {
      id: "agent-portfolio",
      name: "Portfolio Agent",
      role: "사업 포트폴리오 회수 분석",
      capability: "투자 집행·회수 시계열 대조, 사업부 간 재원 배분 영향 추정",
    },
    {
      id: "agent-simulation",
      name: "Simulation Agent",
      role: "대응 대안 시뮬레이션",
      capability: "대안별 손익·회수 기간 추정",
    },
    {
      id: "agent-evolution",
      name: "Evolution Agent",
      role: "프레임워크·룰 개선 제안",
      capability: "KRI 임계치 재산정, 심의 기준 보완",
    },
  ],

  runs: [
    {
      agentId: "agent-sensing",
      nodeId: "sensing",
      output:
        "전장 누적 투자 840억, 누적 회수 487억(58.0%). 투자 심의 당시 계획은 3년차 75%였다.",
      sources: [
        { name: "투자 집행 원장", quality: "complete" },
        { name: "사업부별 손익 배부", quality: "complete" },
        {
          name: "투자 심의 계획서(2023)",
          quality: "stale",
          caveat: "심의 당시 가정이며 이후 전동화 속도 변화가 반영되지 않았다.",
        },
      ],
      duration: "4분 48초",
      confidence: "high",
    },
    {
      agentId: "agent-portfolio",
      nodeId: "rca",
      output:
        "기여도 분해 — 양산 시점 이동 46%, 초기 수율 미달 29%, 단가 협상 지연 18%, 기타 7%.",
      sources: [
        { name: "양산 일정 이력", quality: "complete" },
        {
          name: "고객 중장기 물량 계획",
          quality: "partial",
          caveat: "2개 고객사만 제공받았다. 나머지는 3개월 예보로 대체했다.",
        },
        {
          name: "경쟁사 전장 진입 동향",
          quality: "estimated",
          caveat: "공개 자료 기반 추정이며 실제 캐파 증설 규모는 확인되지 않았다.",
        },
      ],
      duration: "9분 12초",
      confidence: "low",
      confidenceNote:
        "중장기 물량 계획이 일부만 확보되어 회수 전망의 불확실성이 크다. 배분 결정의 근거로 쓰기에는 보강이 필요하다.",
      escalations: [
        {
          id: "esc-longterm-volume",
          question: "미확보 고객사의 중장기 물량 계획을 받을 수 있는가?",
          reason:
            "Agent가 접근할 수 있는 것은 3개월 예보뿐이다. 회수 전망은 3년 단위인데 근거는 분기 단위다.",
          owner: "영업본부 박지우",
          ifUnanswered:
            "확보된 2개 고객사 추세를 전체에 적용해 추정했다. 나머지 고객사가 다르게 움직이면 회수율 전망이 크게 달라진다.",
        },
        {
          id: "esc-investment-ceiling",
          question: "올해 추가 배분 가능한 재원의 상한은 얼마인가?",
          reason: "재무 승인 한도는 시스템에 없다. 자금 계획 담당의 확인이 필요하다.",
          owner: "재무팀 한지훈",
          ifUnanswered: "상한 없이 대안을 산출했다. 한도가 30억 미만이면 1안은 성립하지 않는다.",
        },
      ],
    },
    {
      agentId: "agent-simulation",
      nodeId: "simulate",
      output:
        "1안 전장 증액 30억 → 연 7.5억 회수 가속(회수 4.0년), 2안 기존 사업 구조 개선 20억 → 연 12억(0.5년), 3안 조건부 분할 40% → 연 4.8억(2.9년).",
      sources: [
        { name: "라인별 표준원가", quality: "complete" },
        {
          name: "전장 수주 파이프라인",
          quality: "estimated",
          caveat: "수주 확정 전 물량 포함. 확정분만 보면 1안 회수는 연 4.6억으로 줄어든다.",
        },
        {
          name: "기존 사업 고정비 구조",
          quality: "partial",
          caveat: "공용 설비 배부 기준이 2025년에 바뀌어 이전 연도와 직접 비교되지 않는다.",
        },
      ],
      duration: "13분 26초",
      confidence: "medium",
      confidenceNote:
        "1안의 회수 기간 4.0년은 파이프라인 가정에 민감하다. 확정 물량만으로는 6.5년이 된다.",
    },
  ],
};
