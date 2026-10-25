/**
 * SC01 엔진 응답 모양 — `engine/app/sc01/view.py`가 만드는 그대로다.
 *
 * 화면은 **엔진이 준 값을 그대로 쓴다.** 금액·비율은 문자열 DECIMAL로 오며(API-02), 표시할 때만
 * 숫자로 바꾼다(`lib/sc01/format.ts`). 여기서 다시 계산하면 엔진 규칙과 갈라진다.
 */

export type Risk = "NORMAL" | "ATTENTION" | "CRITICAL";
export type SceneState = "READY" | "ACTIVE" | "HANDED_OFF";
export type SourceStatus = "RECEIVED" | "NEEDS_INFO" | "VERIFIED";
export type TaskStatus = "ASSIGNED" | "IN_PROGRESS" | "NEEDS_INFO" | "COMPLETED";

export interface Metric {
  metric_id: string;
  value: string | null;
  unit: "ratio" | "qty" | "krw";
  computable: boolean;
  risk_level: Risk | null;
  reason: string | null;
}

export interface Assessment {
  model_id: string;
  period: string;
  target: number | null;
  prior: number | null;
  latest: number | null;
  unit_cm: string;
  /** null = 판정 보류(필수 입력 누락). 정상과 다르다. */
  risk: Risk | null;
  partial: boolean;
  metrics: Record<string, Metric>;
}

export interface SourceRow {
  model_id: string;
  period: string;
  /** null = 누락. 확인된 0과 다르다. */
  quantity: number | null;
  unit: string;
  quantity_scope: string;
  allocation_scope: string;
}

export interface Source {
  source_id: string;
  fixture_id: string;
  customer_plan_id: string;
  received_at: string;
  hash: string;
  status: SourceStatus;
  corrects: string | null;
  rows: SourceRow[];
  errors: { row: string; code: string; message: string }[];
  verified_by: string | null;
  verified_at: string | null;
  opinion?: string;
  evidence?: string;
}

export interface CalcRun {
  run_id: string;
  status: "SUCCEEDED" | "FAILED";
  versions: Record<"target" | "prior" | "latest" | "cost" | "rule" | "fixed", string>;
  source_id: string;
  at: string;
  results: Assessment[];
}

export interface Issue {
  issue_id: string;
  cause: string;
  model_id: string;
  period: string;
  risk: Risk | null;
  status: "OPEN" | "RESOLVED";
  owner_role: string;
  runs: string[];
  history: { at: string; run_id: string; risk: Risk | null }[];
}

export interface Task {
  task_id: string;
  type: "DQ" | "SALES" | "PROD" | "MAT" | "FIN";
  node_id: string;
  owner_role: string;
  assigned_to: string | null;
  assignedName: string | null;
  assigned_at: string;
  due_at: string;
  status: TaskStatus;
  accepted_by: string | null;
  accepted_at: string | null;
  completed_at: string | null;
  run_id: string | null;
  issue_id: string | null;
  source_id: string | null;
  overdue: boolean;
  /** 이 업무가 근거로 삼은 계산들. 정정으로 새 계산이 오면 늘어난다. */
  runs: string[];
  /** 계산별 인수·확인 기록 — 정정 전 인수도 지우지 않는다(WF-02). */
  acks: { run_id: string; by: string; at: string }[];
  /** 새 근거에 대한 재확인이 필요하다. */
  reconfirm: boolean;
  /** 완료된 업무를 다시 쓰지 않고 만든 재검토 업무면 원래 업무(WF-03). */
  reopens: string | null;
  history: { at: string; status: string; by: string; note?: string | null }[];
}

export interface AgentDraft {
  summary: string;
  findings: string[];
  evidence_refs: string[];
  questions: string[];
  suggested_tasks: { type: string; reason: string }[];
  limitations: string[];
}

/** Agent 초안 기록(AG-01~03). 검증에 실패한 응답은 엔진이 내보내지 않는다. */
export interface AgentOutput {
  output_id: string;
  run_id: string;
  status: "RUNNING" | "SUCCEEDED" | "FAILED";
  mode: string;
  delayed: boolean;
  attempts: number;
  provenance: string | null;
  model: string | null;
  prompt_version: string | null;
  input_hash: string;
  latency_ms: number | null;
  requested_by: string;
  requested_at: string;
  draft: AgentDraft | null;
  errors: string[];
  adopted_by: string | null;
  adopted_at: string | null;
}

export interface Alert {
  alert_id: string;
  kind: "OVERDUE";
  task_id: string;
  due_at: string;
  at: string;
  to: string[];
  unaccepted: boolean;
  message: string;
}

export interface FormField {
  key: string;
  label: string;
  type: "text" | "bool" | "choice" | "number";
  required?: boolean;
  choices?: string[] | null;
  default?: unknown;
}

/** BPM이 지금 사람을 기다리는 곳 하나. */
export interface Waiting {
  nodeId: string;
  title: string;
  role: string | null;
  review: Record<string, unknown>;
  fields: FormField[];
  taskId: string | null;
}

export interface Review {
  run_id: string;
  by: string;
  at: string;
  opinion: string;
  evidence: string;
  manual_review: boolean;
  agent_output: string | null;
}

export interface AuditEntry {
  seq: number;
  at: string;
  event_code: string | null;
  actor: string;
  actor_name: string;
  actor_role: string;
  action: string;
  detail: Record<string, unknown>;
}

export interface HandoffCheck {
  run_id: string;
  required: string[];
  accepted: Record<string, boolean>;
  conditions: Record<"valid_evidence" | "sales_reviewed" | "follow_ups_accepted" | "not_blocked", boolean>;
  met: boolean;
  reasons: string[];
}

export interface DemoRunView {
  demoRunId: string;
  caseId: string;
  agentMode: string;
  agentOutputs: AgentOutput[];
  alerts: Alert[];
  /** 정정으로 대체된 이전 BPM 실행들(EX03). */
  bpmHistory: { run_id: string; state: string; superseded_at: string; by_source: string }[];
  /** 정정 전에 성립했던 인계들 — 역사로 남는다(WF-03). */
  handoffHistory: { run_id: string; at: string }[];
  clock: string;
  step: string;
  scriptIndex: number;
  scene: SceneState;
  /** 지난 시점을 되짚어 본 것인가 — true면 조작할 수 없다. */
  historical: boolean;
  bpm: null | {
    runId: string;
    state: string;
    waiting: Waiting[];
    position: string[];
    visited: string[];
  };
  sources: Source[];
  forecasts: { version_id: string; source_id: string; approval: string; created_at: string }[];
  calcRuns: CalcRun[];
  latestRunId: string | null;
  issues: Issue[];
  tasks: Task[];
  reviews: Review[];
  handoff: { run_id: string; at: string } | null;
  handoffCheck: HandoffCheck | null;
  audit: AuditEntry[];
}

export interface Pnl {
  revenue: string;
  cm: string;
  fixed: string;
  mgmtProfit: string;
}

export interface Dashboard {
  scope: { customer: string; plant: string; product: string; year: number; note: string };
  asOf: { actualCutoff: string; forecast: string };
  period: string;
  versions: string[];
  approved: string;
  review: string | null;
  totals: Record<string, Pnl>;
  trend: ({ month: string; basis: "ACTUAL" | "ACTUAL_PLUS_FORECAST" | "FORECAST" } & Record<
    string,
    string
  >)[];
  month: string;
  models: {
    modelId: string;
    target: number;
    prior: number;
    latest: number;
    actual: number | null;
    risk: Risk | null;
    achievement: string | null;
  }[];
  openIssues: number;
}

export interface ProcessTopology {
  processId: string;
  name: string | null;
  nodes: {
    id: string;
    kind: string;
    name: string | null;
    role: string | null;
    /** 결정 기록 태스크면 그 결재 노드 id — 캔버스는 그 결재에 접어 그린다(docs/chaeksas-integration.md N1). */
    recordOf?: string | null;
  }[];
  flows: { id: string; source: string; target: string; condition: string | null; default: boolean }[];
}

export interface DemoUser {
  userId: string;
  name: string;
  role: string;
}

export interface ScriptStep {
  index: number;
  code: string;
  at: string;
  actor: string;
  nodeId: string | null;
  label: string;
}

export interface HistoryEntry {
  seq: number;
  event: string;
  clock: string;
  scriptIndex: number;
}

export interface CustomerPlanRow {
  modelId: string;
  period: string;
  quantity: number | null;
}
