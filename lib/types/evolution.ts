/**
 * Management Evolution 타입 (루프 6단계).
 *
 * 이 단계의 대상은 실적이 아니라 **경영 시스템 자체**다 — KRI 감지 임계치, Agent 룰,
 * 프레임워크 지표 정의. 앞 단계들이 "이번 건을 어떻게 할 것인가"를 다뤘다면 여기서는
 * "다음에 같은 일이 생기면 더 빨리 잡히는가"를 다룬다.
 */

import type { Severity } from "@/lib/types/cockpit";

/**
 * 개선 대상. 기획안 3.5가 규정한 **Framework · Process · Agent** 셋을 모두 덮어야 한다.
 *
 * `kri-threshold`·`metric-definition`은 Framework, `process-rule`은 Process, `agent-rule`은
 * Agent에 해당한다. Process가 빠지면 "역할·책임, 검토 시점, 승인·보고 경로"를 고칠 길이
 * 없어져, 지표와 룰만 계속 손보게 된다.
 */
export type ProposalKind =
  | "kri-threshold"
  | "metric-definition"
  | "process-rule"
  | "agent-rule";

export const PROPOSAL_KIND_LABEL: Record<ProposalKind, string> = {
  "kri-threshold": "KRI 임계치",
  "metric-definition": "지표 정의",
  "process-rule": "Process 규칙",
  "agent-rule": "Agent 룰",
};

/** 기획안 3.5의 3개 개선 대상 축. 제안 종류를 이 축으로 묶어 본다. */
export type EvolutionTarget = "framework" | "process" | "agent";

export const EVOLUTION_TARGET_LABEL: Record<EvolutionTarget, string> = {
  framework: "Management Framework",
  process: "Management Process",
  agent: "AI Agent",
};

export function targetOf(kind: ProposalKind): EvolutionTarget {
  switch (kind) {
    case "kri-threshold":
    case "metric-definition":
      return "framework";
    case "process-rule":
      return "process";
    case "agent-rule":
      return "agent";
  }
}

export type ProposalStatus = "proposed" | "adopted" | "deferred";

export const PROPOSAL_STATUS_LABEL: Record<ProposalStatus, string> = {
  proposed: "검토 대기",
  adopted: "채택",
  deferred: "보류",
};

/**
 * 개선 제안 하나.
 *
 * `tradeoff`는 선택이 아니라 필수다 — 부작용 없는 개선은 없고, 그것을 적지 않은 제안은
 * 검토할 수 없다. 임계치를 조이면 반드시 오탐이 늘어난다.
 */
export interface EvolutionProposal {
  id: string;
  kind: ProposalKind;
  title: string;
  /** 이 제안을 촉발한 사건 (Cockpit RiskSignal id 또는 설명). */
  triggeredBy: string;
  rationale: string;
  before: string;
  after: string;
  expectedEffect: string;
  /** 감수해야 하는 부작용. */
  tradeoff: string;
  owner: string;
}

/**
 * 임계치별 백테스트 결과 한 점.
 *
 * 공식이 아니라 **과거 데이터로 재현한 결과 표**다. Mock 단계에서 그럴듯한 수식을 만들면
 * 없는 정밀도를 주장하게 되므로, 임계치별 결과를 값으로 들고 간다.
 */
export interface BacktestPoint {
  threshold: number;
  /** 실제 문제를 잡아낸 건수. */
  detections: number;
  /** 문제가 아니었는데 울린 건수. */
  falsePositives: number;
  /** 현행 임계치 대비 평균 며칠 앞서 감지했는가. */
  leadTimeDays: number;
}

/** 튜닝 대상 KRI 하나. */
export interface KriTuning {
  id: string;
  label: string;
  unit: string;
  /** 현행 감지 임계치. */
  currentThreshold: number;
  /** Evolution Agent 권고 임계치. */
  recommendedThreshold: number;
  /** 임계치 미만이면 감지되는가 (가동률·수율 등). false면 초과 시 감지. */
  detectBelow: boolean;
  step: number;
  /** 임계치별 백테스트 결과. threshold 오름차순. */
  backtest: BacktestPoint[];
  /** 이번 사건에서 드러난 문제. */
  observedIssue: string;
}

/** 이미 반영된 진화 항목. 루프가 이전에도 돌았다는 기록이다. */
export interface AppliedEvolution {
  id: string;
  date: string;
  kind: ProposalKind;
  summary: string;
  /** 반영 후 관측된 효과. */
  observedEffect: string;
}

export interface EvolutionLab {
  /** 이번 진화 검토를 촉발한 안건. */
  subject: string;
  riskId: string;
  kris: KriTuning[];
  proposals: EvolutionProposal[];
  applied: AppliedEvolution[];
}

/** 오탐 비율에 따른 등급. 임계치를 조일수록 올라간다. */
export function falsePositiveSeverity(rate: number): Severity {
  if (rate <= 20) return "good";
  if (rate <= 40) return "warning";
  if (rate <= 60) return "serious";
  return "critical";
}
