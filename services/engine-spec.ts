/**
 * 시나리오 → 엔진 프로세스 명세.
 *
 * 엔진(Python/LangGraph)은 토폴로지를 모르는 범용 런타임이고, **여기가 유일한
 * 토폴로지 원천**이다. 시나리오를 추가할 때 엔진을 고치지 않아도 되는 이유다
 * (CLAUDE.md 4.13 "레지스트리에 한 항목 더하면 끝").
 *
 * 경영 규칙도 여기서 실어 보낸다 — 사유 최소 길이(`DECISION_RATIONALE_MIN_LENGTH`),
 * 승인 노드, 선택지. 엔진이 같은 값을 따로 들고 있으면 UI·API·엔진 세 곳이 갈라진다.
 */

import type { BpmProcessInstance } from "@/lib/types/bpm";
import type { Scenario } from "@/lib/types/scenario";
import { DECISION_RATIONALE_MIN_LENGTH } from "@/lib/types/workspace";
import { approvalNodeId } from "@/services/bpm-engine";

export interface EngineGatewaySpec {
  nodeId: string;
  flag: string;
  whenTrue: string;
  whenFalse: string;
}

export interface EngineAgentOutput {
  agentId: string;
  nodeId: string;
  output: string;
  sources: { name: string; quality: string; caveat?: string }[];
  duration: string;
  confidence: "high" | "medium" | "low";
  confidenceNote?: string;
  escalations: { question: string; reason: string; owner: string; ifUnanswered: string }[];
  flags: Record<string, boolean>;
}

export interface EngineProcessSpec {
  scenarioId: string;
  subject: string;
  riskId: string;
  kri: { label: string; value: string; threshold: string };
  nodes: {
    id: string;
    kind: string;
    label: string;
    actor?: string;
    stage?: string;
    outcome?: string;
    duration?: string;
    agentId?: string;
  }[];
  edges: { id: string; source: string; target: string; label?: string }[];
  agents: { id: string; name: string; role: string; capability: string }[];
  gateways: EngineGatewaySpec[];
  decisionRules: { rationaleMinLength: number };
  agentOutputs: EngineAgentOutput[];
  decisionNodeId?: string;
  alternatives: { id: string; title: string; recommended: boolean }[];
}

/**
 * Mock 모드에서 게이트웨이가 어느 쪽으로 가야 하는가.
 *
 * **`sequence`가 이미 답을 들고 있다** — 어느 분기를 탔는지가 거기 적혀 있다.
 * 값을 따로 적으면 Mock이 주장하는 경로와 엔진이 가는 경로가 어긋날 수 있다.
 */
function flagValueFromSequence(process: BpmProcessInstance, gateway: EngineGatewaySpec): boolean {
  return process.sequence.includes(gateway.whenTrue);
}

function gatewaysOf(process: BpmProcessInstance): EngineGatewaySpec[] {
  return process.nodes
    .filter((node) => node.kind === "gateway")
    .map((node) => {
      if (!node.decision) {
        // 조용히 넘기면 엔진이 분기를 못 해 기본 경로로만 가고, 그 사실이 드러나지 않는다.
        // `buildChains`가 끊어진 참조에 throw하는 것과 같은 이유다(CLAUDE.md 4.8).
        throw new Error(
          `게이트웨이 ${node.id}에 분기 규칙(decision)이 없다 — 엔진이 경로를 고를 수 없다.`,
        );
      }
      return { nodeId: node.id, ...node.decision };
    });
}

/**
 * 게이트웨이 플래그를 만들어 줄 노드 — 그 게이트웨이로 들어오는 엣지의 출발 노드.
 *
 * 없으면 판정이 어디서도 생기지 않아 분기가 항상 기본 경로로 간다.
 */
function flagProducerOf(process: BpmProcessInstance, gatewayId: string): string | undefined {
  return process.edges.find((edge) => edge.target === gatewayId)?.source;
}

export function buildEngineSpec(scenario: Scenario): EngineProcessSpec {
  const { process, reviewCase } = scenario;
  const gateways = gatewaysOf(process);

  // 노드별로 그 노드가 판정해야 하는 플래그와 값을 모은다.
  const flagsByNode = new Map<string, Record<string, boolean>>();
  for (const gateway of gateways) {
    const producer = flagProducerOf(process, gateway.nodeId);
    if (!producer) continue;
    const existing = flagsByNode.get(producer) ?? {};
    existing[gateway.flag] = flagValueFromSequence(process, gateway);
    flagsByNode.set(producer, existing);
  }

  return {
    scenarioId: scenario.id,
    subject: process.subject,
    riskId: process.riskId,
    kri: process.kri,
    nodes: process.nodes.map((node) => ({
      id: node.id,
      kind: node.kind,
      label: node.label,
      actor: node.actor,
      stage: node.stage,
      outcome: node.outcome,
      duration: node.duration,
      agentId: node.agentId,
    })),
    edges: process.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label,
    })),
    agents: process.agents,
    gateways,
    decisionRules: { rationaleMinLength: DECISION_RATIONALE_MIN_LENGTH },
    agentOutputs: process.runs.map((run) => ({
      agentId: run.agentId,
      nodeId: run.nodeId,
      output: run.output,
      sources: run.sources.map((source) => ({
        name: source.name,
        quality: source.quality,
        caveat: source.caveat,
      })),
      duration: run.duration,
      confidence: run.confidence,
      confidenceNote: run.confidenceNote,
      escalations: (run.escalations ?? []).map((escalation) => ({
        question: escalation.question,
        reason: escalation.reason,
        owner: escalation.owner,
        ifUnanswered: escalation.ifUnanswered,
      })),
      flags: flagsByNode.get(run.nodeId) ?? {},
    })),
    decisionNodeId: approvalNodeId(process),
    alternatives: reviewCase.alternatives.map((alternative) => ({
      id: alternative.id,
      // 승인 화면과 같은 표기로 보낸다 — 엔진 응답을 그대로 띄워도 "1안 전장 물량 이관"으로 읽힌다.
      title: `${alternative.tag} ${alternative.name}`,
      recommended: alternative.id === reviewCase.recommendedAlternativeId,
    })),
  };
}
