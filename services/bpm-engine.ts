/**
 * 워크플로우 상태 제어 인터페이스.
 *
 * 지금은 Mock 인스턴스 위에서 순수 함수로 동작하지만, 시그니처는 LangGraph StateGraph로
 * 교체할 때를 염두에 두고 잡았다 — 호출부는 "현재 진행 지점"만 넘기고 노드별 상태는
 * 여기서 받아 간다. 화면이 상태를 직접 계산하지 않는다.
 *
 * 핵심 규칙: **노드 상태는 저장하지 않고 파생한다.** 실행 순서(`sequence`)와 진행 지점이
 * 유일한 진실이므로, 순서와 상태가 어긋나는 상황이 구조적으로 생기지 않는다.
 */

import type {
  BpmNodeSpec,
  BpmNodeStatus,
  BpmProcessInstance,
} from "@/lib/types/bpm";
import type { ManagementStage } from "@/lib/types/cockpit";

/** 진행 지점이 가질 수 있는 최대 인덱스 (마지막 노드까지 완료한 상태). */
export function maxStepIndex(process: BpmProcessInstance): number {
  return process.sequence.length - 1;
}

export function clampStepIndex(process: BpmProcessInstance, index: number): number {
  return Math.min(Math.max(index, 0), maxStepIndex(process));
}

/**
 * 대안 선택과 승인이 걸리는 노드.
 *
 * **`sequence` 순서로 찾아야 한다.** `nodes` 배열 순서로 첫 `user-task`를 집으면
 * 선택되지 않은 분기의 노드가 잡힌다 — 실제로 그랬다. 시나리오 1·3에서 `op-control`이
 * 먼저 선언되어 있고 그 노드는 `sequence`에 없으므로 `indexOf`가 -1이 되어, 승인 후
 * 진행 지점이 Management Action이 아니라 0(맨 처음)으로 돌아갔다. 데모 플레이어가
 * 장면마다 `step`을 절대값으로 덮어써서 가려져 있었다.
 */
export function approvalNodeId(process: BpmProcessInstance): string | undefined {
  return process.sequence.find(
    (id) => process.nodes.find((node) => node.id === id)?.kind === "user-task",
  );
}

/** 승인 후 이동할 진행 지점 — 승인 노드의 **다음** 지점. */
export function approvalStepIndex(process: BpmProcessInstance): number {
  const nodeId = approvalNodeId(process);
  const at = nodeId ? process.sequence.indexOf(nodeId) : -1;
  // 승인 노드가 없으면 진행 지점을 건드리지 않는다는 뜻으로 현재 기본값을 쓴다.
  return at >= 0 ? clampStepIndex(process, at + 1) : process.defaultStepIndex;
}

/**
 * 노드 하나의 상태를 파생한다.
 *
 * `sequence`에 없으면 선택되지 않은 분기이므로 `skipped`.
 * 현재 지점의 노드는 사람이 수행하는 일이면 `waiting`(내 결재가 걸려 있음), 아니면 `active`.
 */
export function deriveNodeStatus(
  process: BpmProcessInstance,
  node: BpmNodeSpec,
  stepIndex: number,
): BpmNodeStatus {
  const position = process.sequence.indexOf(node.id);
  if (position === -1) return "skipped";
  if (position < stepIndex) return "done";
  if (position > stepIndex) return "pending";
  return node.kind === "user-task" ? "waiting" : "active";
}

export function deriveNodeStatuses(
  process: BpmProcessInstance,
  stepIndex: number,
): Record<string, BpmNodeStatus> {
  return Object.fromEntries(
    process.nodes.map((node) => [node.id, deriveNodeStatus(process, node, stepIndex)]),
  );
}

/** 현재 진행 중인 노드. */
export function currentNode(
  process: BpmProcessInstance,
  stepIndex: number,
): BpmNodeSpec | undefined {
  const id = process.sequence[clampStepIndex(process, stepIndex)];
  return process.nodes.find((node) => node.id === id);
}

/** 현재 진행 중인 루프 단계 (CLAUDE.md 2.2의 6단계 중 하나). */
export function currentStage(
  process: BpmProcessInstance,
  stepIndex: number,
): ManagementStage | undefined {
  return currentNode(process, stepIndex)?.stage;
}

/** 완료 비율(%). 진행 표시용. */
export function progressPercent(
  process: BpmProcessInstance,
  stepIndex: number,
): number {
  return (clampStepIndex(process, stepIndex) / maxStepIndex(process)) * 100;
}

/** 사람의 판단을 기다리며 멈춰 있는지. 배너 노출 조건으로 쓴다. */
export function isAwaitingHuman(
  process: BpmProcessInstance,
  stepIndex: number,
): boolean {
  const node = currentNode(process, stepIndex);
  return node?.kind === "user-task";
}
