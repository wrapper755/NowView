/**
 * Rolling Plan 계산.
 *
 * 이 화면에서 가장 틀리기 쉬운 것은 **과제 효과의 이중 계상**이다.
 * 이미 Forecast에 반영된 과제를 또 더하면 Gap이 실제보다 메워진 것처럼 보인다.
 * 그래서 합산은 전부 `reflectedInForecast`로 갈라서 한다.
 *
 * Target은 입력으로만 받고 어떤 함수도 이를 바꾸지 않는다 (CLAUDE.md 1장).
 */

import type { ActionItem, PlanItem, RollingPlan } from "@/lib/types/rolling";
import type { Alternative, ReviewDecision } from "@/lib/types/workspace";

export interface GapSummary {
  /** 확정 목표. 바뀌지 않는다. */
  target: number;
  /** 현재 Forecast. 반영 완료된 과제 효과까지 포함한 값이다. */
  forecast: number;
  /** 현재 잔여 Gap (Forecast − Target, 음수면 미달). */
  gap: number;
  /** 이미 Forecast에 반영된 과제의 목표 회수액 합. */
  reflectedRecovery: number;
  /** 아직 반영되지 않은(승인 직후) 과제의 목표 회수액 합. */
  pendingRecovery: number;
  /** 미반영분까지 반영했을 때의 Forecast 전망. */
  projectedForecast: number;
  /** 그때의 잔여 Gap. */
  projectedGap: number;
  /** 반영 완료 과제의 실제 회수 진척률(%). 목표 회수액이 0이면 0. */
  realizationRate: number;
}

export function summarizeGap(plan: RollingPlan, actions: ActionItem[]): GapSummary {
  const reflected = actions.filter((a) => a.reflectedInForecast);
  const pending = actions.filter((a) => !a.reflectedInForecast);

  const reflectedRecovery = reflected.reduce((sum, a) => sum + a.targetRecovery, 0);
  const pendingRecovery = pending.reduce((sum, a) => sum + a.targetRecovery, 0);
  const realized = reflected.reduce((sum, a) => sum + a.realizedRecovery, 0);

  const projectedForecast = plan.forecast + pendingRecovery;

  return {
    target: plan.target,
    forecast: plan.forecast,
    gap: plan.forecast - plan.target,
    reflectedRecovery,
    pendingRecovery,
    projectedForecast,
    projectedGap: projectedForecast - plan.target,
    realizationRate: reflectedRecovery === 0 ? 0 : (realized / reflectedRecovery) * 100,
  };
}

/**
 * Management Review 승인 결정을 실행 과제로 변환한다 (루프 4단계).
 *
 * 승인 직후의 과제이므로 아직 Forecast에 반영되지 않았고(`reflectedInForecast: false`)
 * 회수 실적도 0이다. 다음 Rolling 회차에서 반영된다.
 */
export function decisionToAction(
  decision: ReviewDecision,
  alternative: Alternative,
  sourceRiskId: string,
): ActionItem {
  return {
    id: `act-${decision.alternativeId}`,
    title: `${alternative.name} (${alternative.lever.label} ${decision.leverValue}${alternative.lever.unit})`,
    owner: alternative.owner,
    due: alternative.leadTime,
    division: "파워트레인/샤시",
    targetRecovery: decision.profitImpact,
    realizedRecovery: 0,
    status: "not-started",
    reflectedInForecast: false,
    sourceRiskId,
  };
}

/**
 * 여러 시나리오의 승인 결정을 하나로 합친다 — Mock 경로와 엔진 경로가 섞일 때 쓴다.
 *
 * **이중 계상 금지가 여기에도 걸린다.** ④ Rolling Plan은 전사 자산이라 모든 시나리오의
 * 승인을 함께 받는데(CLAUDE.md 4.13), 한 시나리오에 엔진 인스턴스가 붙어 있으면 그
 * 시나리오의 권위는 엔진에 있다. Mock 스토어의 결정과 함께 더하면 같은 승인이 두 번
 * 잡히고, **금액이 그럴듯해서 눈으로는 잡히지 않는다.**
 *
 * 엔진이 소유한 시나리오는 아직 승인 전이어도 Mock 결정을 쓰지 않는다 — 실행 중인
 * 그래프가 승인 지점에 닿지도 않았는데 과제가 잡히면 "결정되지 않은 것을 확정된 것처럼
 * 표시하는" 것이 된다(4.10과 같은 이유).
 */
export function mergeDecisions(
  mock: Record<string, ReviewDecision | null>,
  engine: { engagedScenarioIds: string[]; decisionByScenario: Record<string, ReviewDecision> },
): Record<string, ReviewDecision> {
  const engaged = new Set(engine.engagedScenarioIds);
  const merged: Record<string, ReviewDecision> = {};

  for (const [scenarioId, decision] of Object.entries(mock)) {
    if (!decision || engaged.has(scenarioId)) continue;
    merged[scenarioId] = decision;
  }
  for (const [scenarioId, decision] of Object.entries(engine.decisionByScenario)) {
    merged[scenarioId] = decision;
  }
  return merged;
}

/** 실행계획 항목의 현재 상태. 승인 여부에 따라 보여 줄 값이 달라진다. */
export interface PlanItemView {
  item: PlanItem;
  /** 지금 유효한 계획값. 승인 전 `drivenByDecision` 항목은 baseline이 유효하다. */
  effective: string;
  /** 승인으로 조정되었는가. */
  adjusted: boolean;
  /** 승인을 기다리는 조정인가. */
  awaitingDecision: boolean;
}

/**
 * 승인 여부를 반영한 실행계획.
 *
 * 승인 전에는 `planned`를 유효한 값으로 보여주지 않는다 — 결정되지 않은 계획을 확정된
 * 것처럼 표시하면 안 된다. 대신 "승인 시 조정 예정"으로 남겨 둔다.
 */
export function planView(plan: RollingPlan, hasDecision: boolean): PlanItemView[] {
  return plan.plan.map((item) => {
    const adjusted = item.drivenByDecision && hasDecision;
    return {
      item,
      effective: adjusted || !item.drivenByDecision ? item.planned : item.baseline,
      adjusted,
      awaitingDecision: item.drivenByDecision && !hasDecision,
    };
  });
}

/** 분기 합계가 전사 수치와 맞는지 확인한다. 어긋난 Rolling Plan은 보고서로 쓸 수 없다. */
export function assertQuartersBalance(plan: RollingPlan): void {
  const sum = (key: "target" | "forecast") =>
    plan.quarters.reduce((total, q) => total + q[key], 0);

  if (sum("target") !== plan.target) {
    throw new Error(`분기 Target 합 ${sum("target")} ≠ 전사 Target ${plan.target}`);
  }
  if (sum("forecast") !== plan.forecast) {
    throw new Error(`분기 Forecast 합 ${sum("forecast")} ≠ 전사 Forecast ${plan.forecast}`);
  }
}
