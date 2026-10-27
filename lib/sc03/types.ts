/**
 * SC03 엔진 응답 — `engine/app/sc03/view.py`의 모양 그대로. 금액·비율은 원 단위 DECIMAL 문자열이다(화면은 단위만 바꾼다).
 */

import type { Executor, FormField } from "@/lib/sc01/types";

export interface Sc03Waiting {
  nodeId: string;
  title: string;
  role: string | null;
  /** 이 결재의 담당 — 인수는 과제 책임자다. */
  assignee: string | null;
  review: Record<string, unknown>;
  fields: FormField[];
  taskId: string | null;
}

export interface Check {
  check_id: string;
  label: string;
  diff: string;
  ok: boolean;
}

export interface ModelPnl {
  model_id: string;
  computable: boolean;
  f01_qty?: number;
  f02_qty?: number;
  cm_f01?: string;
  volume_effect?: string;
  cost_effect?: string;
  cm_combined?: string;
}

export interface Period {
  kind: "year" | "q3" | "remaining" | "next12" | "month";
  label: string;
  from: string;
  to: string;
  computable: boolean;
  reason?: string;
  fixed?: string;
  fixed_applied?: string;
  /** 2028 Target은 미설정 — 향후 12개월이면 null(0이 아니다). */
  target?: string | null;
  f01?: string;
  volume_profit?: string;
  volume_effect?: string;
  cost_effect?: string;
  event_effect?: string;
  combined?: string;
  existing_gap?: string | null;
  total_gap?: string | null;
  models?: ModelPnl[];
  checks?: Check[];
}

export interface AnalysisRun {
  run_id: string;
  seq: number;
  created_at: string;
  created_by: string;
  memo: string;
  sources: string[];
  status: "CALCULATED" | "CALCULATION_BLOCKED";
  variant?: string;
  result: {
    basis: Record<string, string | null>;
    fixed_multiplier: number;
    status: string;
    passed: boolean;
    failed_checks: string[];
    periods: Record<"year" | "q3" | "remaining" | "next12", Period>;
    months: Period[];
    purchase: { remaining_increase: string | null; remaining_qty: number | null; next12_increase: string | null; next12_qty: number | null };
    b_july: { f01: number; f02: number; unit_cm: string } | null;
    assumptions: string[];
  };
}

export interface Report {
  report_id: string;
  seq: number;
  kind: "DRAFT" | "FROZEN";
  status: string;
  run_id: string;
  created_at: string;
  created_by: string;
  basis_text: string;
  kpis: Record<string, string | null>;
  previous?: string | null;
  change_summary?: string;
  affects?: string[];
  frozen_by?: string;
  frozen_at?: string;
  opinion?: string;
  source_hash?: string;
  distributed_at?: string | null;
}

export interface Fact {
  fact_id: string;
  dept: string;
  category: "FACT" | "ASSUMPTION" | "UNCONFIRMED";
  statement: string;
  evidence_ref: string;
  reviewer: string;
  confirmed_at: string;
  state: string;
  report_id: string;
  followup_ref: string | null;
}

export interface Question {
  question_id: string;
  kind: "FOLLOWUP" | "DISPUTE";
  fact_ref: string;
  question: string;
  blocking: boolean | null;
  owner: string;
  due_at: string | null;
  decision_by: string | null;
  decided_at: string | null;
  treatment: string | null;
  state: string;
}

export interface DeptStatus {
  dept: string;
  label: string;
  user: string;
  state: "PENDING" | "RESPONDED" | "DISPUTED" | "STALE";
  reply: { reply: string; by: string; at: string; report_id: string; facts: string[]; opinion: string } | null;
}

export interface MeetingRecord {
  record_id: string;
  record_type: string;
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
  agenda: string;
  chair: string;
  scheduled_at: string;
  report_version: string | null;
  state: string;
  opened_at?: string | null;
  attendance: { record_id: string; actor: string; state: string; at: string }[];
  records: MeetingRecord[];
}

export interface Candidate {
  candidate_id: string;
  dept: string;
  candidate: string;
  mechanism: string;
  constraints: string;
  evidence_ref: string;
  effect_2027: string | null;
  effect_12m: string | null;
  decision: "INCLUDE" | "EXCLUDE_THIS_REVIEW" | null;
  decision_reason: string | null;
  decided_by: string | null;
  decided_at: string | null;
  task_id: string | null;
}

export interface Assignment {
  task_id: string;
  candidate_refs: string[];
  title: string;
  owner: string | null;
  collaborators: string[];
  question: string;
  deliverable: string;
  dependency: string;
  due_at: string | null;
  basis: string;
  effect_2027: string | null;
  effect_12m: string | null;
  assignment_version: number;
  state: "DRAFT" | "ASSIGNED" | "RETURNED" | "ACCEPTED";
  assigned_at: string | null;
  accept_due?: string;
  accepted_at: string | null;
  accepted_version: number | null;
  return_reason?: string;
  submitted_at: string | null;
  history: { at: string; state: string; by: string; note: string | null; version?: number }[];
}

export interface Sc03View {
  scene: "SC03";
  demoRunId: string;
  caseId: string;
  caseLabel: string;
  clock: string;
  step: string;
  scriptIndex: number;
  historical: boolean;
  status: { review: string; outcome: string | null; risk: string; forecast: string; target: string; scene: string };
  sc02: {
    handoff: Record<string, string | null>;
    price: { version_id: string; old_price: string; new_price: string; effective_date: string; run_id: string; part_id: string };
    request_price: string | null;
    cost: { cost_version_id: string; parent_cost_version: string; effective_from: string; registered_at: string };
    issues: { issue_id: string; type: "VOLUME" | "COST"; risk: string; status: string; run_id: string; summary: string }[];
    sc01_run: string;
    forecast_approval: string;
  };
  review: { review_id: string; state: string; outcome: string | null; started_at: string | null; started_by: string | null; completed_at: string | null };
  schedule: Record<string, string>;
  runs: AnalysisRun[];
  latestRunId: string | null;
  reports: Report[];
  currentDraftId: string | null;
  frozenReportId: string | null;
  confirmation: { report_id: string; due_at: string; requested_at: string; requested_by: string; memo: string } | null;
  departments: DeptStatus[];
  facts: Fact[];
  questions: Question[];
  freezeProblems: string[];
  meetings: Meeting[];
  candidates: Candidate[];
  decision: { decision_id: string; outcome: string; content: string; conditions: string; open_questions: string[]; decided_by: string; decided_at: string } | null;
  minutes: { minutes_id: string; included: string[]; excluded: { candidate_id: string; reason: string }[]; open_questions: string[]; tasks: string[]; confirmed_by: string; confirmed_at: string; opinion: string; next_meeting: string }[];
  assignments: Assignment[];
  acceptance: { assigned: number; accepted: number; rate: string | null };
  delayed: string[];
  completion: { items: { id: string; label: string; ok: boolean }[]; met: boolean; blocking: string[] };
  revisions: { report_id: string; run_id: string; base_report: string; status: string; reason: string; changes: { kind: string; label: string; before: string; after: string; diff: string }[]; created_at: string }[];
  handoff: Record<string, unknown> | null;
  agentMode: string;
  agentOutputs: {
    output_id: string;
    kind: "AG30" | "AG31";
    status: "SUCCEEDED" | "FAILED";
    created_at: string;
    source_version: string | null;
    prompt_version: string;
    draft: { summary: string; findings: { text: string; evidence_refs: string[] }[]; questions: string[]; draft_text: string } | null;
    errors: string[];
    adopted_by: string | null;
    adopted_at: string | null;
    review_status: string;
  }[];
  tasks: { task_id: string; type: string; node_id: string; assigned_to: string; assignedName: string | null; due_at: string; status: string; overdue: boolean; opened_late?: boolean }[];
  alerts: { alert_id: string; target: string; due_at: string; at: string; to: string[]; message: string }[];
  audit: { seq: number; at: string; actor: string; actor_name: string; actor_role: string; action: string; event_code: string | null; detail: Record<string, unknown> }[];
  executor: Executor;
  answerHere: boolean;
  bpm: {
    executor: Executor;
    externalRunId: string | null;
    runId: string | null;
    state: string;
    waiting: Sc03Waiting[];
    center: { job: { job_id: string } | null; problem: string | null; package: string | null } | null;
    position: string[];
    visited: string[];
  } | null;
}

export interface Sc03Case {
  caseId: string;
  label: string;
}

export interface Sc03ScriptStep {
  index: number;
  code: string;
  at: string;
  actor: string;
  kind: "start" | "act" | "view" | "record" | "agent" | "revision" | "clock";
  nodeId: string | null;
  label: string;
  event: string | null;
}
