/**
 * 엔진 스냅샷 → 화면 뷰모델 (CLAUDE.md 4.17).
 *
 * 이 변환이 틀리면 **엔진 모드에서만 나는 버그**가 된다 — Mock 경로는 멀쩡하므로
 * 기존 테스트가 전부 통과하고, 브라우저에서 눈으로 잡기도 어렵다.
 *
 * 특히 "미완료 Agent 산출물은 감춘다"는 규칙이 여기서 한 번 더 걸린다. Mock 경로에서
 * 두 번 새어 나갔던 종류라 경로가 늘어나면 다시 샌다고 봐야 한다.
 */

import { describe, expect, it } from "vitest";

import { scenarios } from "@/lib/mock-data/scenarios";
import type { EngineSnapshot } from "@/services/engine-client";
import {
  engineDecisionToReview,
  engineDecisionsFrom,
  engineEvolutionOutputs,
  engineProcessView,
  engineRunsFrom,
  engineStagesByRisk,
} from "@/services/engine-view";
import { simulateAlternative } from "@/services/agent-orchestrator";

const scenario = scenarios.find((s) => s.id === "scn-profitability")!;
const process = scenario.process;

function snapshotWith(overrides: Partial<EngineSnapshot> = {}): EngineSnapshot {
  return {
    instanceId: "inst-test",
    scenarioId: scenario.id,
    subject: process.subject,
    riskId: process.riskId,
    agentMode: "mock",
    status: "waiting",
    visited: ["start", "sensing", "rca", "gw-escalate", "simulate"],
    next: ["review"],
    nodeStatuses: {
      start: "done",
      sensing: "done",
      rca: "done",
      "gw-escalate": "done",
      "op-control": "skipped",
      simulate: "done",
      review: "waiting",
      action: "pending",
      rolling: "pending",
      evolution: "pending",
      end: "pending",
    },
    runs: [],
    flags: { crossFunctionalCoordination: true },
    decision: null,
    acknowledged: [],
    pendingApproval: {
      kind: "decision",
      nodeId: "review",
      label: "Management Review",
      rationaleMinLength: 10,
    },
    specWarnings: [],
    historical: false,
    ...overrides,
  };
}

function runFor(nodeId: string, provenance = "mock") {
  const source = process.runs.find((r) => r.nodeId === nodeId)!;
  return {
    agentId: source.agentId,
    nodeId: source.nodeId,
    output: source.output,
    sources: source.sources.map((s) => ({ ...s })),
    duration: source.duration,
    confidence: source.confidence,
    confidenceNote: source.confidenceNote ?? null,
    escalations: (source.escalations ?? []).map(({ question, reason, owner, ifUnanswered }) => ({
      question,
      reason,
      owner,
      ifUnanswered,
    })),
    provenance,
  };
}

/**
 * 임의 노드의 실행 기록을 만든다.
 *
 * Mock에는 `evolution` 노드의 산출물이 **없다**(시나리오 1의 runs는 sensing·rca·simulate
 * 셋뿐이다). 엔진 Mock 모드에서는 그 노드가 `provenance: "mock-missing"`으로 나오고,
 * LLM 모드에서는 실제 산출물이 생긴다. 후자를 시험하려면 합성 기록이 필요하다.
 */
function syntheticRun(nodeId: string, agentId: string, provenance: string) {
  return {
    agentId,
    nodeId,
    output: "가동률 KRI 임계치 85% → 87% 상향을 제안한다.",
    sources: [{ name: "임계치 백테스트", quality: "complete" as const }],
    duration: "3분 20초",
    confidence: "high" as const,
    confidenceNote: null,
    escalations: [],
    provenance,
  };
}

describe("노드 상태", () => {
  it("엔진이 준 상태를 그대로 쓴다", () => {
    const view = engineProcessView(process, snapshotWith());
    expect(view.statuses["simulate"]).toBe("done");
    expect(view.statuses["review"]).toBe("waiting");
    expect(view.statuses["op-control"]).toBe("skipped");
  });

  it("모르는 상태 값은 pending으로 떨어뜨린다", () => {
    // 엔진과 화면이 같은 어휘를 쓰기로 했지만 한쪽만 값을 늘리면 조용히 어긋난다.
    // 캔버스가 undefined를 받으면 노드가 색 없이 그려져 원인을 찾기 어렵다.
    const view = engineProcessView(
      process,
      snapshotWith({ nodeStatuses: { ...snapshotWith().nodeStatuses, action: "paused" } }),
    );
    expect(view.statuses["action"]).toBe("pending");
  });

  it("모든 노드에 상태가 있다", () => {
    const view = engineProcessView(process, snapshotWith({ nodeStatuses: {} }));
    for (const node of process.nodes) {
      expect(view.statuses[node.id]).toBeDefined();
    }
  });
});

describe("미완료 Agent 산출물 은닉", () => {
  it("완료되지 않은 노드의 산출물은 통과시키지 않는다", () => {
    // 엔진이 실수로 실려 보내도 화면까지 가면 안 된다 — 두 경로로 새어 나간 전례가 있다.
    const view = engineProcessView(
      process,
      snapshotWith({
        nodeStatuses: { ...snapshotWith().nodeStatuses, simulate: "active" },
        runs: [runFor("sensing"), runFor("rca"), runFor("simulate")],
      }),
    );
    expect(view.runByNode["simulate"]).toBeUndefined();
    expect(view.runByNode["rca"]).toBeDefined();

    const simulateActivity = view.activities.find((a) => a.nodeId === "simulate")!;
    expect(simulateActivity.status).toBe("running");
    expect(simulateActivity.run).toBeUndefined();
  });

  it("완료된 노드의 산출물은 근거 데이터와 함께 통과한다", () => {
    const view = engineProcessView(process, snapshotWith({ runs: [runFor("rca")] }));
    const run = view.runByNode["rca"];
    expect(run.output.length).toBeGreaterThan(0);
    expect(run.sources.length).toBeGreaterThan(0);
    // 품질 정보가 사라지면 "무엇이 불완전한지"를 알 수 없다(CLAUDE.md 4.12).
    for (const source of run.sources) {
      expect(source.quality).toBeDefined();
      if (source.quality !== "complete") expect(source.caveat).toBeTruthy();
    }
  });

  it("에스컬레이션에 목록 key로 쓸 id를 붙인다", () => {
    const view = engineProcessView(process, snapshotWith({ runs: [runFor("rca")] }));
    const escalations = view.runByNode["rca"].escalations ?? [];
    expect(escalations.length).toBeGreaterThan(0);
    expect(new Set(escalations.map((e) => e.id)).size).toBe(escalations.length);
    for (const escalation of escalations) {
      // 답을 못 받고 진행할 때 어떤 가정 위에 서는지가 보존되어야 한다.
      expect(escalation.ifUnanswered.length).toBeGreaterThan(0);
    }
  });

  it("산출물의 출처를 보존한다", () => {
    const view = engineProcessView(
      process,
      snapshotWith({ runs: [runFor("rca", "llm:kimi-k3:cloud")] }),
    );
    expect(view.provenanceByNode["rca"]).toBe("llm:kimi-k3:cloud");
  });
});

describe("현재 단계", () => {
  it("사람 대기 지점을 현재 노드로 삼는다", () => {
    const view = engineProcessView(process, snapshotWith());
    expect(view.activeNode?.id).toBe("review");
    expect(view.awaitingHuman).toBe(true);
  });

  it("대기 중이 아니면 active 노드를 쓴다", () => {
    const view = engineProcessView(
      process,
      snapshotWith({
        status: "running",
        pendingApproval: null,
        next: ["simulate"],
        nodeStatuses: { ...snapshotWith().nodeStatuses, simulate: "active", review: "pending" },
      }),
    );
    expect(view.activeNode?.id).toBe("simulate");
    expect(view.awaitingHuman).toBe(false);
    expect(view.runningCount).toBe(1);
  });

  it("종료된 인스턴스는 현재 노드가 없고 실행 중인 Agent도 없다", () => {
    const done = Object.fromEntries(process.nodes.map((n) => [n.id, "done"]));
    const view = engineProcessView(
      process,
      snapshotWith({ status: "done", pendingApproval: null, next: [], nodeStatuses: done }),
    );
    expect(view.activeNode).toBeNull();
    expect(view.runningCount).toBe(0);
  });
});

describe("Agent 활동", () => {
  it("Agent 노드마다 활동이 하나씩 나온다", () => {
    const view = engineProcessView(process, snapshotWith());
    const agentNodes = process.nodes.filter((n) => n.agentId);
    expect(view.activities.length).toBe(agentNodes.length);
  });

  it("존재하지 않는 Agent를 참조하면 조용히 넘기지 않고 throw한다", () => {
    const broken = {
      ...process,
      nodes: process.nodes.map((n) => (n.id === "rca" ? { ...n, agentId: "agent-없음" } : n)),
    };
    expect(() => engineProcessView(broken, snapshotWith())).toThrow(/존재하지 않는 Agent/);
  });

  it("모든 시나리오가 변환된다", () => {
    for (const item of scenarios) {
      const statuses = Object.fromEntries(item.process.nodes.map((n) => [n.id, "pending"]));
      const view = engineProcessView(
        item.process,
        snapshotWith({
          scenarioId: item.id,
          nodeStatuses: statuses,
          pendingApproval: null,
          runs: [],
        }),
      );
      expect(view.activities.length).toBeGreaterThan(0);
      expect(Object.keys(view.runByNode)).toHaveLength(0);
    }
  });
});

describe("엔진 결정 → 화면 결정", () => {
  const reviewCase = scenario.reviewCase;
  const recommended = reviewCase.alternatives.find(
    (a) => a.id === reviewCase.recommendedAlternativeId,
  )!;

  it("금액은 화면이 계산한다", () => {
    // 엔진은 "무엇을 골랐는가"만 돌려준다. 엔진이 금액도 내면 화면·API와 갈라진다.
    const converted = engineDecisionToReview(reviewCase, {
      nodeId: "review",
      alternativeId: recommended.id,
      leverValue: 3,
      rationale: "충분히 긴 사유를 적었습니다.",
      decidedAt: "2026-09-26 22:53",
    })!;
    expect(converted.profitImpact).toBe(simulateAlternative(recommended, 3).profitImpact);
    expect(converted.leverValue).toBe(3);
  });

  it("결정 시각은 엔진이 찍은 것을 쓴다", () => {
    // 화면이 찍으면 새로고침할 때마다 값이 달라진다.
    const converted = engineDecisionToReview(reviewCase, {
      nodeId: "review",
      alternativeId: recommended.id,
      rationale: "사유",
      decidedAt: "2026-09-26 22:53",
    })!;
    expect(converted.decidedAt).toBe("2026-09-26 22:53");
  });

  it("레버가 없으면 그 대안의 기본값을 쓴다", () => {
    const converted = engineDecisionToReview(reviewCase, {
      nodeId: "review",
      alternativeId: recommended.id,
      rationale: "사유",
    })!;
    expect(converted.leverValue).toBe(recommended.lever.base);
  });

  it("다른 시나리오의 대안이면 null이다", () => {
    // 억지로 끼워 넣으면 엉뚱한 금액이 Gap에 더해진다.
    const other = scenarios.find((s) => s.id !== scenario.id)!;
    const converted = engineDecisionToReview(reviewCase, {
      nodeId: "review",
      alternativeId: other.reviewCase.recommendedAlternativeId,
      rationale: "사유",
    });
    expect(converted).toBeNull();
  });

  it("결정이 없으면 null이다", () => {
    expect(engineDecisionToReview(reviewCase, null)).toBeNull();
  });
});

describe("전사 화면 파생 (①⑤)", () => {
  const processOf = (id: string) => scenarios.find((s) => s.id === id)!.process;
  const reviewCaseOf = (id: string) => scenarios.find((s) => s.id === id)!.reviewCase;

  it("Agent 소요시간은 완료된 실행만 센다", () => {
    // 미완료 노드의 기록이 섞이면 "분석이 더 오래 걸렸다"고 과장된다.
    const runs = engineRunsFrom(
      {
        [scenario.id]: snapshotWith({
          nodeStatuses: { ...snapshotWith().nodeStatuses, simulate: "active" },
          runs: [runFor("sensing"), runFor("rca"), runFor("simulate")],
        }),
      },
      processOf,
    );
    expect(runs.map((r) => r.nodeId).sort()).toEqual(["rca", "sensing"]);
  });

  it("여러 인스턴스의 실행 기록을 합친다", () => {
    const other = scenarios.find((s) => s.id === "scn-delivery")!;
    const otherStatuses = Object.fromEntries(other.process.nodes.map((n) => [n.id, "pending"]));
    const runs = engineRunsFrom(
      {
        [scenario.id]: snapshotWith({ runs: [runFor("rca")] }),
        [other.id]: snapshotWith({
          scenarioId: other.id,
          riskId: other.process.riskId,
          nodeStatuses: otherStatuses,
          pendingApproval: null,
          runs: [],
        }),
      },
      processOf,
    );
    expect(runs).toHaveLength(1);
  });

  it("리스크 단계를 현재 대기 노드의 단계로 바꾼다", () => {
    const stages = engineStagesByRisk({ [scenario.id]: snapshotWith() }, processOf);
    // review 노드에서 멈춰 있으므로 management-review다.
    expect(stages[scenario.process.riskId]).toBe("management-review");
  });

  it("종료된 인스턴스는 마지막으로 지난 노드의 단계를 쓴다", () => {
    const done = Object.fromEntries(scenario.process.nodes.map((n) => [n.id, "done"]));
    const stages = engineStagesByRisk(
      {
        [scenario.id]: snapshotWith({
          status: "done",
          pendingApproval: null,
          next: [],
          nodeStatuses: done,
          visited: [...scenario.process.sequence],
        }),
      },
      processOf,
    );
    expect(stages[scenario.process.riskId]).toBe("management-evolution");
  });

  it("스냅샷이 없으면 아무 단계도 덮지 않는다", () => {
    expect(engineStagesByRisk({}, processOf)).toEqual({});
  });

  it("승인 결정을 시나리오별로 뽑는다", () => {
    const recommended = reviewCaseOf(scenario.id).alternatives.find(
      (a) => a.id === reviewCaseOf(scenario.id).recommendedAlternativeId,
    )!;
    const decisions = engineDecisionsFrom(
      {
        [scenario.id]: snapshotWith({
          decision: {
            nodeId: "review",
            alternativeId: recommended.id,
            leverValue: recommended.lever.base,
            rationale: "충분히 긴 사유를 적었습니다.",
            decidedAt: "2026-09-26 22:53",
          },
        }),
      },
      reviewCaseOf,
    );
    expect(decisions[scenario.id].alternativeId).toBe(recommended.id);
  });

  it("Evolution Agent 산출물은 완료 전에는 나오지 않는다", () => {
    // 미완료 Agent의 산출물은 어느 화면에서도 미리 보여주지 않는다(4.5).
    const outputs = engineEvolutionOutputs({ [scenario.id]: snapshotWith() }, processOf);
    expect(outputs).toHaveLength(0);
  });

  it("완료된 Evolution Agent 산출물을 출처와 함께 돌려준다", () => {
    const done = Object.fromEntries(scenario.process.nodes.map((n) => [n.id, "done"]));
    const outputs = engineEvolutionOutputs(
      {
        [scenario.id]: snapshotWith({
          status: "done",
          pendingApproval: null,
          next: [],
          nodeStatuses: done,
          runs: [syntheticRun("evolution", "agent-evolution", "llm:kimi-k3:cloud")],
        }),
      },
      processOf,
    );
    expect(outputs).toHaveLength(1);
    expect(outputs[0].provenance).toBe("llm:kimi-k3:cloud");
    expect(outputs[0].agentName).toBe("Evolution Agent");
    expect(outputs[0].run.output.length).toBeGreaterThan(0);
  });

  it("Mock에 evolution 산출물이 없다는 사실을 잠근다", () => {
    // 여기가 바뀌면(Mock에 산출물을 넣으면) ⑤의 "mock-missing" 표시가 사라진다.
    // 지어내지 않기로 한 판단이므로, 바꿀 때 의식하고 바꿔야 한다.
    for (const item of scenarios) {
      const evolutionNode = item.process.nodes.find((n) => n.stage === "management-evolution" && n.agentId);
      expect(evolutionNode).toBeDefined();
      expect(item.process.runs.find((r) => r.nodeId === evolutionNode!.id)).toBeUndefined();
    }
  });
});
