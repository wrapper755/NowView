/**
 * 시나리오 2 — 전장 ECU 납기 준수율 하락 대응.
 *
 * **구조 재사용을 검증하는 것이 이 시나리오의 목적 중 하나다**(기획안 4.2). 노드 종류,
 * 상태 파생 규칙, Agent 실행 기록 형식은 시나리오 1과 완전히 동일하고 내용만 다르다.
 * 시나리오 1과 다른 점은 둘뿐이다:
 *   · 게이트웨이에서 **현업 통제 경로가 선택된다** — 시나리오 1은 에스컬레이션됐다.
 *     Operation Control이 실제로 작동하는 모습을 보여 주는 것이 이 시나리오의 몫이다.
 *   · Agent 하나(Supply Risk Agent)가 추가된다. 나머지 Agent는 그대로 재사용한다.
 *
 * 수치 연동: KRI 납기 준수율 94.2% / 임계 97%는 `next-automotive.ts`의 리스크 신호
 * `risk-delivery`와 같아야 한다.
 */

import type { BpmProcessInstance } from "@/lib/types/bpm";

const MAIN_LANE_Y = 0;
const BRANCH_LANE_Y = 170;

export const deliveryProcess: BpmProcessInstance = {
  id: "proc-2026-0921-delivery",
  subject: "전장 ECU 납기 준수율 하락 대응",
  riskId: "risk-delivery",
  kri: { label: "납기 준수율", value: "94.2%", threshold: "97.0%" },
  startedAt: "2026-09-21 09:00",

  // 이번에는 현업 통제(op-control)가 선택되고 경영 검토 경로가 skipped가 된다.
  sequence: [
    "start",
    "sensing",
    "rca",
    "gw-escalate",
    "op-control",
    "verify",
    "rolling",
    "evolution",
    "end",
  ],
  // 현업 통제를 수행 중인 지점에서 시작한다 (sequence 인덱스 4).
  defaultStepIndex: 4,

  nodes: [
    {
      id: "start",
      kind: "start",
      label: "납기 준수율 임계 이탈",
      stage: "risk-sensing",
      position: { x: 0, y: MAIN_LANE_Y + 10 },
      outcome: "주간 납기 준수율 94.2% (임계 97%) — 자동 착수",
      duration: "즉시",
    },
    {
      id: "sensing",
      kind: "agent-task",
      label: "출하 지연 건 수집",
      actor: "Risk Sensing Agent",
      agentId: "agent-sensing",
      stage: "risk-sensing",
      position: { x: 100, y: MAIN_LANE_Y },
      outcome: "4주간 지연 출하 37건, 고객사·품번·지연일수별 분포 확보",
      duration: "3분 05초",
    },
    {
      id: "rca",
      kind: "agent-task",
      label: "지연 원인 분해",
      actor: "Supply Risk Agent",
      agentId: "agent-supply",
      stage: "risk-sensing",
      position: { x: 296, y: MAIN_LANE_Y },
      outcome: "주 원인: MCU 입고 지연(기여도 58%) · 부 원인: 긴급 오더 우선순위 충돌",
      duration: "6분 21초",
    },
    {
      id: "gw-escalate",
      kind: "gateway",
      label: "부서 간 조정 필요?",
      stage: "operation-control",
      position: { x: 492, y: MAIN_LANE_Y + 12 },
      outcome: "구매·생산 권한 내 처리 가능 → 현업 통제로 대응",
      // 같은 규칙, 반대 판정 — 구매·생산 권한 안이라 거짓으로 판정되어 현업 통제로 간다.
      // 캔버스에서는 이쪽이 `main` 핸들(직선)이지만 핸들과 판정은 무관하다.
      decision: {
        flag: "crossFunctionalCoordination",
        whenTrue: "simulate",
        whenFalse: "op-control",
      },
    },
    {
      id: "simulate",
      kind: "agent-task",
      label: "대응 대안 시뮬레이션",
      actor: "Simulation Agent",
      agentId: "agent-simulation",
      stage: "management-review",
      position: { x: 628, y: BRANCH_LANE_Y },
    },
    {
      id: "op-control",
      kind: "user-task",
      label: "현업 단위 사전 통제",
      actor: "구매본부 최민서",
      stage: "operation-control",
      position: { x: 628, y: MAIN_LANE_Y },
      outcome: "안전재고 상향 및 긴급 오더 우선순위 규칙 적용 — 권한 내 처리",
    },
    {
      id: "verify",
      kind: "service-task",
      label: "통제 효과 확인",
      actor: "Operation Control Engine",
      stage: "operation-control",
      position: { x: 824, y: MAIN_LANE_Y },
      outcome: "적용 2주 후 납기 준수율 96.1%로 회복 — 임계 재이탈 없음",
    },
    {
      id: "rolling",
      kind: "service-task",
      label: "Forecast 영향 반영",
      actor: "Rolling Plan Engine",
      stage: "rolling-plan",
      position: { x: 1020, y: MAIN_LANE_Y },
    },
    {
      id: "evolution",
      kind: "agent-task",
      label: "통제 기준 개선",
      actor: "Evolution Agent",
      agentId: "agent-evolution",
      stage: "management-evolution",
      position: { x: 1216, y: MAIN_LANE_Y },
    },
    {
      id: "end",
      kind: "end",
      label: "루프 종료",
      stage: "management-evolution",
      position: { x: 1412, y: MAIN_LANE_Y + 10 },
    },
  ],

  edges: [
    { id: "e-start-sensing", source: "start", target: "sensing" },
    { id: "e-sensing-rca", source: "sensing", target: "rca" },
    { id: "e-rca-gw", source: "rca", target: "gw-escalate" },
    {
      id: "e-gw-op",
      source: "gw-escalate",
      target: "op-control",
      sourceHandle: "main",
      label: "아니오",
    },
    {
      id: "e-gw-simulate",
      source: "gw-escalate",
      target: "simulate",
      sourceHandle: "branch",
      label: "예",
    },
    { id: "e-op-verify", source: "op-control", target: "verify" },
    { id: "e-verify-rolling", source: "verify", target: "rolling" },
    { id: "e-rolling-evolution", source: "rolling", target: "evolution" },
    { id: "e-evolution-end", source: "evolution", target: "end" },
  ],

  // Supply Risk Agent만 추가되고 나머지는 시나리오 1과 같은 Agent를 그대로 쓴다.
  agents: [
    {
      id: "agent-sensing",
      name: "Risk Sensing Agent",
      role: "실적 편차 및 선행 리스크 감지",
      capability: "MES·ERP 시계열 수집, KRI 임계치 비교",
    },
    {
      id: "agent-supply",
      name: "Supply Risk Agent",
      role: "공급망 기인 지연 원인 분석",
      capability: "입고 리드타임·재고 수준·오더 우선순위 축 기여도 분해",
    },
    {
      id: "agent-simulation",
      name: "Simulation Agent",
      role: "대응 대안 시뮬레이션",
      capability: "대안별 손익·납기 영향 추정",
    },
    {
      id: "agent-evolution",
      name: "Evolution Agent",
      role: "프레임워크·룰 개선 제안",
      capability: "KRI 임계치 재산정, 통제 기준 보완",
    },
  ],

  runs: [
    {
      agentId: "agent-sensing",
      nodeId: "sensing",
      output:
        "4주간 지연 출하 37건. 고객사 A 21건·B 11건·기타 5건이며 평균 지연 3.4일. 전량 전장 ECU 품번이다.",
      sources: [
        { name: "WMS 출하 실적", quality: "complete" },
        { name: "고객 납기 약정 마스터", quality: "complete" },
        {
          name: "긴급 오더 접수 이력",
          quality: "partial",
          caveat: "구두 접수분은 시스템에 남지 않아 실제 긴급 오더는 더 많을 수 있다.",
        },
      ],
      duration: "3분 05초",
      confidence: "high",
    },
    {
      agentId: "agent-supply",
      nodeId: "rca",
      output:
        "기여도 분해 — MCU 입고 지연 58%, 긴급 오더 우선순위 충돌 27%, 라인 전환 준비 9%, 기타 6%.",
      sources: [
        { name: "구매 입고 실적", quality: "complete" },
        {
          name: "공급사 납기 회신",
          quality: "estimated",
          caveat: "공급사가 통보한 예정일이며 실제 입고와 평균 4일 차이가 있었다.",
        },
        {
          name: "생산 계획 변경 이력",
          quality: "partial",
          caveat: "라인 전환 관련 변경은 시나리오 1 승인 이후분만 기록돼 있다.",
        },
      ],
      duration: "6분 21초",
      confidence: "medium",
      confidenceNote:
        "공급사 회신일이 추정치라 MCU 기여도 58%는 ±7%p 범위로 본다.",
      escalations: [
        {
          id: "esc-emergency-order",
          question: "긴급 오더를 접수 단계에서 제한할 수 있는가?",
          reason:
            "구두 접수분이 시스템에 없어 Agent는 실제 긴급 오더 규모를 알 수 없다. 영업 운영 규칙은 데이터로 확인되지 않는다.",
          owner: "영업본부 박지우",
          ifUnanswered:
            "시스템 기록분만으로 27% 기여도를 산정했다. 구두 접수가 많다면 우선순위 규칙 개선 효과가 과소평가된다.",
        },
      ],
    },
  ],
};
