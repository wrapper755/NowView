/**
 * Management Review 작업공간 타입.
 *
 * 설계 원칙 (CLAUDE.md 1장 Human-in-the-Loop):
 * Agent는 감지·분석·시뮬레이션까지 하고, **선택과 승인은 사람이 한다.**
 * 그래서 `recommendedAlternativeId`는 어디까지나 권고이며, 결정에는 사람이 적은
 * 사유(`rationale`)가 반드시 남는다 — 근거 없는 승인은 기록으로 남길 가치가 없다.
 */

import type { AgentEscalation, Confidence, DataSource } from "@/lib/types/agent";
import type { Severity } from "@/lib/types/cockpit";

/**
 * 시뮬레이션 레버 하나.
 *
 * 응답 모델은 의도적으로 선형이다. Mock 단계에서 비선형 곡선을 꾸며내면 근거 없는
 * 정밀도를 주장하게 된다. 실제 엔진이 붙으면 이 계수 대신 추정 결과를 받는다.
 */
export interface SimulationLever {
  id: string;
  label: string;
  unit: string;
  min: number;
  max: number;
  step: number;
  /** Agent가 제안한 기본값. 이 값에서의 효과가 Agent 보고서의 수치와 일치해야 한다. */
  base: number;
  /** 레버 1단위당 영업이익 개선액(억원). 연간 기준이다. */
  profitPerUnit: number;
  /**
   * 부수 효과 지표의 이름·단위·계수.
   *
   * 시나리오마다 다르다 — 수익성 안건은 가동률(%p), 납기 안건은 납기 준수율(%p)이다.
   * 처음에는 `utilizationPerUnit`으로 가동률이 타입에 박혀 있었는데, 두 번째 시나리오를
   * 붙이면서 그것이 시나리오 고유 가정이었음이 드러나 일반화했다.
   */
  secondaryLabel: string;
  secondaryUnit: string;
  secondaryPerUnit: number;
  /**
   * 레버 1단위당 실행 비용(억원). 일회성 투자·이설 비용이다.
   *
   * 비용도 레버에 비례해야 한다 — 효과만 늘고 비용은 고정이면 레버를 끝까지 올리는 것이
   * 항상 정답이 되어 트레이드오프가 사라진다.
   */
  costPerUnit: number;
}

/** 레버 값이 이 값 이하이면 해당 등급. 오름차순으로 둔다. */
export interface RiskBand {
  upTo: number;
  severity: Severity;
}

export interface Alternative {
  id: string;
  /** "1안" 같은 짧은 식별 라벨. */
  tag: string;
  name: string;
  summary: string;
  lever: SimulationLever;
  /** 레버를 키울수록 올라가는 리스크 구간. */
  riskBands: RiskBand[];
  riskNote: string;
  leadTime: string;
  owner: string;
  /**
   * 실행 조건 — 이것이 갖춰지지 않으면 기대 효과가 나지 않는다.
   *
   * 기획안 2.1: "대응 대안에는 기대 효과뿐 아니라 비용·위험·실행 조건을 함께 제시한다."
   * 조건 없이 효과만 적힌 대안은 비교가 아니라 홍보다.
   */
  prerequisites: string[];
  /** 비용의 성격 (투자비인지 일회성 비용인지). 금액은 `lever.costPerUnit`에서 나온다. */
  costNote: string;
}

/** Agent 보고서의 한 절. 근거 소스가 없는 절은 두지 않는다. */
export interface AgentReportSection {
  id: string;
  title: string;
  body: string;
  /** 근거 소스와 그 품질. 불완전한 데이터 위에 선 결론임을 숨기지 않는다. */
  sources: DataSource[];
  /** 이 절의 신뢰도. */
  confidence: Confidence;
  /** `high`가 아니면 그 이유. */
  confidenceNote?: string;
}

export interface ReviewCase {
  id: string;
  subject: string;
  /** 연결된 BPM 프로세스 id — 같은 안건임을 보장한다. */
  processId: string;
  /** 연결된 Cockpit RiskSignal id. */
  riskId: string;
  /** 전사 영업이익 Gap(억원). 음수이며 Cockpit 값과 일치해야 한다. */
  profitGap: number;
  report: AgentReportSection[];
  /**
   * Agent가 답하지 못해 사람에게 넘긴 판단.
   *
   * 결정의 전제이므로 승인 화면에서 먼저 보여야 한다 — 답하지 않은 질문 위에서 내린
   * 결정은 그 가정이 틀리면 함께 무너진다.
   */
  escalations: AgentEscalation[];
  /** Agent 권고안. 사람이 따를 의무는 없다. */
  recommendedAlternativeId: string;
  alternatives: Alternative[];
}

/**
 * 결정 사유 최소 길이.
 *
 * UI(승인 버튼 활성 조건)와 API(`/api/bpm/decision` 검증)가 같은 값을 써야 한다 —
 * 두 곳에 각자 숫자를 박아 두면 한쪽만 바뀌어 규칙이 갈라진다.
 */
export const DECISION_RATIONALE_MIN_LENGTH = 10;

/** 사람이 내린 결정. 사유 없이는 만들 수 없다. */
export interface ReviewDecision {
  alternativeId: string;
  /** 승인 시점의 레버 값. 기본값과 다르면 사람이 조정했다는 뜻이다. */
  leverValue: number;
  /** 해당 레버 값에서의 영업이익 개선액(억원). */
  profitImpact: number;
  /** 사람이 적은 결정 사유. */
  rationale: string;
  decidedAt: string;
}
