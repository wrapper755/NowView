/**
 * 시나리오 레지스트리.
 *
 * 기획안 4.2는 첫 시나리오로 작동모델을 연결·검증한 뒤 약 3개로 확장하라고 한다.
 * 세 번째를 붙일 때도 **이 파일에 한 항목을 더하는 것으로 끝나야 한다** — 화면이나
 * 스토어를 고쳐야 한다면 그건 구조가 시나리오에 묶여 있다는 뜻이다.
 *
 * 시나리오 2를 붙이면서 실제로 하나 걸렸다: 대안의 부수 효과가 `utilizationPerUnit`
 * (가동률)으로 타입에 박혀 있었다. 납기 시나리오에는 맞지 않아 `secondaryLabel`/
 * `secondaryUnit`/`secondaryPerUnit`으로 일반화했다.
 */

import { deliveryProcess } from "@/lib/mock-data/bpm-process-delivery";
import { bpmProcess } from "@/lib/mock-data/bpm-process";
import { deliveryReviewCase } from "@/lib/mock-data/review-case-delivery";
import { reviewCase } from "@/lib/mock-data/review-case";
import { deliveryScenes, profitabilityScenes } from "@/lib/demo-scenario";
import { simulateAlternative } from "@/services/agent-orchestrator";
import type { Scenario } from "@/lib/types/scenario";
import type { ReviewCase, ReviewDecision } from "@/lib/types/workspace";

/**
 * 데모가 자동으로 적용하는 결정을 만든다.
 *
 * 금액은 `simulateAlternative`로 계산해 화면·API와 같은 값이 되게 한다(하드코딩 금지).
 * `decidedAt`은 **고정 문자열**이다 — 스토어가 모듈 로드 시점에 만들어지므로 `new Date()`를
 * 쓰면 서버와 클라이언트 값이 달라져 하이드레이션이 깨진다.
 */
function demoDecisionFor(
  source: ReviewCase,
  rationale: string,
  decidedAt: string,
): ReviewDecision {
  const alternative = source.alternatives.find(
    (a) => a.id === source.recommendedAlternativeId,
  );
  if (!alternative) {
    throw new Error(`${source.id}: Agent 권고안을 찾을 수 없다`);
  }
  return {
    alternativeId: alternative.id,
    leverValue: alternative.lever.base,
    profitImpact: simulateAlternative(alternative, alternative.lever.base).profitImpact,
    rationale,
    decidedAt,
  };
}

export const scenarios: Scenario[] = [
  {
    id: "scn-profitability",
    title: "수익성 하락 및 목표 미달 위험 대응",
    shortTitle: "수익성 하락",
    summary:
      "파워트레인 가동률이 임계치를 이탈해 영업이익 Gap이 확대됐다. 부서 간 조정이 필요해 Management Review로 에스컬레이션된다.",
    riskId: "risk-utilization",
    process: bpmProcess,
    reviewCase,
    scenes: profitabilityScenes,
    demoDecision: demoDecisionFor(
      reviewCase,
      "가동률 회복이 구조적 문제에 대한 정면 대응이라 판단한다. 전환 기간 중 납기 리스크는 2개 라인으로 제한해 감수한다.",
      "2026-09-30 15:20",
    ),
  },
  {
    id: "scn-delivery",
    title: "납기 목표 준수 위험 대응",
    shortTitle: "납기 준수",
    summary:
      "전장 ECU 납기 준수율이 임계치를 밑돌았다. 구매·생산 권한 안에서 처리 가능해 경영 검토 없이 현업 통제로 대응한다.",
    riskId: "risk-delivery",
    process: deliveryProcess,
    reviewCase: deliveryReviewCase,
    scenes: deliveryScenes,
    demoDecision: demoDecisionFor(
      deliveryReviewCase,
      "MCU 입고 지연이 주 원인이므로 재고 완충이 가장 빠른 대응이다. 운전자본 부담은 25일 수준으로 제한한다.",
      "2026-10-05 11:40",
    ),
  },
];

export const DEFAULT_SCENARIO_ID = scenarios[0].id;

export function scenarioById(id: string): Scenario {
  return scenarios.find((s) => s.id === id) ?? scenarios[0];
}
