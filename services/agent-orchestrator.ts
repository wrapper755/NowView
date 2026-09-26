/**
 * Multi-Agent 분석 및 시뮬레이션 호출기.
 *
 * 지금은 기록된 실행 결과(`process.runs`)를 진행 지점에 맞춰 해석하는 읽기 전용 계층이다.
 * 실제 LangGraph 연동 시 `AgentActivity`를 그대로 유지하고 내부만 실 호출로 바꾸면 되도록,
 * 화면이 소비하는 형태를 여기서 고정한다.
 */

import { deriveNodeStatus } from "@/services/bpm-engine";
import type {
  AgentRun,
  AgentSpec,
  BpmNodeStatus,
  BpmProcessInstance,
} from "@/lib/types/bpm";
import type { Severity } from "@/lib/types/cockpit";
import type { Alternative } from "@/lib/types/workspace";

/** Agent 실행 상태. 노드 상태에서 파생하므로 따로 저장하지 않는다. */
export type AgentActivityStatus = "done" | "running" | "queued" | "skipped";

export interface AgentActivity {
  agent: AgentSpec;
  /** 수행 노드 id와 라벨. */
  nodeId: string;
  nodeLabel: string;
  status: AgentActivityStatus;
  /** 아직 실행되지 않았으면 산출물이 없다 — 미리 보여주면 안 된다. */
  run?: AgentRun;
}

function toActivityStatus(nodeStatus: BpmNodeStatus): AgentActivityStatus {
  switch (nodeStatus) {
    case "done":
      return "done";
    case "active":
    case "waiting":
      return "running";
    case "skipped":
      return "skipped";
    default:
      return "queued";
  }
}

/**
 * 현재 진행 지점에서의 Agent 활동 목록.
 *
 * 아직 수행되지 않은 Agent의 산출물은 `run`을 비워 반환한다. 미래 결과를 미리 노출하면
 * "Agent가 이미 분석을 마쳤다"는 잘못된 인상을 주므로 의도적으로 감춘다.
 */
export function agentActivities(
  process: BpmProcessInstance,
  stepIndex: number,
): AgentActivity[] {
  return process.nodes
    .filter((node) => node.agentId)
    .map((node) => {
      const agent = process.agents.find((a) => a.id === node.agentId);
      if (!agent) {
        throw new Error(`노드 ${node.id}가 존재하지 않는 Agent ${node.agentId}를 참조한다`);
      }

      const status = toActivityStatus(deriveNodeStatus(process, node, stepIndex));
      const run = process.runs.find((r) => r.nodeId === node.id);

      return {
        agent,
        nodeId: node.id,
        nodeLabel: node.label,
        status,
        run: status === "done" ? run : undefined,
      };
    });
}

/** 지금 실행 중인 Agent 수. 헤더 요약에 쓴다. */
export function runningAgentCount(
  process: BpmProcessInstance,
  stepIndex: number,
): number {
  return agentActivities(process, stepIndex).filter((a) => a.status === "running")
    .length;
}

/** 산출물이 확정된 Agent 실행 기록만. 사람이 검증할 수 있는 근거가 있는 것들이다. */
export function completedRuns(
  process: BpmProcessInstance,
  stepIndex: number,
): AgentActivity[] {
  return agentActivities(process, stepIndex).filter((a) => a.status === "done" && a.run);
}

// ── 대안 시뮬레이션 ────────────────────────────────────────────────────────────

export interface SimulationResult {
  /** 연간 영업이익 개선액(억원). */
  profitImpact: number;
  /** 가동률 개선(%p). */
  utilizationImpact: number;
  /** 일회성 실행 비용(억원). */
  cost: number;
  /**
   * 회수 기간(년) = 비용 ÷ 연간 개선액.
   *
   * 비용과 효과는 **시간 단위가 다르다** — 비용은 일회성이고 효과는 연간이다.
   * 둘을 단순히 빼면(효과 − 비용) 첫해 기준으로는 손해처럼 보이는 잘못된 그림이 되므로,
   * 차감 대신 회수 기간으로 보여 준다.
   *
   * 개선액이 0 이하면 회수되지 않으므로 `null`이다.
   */
  paybackYears: number | null;
  /** 해당 레버 값에서의 리스크 등급. */
  severity: Severity;
}

/**
 * 레버 값에서의 리스크 등급. 구간을 넘어서면 가장 높은 등급으로 고정한다.
 * 구간은 오름차순 전제이므로 처음 만족하는 구간이 답이다.
 */
function severityAt(alternative: Alternative, leverValue: number): Severity {
  const band = alternative.riskBands.find((b) => leverValue <= b.upTo);
  return band?.severity ?? alternative.riskBands[alternative.riskBands.length - 1].severity;
}

/**
 * 대안 하나를 주어진 레버 값으로 시뮬레이션한다.
 *
 * 응답은 선형이다 — Mock 단계에서 비선형 곡선을 만들면 없는 정밀도를 주장하게 된다.
 * 실제 엔진 연동 시 이 함수만 교체하면 화면은 그대로 둘 수 있다.
 */
export function simulateAlternative(
  alternative: Alternative,
  leverValue: number,
): SimulationResult {
  const { profitPerUnit, utilizationPerUnit, costPerUnit } = alternative.lever;
  const profitImpact = leverValue * profitPerUnit;
  const cost = leverValue * costPerUnit;

  return {
    profitImpact,
    utilizationImpact: leverValue * utilizationPerUnit,
    cost,
    paybackYears: profitImpact > 0 ? cost / profitImpact : null,
    severity: severityAt(alternative, leverValue),
  };
}

/** Agent가 제안한 기본값에서의 결과. 대안 비교표의 기준선이다. */
export function baselineResult(alternative: Alternative): SimulationResult {
  return simulateAlternative(alternative, alternative.lever.base);
}
