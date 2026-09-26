/**
 * 화면 간 수치 연동 항등식 (CLAUDE.md 4.6).
 *
 * 지금까지 이 항등식들은 **주석과 런타임 assert로만** 지켜졌다. 주석은 데이터를 고칠 때
 * 읽히지 않고, 런타임 assert는 그 화면을 열어야 터진다. 세 시나리오가 같은 전사 Gap을
 * 나눠 메우게 되면서 연결이 늘었으므로 여기서 한 번에 잠근다.
 *
 * 값 하나를 고칠 때 함께 고쳐야 할 곳을 이 파일이 알려주는 것이 목적이다.
 */

import { describe, expect, it } from "vitest";

import { nextAutomotive } from "@/lib/mock-data/next-automotive";
import { rollingPlan } from "@/lib/mock-data/rolling-plan";
import { scenarios } from "@/lib/mock-data/scenarios";
import { assertBridgeBalances, gapOf } from "@/lib/types/cockpit";
import { assertQuartersBalance } from "@/services/rolling-plan";
import { baselineResult } from "@/services/agent-orchestrator";

describe("전사 손익 합산", () => {
  it("사업부 매출 합이 전사 매출과 같다", () => {
    const target = nextAutomotive.divisions.reduce((s, d) => s + d.revenue.target, 0);
    const forecast = nextAutomotive.divisions.reduce((s, d) => s + d.revenue.forecast, 0);
    expect(target).toBe(nextAutomotive.revenue.target);
    expect(forecast).toBe(nextAutomotive.revenue.forecast);
  });

  it("사업부 영업이익 합이 전사 영업이익과 같다", () => {
    const target = nextAutomotive.divisions.reduce(
      (s, d) => s + d.operatingProfit.target,
      0,
    );
    const forecast = nextAutomotive.divisions.reduce(
      (s, d) => s + d.operatingProfit.forecast,
      0,
    );
    expect(target).toBe(nextAutomotive.operatingProfit.target);
    expect(forecast).toBe(nextAutomotive.operatingProfit.forecast);
  });

  it("사업부 매출 비중 합이 100%다", () => {
    const share = nextAutomotive.divisions.reduce((s, d) => s + d.revenueShare, 0);
    expect(share).toBe(100);
  });
});

describe("영업이익 브릿지", () => {
  it("증감 요인 합이 Target과 Forecast의 차이와 일치한다", () => {
    expect(() => assertBridgeBalances(nextAutomotive.bridge)).not.toThrow();
  });

  it("브릿지 양 끝이 전사 Target·Forecast와 같다", () => {
    const anchors = nextAutomotive.bridge.filter((s) => s.kind === "anchor");
    expect(anchors[0].value).toBe(nextAutomotive.operatingProfit.target);
    expect(anchors[1].value).toBe(nextAutomotive.operatingProfit.forecast);
  });

  it("확정 Action 회수 효과가 committedActionRecovery와 같다", () => {
    const action = nextAutomotive.bridge.find((s) => s.driver === "action");
    expect(action?.value).toBe(nextAutomotive.committedActionRecovery);
  });
});

describe("Rolling Plan", () => {
  it("분기 합이 전사 Target·Forecast와 같다", () => {
    expect(() => assertQuartersBalance(rollingPlan)).not.toThrow();
  });

  it("전사 Target·Forecast가 Cockpit과 같다", () => {
    expect(rollingPlan.target).toBe(nextAutomotive.operatingProfit.target);
    expect(rollingPlan.forecast).toBe(nextAutomotive.operatingProfit.forecast);
  });

  it("마지막 Rolling 회차의 Forecast가 현재 Forecast와 같다", () => {
    const latest = rollingPlan.revisions[rollingPlan.revisions.length - 1];
    expect(latest.forecast).toBe(rollingPlan.forecast);
  });

  it("Rolling 회차 Forecast가 시간순으로 기록돼 있다", () => {
    const dates = rollingPlan.revisions.map((r) => r.date);
    expect([...dates].sort()).toEqual(dates);
  });

  it("Forecast 반영 완료 과제의 목표 회수액 합이 committedActionRecovery와 같다", () => {
    const reflected = rollingPlan.actions
      .filter((a) => a.reflectedInForecast)
      .reduce((s, a) => s + a.targetRecovery, 0);
    expect(reflected).toBe(nextAutomotive.committedActionRecovery);
  });

  it("실제 회수액이 목표 회수액을 넘지 않는다", () => {
    for (const action of rollingPlan.actions) {
      expect(action.realizedRecovery).toBeLessThanOrEqual(action.targetRecovery);
    }
  });
});

describe("시나리오 간 연동", () => {
  it("모든 시나리오가 같은 전사 영업이익 Gap을 본다", () => {
    const gap = gapOf(nextAutomotive.operatingProfit);
    for (const scenario of scenarios) {
      expect(scenario.reviewCase.profitGap).toBe(gap);
    }
  });

  it("시나리오의 riskId가 실제 리스크 신호를 가리킨다", () => {
    const ids = new Set(nextAutomotive.risks.map((r) => r.id));
    for (const scenario of scenarios) {
      expect(ids.has(scenario.riskId)).toBe(true);
      expect(scenario.process.riskId).toBe(scenario.riskId);
      expect(scenario.reviewCase.riskId).toBe(scenario.riskId);
    }
  });

  it("Review 안건이 자기 프로세스를 가리킨다", () => {
    for (const scenario of scenarios) {
      expect(scenario.reviewCase.processId).toBe(scenario.process.id);
    }
  });

  it("프로세스 KRI가 연결된 리스크 신호의 KRI와 같다", () => {
    for (const scenario of scenarios) {
      const risk = nextAutomotive.risks.find((r) => r.id === scenario.riskId);
      expect(risk?.kri.label).toBe(scenario.process.kri.label);
      expect(risk?.kri.value).toBe(scenario.process.kri.value);
      expect(risk?.kri.threshold).toBe(scenario.process.kri.threshold);
    }
  });
});

describe("시나리오 1의 대안 효과가 Agent 산출물 문구와 일치한다", () => {
  /**
   * Simulation Agent의 산출물은 사람이 읽는 문장이라 값이 문자열 안에 박혀 있다.
   * 대안 계수를 고치면서 문구를 안 고치면 화면 두 곳이 다른 금액을 말하게 된다.
   */
  const profitability = scenarios[0];
  const simulationRun = profitability.process.runs.find(
    (r) => r.agentId === "agent-simulation",
  );

  it("Simulation Agent 산출물이 존재한다", () => {
    expect(simulationRun).toBeDefined();
  });

  it("각 대안의 기본값 효과가 산출물 문구에 그대로 적혀 있다", () => {
    const output = simulationRun!.output;
    for (const alternative of profitability.reviewCase.alternatives) {
      const { profitImpact } = baselineResult(alternative);
      expect(output).toContain(`+${profitImpact}억`);
    }
  });
});
