/**
 * Management Review 작업공간 타입.
 *
 * 설계 원칙 (CLAUDE.md 1장 Human-in-the-Loop):
 * Agent는 감지·분석·시뮬레이션까지 하고, **선택과 승인은 사람이 한다.**
 * 그래서 `recommendedAlternativeId`는 어디까지나 권고이며, 결정에는 사람이 적은
 * 사유(`rationale`)가 반드시 남는다 — 근거 없는 승인은 기록으로 남길 가치가 없다.
 */

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
  /** 레버 1단위당 영업이익 개선액(억원). */
  profitPerUnit: number;
  /** 레버 1단위당 가동률 개선(%p). */
  utilizationPerUnit: number;
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
}

/** Agent 보고서의 한 절. 근거 소스가 없는 절은 두지 않는다. */
export interface AgentReportSection {
  id: string;
  title: string;
  body: string;
  sources: string[];
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
