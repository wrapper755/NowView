/**
 * 대안 시뮬레이션과 시나리오 레지스트리 무결성.
 *
 * 시뮬레이션은 의도적으로 선형이다(CLAUDE.md 4.7). 그래서 검증할 것은 곡선의 모양이
 * 아니라 **관계**다 — 비용이 레버에 비례하는가, 회수 기간이 비용÷효과인가,
 * 등급 구간이 단조로운가.
 */

import { describe, expect, it } from "vitest";

import { scenarios } from "@/lib/mock-data/scenarios";
import { baselineResult, simulateAlternative } from "@/services/agent-orchestrator";
import { maxStepIndex } from "@/services/bpm-engine";

const allAlternatives = scenarios.flatMap((s) => s.reviewCase.alternatives);

describe("시뮬레이션 계산", () => {
  it("효과와 비용이 레버에 비례한다", () => {
    for (const alternative of allAlternatives) {
      const { lever } = alternative;
      const single = simulateAlternative(alternative, 1);
      const triple = simulateAlternative(alternative, 3);
      expect(triple.profitImpact).toBeCloseTo(single.profitImpact * 3, 6);
      expect(triple.cost).toBeCloseTo(single.cost * 3, 6);
      expect(triple.secondaryImpact).toBeCloseTo(single.secondaryImpact * 3, 6);
      expect(single.profitImpact).toBeCloseTo(lever.profitPerUnit, 6);
    }
  });

  it("레버가 0이면 효과도 비용도 0이고 회수되지 않는다", () => {
    for (const alternative of allAlternatives) {
      const zero = simulateAlternative(alternative, 0);
      expect(zero.profitImpact).toBe(0);
      expect(zero.cost).toBe(0);
      expect(zero.paybackYears).toBeNull();
    }
  });

  it("회수 기간이 비용 ÷ 연간 효과다", () => {
    for (const alternative of allAlternatives) {
      const result = baselineResult(alternative);
      if (result.profitImpact <= 0) {
        expect(result.paybackYears).toBeNull();
        continue;
      }
      expect(result.paybackYears).toBeCloseTo(result.cost / result.profitImpact, 6);
    }
  });

  it("리스크 등급 구간이 오름차순이고 최대값을 덮는다", () => {
    for (const alternative of allAlternatives) {
      const bands = alternative.riskBands;
      const upTos = bands.map((b) => b.upTo);
      expect([...upTos].sort((a, b) => a - b)).toEqual(upTos);
      expect(upTos[upTos.length - 1]).toBeGreaterThanOrEqual(alternative.lever.max);
    }
  });

  it("레버를 올릴수록 리스크 등급이 나빠지기만 한다", () => {
    const rank = { good: 0, warning: 1, serious: 2, critical: 3 } as const;
    for (const alternative of allAlternatives) {
      const { lever } = alternative;
      let previous = -1;
      for (let v = lever.min; v <= lever.max; v += lever.step) {
        const current = rank[simulateAlternative(alternative, v).severity];
        expect(current).toBeGreaterThanOrEqual(previous);
        previous = current;
      }
    }
  });
});

describe("대안 정의", () => {
  it("Agent 제안값이 레버 범위 안에 있다", () => {
    for (const alternative of allAlternatives) {
      const { lever } = alternative;
      expect(lever.base).toBeGreaterThanOrEqual(lever.min);
      expect(lever.base).toBeLessThanOrEqual(lever.max);
    }
  });

  it("모든 대안에 실행 조건과 비용 설명이 있다", () => {
    // 기획안 2.1: 효과뿐 아니라 비용·위험·실행 조건을 함께 제시한다.
    for (const alternative of allAlternatives) {
      expect(alternative.prerequisites.length).toBeGreaterThan(0);
      expect(alternative.costNote.length).toBeGreaterThan(0);
      expect(alternative.riskNote.length).toBeGreaterThan(0);
    }
  });

  it("배분 안건은 비용이 0인 대안이 없다", () => {
    // 배분은 반드시 한쪽에서 빼 온다 — 공짜 선택지가 있으면 트레이드오프가 아니다.
    const allocation = scenarios.find((s) => s.id === "scn-allocation")!;
    for (const alternative of allocation.reviewCase.alternatives) {
      expect(baselineResult(alternative).cost).toBeGreaterThan(0);
    }
  });
});

describe("시나리오 레지스트리", () => {
  it("id와 짧은 이름이 중복되지 않는다", () => {
    const ids = scenarios.map((s) => s.id);
    const names = scenarios.map((s) => s.shortTitle);
    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(names).size).toBe(names.length);
  });

  it("모든 장면의 진행 지점이 프로세스 범위 안이다", () => {
    for (const scenario of scenarios) {
      const max = maxStepIndex(scenario.process);
      for (const scene of scenario.scenes) {
        expect(scene.step).toBeGreaterThanOrEqual(0);
        expect(scene.step).toBeLessThanOrEqual(max);
      }
    }
  });

  it("모든 장면이 실제 화면 경로를 가리킨다", () => {
    const routes = new Set(["/", "/bpm-tracker", "/workspace", "/rolling-plan", "/evolution"]);
    for (const scenario of scenarios) {
      for (const scene of scenario.scenes) {
        expect(routes.has(scene.route)).toBe(true);
      }
    }
  });

  it("장면의 진행 지점이 뒤로 가지 않는다", () => {
    for (const scenario of scenarios) {
      const steps = scenario.scenes.map((s) => s.step);
      expect([...steps].sort((a, b) => a - b)).toEqual(steps);
    }
  });

  it("승인 장면은 그 뒤로 계속 승인 상태다", () => {
    // decided가 한 번 true가 된 뒤 false로 돌아가면 스크러버로 되짚을 때 앞뒤가 안 맞는다.
    for (const scenario of scenarios) {
      const firstDecided = scenario.scenes.findIndex((s) => s.decided);
      if (firstDecided === -1) continue;
      for (const scene of scenario.scenes.slice(firstDecided)) {
        expect(scene.decided).toBe(true);
      }
    }
  });

  it("데모 결정이 Agent 권고안이고 금액이 계산값과 같다", () => {
    for (const scenario of scenarios) {
      const { demoDecision, reviewCase } = scenario;
      expect(demoDecision.alternativeId).toBe(reviewCase.recommendedAlternativeId);
      const alternative = reviewCase.alternatives.find(
        (a) => a.id === demoDecision.alternativeId,
      )!;
      expect(demoDecision.leverValue).toBe(alternative.lever.base);
      expect(demoDecision.profitImpact).toBe(baselineResult(alternative).profitImpact);
    }
  });

  it("데모 결정 사유가 승인 최소 길이를 넘는다", () => {
    for (const scenario of scenarios) {
      expect(scenario.demoDecision.rationale.trim().length).toBeGreaterThanOrEqual(10);
    }
  });
});
