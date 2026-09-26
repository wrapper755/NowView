/**
 * 엔진 프로세스 명세 생성 (CLAUDE.md 5.2).
 *
 * 엔진은 토폴로지를 모르는 범용 런타임이고 이 생성기가 유일한 토폴로지 원천이다.
 * **여기가 틀리면 엔진이 Mock과 다른 경로를 간다** — 두 구현이 조용히 갈라지는
 * 전형적인 지점이라 세 시나리오 전부를 잠근다.
 */

import { describe, expect, it } from "vitest";

import { scenarios } from "@/lib/mock-data/scenarios";
import { DECISION_RATIONALE_MIN_LENGTH } from "@/lib/types/workspace";
import { approvalNodeId } from "@/services/bpm-engine";
import { buildEngineSpec } from "@/services/engine-spec";

describe("명세 생성", () => {
  it("모든 시나리오가 명세로 변환된다", () => {
    for (const scenario of scenarios) {
      const spec = buildEngineSpec(scenario);
      expect(spec.scenarioId).toBe(scenario.id);
      expect(spec.nodes.length).toBe(scenario.process.nodes.length);
      expect(spec.edges.length).toBe(scenario.process.edges.length);
      expect(spec.riskId).toBe(scenario.process.riskId);
    }
  });

  it("모든 게이트웨이에 분기 규칙이 실린다", () => {
    for (const scenario of scenarios) {
      const spec = buildEngineSpec(scenario);
      const gatewayNodes = scenario.process.nodes.filter((n) => n.kind === "gateway");
      expect(spec.gateways.length).toBe(gatewayNodes.length);
      for (const gateway of spec.gateways) {
        expect(gateway.flag.length).toBeGreaterThan(0);
        // 분기 대상이 실제 노드여야 한다 — 아니면 엔진 조립이 실패한다.
        const ids = spec.nodes.map((n) => n.id);
        expect(ids).toContain(gateway.whenTrue);
        expect(ids).toContain(gateway.whenFalse);
      }
    }
  });

  it("분기 규칙이 없는 게이트웨이는 조용히 넘기지 않고 throw한다", () => {
    const scenario = scenarios[0];
    const broken = {
      ...scenario,
      process: {
        ...scenario.process,
        nodes: scenario.process.nodes.map((node) =>
          node.kind === "gateway" ? { ...node, decision: undefined } : node,
        ),
      },
    };
    expect(() => buildEngineSpec(broken)).toThrow(/분기 규칙/);
  });
});

describe("Mock 플래그가 선언된 경로와 일치한다", () => {
  it("플래그 값이 sequence가 실제로 탄 분기와 같다", () => {
    // 값을 따로 적으면 Mock이 주장하는 경로와 엔진이 가는 경로가 어긋난다.
    for (const scenario of scenarios) {
      const spec = buildEngineSpec(scenario);
      for (const gateway of spec.gateways) {
        const tookTrue = scenario.process.sequence.includes(gateway.whenTrue);
        const flagValues = spec.agentOutputs
          .map((output) => output.flags[gateway.flag])
          .filter((value) => value !== undefined);

        expect(flagValues.length).toBe(1);
        expect(flagValues[0]).toBe(tookTrue);
      }
    }
  });

  it("판정은 게이트웨이 직전 노드가 만든다", () => {
    for (const scenario of scenarios) {
      const spec = buildEngineSpec(scenario);
      for (const gateway of spec.gateways) {
        const producer = scenario.process.edges.find((e) => e.target === gateway.nodeId)?.source;
        const owner = spec.agentOutputs.find((o) => gateway.flag in o.flags);
        expect(owner?.nodeId).toBe(producer);
      }
    }
  });

  it("수익성·배분 안건은 에스컬레이션되고 납기 안건은 현업 통제로 간다", () => {
    // 기획안 3.3의 두 경로. 같은 규칙으로 갈린다는 것이 요점이다.
    const expected: Record<string, boolean> = {
      "scn-profitability": true,
      "scn-allocation": true,
      "scn-delivery": false,
    };
    for (const scenario of scenarios) {
      const spec = buildEngineSpec(scenario);
      const gateway = spec.gateways[0];
      const value = spec.agentOutputs.find((o) => gateway.flag in o.flags)!.flags[gateway.flag];
      expect(value).toBe(expected[scenario.id]);
    }
  });
});

describe("경영 규칙이 명세로 전달된다", () => {
  it("사유 최소 길이가 TS 상수와 같다", () => {
    // 엔진이 숫자를 따로 들고 있으면 UI·API·엔진이 갈라진다.
    for (const scenario of scenarios) {
      expect(buildEngineSpec(scenario).decisionRules.rationaleMinLength).toBe(
        DECISION_RATIONALE_MIN_LENGTH,
      );
    }
  });

  it("승인 노드가 sequence 안의 user-task다", () => {
    for (const scenario of scenarios) {
      const spec = buildEngineSpec(scenario);
      expect(spec.decisionNodeId).toBe(approvalNodeId(scenario.process));
      expect(scenario.process.sequence).toContain(spec.decisionNodeId!);
    }
  });

  it("대안 목록에 권고안이 정확히 하나다", () => {
    for (const scenario of scenarios) {
      const spec = buildEngineSpec(scenario);
      const recommended = spec.alternatives.filter((a) => a.recommended);
      expect(recommended.length).toBe(1);
      expect(recommended[0].id).toBe(scenario.reviewCase.recommendedAlternativeId);
    }
  });
});

describe("Agent 산출물", () => {
  it("근거 데이터의 품질과 유의사항이 보존된다", () => {
    // 품질 정보가 빠지면 LLM 프롬프트에서 "무엇이 불완전한지"가 사라진다(CLAUDE.md 4.12).
    for (const scenario of scenarios) {
      const spec = buildEngineSpec(scenario);
      for (const output of spec.agentOutputs) {
        const original = scenario.process.runs.find((r) => r.nodeId === output.nodeId)!;
        expect(output.sources.length).toBe(original.sources.length);
        for (const [index, source] of output.sources.entries()) {
          expect(source.name).toBe(original.sources[index].name);
          expect(source.quality).toBe(original.sources[index].quality);
          if (source.quality !== "complete") expect(source.caveat).toBeTruthy();
        }
      }
    }
  });

  it("소요시간이 엔진·TS 양쪽이 읽는 형식이다", () => {
    for (const scenario of scenarios) {
      for (const output of buildEngineSpec(scenario).agentOutputs) {
        expect(output.duration).toMatch(/^(\d+시간\s*)?\d+분(\s*\d+초)?$|^\d+분\s*\d+초$/);
      }
    }
  });
});
