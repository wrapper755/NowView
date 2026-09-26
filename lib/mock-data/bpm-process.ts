/**
 * BPM 프로세스 인스턴스 Mock — Cockpit의 `risk-utilization` 안건이 루프를 타는 모습.
 *
 * Cockpit의 리스크 목록에서 "파워트레인 가동률 임계치 이탈"(심각)이 Management Review로
 * 에스컬레이션되어 있다. 이 화면은 그 같은 사건을 프로세스 관점으로 보여주므로,
 * `riskId`와 `kri` 값은 `next-automotive.ts`의 해당 항목과 일치해야 한다.
 *
 * 좌표는 가로 1레인 + 미실행 분기 1레인 구성이다. 노드 폭 176px에 간격 196px을 두어
 * 서로 겹치지 않는다 — 좌표를 수정할 때 이 간격을 깨지 않도록 주의한다.
 */

import type { BpmProcessInstance } from "@/lib/types/bpm";

const MAIN_LANE_Y = 0;
const BRANCH_LANE_Y = 170;

export const bpmProcess: BpmProcessInstance = {
  id: "proc-2026-0912-utilization",
  subject: "파워트레인 가동률 임계치 이탈 대응",
  riskId: "risk-utilization",
  kri: { label: "설비 가동률", value: "82.1%", threshold: "85.0%" },
  startedAt: "2026-09-12 06:00",

  // op-control은 이 분기에서 선택되지 않았다 → skipped로 파생된다.
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
  // Management Review에서 사람의 판단을 기다리는 지점에서 시작한다 (sequence 인덱스 5).
  defaultStepIndex: 5,

  nodes: [
    {
      id: "start",
      kind: "start",
      label: "KRI 임계치 이탈 감지",
      stage: "risk-sensing",
      position: { x: 0, y: MAIN_LANE_Y + 10 },
      outcome: "가동률 85% 미달 3일 연속 — 자동 착수",
      duration: "즉시",
    },
    {
      id: "sensing",
      kind: "agent-task",
      label: "실적 편차·선행 리스크 수집",
      actor: "Risk Sensing Agent",
      agentId: "agent-sensing",
      stage: "risk-sensing",
      position: { x: 100, y: MAIN_LANE_Y },
      outcome: "가동률·수율·발주량 3개월 시계열 및 구매단가 변동 수집",
      duration: "4분 12초",
    },
    {
      id: "rca",
      kind: "agent-task",
      label: "다차원 원인 분석",
      actor: "Root Cause Agent",
      agentId: "agent-rca",
      stage: "risk-sensing",
      position: { x: 296, y: MAIN_LANE_Y },
      outcome: "주 원인: 내연 부품 발주 축소(기여도 62%) · 부 원인: 고정비 흡수율 하락",
      duration: "7분 38초",
    },
    {
      id: "gw-escalate",
      kind: "gateway",
      label: "부서 간 조정 필요?",
      stage: "operation-control",
      position: { x: 492, y: MAIN_LANE_Y + 12 },
      outcome: "생산·영업·구매 3개 본부 연동 필요 → 에스컬레이션",
    },
    {
      id: "op-control",
      kind: "user-task",
      label: "현업 단위 사전 통제",
      actor: "생산본부",
      stage: "operation-control",
      position: { x: 470, y: BRANCH_LANE_Y },
    },
    {
      id: "simulate",
      kind: "agent-task",
      label: "대응 대안 3안 시뮬레이션",
      actor: "Simulation Agent",
      agentId: "agent-simulation",
      stage: "management-review",
      position: { x: 628, y: MAIN_LANE_Y },
      outcome: "라인 재배치 / 전장 물량 이관 / 보전비 이연 — 손익 영향 산출 완료",
      duration: "11분 04초",
    },
    {
      id: "review",
      kind: "user-task",
      label: "Management Review",
      actor: "경영진 (CFO 주재)",
      stage: "management-review",
      position: { x: 824, y: MAIN_LANE_Y },
      outcome: "Agent 보고서 검토 중 — 대안 선택 및 승인 대기",
    },
    {
      id: "action",
      kind: "user-task",
      label: "실행 과제 변환·배포",
      actor: "사업기획팀",
      stage: "management-action",
      position: { x: 1020, y: MAIN_LANE_Y },
    },
    {
      id: "rolling",
      kind: "service-task",
      label: "Forecast 즉시 갱신",
      actor: "Rolling Plan Engine",
      stage: "rolling-plan",
      position: { x: 1216, y: MAIN_LANE_Y },
    },
    {
      id: "evolution",
      kind: "agent-task",
      label: "KRI 임계치·룰 개선",
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
    // 분기 라벨은 짧게 — 게이트웨이와 다음 노드 사이 간격이 좁아 긴 라벨은 노드에 가려진다.
    // 조건 자체는 게이트웨이 노드 라벨("부서 간 조정 필요?")이 이미 말해 준다.
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
      id: "agent-rca",
      name: "Root Cause Agent",
      role: "다차원 원인 분석",
      capability: "물량·단가·원가·수율 축 기여도 분해",
    },
    {
      id: "agent-simulation",
      name: "Simulation Agent",
      role: "대응 대안 시뮬레이션",
      capability: "대안별 손익·가동률 영향 추정",
    },
    {
      id: "agent-evolution",
      name: "Evolution Agent",
      role: "프레임워크·룰 개선 제안",
      capability: "KRI 임계치 재산정, 감지 룰 보완",
    },
  ],

  runs: [
    {
      agentId: "agent-sensing",
      nodeId: "sensing",
      output:
        "가동률 82.1%(임계 85%) 3일 연속 미달. 동일 기간 내연 부품 발주량 -11.4%, 고정비 흡수율 91.4%.",
      sources: ["MES 설비 가동 로그", "ERP 수주 잔량", "월 결산 고정비 배부표"],
      duration: "4분 12초",
    },
    {
      agentId: "agent-rca",
      nodeId: "rca",
      output:
        "기여도 분해 — 발주 축소 62%, 고정비 흡수율 하락 24%, 직행률 저하 9%, 기타 5%. 전동화 전환 추세로 회복 가능성 낮음.",
      sources: ["고객 발주 예보(3개월)", "라인별 가동 실적", "직행률 일별 추이"],
      duration: "7분 38초",
    },
    {
      agentId: "agent-simulation",
      nodeId: "simulate",
      output:
        "1안 라인 재배치 +18억/가동률 +3.2%p, 2안 전장 물량 이관 +12억/리드타임 리스크, 3안 보전비 이연 +9억/설비 리스크 누적.",
      sources: ["라인별 표준원가", "전장 수주 파이프라인", "설비 보전 이력"],
      duration: "11분 04초",
    },
  ],
};
