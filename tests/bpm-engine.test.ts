/**
 * BPM 상태 파생 규칙 (CLAUDE.md 4.5).
 *
 * 노드 상태는 저장하지 않고 `sequence`와 진행 지점에서 파생한다. 이 규칙이 깨지면
 * "순서와 상태가 따로 노는" 상황이 생기는데, 화면을 열어 보기 전에는 드러나지 않는다.
 *
 * **미완료 Agent 산출물 은닉은 실제로 두 번 새어 나갔다** — `AgentRun.output` 경로와
 * `BpmNodeSpec.outcome` 경로. 그래서 여기서 명시적으로 잠근다.
 */

import { describe, expect, it } from "vitest";

import { scenarios } from "@/lib/mock-data/scenarios";
import { agentActivities, runningAgentCount } from "@/services/agent-orchestrator";
import {
  approvalNodeId,
  approvalStepIndex,
  currentNode,
  deriveNodeStatus,
  deriveNodeStatuses,
  isAwaitingHuman,
  maxStepIndex,
  progressPercent,
} from "@/services/bpm-engine";

const profitability = scenarios.find((s) => s.id === "scn-profitability")!;
const delivery = scenarios.find((s) => s.id === "scn-delivery")!;

describe("노드 상태 파생", () => {
  it("sequence에 없는 노드는 어느 지점에서도 skipped다", () => {
    for (const scenario of scenarios) {
      const outside = scenario.process.nodes.filter(
        (n) => !scenario.process.sequence.includes(n.id),
      );
      for (let step = 0; step <= maxStepIndex(scenario.process); step++) {
        const statuses = deriveNodeStatuses(scenario.process, step);
        for (const node of outside) {
          expect(statuses[node.id]).toBe("skipped");
        }
      }
    }
  });

  it("진행 지점 앞의 노드는 done, 뒤는 pending이다", () => {
    const step = 4;
    const statuses = deriveNodeStatuses(profitability.process, step);
    const seq = profitability.process.sequence;
    for (let i = 0; i < seq.length; i++) {
      if (i < step) expect(statuses[seq[i]]).toBe("done");
      if (i > step) expect(statuses[seq[i]]).toBe("pending");
    }
  });

  it("현재 지점이 user-task면 active가 아니라 waiting이다", () => {
    for (const scenario of scenarios) {
      for (let step = 0; step <= maxStepIndex(scenario.process); step++) {
        const node = currentNode(scenario.process, step);
        if (!node) continue;
        const status = deriveNodeStatuses(scenario.process, step)[node.id];
        expect(status).toBe(node.kind === "user-task" ? "waiting" : "active");
      }
    }
  });

  it("사람 대기 여부가 현재 노드 종류와 일치한다", () => {
    for (const scenario of scenarios) {
      for (let step = 0; step <= maxStepIndex(scenario.process); step++) {
        const node = currentNode(scenario.process, step);
        expect(isAwaitingHuman(scenario.process, step)).toBe(node?.kind === "user-task");
      }
    }
  });

  it("진행률이 0에서 100 사이이고 단조 증가한다", () => {
    let previous = -1;
    for (let step = 0; step <= maxStepIndex(profitability.process); step++) {
      const percent = progressPercent(profitability.process, step);
      expect(percent).toBeGreaterThanOrEqual(0);
      expect(percent).toBeLessThanOrEqual(100);
      expect(percent).toBeGreaterThan(previous);
      previous = percent;
    }
  });
});

describe("미완료 Agent 산출물 은닉", () => {
  it("완료되지 않은 Agent의 run은 넘기지 않는다", () => {
    for (const scenario of scenarios) {
      for (let step = 0; step <= maxStepIndex(scenario.process); step++) {
        for (const activity of agentActivities(scenario.process, step)) {
          if (activity.status !== "done") {
            expect(activity.run).toBeUndefined();
          }
        }
      }
    }
  });

  it("완료된 Agent는 기록이 있으면 run을 넘긴다", () => {
    const lastStep = maxStepIndex(profitability.process);
    const done = agentActivities(profitability.process, lastStep).filter(
      (a) => a.status === "done",
    );
    const withRecord = done.filter((a) =>
      profitability.process.runs.some((r) => r.nodeId === a.nodeId),
    );
    expect(withRecord.length).toBeGreaterThan(0);
    for (const activity of withRecord) {
      expect(activity.run).toBeDefined();
    }
  });

  it("사람이 판단을 기다리는 지점에서는 실행 중 Agent가 없다", () => {
    // user-task는 Agent가 할 일이 끝난 뒤에 오므로 running Agent가 남아 있으면 안 된다.
    for (const scenario of scenarios) {
      for (let step = 0; step <= maxStepIndex(scenario.process); step++) {
        if (!isAwaitingHuman(scenario.process, step)) continue;
        expect(runningAgentCount(scenario.process, step)).toBe(0);
      }
    }
  });
});

describe("시나리오 3.3의 두 경로", () => {
  it("수익성 안건은 에스컬레이션되어 현업 통제를 건너뛴다", () => {
    expect(profitability.process.sequence).not.toContain("op-control");
    expect(profitability.process.sequence).toContain("review");
  });

  it("납기 안건은 현업 통제로 처리되어 경영 검토를 건너뛴다", () => {
    expect(delivery.process.sequence).toContain("op-control");
    expect(delivery.process.sequence).not.toContain("review");
  });
});

describe("승인 지점", () => {
  it("선택되지 않은 분기의 user-task를 집지 않는다", () => {
    // `nodes` 배열 순서로 찾으면 시나리오 1·3에서 `op-control`이 잡힌다.
    // 그 노드는 `sequence`에 없어 indexOf가 -1이 되고, 승인 후 진행 지점이
    // Management Action이 아니라 0(맨 처음)으로 돌아갔다 — 실제로 그랬다.
    for (const scenario of scenarios) {
      const nodeId = approvalNodeId(scenario.process);
      expect(nodeId).toBeDefined();
      expect(scenario.process.sequence).toContain(nodeId!);
    }
  });

  it("승인 후 지점이 승인 노드의 바로 다음이다", () => {
    for (const scenario of scenarios) {
      const { process } = scenario;
      const at = process.sequence.indexOf(approvalNodeId(process)!);
      expect(approvalStepIndex(process)).toBe(at + 1);
      // 0으로 되돌아가지 않는다 — 이것이 깨졌던 증상이다.
      expect(approvalStepIndex(process)).toBeGreaterThan(0);
    }
  });

  it("승인 지점의 노드는 승인 대기 상태로 파생된다", () => {
    for (const scenario of scenarios) {
      const { process } = scenario;
      const at = process.sequence.indexOf(approvalNodeId(process)!);
      const node = process.nodes.find((n) => n.id === approvalNodeId(process))!;
      expect(deriveNodeStatus(process, node, at)).toBe("waiting");
    }
  });
});
