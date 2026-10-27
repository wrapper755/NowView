/**
 * SC04 엔진 응답 — `engine/app/sc04/view.py`의 모양 그대로. 금액은 원 단위 DECIMAL 문자열이다(화면은 단위만 바꾼다).
 * 보고본(REP41-v1)과 판단본(DEC41-v2)은 다른 계산 실행이다 — 화면은 두 버전을 섞어 집계하지 않는다.
 */

import type { Executor, FormField } from "@/lib/sc01/types";

export interface Sc04Waiting {
  nodeId: string;
  title: string;
  role: string | null;
  /** 이 결재의 담당 — 인수·검증 보완은 그 책임자다. */
  assignee: string | null;
  review: Record<string, unknown>;
  fields: FormField[];
  taskId: string | null;
}

export interface Confirmation {
  decision: "CONFIRMED" | "REWORK_REQUESTED";
  by: string;
  at: string;
  opinion: string;
  evidence_hash: string | null;
}

export interface ResultVersion {
  version: number;
  ref: string;
  outcome: "SUBMITTED" | "EXCLUDED";
  conclusion: string;
  evidence_refs: string[];
  risks: string;
  reason: string | null;
  assumption_refs: string[];
  submitted_by: string;
  submitted_at: string;
  confirmation: Confirmation | null;
  change?: string;
  causes: Array<{ model_id: string; t01: number; f01: number; unit_cm: string; contribution: string }> | null;
}

export interface AnalysisResult {
  result_id: string;
  seq: number;
  task_id: string;
  alts: string[];
  writer: string;
  confirmer: string;
  state: "AWAITING" | "SUBMITTED" | "CONFIRMED" | "REWORK_REQUESTED";
  versions: ResultVersion[];
}

export interface Followup {
  question_id: string;
  question: string;
  owner: string;
  due_at: string | null;
  treatment: string | null;
  state: string;
  history: Array<{ at: string; note: string; by?: string }>;
}

export interface Assumption {
  alt_id: string;
  name: string;
  task_id: string;
  model_id: string;
  cost_item: string;
  start: string;
  monthly_qty: number;
  avoid_price: string;
  outsource_price: string;
  logistics_price: string;
  emergency_before: number;
  emergency_after: number;
  per_event_cost: string;
  monthly_support: string;
  one_off_cost: string | null;
  one_off_month: string;
  budget: string;
  draft_dup_price: string | null;
  avoided_fixed: string;
  duplicate_override: Record<string, string>;
  version: number;
  result_ref: string;
}

export interface EffectLine {
  alt_id: string;
  month: string;
  start: string;
  applied: boolean;
  qty: number;
  avoided: string;
  added: string;
  logistics: string;
  support: string;
  one_off: string;
  draft_discount: string;
  duplicate: string;
  net: string;
  fixed_saving: string;
}

export interface AltEffect {
  alt_id: string;
  name: string;
  start: string;
  counted: boolean;
  net_2027: string;
  one_off: string;
  duplicate: string;
  fixed_saving: string;
  normal_monthly: string;
  normal_annual: string;
}

export interface PeriodResult {
  kind: "year" | "q3" | "q4" | "remaining";
  label: string;
  target: string;
  base: string;
  effect: string;
  forecast: string;
  /** 목표 부족 — 음수면 목표 초과다(0으로 자르지 않는다). */
  gap_before: string;
  gap: string;
  forecast_excl_conditional: string;
  gap_excl_conditional: string;
}

export interface MonthResult {
  period: string;
  target: string;
  base: string;
  effect: string;
  effect_excl: string;
}

export interface ValidationError {
  alt_id: string;
  code: string;
  message: string;
  amount: string | null;
}

export interface EffectRun {
  run_id: string;
  seq: number;
  kind: "VERIFY" | "REPORT" | "DECISION" | "APPROVED_SCOPE";
  basis_ref: string;
  assumptions_hash: string;
  include: string[] | null;
  conditional: string[];
  calculated_at: string;
  created_by: string;
  status: "VERIFIED" | "VALIDATION_FAILED";
  result: {
    lines: EffectLine[];
    alts: AltEffect[];
    months: MonthResult[];
    periods: Record<PeriodResult["kind"], PeriodResult>;
    effect_total: string;
    normal_annual_total: string;
    duplicate_total: string;
    fixed_saving_total: string;
    fixed_cost_monthly: string;
    errors: ValidationError[];
    passed: boolean;
    status: string;
  };
}

export interface Rework {
  rework_id: string;
  run_id: string;
  alt_id: string;
  items: ValidationError[];
  reason: string;
  owner: string;
  due_at: string;
  requested_by: string;
  requested_at: string;
  state: "OPEN" | "RESOLVED";
  resolved_by?: string;
  resolved_at?: string;
}

export interface RecommendationItem {
  alt_id: string;
  name: string;
  recommended: boolean;
  priority: number | null;
  reason: string;
  owner: string;
  worker: string;
  net_2027: string;
  normal_annual: string;
  start: string;
  budget: string;
}

export interface Recommendation {
  ref: string;
  run_id: string;
  items: RecommendationItem[];
  excluded: Array<{ alt_id: string; name: string; reason: string; evidence: string; effect: null }>;
  owner_confirmations: Array<{ by: string; at: string }>;
  confirmed_by: string;
  confirmed_at: string;
}

export interface ReportVersion {
  report_id: string;
  seq: number;
  kind: "REPORT" | "DECISION";
  parent: string | null;
  status: "FROZEN" | "DRAFT" | "CONFIRMED" | "SUPERSEDED";
  run_id: string;
  conclusion?: string;
  snapshot?: Record<string, unknown> & { effect?: string; gap?: string; gap_before?: string };
  content_hash: string | null;
  frozen_by: string | null;
  frozen_at: string | null;
  distribution?: { at: string; by: string; recipients: string[]; memo: string };
  changes?: Array<{ alt_id: string; field: string; label: string; before: unknown; after: unknown }>;
  reason?: string;
  change_confirmed_by?: string | null;
  diff?: Array<{ alt_id: string; start_before: string; start_after: string; before: string; after: string; diff: string }>;
  created_by?: string;
  created_at?: string;
  opinion?: string;
}

export interface MeetingRecord {
  record_id: string;
  record_type: "QUESTION" | "ANSWER" | "DIRECTIVE" | "NOTE";
  meeting_id: string;
  actor_id: string;
  event_at: string;
  subject: string;
  content: string;
  related_ref: string;
  state: string;
}

export interface Meeting {
  meeting_id: string;
  type: string;
  subject: string;
  chair: string;
  reporter: string;
  scheduled_at: string;
  report_version: string;
  state: "READY" | "IN_PROGRESS" | "HELD";
  opened_at: string | null;
  report_summary?: string;
  attendance: Array<{ record_id: string; actor: string; state: string; at: string }>;
  records: MeetingRecord[];
}

export interface Directive {
  directive_id: string;
  seq: number;
  kind: "CONDITION" | "SUPPORT" | "DISCOVERY";
  alt_ref: string | null;
  action_ref: string | null;
  content: string;
  owner: string | null;
  collaborators: string[];
  verifier: string | null;
  due_at: string | null;
  responsibility: "PENDING" | "ACCEPTED";
  responsibility_at: string | null;
  fulfillment: "OPEN" | "VERIFIED_FULFILLED";
  /** 미산정 — 0이 아니다. */
  expected_effect: string | null;
  state: string;
  source: string;
}

export interface Decision {
  decision_id: string;
  meeting_id: string;
  report_ref: string;
  items: Record<string, { alt_id: string; outcome: "APPROVED" | "CONDITIONAL" | "HOLD" | "REJECTED"; reason: string; condition_refs?: string[] }>;
  approved: string[];
  conditional: string[];
  run_id: string;
  approved_effect: string;
  gap: string;
  gap_excl_conditional: string;
  decided_by: string;
  decided_at: string;
}

export interface ApprovalItem {
  alt_id: string;
  decision: string;
  owner: string;
  worker: string;
  budget: string | null;
  planned: string;
  plan_due: string | null;
  completion_due: string | null;
  conditions: string[];
}

export interface ApprovalDraft {
  version: number;
  decision_ref: string;
  overall_owner: string | null;
  total_budget: string | null;
  plan_due: string | null;
  items: Record<string, ApprovalItem>;
  delegation: string;
  minutes: string;
  drafted_by: string;
  drafted_at: string;
  missing: string[];
  returned?: { at: string; by: string; opinion: string };
}

export interface Approval {
  approval_id: string;
  version: number;
  decision_ref: string;
  decision_hash: string;
  overall_owner: string;
  total_budget: string;
  items: Record<string, ApprovalItem>;
  directives: string[];
  budget_status: { planned: string; committed: string; spent: string; headroom: string };
  delegation: string;
  policy_id: string;
  minutes_ref: string;
  approved_effect: string;
  gap: string;
  approved_by: string;
  approved_at: string;
  state: string;
  content_hash: string;
}

export interface Assignment {
  target_id: string;
  seq: number;
  kind: "ACTION" | "SUPPORT" | "OVERALL";
  owner: string;
  assignment_version: number;
  state: "ASSIGNED" | "ACCEPTED" | "RETURNED";
  assigned_at: string;
  accept_due: string;
  accepted_at: string | null;
  accepted_by: string | null;
  accepted_version: number | null;
  return_reason?: string;
  clarification?: string;
  history: Array<{ at: string; state: string; by: string; version: number; note?: string; change?: string }>;
  alt_id?: string;
  analysis_task?: string;
  approval_ref: string;
  decision?: string;
  worker?: string;
  expected_effect?: string;
  budget?: string | null;
  plan_due?: string | null;
  completion_due?: string | null;
  conditions?: string[];
  execution_gate?: string;
  total_budget?: string;
  directive?: string;
}

export interface Completion {
  items: Array<{ id: string; label: string; ok: boolean }>;
  met: boolean;
  blocking: string[];
  rate: { assigned: number; accepted: number; overall_accepted: boolean; rate: string | null };
  open_conditions: string[];
}

export interface Handoff {
  handoff_id: string;
  review_id: string;
  source_handoff: string;
  meeting: string;
  report: string;
  decision: string;
  approval: string;
  minutes: string;
  overall_owner: string;
  acceptance_ref: { version: number; at: string };
  actions: Array<Partial<Assignment>>;
  conditions: Array<Partial<Directive>>;
  directives: Array<Partial<Directive>>;
  excluded: Array<{ alt_id: string; result?: string; evidence?: string; decision?: string; reason?: string }>;
  financial_snapshot: {
    baseline: string;
    target: string;
    effect: string;
    gap: string;
    conditional_effect: string;
    gap_excl_conditional: string;
    normal_annual_reference: string;
  };
  execution_gates: Array<{ target_id: string; gate: string }>;
  budget: { total: string; planned: string; committed: string; spent: string; headroom: string };
  detail_plan: string;
  state_snapshot: Record<string, string>;
  as_of: string;
  completed_by: string;
  memo: string;
}

export interface Task {
  task_id: string;
  seq: number;
  type: string;
  node_id: string;
  request_id: string | null;
  assigned_to: string;
  assignedName: string | null;
  assigned_at: string;
  due_at: string;
  status: "ASSIGNED" | "COMPLETED";
  completed_at: string | null;
  completed_by: string | null;
  reopens: string | null;
  opened_late?: boolean;
  overdue: boolean;
}

export interface AgentOutput {
  output_id: string;
  kind: "AG41" | "AG42" | "AG43";
  prompt_version: string;
  mode: string;
  created_at: string;
  status: "SUCCEEDED" | "FAILED";
  draft: { summary: string; findings: Array<{ text: string; evidence_refs: string[] }>; questions: string[]; draft_text: string } | null;
  errors: string[];
  source_version: string | null;
  adopted_by: string | null;
  adopted_at: string | null;
  review_status: string;
}

export interface BudgetPolicy {
  allowed: boolean;
  approver: string | null;
  rule: string;
  total_after: string;
}

export interface Sc04View {
  scene: "SC04";
  demoRunId: string;
  caseId: string;
  caseLabel: string;
  clock: string;
  step: string;
  scriptIndex: number;
  historical: boolean;
  status: {
    review: string;
    approval: string | null;
    conditions: string | null;
    risk: string;
    forecast: string;
    target: string;
    scene: string;
  };
  sc03: {
    demo_run_id: string;
    handoff: Record<string, unknown> & { handoff_id: string; next_meeting: { meeting_id: string; at: string }; analysis_due: string; consolidation_due: string };
    kpis: Record<string, string | null>;
    tasks: Array<{ task_id: string; title: string; owner: string; collaborators: string[]; question: string; deliverable: string; due_at: string; candidate_refs: string[]; assignment_version: number; accepted_at: string }>;
    questions: Array<Record<string, unknown>>;
    excluded_candidates: Array<{ candidate_id: string; reason: string; evidence_ref: string }>;
  };
  review: { review_id: string; state: string; started_at: string | null; completed_at: string | null };
  schedule: Record<string, string>;
  baseline: Array<{ period: string; target: string; base: string }>;
  results: AnalysisResult[];
  followups: Followup[];
  assumptions: Assumption[];
  assumptionLog: Array<{ alt_id: string; version: number; at: string; by: string; note: string }>;
  runs: EffectRun[];
  verification: { run_id: string; assumptions_hash: string; verified_by: string | null; verified_at: string | null; memo: string; state: string } | null;
  rework: Rework[];
  recommendation: Recommendation | null;
  reports: ReportVersion[];
  reportId: string | null;
  decisionId: string | null;
  meeting: Meeting | null;
  directives: Directive[];
  decision: Decision | null;
  approvalDraft: ApprovalDraft | null;
  approvals: Approval[];
  minutes: Array<{ minutes_id: string; body: string; records: string[]; confirmed_by: string; confirmed_at: string; state: string; agent_drafts: string[] }>;
  assignments: Assignment[];
  acceptance: Completion["rate"];
  completion: Completion;
  handoff: Handoff | null;
  agentMode: string;
  agentOutputs: AgentOutput[];
  tasks: Task[];
  alerts: Array<{ alert_id: string; target: string; due_at: string; at: string; to: string[]; message: string }>;
  audit: { seq: number; at: string; actor: string; actor_name: string; actor_role: string; action: string; event_code: string | null; detail: Record<string, unknown> }[];
  executor: Executor;
  answerHere: boolean;
  bpm: {
    executor: Executor;
    externalRunId: string | null;
    runId: string | null;
    state: string;
    waiting: Sc04Waiting[];
    center: { job: { job_id: string; at: string } | null; problem: string | null; package: string | null } | null;
    position: string[];
    visited: string[];
  } | null;
}

export interface Sc04Case {
  caseId: string;
  label: string;
}

export interface Sc04ScriptStep {
  index: number;
  code: string;
  at: string;
  actor: string;
  kind: "start" | "act" | "view" | "record" | "agent" | "clock";
  nodeId: string | null;
  label: string;
  event: string | null;
}
