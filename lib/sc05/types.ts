/**
 * SC05 엔진 응답 — `engine/app/sc05/view.py`의 모양 그대로. 금액은 원 단위 DECIMAL 문자열이다(화면은 단위만 바꾼다).
 * 문서에는 지금 시각까지의 기록만 있다 — 배경 원천도 시각이 지나야 들어온다(미래 행을 받아 화면에서 감추지 않는다).
 * FC51-D(검토안)와 FC51(공식본)은 같은 RUN의 승인 전후다 — 화면은 두 버전의 월손익을 더하지 않는다.
 */

import type { Executor, FormField } from "@/lib/sc01/types";

export interface Sc05Waiting {
  nodeId: string;
  title: string;
  role: string | null;
  assignee: string | null;
  review: Record<string, unknown>;
  fields: FormField[];
  taskId: string | null;
}

export interface Activity {
  activity_id: string;
  name: string;
  owner: string | null;
  start: string | null;
  end: string | null;
  predecessors: string[];
  cooperation: string | null;
  /** null = 미입력(0원과 다르다). */
  cost: string | null;
  completion: string | null;
  evidence: string | null;
}

export interface Plan {
  plan_id: string;
  seq: number;
  task_id: string;
  version: number;
  parent?: string | null;
  background: boolean;
  activities: Activity[];
  effect_rule?: string;
  budget: string;
  effect_start: string;
  due_at: string;
  state: string;
  summary?: string;
  scope_note?: string;
  change_reason?: string | null;
  change_impact?: string | null;
  confirmed_by: string | null;
  confirmed_at: string | null;
  management_check: "PENDING" | "VERIFIED" | "REWORK_REQUIRED";
  verified_by: string | null;
  verified_at: string | null;
  agent_ref?: string | null;
  diff?: Array<{ activity_id?: string; fields?: string[]; before?: Activity | null; after?: Activity; scope?: string; kept?: boolean } & Record<string, unknown>>;
  scope_problems?: string[];
  /** 확정 차단 사유 — 엔진이 낸다(누락·순환·승인 범위). 배경 계획은 빈 목록이다. */
  problems: string[];
  history?: Array<{ at: string; state: string; by: string; note?: string }>;
}

export interface Condition {
  condition_id: string;
  content: string;
  owner: string;
  verifier: string;
  due_at: string;
  state: string;
  evidence: Array<{ version: number; refs: string[]; details: string; plan_version: string | null; by: string; at: string }>;
  confirmed_by?: string;
  confirmed_at?: string;
  history: Array<{ at: string; state: string; by: string; note?: string }>;
}

export interface Request {
  request_id: string;
  task_id: string;
  scope: "ONEOFF" | "OPERATING";
  amount: string;
  reason: string;
  state: string;
  background: boolean;
  approval_ref: string;
  history: Array<{ at: string; state: string; by: string; note?: string }>;
}

export interface Txn {
  txn_id: string;
  task_id: string;
  scope: "ONEOFF" | "OPERATING";
  request_ref: string;
  at: string;
  type: "COMMIT" | "SETTLE";
  commitment_delta: string;
  paid_delta: string;
  pnl_cost: string;
  evidence: string;
}

export interface BudgetLine {
  limit: string;
  commitment: string;
  paid: string;
  available: string;
}

export interface Requirement {
  id: string;
  label: string;
  ok: boolean;
}

export interface ChangeCase {
  change_id: string;
  plan_ref: string;
  model_id: string;
  received_at: string | null;
  shared_at: string | null;
  ack_at: string | null;
  ack_by: string | null;
  delegate: boolean;
  decision: "NORMAL" | "URGENT" | null;
  order_ref: string | null;
  note: string | null;
  state: string;
  background: boolean;
  /** 공유·구매 확인 소요(분, 엔진 계산). null = 미확인 — 0분이 아니다. */
  share_minutes: string | null;
  ack_minutes: string | null;
  response: { inventory: number; open_orders: number; need_date: string; normal_date: string | null; rationale: string } | null;
}

export interface Order {
  order_id: string;
  change_ref: string | null;
  qty: number;
  urgent: boolean;
  transport: string;
  premium: string;
  extra: string | null;
  ordered_at: string | null;
  recorded_at: string | null;
  approver: string | null;
  approved_at: string | null;
  late: number | null;
  quality: number | null;
  result_status: string | null;
  background: boolean;
  state: string;
}

export interface Timing {
  measured: number;
  unconfirmed: number;
  reversed: number;
  average: string | null;
  max: string | null;
  delayed: number;
  limit: number;
}

export interface Observation {
  orders: number;
  qty: number;
  urgent: number;
  urgent_rate: string | null;
  extra_cost: string | null;
  baseline_count: number;
  baseline_cost: string;
  support: string | null;
  net: string | null;
  late: number | null;
  quality: number | null;
  unconfirmed_results: number;
  duplicates: string[];
  unknown_cost: string[];
  changes: number;
  share: Timing;
  ack: Timing;
  blocking: string[];
  complete: boolean;
  period: string;
  scope: string;
  comparison_basis: string;
  one_off_august: string;
  observation_id?: string;
  confirmed_by?: string;
  confirmed_at?: string;
}

export interface OperatingPlan {
  plan_id: string;
  task_id: string;
  version: number;
  remaining_plan: string;
  assumption_note: string;
  assumptions: { urgent?: Record<string, number>; support?: string; qty?: number; fixed_saving?: string; stabilize_due?: string };
  state: string;
  owner_confirm: { by: string; at: string };
  management_verify: { by: string; at: string; comment: string } | null;
  progress: string;
}

export interface MonthRow {
  period: string;
  kind: "ACTUAL" | "FORECAST";
  target: string;
  basis_profit: string;
  effect: string;
  profit: string;
  gap: string;
  fixed: string;
  models: Array<{ model_id: string; qty: number; basis_cm: string; effect: string; cm: string }>;
}

export interface PeriodRow {
  kind: string;
  label: string;
  target: string;
  basis_profit: string;
  effect: string;
  profit: string;
  gap: string;
}

export interface Run {
  run_id: string;
  method: string;
  cutoff: string;
  prior_official: string;
  months: MonthRow[];
  periods: Record<"year" | "closed" | "forecast" | "q3", PeriodRow>;
  annual: string;
  target: string;
  gap: string;
  reconciliation: {
    prior_total: string;
    new_total: string;
    rows: Array<{ cause: string; month: string; amount: string }>;
    by_cause: Array<{ cause: string; label: string; amount: string }>;
    delta: string;
    residual: string;
    ok: boolean;
  };
  effects: Array<{ task_id: string; month: string; net: string; source?: string }>;
  errors: string[];
  valid: boolean;
  run_hash: string;
  calculated_at: string;
}

export interface Forecast {
  forecast_id: string;
  kind: "OFFICIAL" | "REVIEW";
  run_id: string;
  state: string;
  background: boolean;
  months?: MonthRow[];
  annual?: string;
  approved_at?: string | null;
  approved_by?: string | null;
  published_at?: string | null;
  parent_official?: string | null;
  review_ref?: string;
  change_reasons?: string;
  confirmations?: Record<string, { decision: string; by: string; at: string; run_hash: string; comment: string }>;
  drafted_at?: string;
  submitted_at?: string | null;
  return_reason?: string;
  stale_reason?: string;
  note?: string;
  history?: Array<{ at: string; state: string; by: string; note?: string }>;
}

export interface Followup {
  followup_id: string;
  target: string;
  owner: string | null;
  due_at: string | null;
  content: string | null;
  state?: string;
}

export interface Evidence {
  evidence_id: string;
  type: string;
  object_refs: string[];
  written_at: string;
  written_by: string | null;
  body: string;
  confirmed_by: string | null;
  confirmed_at: string | null;
}

export interface AgentOutput {
  output_id: string;
  kind: string;
  prompt_version: string;
  model_version: string;
  mode: "REPLAY" | "LIVE";
  created_at: string;
  status: "SUCCEEDED" | "FAILED";
  draft: {
    summary: string;
    findings: Array<{ text: string; evidence_refs: string[] }>;
    questions: string[];
    draft_text: string;
    activities?: Activity[];
  } | null;
  errors: string[];
  source_hash: string | null;
  review_status: "UNREVIEWED" | "REVIEWED" | "MODIFIED_BY_HUMAN" | "ACCEPTED_BY_HUMAN";
  reviewed_by: string | null;
  reviewed_at: string | null;
}

export interface Handoff {
  handoff_id: string;
  source_handoff: string;
  approval: string;
  decision: string;
  forecast: { parent: string; official: string; approved_at: string; published_at: string };
  financial_snapshot: { target: string; forecast: string; gap: string; effect: string; effect_closed: string; effect_remaining: string };
  followups: Followup[];
  operation: Record<string, string>;
  state_snapshot: Record<string, string>;
  completed_by: string;
  completed_at: string;
}

export interface Task {
  task_id: string;
  type: string;
  node_id: string;
  assigned_to: string;
  assignedName: string | null;
  due_at: string;
  status: string;
  overdue: boolean;
  opened_late: boolean;
}

export interface Sc05View {
  scene: "SC05";
  demoRunId: string;
  caseId: string;
  caseLabel: string;
  clock: string;
  step: string;
  scriptIndex: number;
  historical: boolean;
  status: {
    scene: string;
    plan: string | null;
    planVersion: string | null;
    managementCheck: string | null;
    con41: string;
    sup41: string;
    operation: string;
    official: string | null;
    review: string | null;
    risk: string;
    target: string;
  };
  sc04: {
    handoff: { handoff_id: string; approval: string; decision: string; minutes: string; overall_owner: string; financial_snapshot: Record<string, string>; as_of: string };
    approval: { approval_id: string; total_budget: string; delegation: string | null };
    actions: Record<string, { target_id: string; owner: string; worker: string; budget: string; expected_effect: string; plan_due: string; completion_due: string; conditions: string[]; decision: string }>;
    directives: Record<string, { directive_id: string; kind: string; content: string; owner: string; verifier: string | null; due_at: string; expected_effect: string | null }>;
    decision_months: Array<{ period: string; target: string; base: string; effect: string }>;
    gap_before: string;
  };
  sceneInfo: { started_at: string | null; completed_at: string | null; risk: string; target: string };
  schedule: Record<string, string>;
  settings: Record<string, number>;
  plans: Plan[];
  planPointer: string | null;
  collaborations: Array<{ collab_id: string; plan_version: string; kind: string; content: string; contact: string | null; by: string; at: string }>;
  conditions: Condition[];
  requests: Request[];
  ledger: Txn[];
  budget: { tasks: Array<BudgetLine & { task_id: string }>; total: BudgetLine; operating: BudgetLine };
  startCheck: { items: Requirement[]; ready: "READY" | "WAIT"; start_allowed: boolean; apply_at: string; blocking: string[]; plan_version: string | null } | null;
  start: { start_id: string; plan_version: string; started_at: string; started_by: string } | null;
  operation: Array<{ task_id: string; owner: string; state: string; started_at: string | null; history: Array<{ at: string; state: string; ref?: string }> }>;
  customerPlans: Array<{ plan_ref: string; received_at: string; lines: Array<{ model_id: string; month_total: number; windows: string[]; before: number[]; after: number[]; changed: boolean; month_diff: number; note: string }> }>;
  changes: ChangeCase[];
  orders: Order[];
  sourceIssues: Array<{ kind: string; order_id: string }>;
  observation: Observation | null;
  observationPreview: Observation | null;
  operatingPlans: OperatingPlan[];
  runs: Run[];
  forecasts: Forecast[];
  official: string | null;
  reviewForecastId: string | null;
  forecastBlocking: string[];
  shares: Array<{ share_id: string; object: string; recipients: string; at: string }>;
  followups: Followup[];
  directiveLog: Array<{ directive_id: string; at: string; state: string; ref: string }>;
  evidence: Evidence[];
  completion: { items: Requirement[]; met: boolean; blocking: string[] } | null;
  handoff: Handoff | null;
  agentMode: "REPLAY" | "LIVE";
  agentOutputs: AgentOutput[];
  tasks: Task[];
  alerts: Array<{ alert_id: string; kind: string; target: string; due_at: string; at: string; to: string[]; message: string }>;
  audit: { seq: number; at: string; actor: string; actor_name: string; action: string; event_code: string | null; detail: Record<string, unknown> }[];
  executor: Executor;
  answerHere: boolean;
  bpm: {
    executor: Executor;
    externalRunId: string | null;
    runId: string | null;
    state: string;
    waiting: Sc05Waiting[];
    center: { job: { job_id: string; at: string } | null; problem: string | null; package: string | null } | null;
    position: string[];
    visited: string[];
  } | null;
}

export interface Sc05Case {
  caseId: string;
  label: string;
}

export interface Sc05ScriptStep {
  index: number;
  code: string;
  at: string;
  actor: string;
  kind: "start" | "act" | "view" | "agent" | "review";
  nodeId: string | null;
  label: string;
  event: string | null;
}
