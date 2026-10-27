/**
 * SC06 응답 모양 — 엔진 `app/sc06/domain.py`의 조회 서비스(구현명세 10장)를 그대로 옮긴 것이다. 금액은 **원 정수**이고
 * 미확인·미산정은 `null`이다(0이 아니다). 모든 조회 응답에 문맥(`ReadContext`)이 붙는다.
 */

export interface Person {
  account: string;
  userId: string | null;
  name: string;
  role: string | null;
}

export interface ReadContext {
  review_id: string;
  report_version: string;
  calculation_version: string;
  calculation_hash: string;
  as_of: string;
  data_status: "COMPLETE" | "INCOMPLETE";
  basis_version: string;
  /** 보고본 뒤에 생긴 새 산정 — 이 보고본 숫자는 그대로이고 영향받는 확인을 다시 해야 한다(X61-05) */
  newer_calculation: {
    calculation_version: string;
    reason: string | null;
    changed_tasks: string[];
    reconfirm: string[];
    totals: Totals;
    tasks: TaskEffect[];
  } | null;
}

export interface TaskEffect {
  task_id: string;
  expected_krw: number;
  actual_krw: number | null;
  variance_krw: number | null;
  calculation_status: "CONFIRMED" | "PENDING";
  months: number;
}

export interface TaskRow extends TaskEffect {
  name: string | null;
  completed_at: string | null;
  activity_judgment: "COMPLETION_CONFIRMED" | "REVIEWED" | "HOLD";
  judgment_id: string | null;
  performance: string;
  evidence_refs: string[];
  followup: string | null;
  focus: boolean;
}

export interface Totals {
  expected_krw: number;
  actual_krw: number | null;
  variance_krw: number | null;
  calculation_status: "CONFIRMED" | "PENDING";
  confirmed_subtotal: { tasks: string[]; expected_krw: number; actual_krw: number };
}

export interface Judgment {
  judgment_id: string;
  task_id: string | null;
  target: string;
  collection_label: string;
  collection_state: "COMPLETE" | "PARTIAL";
  missing: string | null;
  alternatives: string[];
  impact: string | null;
  decision: string | null;
  judged_by: Person | null;
  judged_at: string | null;
  owner: Person | null;
  due_at: string | null;
  evidence_id: string;
  judgment_state: "REVIEWABLE" | "HOLD";
  activity_state: string;
  hold_reasons: string[];
}

export interface AgentRun {
  run_id: string;
  at: string;
  input_scope: string;
  task: string;
  draft: string;
  candidate_cause: string | null;
  human: string | null;
  reviewed_by: Person | null;
  reviewed_at: string | null;
  links: string[];
  state: "HUMAN_REVIEWED" | "CANDIDATE";
  mode: "REPLAY" | "LIVE";
}

export interface CauseGroup {
  cause: string;
  label: string;
  count: number;
  actual_urgent_cost_krw: number | null;
  orders?: string[];
}

export interface Summary extends ReadContext {
  period: { start: string; end: string; label: string };
  data_close: string;
  report_date: string;
  scope: { plant: string; product: string; models: string; unit: string; display: string };
  tasks: TaskRow[];
  totals: Totals;
  judgments: Judgment[];
  agent: AgentRun[];
  cause_overview: CauseGroup[];
  batch: { batch_id: string; seed_id: string; sha256: string; problems: string[]; loaded_at: string };
  checks: Array<{ check_id: string; label: string; value: number | null }>;
}

export interface MonthEffect {
  effect_id: string;
  task_id: string;
  month: string;
  expected: number;
  qty: number | null;
  baseline_or_avoided: number | null;
  actual_cost: number | null;
  operating_cost: number;
  net: number | null;
  variance: number | null;
  urgent_count: number | null;
  status: "CONFIRMED" | "PENDING";
}

export interface Metric {
  metric_id: string;
  label: string;
  value: number | string | null;
  unit: string;
  unconfirmed?: number;
}

export interface Order {
  order_id: string;
  month: string;
  model_id: string;
  part_id: string;
  qty: number;
  urgent: boolean;
  freight: number | null;
  surcharge: number | null;
  urgent_cost: number | null;
  cause: string | null;
  ordered_at: string | null;
  approver: Person | null;
  approved_at: string | null;
  delivery_issue: number;
  quality_issue: number;
  evidence_id: string;
  held: boolean;
}

export interface Change {
  change_id: string;
  received_at: string | null;
  shared_at: string | null;
  confirmed_at: string | null;
  required_at: string | null;
  supply_at: string | null;
  cause: string;
  reason: string;
  evidence_id: string;
  share_minutes: number | null;
  confirm_minutes: number | null;
  supply_gap_minutes: number | null;
}

export interface Variance extends ReadContext {
  task_id: string;
  task: TaskEffect;
  cause_groups: CauseGroup[];
  cause_total: { count: number; actual_urgent_cost_krw: number | null };
  cause_reconciliation: { count_residual: number; cost_residual: number | null; problems: string[] };
  variance_krw: number | null;
  months: MonthEffect[];
  metrics: Metric[];
  limits: { share_minutes: number; confirm_minutes: number };
  order: Order | null;
  change: Change | null;
  evidence: string[];
  agent: AgentRun | null;
  urgent_orders: Array<{
    order_id: string;
    month: string;
    cause: string | null;
    urgent_cost: number | null;
    held: boolean;
    share_minutes: number | null;
    confirm_minutes: number | null;
    supply_gap_minutes: number | null;
  }>;
}

export interface Evidence extends ReadContext {
  evidence_id: string;
  kind: string;
  target: string;
  written_at: string | null;
  written_by: Person | null;
  body: string;
  checked_by: Person | null;
  checked_at: string | null;
  virtual: boolean;
}

export interface Estimation {
  krw: number | null;
  estimation_status: "CONFIRMED" | "NOT_ESTIMATED" | "NOT_APPLICABLE";
  note: string | null;
}

export interface Followup {
  followup_id: string;
  kind: string;
  links: string[];
  causes: string[];
  content: string;
  owner: Person | null;
  cooperation: Person[];
  state: string;
  registered_at: string | null;
  due_at: string | null;
  next_check_at: string | null;
  effect: Estimation;
  budget: Estimation;
  scope_check: string;
}

export interface ReportRecord {
  record_id: string;
  version: string;
  step: string;
  actor: Person | null;
  at: string | null;
  state: string;
  content: string;
  refs: string[];
}

export interface QuarterRow {
  period?: string;
  target: number;
  fc51_profit: number;
  fc51_effect: number;
  confirmed_effect: number | null;
  effect_diff: number | null;
  profit: number | null;
  vs_target: number | null;
}

export interface Report extends ReadContext {
  state: string;
  finalized_at: string | null;
  report_date: string;
  next_review: string;
  problems: string[];
  totals: Totals;
  focus: TaskEffect;
  conclusion: ReportRecord | null;
  note: ReportRecord | null;
  confirmations: ReportRecord[];
  followups: Followup[];
  proposal_evidence: { evidence_id: string; body: string; written_by: string; checked_by: string } | null;
  monitoring: { evidence_id: string; body: string; written_at: string | null } | null;
  judgment: Judgment | null;
  risk: { risk_id: string; state: string; source: string };
  quarter_profit: { months: QuarterRow[]; quarter: QuarterRow };
  annual: { official: string; annual: string; target: string; gap: string };
  agent: AgentRun | null;
}

/** 문서 머리 — 장면 6이 열렸는지·어느 보고본인지. 숫자는 조회 서비스로 받는다. */
export interface Sc06Meta {
  scene: "SC06";
  demoRunId: string;
  caseId: string;
  clock: string;
  reviewId: string;
  reportVersion: string;
  calculationVersion: string;
  reportState: string;
  sc05: { handoff_id: string; official: string; annual: string; target: string; gap: string };
  batch: { batch_id: string; seed_id: string; sha256: string; problems: string[] };
}
