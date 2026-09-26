/**
 * 엔진 스냅샷 → 화면 뷰모델.
 *
 * **화면이 출처를 알면 안 된다.** 트래커는 Mock에서 파생한 값이든 엔진이 돌려준 값이든
 * 같은 모양을 받아 그리고, 분기는 이 파일 하나에만 있다. 화면마다 `if (engineMode)`가
 * 흩어지면 두 경로가 조금씩 달라지고, 결국 "엔진 모드에서만 나는 버그"가 생긴다.
 *
 * 순수 함수로 둔 이유: 이 변환이 틀리면 노드 상태와 Agent 산출물이 어긋나는데,
 * 브라우저에서 눈으로 잡기 어렵다. 테스트로 잠근다(`tests/engine-view.test.ts`).
 */

import { simulateAlternative, type AgentActivity, type AgentActivityStatus } from "@/services/agent-orchestrator";
import type { EngineSnapshot } from "@/services/engine-client";
import type { AgentEscalation, DataSource } from "@/lib/types/agent";
import type {
  AgentRun,
  BpmNodeSpec,
  BpmNodeStatus,
  BpmProcessInstance,
} from "@/lib/types/bpm";
import type { ReviewCase, ReviewDecision } from "@/lib/types/workspace";

const NODE_STATUSES: BpmNodeStatus[] = ["done", "active", "waiting", "pending", "skipped"];

export interface EngineProcessView {
  statuses: Record<string, BpmNodeStatus>;
  activities: AgentActivity[];
  activeNode: BpmNodeSpec | null;
  awaitingHuman: boolean;
  runningCount: number;
  /** 완료된 노드의 산출물만 들어 있다. */
  runByNode: Record<string, AgentRun>;
  /** 산출물의 출처 — `mock` · `mock-missing` · `llm:<model>`. */
  provenanceByNode: Record<string, string>;
}

function toActivityStatus(status: BpmNodeStatus): AgentActivityStatus {
  switch (status) {
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
 * 엔진이 모르는 노드 상태를 받았을 때 `pending`으로 떨어뜨린다.
 *
 * 엔진과 화면이 같은 어휘를 쓰기로 했지만, 한쪽만 값을 늘리면 조용히 어긋난다.
 * 캔버스가 `undefined`를 받으면 노드가 색 없이 그려져 원인을 찾기 어렵다.
 */
function normalizeStatus(raw: string | undefined): BpmNodeStatus {
  return NODE_STATUSES.includes(raw as BpmNodeStatus) ? (raw as BpmNodeStatus) : "pending";
}

function toAgentRun(run: EngineSnapshot["runs"][number]): AgentRun {
  return {
    agentId: run.agentId,
    nodeId: run.nodeId,
    output: run.output,
    sources: run.sources as DataSource[],
    duration: run.duration,
    confidence: run.confidence,
    confidenceNote: run.confidenceNote ?? undefined,
    // 엔진의 에스컬레이션에는 id가 없다 — 목록 key로 쓰이므로 노드 기준으로 만든다.
    escalations: run.escalations.map((escalation, index) => ({
      id: `${run.nodeId}-esc-${index}`,
      ...escalation,
    })) as AgentEscalation[],
  };
}

/**
 * 엔진 결정 → 화면의 `ReviewDecision`.
 *
 * **금액은 여기서 계산한다.** 엔진은 "무엇을 골랐는가"(대안·레버)만 돌려주고 손익은
 * `simulateAlternative`가 낸다 — 엔진이 금액도 계산하면 화면·API와 값이 갈라진다
 * (CLAUDE.md 4.16 규칙 소유권). 반대로 **결정 시각은 엔진이 찍은 것을 그대로 쓴다**.
 *
 * ③과 ④가 같은 함수를 쓴다. 두 화면이 각자 변환하면 협업 스테이션이 보여주는 금액과
 * Rolling Plan의 과제 목표액이 갈라질 수 있는데, 그건 눈으로 잡히지 않는다.
 *
 * 대안이 그 안건 목록에 없으면 `null`이다 — 다른 시나리오의 결정을 억지로 끼워 넣으면
 * 엉뚱한 금액이 Gap에 더해진다.
 */
export function engineDecisionToReview(
  reviewCase: ReviewCase,
  decision: EngineSnapshot["decision"],
): ReviewDecision | null {
  if (!decision) return null;
  const chosen = reviewCase.alternatives.find((a) => a.id === decision.alternativeId);
  if (!chosen) return null;
  const leverValue = decision.leverValue ?? chosen.lever.base;
  return {
    alternativeId: chosen.id,
    leverValue,
    profitImpact: simulateAlternative(chosen, leverValue).profitImpact,
    rationale: decision.rationale,
    decidedAt: decision.decidedAt ?? "—",
  };
}

export function engineProcessView(
  process: BpmProcessInstance,
  snapshot: EngineSnapshot,
): EngineProcessView {
  const statuses: Record<string, BpmNodeStatus> = {};
  for (const node of process.nodes) {
    statuses[node.id] = normalizeStatus(snapshot.nodeStatuses[node.id]);
  }

  const runByNode: Record<string, AgentRun> = {};
  const provenanceByNode: Record<string, string> = {};
  for (const run of snapshot.runs) {
    // **완료된 노드의 산출물만 통과시킨다.** 엔진은 노드가 돌기 전에는 기록을 만들지
    // 않으므로 보통 문제가 없지만, 이 규칙을 화면 쪽에서도 한 번 더 지킨다 —
    // Mock 경로에서 두 번 새어 나갔던 종류의 실수다(CLAUDE.md 4.5).
    if (statuses[run.nodeId] !== "done") continue;
    runByNode[run.nodeId] = toAgentRun(run);
    provenanceByNode[run.nodeId] = run.provenance;
  }

  const activities: AgentActivity[] = process.nodes
    .filter((node) => node.agentId)
    .map((node) => {
      const agent = process.agents.find((a) => a.id === node.agentId);
      if (!agent) {
        throw new Error(`노드 ${node.id}가 존재하지 않는 Agent ${node.agentId}를 참조한다`);
      }
      const status = toActivityStatus(statuses[node.id]);
      return {
        agent,
        nodeId: node.id,
        nodeLabel: node.label,
        status,
        run: status === "done" ? runByNode[node.id] : undefined,
      };
    });

  // 사람 대기가 우선이다 — 그것이 지금 화면을 보는 사람에게 걸린 일이다.
  const waitingId = snapshot.pendingApproval?.nodeId;
  const activeId =
    waitingId ??
    process.nodes.find((node) => statuses[node.id] === "active")?.id ??
    snapshot.next[0];
  const activeNode = process.nodes.find((node) => node.id === activeId) ?? null;

  return {
    statuses,
    activities,
    activeNode,
    awaitingHuman: snapshot.pendingApproval !== null,
    runningCount: activities.filter((activity) => activity.status === "running").length,
    runByNode,
    provenanceByNode,
  };
}
