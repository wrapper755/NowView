import type { CompanyExchange, FormField as FormFieldSpec } from "@/lib/sc01/types";

/**
 * SC07 응답 모양 — 엔진 `app/sc07/domain.py`의 조회 서비스(구현명세 6장)를 그대로 옮긴 것이다. 모든 조회 응답에 문맥
 * (`ReadContext`: 데이터 버전·개선건·버전 묶음·기준시각)이 붙는다. 시각은 KST ISO8601이고 없으면 `null`이다(0분·정상이 아니다).
 */

export interface Person {
  account: string;
  userId: string | null;
  name: string;
  role: string | null;
}

export interface ReadContext {
  dataset_version: string;
  improvement_id: string;
  version_bundle: { agent: string; measure: string; projection: string; verification_set: string };
  as_of: string;
  fictional: boolean;
}

export type Cause = "SUPPLY" | "INTERNAL" | "MIXED" | "NEED_EVIDENCE" | "NO_CONSTRAINT";
export type Status3 = "OVER" | "WITHIN" | "UNKNOWN";

export interface MissingField {
  field: string;
  label: string;
  reason: "MISSING" | "ACCESS_DENIED" | "NOT_JOINED" | "INVALID_DELEGATION" | "NOT_CONFIRMED";
  reason_label: string;
  owner: string;
}

/** 규칙 계산 한 건(`calc.assess`) + 개선 Agent 출력 모양(`domain.agent_output`) */
export interface AgentOutput {
  input_id: string;
  confirmed_at: string | null;
  confirmed_by: "PRIMARY" | "DEPUTY" | null;
  elapsed_minutes: number | null;
  deadline_status: Status3;
  cutoff_status: Status3;
  supply_status: Status3;
  supply_gap_minutes: number | null;
  candidate_cause: Cause | null;
  candidate_label: string;
  data_status: "COMPLETE" | "INCOMPLETE" | "DATA_INVALID";
  missing_fields: MissingField[];
  internal_review: boolean;
  threshold_min: number;
  facts: Array<{ text: string; evidence_refs: string[] }>;
  evidence_refs: string[];
  next_action: string;
  agent_version: string;
  projection_version: string;
  execution_mode: string;
  payload?: Record<string, unknown>;
}

export interface ImprovementItem {
  item_id: string;
  target: string;
  before: string;
  after: string;
  scope: string;
}

export interface Improvement extends ReadContext {
  execution_mode: string;
  improvement: {
    improvement_id: string;
    proposed_on: string | null;
    source: string;
    main: ImprovementItem | null;
    framework: ImprovementItem | null;
    process: ImprovementItem | null;
    application: ImprovementItem | null;
    excluded: ImprovementItem | null;
    rules: Array<{ rule_id: string; content: string; version: string; guard: string }>;
    versions: Array<{ id: string; kind: string; value: string; previous: string; note: string }>;
  };
  source: {
    report_version: string;
    report_state: string;
    order: { order_id: string; cost_krw: number; approved_by: string | null };
    change: { change_id: string; order_id: string; shared_at: string; required_at: string; supply_at: string; cause: string };
    evidence_id: string;
  };
  before: {
    agent: {
      run_id: string;
      at: string;
      input_scope: string;
      task: string;
      draft: string;
      human: string | null;
      reviewed_by: string | null;
      reviewed_at: string | null;
      state: string;
      mode: string;
    };
    agent_version: string;
    projection_version: string;
    payload: Record<string, unknown>;
    evidence_id: string;
  };
  after: AgentOutput & { payload: Record<string, unknown> };
}

export interface VerificationCase {
  check: string;
  title: string;
  input_ref: string;
  expected: string;
  observed: string | null;
  status: "PASS" | "FAIL" | "NOT_RUN";
  simulated: string;
  simulated_status: string;
  simulated_mode: string;
  fixture: boolean;
  evidence_refs: string[];
  detail: Record<string, unknown> | null;
  simulated_run_id: null;
}

export interface Verification extends ReadContext {
  execution_mode: string | null;
  run: { run_id: string; executed_at: string; executed_by: string; agent_version: string; passed: boolean } | null;
  summary: { total: number; passed: number; not_run: number; state: "NOT_RUN" | "PASSED" | "NEEDS_WORK" };
  representative: {
    check: string;
    input: Record<string, unknown> & { input_id: string; evidence_refs: string[] };
    output: AgentOutput | null;
    human: string | null;
    human_by: Person | null;
  };
  cases: VerificationCase[];
}

export interface StateCheck {
  key: string;
  ok: boolean;
  label: string;
  detail: string;
}

export interface ApplicationState {
  state: "ST703" | "ST704" | "ST705" | "ST706" | "ST707";
  label: string;
  checks: StateCheck[];
  attention: string[];
  verification_passed: boolean;
  confirmed: boolean;
  setting_reflected: boolean;
  execution_status: "NOT_CONFIRMED" | string;
  operation_run_id: string | null;
  reserved_only: boolean;
}

export interface Confirmation {
  record_id: string;
  actor: Person | null;
  version: string | null;
  state: "CONFIRMED" | "REWORK_REQUESTED" | "PENDING";
  at: string | null;
  content: string | null;
}

export interface Application extends ReadContext {
  application_id: string;
  scope: string;
  scope_detail: string;
  target_version: string;
  previous_version: string;
  snapshot: {
    snapshot_id: string;
    previous_version: string;
    active_version: string;
    scope: string;
    evidence_type: string;
    applied_at: string;
    applied_by: Person | null;
    content: string;
    checked_at: string | null;
    checked_by: Person | null;
    check_result: "MATCH" | "MISMATCH" | null;
    check_note: string | null;
  } | null;
  confirmations: Confirmation[];
  state: ApplicationState;
  execution: { status: string; operation_run_id: string | null; next_run_at: string | null };
  follow_up: {
    owner: Person | null;
    planned_at: string;
    items: string;
    state: string;
    measured: boolean;
  } | null;
  rollback: { previous_version: string; note: string };
}

export interface EvidenceView extends ReadContext {
  source: "SC07근거" | "SC06근거";
  status: string;
  evidence: Record<string, unknown> & { evidence_id: string };
}

export interface Sc07Waiting {
  nodeId: string;
  title: string;
  role: string | null;
  assignee: string | null;
  review: Record<string, unknown>;
  fields: FormFieldSpec[];
  taskId: string | null;
}

/** 확인·적용 절차의 한 단계 — 결재 · 남길 기록 · 담당 · 데이터 일정. 기록은 끝난 것만 온다. */
export interface ProcedureStep {
  nodeId: string;
  recordId: string;
  role: string;
  assignee: string;
  assigneeName: string;
  plannedAt: string | null;
  record: {
    record_id: string;
    actor: Person | null;
    at: string;
    state?: string;
    content?: string;
    version?: string;
    result?: string;
    evidence_type?: string;
  } | null;
}

export interface SettingRecord {
  snapshot_id: string;
  previous_version: string;
  active_version: string;
  scope: string;
  evidence_type: string;
  applied_at: string;
  applied_by: string;
  content: string;
  checked_at: string | null;
  checked_by: string | null;
  check_result: "MATCH" | "MISMATCH" | null;
  check_note: string | null;
}

export type Sc07Executor = "embedded" | "studio" | "center";

export interface Sc07Status {
  procedure: "PENDING" | "CONFIRMING" | "NEEDS_WORK" | "APPLIED";
  verification: "NOT_RUN" | "PASSED" | "FAILED";
  application: ApplicationState["state"];
  applicationLabel: string;
  execution: string;
  confirmed: string[];
  followUp: string | null;
}

export interface Sc07Meta {
  scene: "SC07";
  demoRunId: string;
  caseId: string;
  clock: string;
  step: string | null;
  scriptIndex: number;
  historical: boolean;
  improvementId: string;
  applicationId: string;
  datasetVersion: string;
  versionBundle: Record<string, string>;
  sc06: { report_version: string; report_state: string };
  batch: { batch_id: string; seed_id: string; sha256: string; dataset_version: string };
  status: Sc07Status;
  companyLog?: CompanyExchange[];
  executor: Sc07Executor | null;
  answerHere: boolean;
  procedure: {
    startedAt: string | null;
    verification: { run_id: string; executed_at: string; agent_version: string; set: string; passed: boolean; failed: string[]; total: number } | null;
    steps: ProcedureStep[];
    /** 설정 반영 기록 — 계정(USR-OPS71 …)으로 적힌다. 화면에 사람 이름은 조회(`Application`)로 받는다. */
    setting: SettingRecord | null;
    followUp: { owner: string; planned_at: string; items: string; state: string } | null;
    plan: { target_version: string; scope: string; snapshot_id: string; next_run_at: string | null };
    history: Array<Record<string, unknown> & { record_id?: string; retired?: string }>;
    lastRejection: { node_id: string; status: number; reason: string; blocking_items?: string[] | null } | null;
  };
  tasks?: Array<{
    task_id: string;
    node_id: string;
    assigned_to: string;
    assignedName: string | null;
    status: "ASSIGNED" | "COMPLETED";
    completed_at: string | null;
    opened_late: boolean;
  }>;
  bpm: {
    executor: Sc07Executor;
    externalRunId: string | null;
    runId: string | null;
    state: string;
    waiting: Sc07Waiting[];
    center: { job: { job_id: string; at: string } | null; problem: string | null; package: string | null } | null;
    position: string[];
    visited: string[];
  } | null;
}

export interface Sc07ScriptStep {
  index: number;
  code: string;
  actor: string;
  kind: "start" | "act";
  nodeId: string | null;
  label: string;
  record: string | null;
}
