/**
 * BPM 프로세스 및 Agent 실행 타입.
 *
 * 설계 원칙 (CLAUDE.md 1장 Deterministic BPM + Probabilistic AI):
 * 워크플로우의 상태 전이는 결정론적이다 — 실행 순서(`sequence`)가 유일한 진실이고,
 * 각 노드의 상태는 저장하지 않고 현재 진행 지점에서 **파생**한다(`services/bpm-engine.ts`).
 * 노드마다 status 필드를 두면 순서와 상태가 따로 놀아 곧 어긋난다.
 */

import type { ManagementStage } from "@/lib/types/cockpit";

/** BPMN 2.0 요소 종류. 모양과 아이콘으로 구분하며 색에만 의존하지 않는다. */
export type BpmNodeKind =
  | "start"
  | "end"
  /** AI Agent가 수행 (데이터 수집·분석·시뮬레이션) */
  | "agent-task"
  /** 사람이 수행 — Human-in-the-Loop 지점 */
  | "user-task"
  /** 시스템이 자동 수행 */
  | "service-task"
  /** 배타 분기 */
  | "gateway";

/**
 * 노드 진행 상태. 저장하지 않고 파생한다.
 *
 * `waiting`은 사람의 판단을 기다리며 멈춰 있는 상태로, `active`와 구분한다 —
 * 경영진이 "지금 내 결재가 걸려 있는지"를 한눈에 알아야 한다.
 */
export type BpmNodeStatus = "done" | "active" | "waiting" | "pending" | "skipped";

export const BPM_STATUS_LABEL: Record<BpmNodeStatus, string> = {
  done: "완료",
  active: "진행 중",
  waiting: "승인 대기",
  pending: "대기",
  skipped: "미실행",
};

export interface BpmNodeSpec {
  id: string;
  kind: BpmNodeKind;
  label: string;
  /** 수행 주체. 사람이면 부서·이름, Agent면 Agent 이름. */
  actor?: string;
  stage: ManagementStage;
  /** React Flow 캔버스 좌표. 자동 레이아웃을 쓰지 않으므로 직접 지정한다. */
  position: { x: number; y: number };
  /** 완료 시 산출물 요약. */
  outcome?: string;
  /** 소요 시간 표시용 문자열. */
  duration?: string;
  /** 이 노드를 수행하는 Agent id (`agent-task`에만 있다). */
  agentId?: string;
}

export interface BpmEdgeSpec {
  id: string;
  source: string;
  target: string;
  /** 게이트웨이 분기 조건 등. */
  label?: string;
  /** 게이트웨이 출발 핸들 id (`main` | `branch`). */
  sourceHandle?: string;
}

export interface AgentSpec {
  id: string;
  name: string;
  /** 한 줄 역할. */
  role: string;
  /** 담당 분석 영역. */
  capability: string;
}

/** Agent 한 번의 실행 기록. 상태는 저장하지 않고 진행 지점에서 파생한다. */
export interface AgentRun {
  agentId: string;
  /** 수행한 노드 id. */
  nodeId: string;
  /** 산출물 요약. */
  output: string;
  /** 근거로 참조한 데이터 소스. 사람이 검증할 수 있어야 한다. */
  sources: string[];
  duration: string;
}

export interface BpmProcessInstance {
  id: string;
  /** 처리 중인 안건 제목. */
  subject: string;
  /** 연결된 Cockpit `RiskSignal.id`. 두 화면이 같은 사건을 가리킨다. */
  riskId: string;
  kri: { label: string; value: string; threshold: string };
  startedAt: string;
  /**
   * 실행 순서. 여기에 없는 노드는 선택되지 않은 분기이므로 `skipped`가 된다.
   * 노드 상태 전체가 이 배열과 현재 진행 지점에서 파생된다.
   */
  sequence: string[];
  /** 데모 시작 지점 (`sequence` 인덱스). */
  defaultStepIndex: number;
  nodes: BpmNodeSpec[];
  edges: BpmEdgeSpec[];
  agents: AgentSpec[];
  runs: AgentRun[];
}
