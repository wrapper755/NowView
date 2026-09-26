/**
 * Rolling Plan 집계와 실행계획 조정.
 *
 * **이중 계상 금지가 이 화면에서 가장 틀리기 쉽다**(CLAUDE.md 4.6). 이미 Forecast에
 * 반영된 과제를 또 더하면 Gap이 실제보다 메워진 것처럼 보이는데, 숫자가 그럴듯해서
 * 눈으로는 잡히지 않는다.
 */

import { describe, expect, it } from "vitest";

import { rollingPlan } from "@/lib/mock-data/rolling-plan";
import { scenarios } from "@/lib/mock-data/scenarios";
import { decisionToAction, planView, summarizeGap } from "@/services/rolling-plan";

const profitability = scenarios.find((s) => s.id === "scn-profitability")!;

/** 승인된 결정을 실행 과제로 바꿔 준다. 화면이 하는 일과 같은 경로다. */
function actionFor(scenarioId: string) {
  const scenario = scenarios.find((s) => s.id === scenarioId)!;
  const decision = scenario.demoDecision;
  const alternative = scenario.reviewCase.alternatives.find(
    (a) => a.id === decision.alternativeId,
  )!;
  return decisionToAction(decision, alternative, scenario.reviewCase.riskId);
}

describe("Gap 집계", () => {
  it("승인 과제를 더해도 현재 Forecast는 바뀌지 않는다", () => {
    const before = summarizeGap(rollingPlan, rollingPlan.actions);
    const after = summarizeGap(rollingPlan, [
      actionFor("scn-profitability"),
      ...rollingPlan.actions,
    ]);
    expect(after.forecast).toBe(before.forecast);
    expect(after.gap).toBe(before.gap);
  });

  it("미반영 과제는 전망치에만 반영된다", () => {
    const action = actionFor("scn-profitability");
    const after = summarizeGap(rollingPlan, [action, ...rollingPlan.actions]);
    expect(after.pendingRecovery).toBe(action.targetRecovery);
    expect(after.projectedForecast).toBe(rollingPlan.forecast + action.targetRecovery);
    expect(after.projectedGap).toBe(after.projectedForecast - rollingPlan.target);
  });

  it("세 시나리오를 모두 승인하면 전망치가 합산된다", () => {
    const actions = scenarios.map((s) => actionFor(s.id));
    const total = actions.reduce((sum, a) => sum + a.targetRecovery, 0);
    const after = summarizeGap(rollingPlan, [...actions, ...rollingPlan.actions]);

    expect(after.pendingRecovery).toBeCloseTo(total, 6);
    expect(after.projectedForecast).toBeCloseTo(rollingPlan.forecast + total, 6);
    // 현재 Forecast는 여전히 그대로 — 이것이 이중 계상 금지의 핵심이다.
    expect(after.forecast).toBe(rollingPlan.forecast);
  });

  it("반영 완료 과제만 회수 진척률에 들어간다", () => {
    const reflected = rollingPlan.actions.filter((a) => a.reflectedInForecast);
    const target = reflected.reduce((s, a) => s + a.targetRecovery, 0);
    const realized = reflected.reduce((s, a) => s + a.realizedRecovery, 0);

    // 미반영 과제(회수 0)를 더해도 진척률이 희석되면 안 된다.
    const withPending = summarizeGap(rollingPlan, [
      actionFor("scn-profitability"),
      ...rollingPlan.actions,
    ]);
    expect(withPending.realizationRate).toBeCloseTo((realized / target) * 100, 6);
  });
});

describe("승인 결정을 실행 과제로 변환", () => {
  it("승인 직후 과제는 미반영이고 회수 실적이 0이다", () => {
    for (const scenario of scenarios) {
      const action = actionFor(scenario.id);
      expect(action.reflectedInForecast).toBe(false);
      expect(action.realizedRecovery).toBe(0);
      expect(action.status).toBe("not-started");
    }
  });

  it("목표 회수액이 결정의 손익 효과와 같다", () => {
    for (const scenario of scenarios) {
      const action = actionFor(scenario.id);
      expect(action.targetRecovery).toBe(scenario.demoDecision.profitImpact);
    }
  });

  it("담당과 연결 리스크가 대안·안건에서 따라온다", () => {
    const scenario = profitability;
    const action = actionFor(scenario.id);
    const alternative = scenario.reviewCase.alternatives.find(
      (a) => a.id === scenario.demoDecision.alternativeId,
    )!;
    expect(action.owner).toBe(alternative.owner);
    expect(action.sourceRiskId).toBe(scenario.riskId);
  });
});

describe("실행계획(Plan) 조정", () => {
  it("승인 전에는 조정 후 값을 유효한 계획으로 쓰지 않는다", () => {
    for (const view of planView(rollingPlan, false)) {
      if (view.item.drivenByDecision) {
        expect(view.effective).toBe(view.item.baseline);
        expect(view.awaitingDecision).toBe(true);
        expect(view.adjusted).toBe(false);
      }
    }
  });

  it("승인 후에는 조정 후 값이 유효해진다", () => {
    for (const view of planView(rollingPlan, true)) {
      if (view.item.drivenByDecision) {
        expect(view.effective).toBe(view.item.planned);
        expect(view.adjusted).toBe(true);
        expect(view.awaitingDecision).toBe(false);
      }
    }
  });

  it("승인과 무관한 항목은 승인 여부에 흔들리지 않는다", () => {
    const independent = (hasDecision: boolean) =>
      planView(rollingPlan, hasDecision).filter((v) => !v.item.drivenByDecision);
    expect(independent(false).map((v) => v.effective)).toEqual(
      independent(true).map((v) => v.effective),
    );
  });

  it("활동·물량·일정·자원 네 축을 모두 덮는다", () => {
    const dimensions = new Set(rollingPlan.plan.map((p) => p.dimension));
    expect(dimensions).toEqual(new Set(["activity", "volume", "schedule", "resource"]));
  });
});
