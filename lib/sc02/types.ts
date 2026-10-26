/**
 * SC02 엔진 응답 모양 — `engine/app/sc02/view.py`. 금액·비율은 문자열 DECIMAL(원 단위)이다(API-22).
 * 화면은 단위만 바꾼다 — 계산하지 않는다.
 */

import type { DemoUser, FormField, ProcessTopology, Risk, Waiting } from "@/lib/sc01/types";

export type { DemoUser, FormField, ProcessTopology, Risk, Waiting };

export interface PeriodIncrease {
  from: string;
  to: string;
  purchase_qty: number | null;
  increase: string | null;
  computable: boolean;
  reasons: string[];
}

export interface PeriodPnl {
  label: string;
  kind: "month" | "quarter" | "remaining" | "year" | "next12";
  from: string;
  to: string;
  computable: boolean;
  reason?: string;
  revenue_f02?: string;
  fixed?: string;
  profit_f01?: string;
  profit_volume?: string;
  volume_effect?: string;
  cost_effect?: string;
  profit_combined?: string;
  total_change?: string;
  target_profit?: string | null;
  target_gap?: string | null;
  bridge_diff?: string;
}

export interface ModelPnl {
  model_id: string;
  computable: boolean;
  cm_f01?: string;
  volume_effect?: string;
  cost_effect?: string;
  cm_combined?: string;
}

export interface MonthlyRow {
  period: string;
  model_id: string;
  f01: number | null;
  f02: number | null;
  assumed: boolean;
  unit_cm: string | null;
  part_qty: number | null;
  volume: string | null;
  cost: string | null;
}

export interface Problem {
  code: string;
  field: string;
  message: string;
  action: string;
}

export interface Analysis {
  version_id: string;
  kind: string;
  part_id: string;
  old_price: string;
  new_price: string | null;
  effective_date: string;
  versions: Record<string, string>;
  rate: string | null;
  rate_risk: Risk | null;
  remaining: PeriodIncrease;
  next12: PeriodIncrease;
  amount_risk: Risk | null;
  risk: Risk | null;
  ceo_required: boolean | null;
  comparison: {
    base_version: string;
    from: string;
    to: string;
    base_increase: string;
    increase: string;
    reduction: string;
    price_effect: string;
    deferral_effect: string;
  } | null;
  problems: Problem[];
  computable: boolean;
  periods: PeriodPnl[];
  q3_models: ModelPnl[];
  next12_models: ModelPnl[];
  monthly: MonthlyRow[];
  assumptions: Record<string, string>;
}

export interface Run {
  run_id: string;
  seq: number;
  price_version_id: string;
  kind: "REQUEST" | "OFFER" | "NEGOTIATION" | "PROPOSAL" | "APPROVED";
  status: "SUCCEEDED" | "BLOCKED";
  input_hash: string;
  at: string;
  by: string;
  is_stale: boolean;
  result: Analysis;
}

export interface PriceVersion {
  version_id: string;
  kind: Run["kind"];
  old_price: string;
  new_price: string | null;
  effective_date: string;
  predecessor_id: string | null;
  created_at: string;
  run_id: string | null;
}

export interface RequestItem {
  part_id: string;
  unit: string;
  currency: string;
  tax_basis: string;
  old_price: string;
  requested_price: string;
  effective_date: string | null;
  reason: string;
}

export interface PriceRequest {
  request_id: string;
  revision: number;
  supplier_id: string;
  supplier_name: string;
  source_doc_id: string;
  source_text: string;
  received_at: string;
  received_by: string;
  status: string;
  verified_at: string | null;
  verified_by: string | null;
  opinion: string | null;
  items: RequestItem[];
  errors: { field: string; message: string }[];
  negotiation_due?: { due_at: string; history: { at: string; by: string; due_at: string; previous?: string; reason: string }[] };
}

export interface Report {
  reported_at: string;
  reported_by: string;
  participants: string;
  summary: string;
  need: string;
  negotiation_direction: string;
  conclusion: string;
}

export interface Negotiation {
  negotiation_id: string;
  revision: number;
  round_no: number;
  held_at: string;
  recorded_by: string;
  participants: string;
  outcome: "잠정합의" | "미합의";
  price: string | null;
  effective_date: string;
  unresolved: string;
  due_at: string | null;
  analysis_required: boolean;
}

export interface Proposal {
  proposal_key: string;
  revision: number;
  price_version_id: string;
  run_id: string;
  price: string;
  effective_date: string;
  reason: string;
  diff_reason: string;
  evidence_ids: string[];
  status: string;
  submitted_at: string;
  submitted_by: string;
  ceo_expected: boolean | null;
  previous: string | null;
  authority?: { amount: string; threshold: string; authority_version: string; required: boolean; at: string };
  final_step?: string;
  approved_at?: string;
}

export interface Decision {
  decision_id: string;
  proposal_key: string;
  step: "TEAM" | "EXEC" | "CEO";
  actor: string;
  decision: "승인" | "보완" | "반려" | "추가협상지시";
  comment: string;
  decided_at: string;
  authority_version: string;
  assignee?: string;
  due_at?: string;
}

export interface Instruction {
  instruction_id: string;
  proposal_key: string;
  by: string;
  step: string;
  reason: string;
  condition: string;
  assignee: string;
  due_at: string;
  at: string;
  status: string;
}

export interface CostModel {
  model_id: string;
  qty_per: string;
  outsource_before: string;
  part_before: string;
  rest: string;
  part_after: string;
  outsource_after: string;
}

export interface CostVersion {
  cost_version_id: string;
  parent_cost_version: string;
  approved_proposal: string;
  price_version_id: string;
  run_id: string;
  part_id: string;
  old_price: string;
  new_price: string;
  effective_from: string;
  models: CostModel[];
  registered_by: string;
  registered_at: string;
  status: "REGISTERED_FUTURE" | "EFFECTIVE";
}

export interface ReviewLink {
  issue_id: string;
  issue_type: "VOLUME" | "COST";
  latest_run_id: string;
  risk_status: string;
}

export interface Bundle {
  bundle_id: string;
  at: string;
  provisional: boolean;
  reason: string;
  hash: string;
  proposal: string | null;
  price_run: string;
  quantity_run: string;
  cost_version: string | null;
  evidence: string[];
  decisions: string[];
}

export interface Handoff {
  handoff_id: string;
  revision: number;
  review_id: string;
  selected_run: string;
  bundle_id: string;
  bundle_hash: string;
  assignee: string;
  requested_by: string;
  requested_at: string;
  due_at: string;
  note: string;
  provisional: boolean;
  status: "FINANCE_PENDING" | "HANDED_OFF";
  accepted_by: string | null;
  accepted_at: string | null;
  opinion: string | null;
  sc03_due_at: string | null;
}

export interface Sc02Task {
  task_id: string;
  type: string;
  node_id: string;
  assigned_to: string;
  assignedName: string | null;
  assigned_at: string;
  due_at: string;
  status: "ASSIGNED" | "COMPLETED";
  completed_at: string | null;
  reopens: string | null;
  overdue: boolean;
  history: { at: string; status: string; by: string; note: string | null }[];
}

export interface AgentOutput {
  output_id: string;
  kind: "AG21" | "AG22" | "AG24";
  run_id: string;
  status: "SUCCEEDED" | "FAILED";
  mode: string;
  created_at: string;
  draft: {
    summary: string;
    findings: { text: string; evidence_refs: string[] }[];
    questions: string[];
    draft_text: string;
  } | null;
  errors: string[];
  stale: boolean;
  adopted_by: string | null;
  adopted_at: string | null;
}

export interface Sc02Status {
  request: string | null;
  approval: string | null;
  cost: string | null;
  handoff: string | null;
  risk: "OPEN";
  forecast: "REVIEW_PENDING";
  scene: string;
  sceneCode: string;
}

export interface Sc02View {
  scene: "SC02";
  demoRunId: string;
  caseId: string;
  caseLabel: string;
  clock: string;
  step: string;
  scriptIndex: number;
  historical: boolean;
  status: Sc02Status;
  sc01: {
    demo_run_id: string;
    run_id: string;
    forecast: string;
    forecast_approval: string;
    handed_off_at: string;
    issue: { issue_id: string; risk: Risk | null; status: string; model_id: string; period: string; runs: string[] };
  };
  request: PriceRequest | null;
  report: Report | null;
  priceVersions: PriceVersion[];
  runs: Run[];
  negotiations: Negotiation[];
  proposals: Proposal[];
  decisions: Decision[];
  instruction: Instruction | null;
  costVersions: CostVersion[];
  issue: { issue_id: string; risk: Risk | null; status: string; history: { at: string; run_id: string; risk: Risk | null }[] } | null;
  review: { review_id: string; links: ReviewLink[]; bundles: Bundle[] };
  selectedRunId: string | null;
  selectedProvisional: boolean;
  handoff: Handoff | null;
  handoffHistory: Handoff[];
  handoffCheck: { conditions: Record<string, boolean>; met: boolean; reasons: string[] };
  evidence: string[];
  agentMode: string;
  agentOutputs: AgentOutput[];
  tasks: Sc02Task[];
  alerts: { alert_id: string; task_id: string; due_at: string; at: string; to: string[]; message: string }[];
  audit: {
    seq: number;
    at: string;
    actor: string;
    actor_name: string;
    actor_role: string;
    action: string;
    event_code: string | null;
    detail: Record<string, unknown>;
  }[];
  bpm: {
    executor: "embedded";
    runId: string;
    state: string;
    waiting: Waiting[];
    position: string[];
    visited: string[];
  } | null;
}

export interface Sc02Case {
  caseId: string;
  label: string;
}
