/**
 * Rolling Plan 및 실행 과제 타입.
 *
 * 설계 원칙 (CLAUDE.md 1장 Target vs Forecast vs Plan):
 * **Target은 어떤 경우에도 바뀌지 않는다.** 실행 결과와 최신 가정은 Forecast에만 반영하고,
 * 둘의 차이는 잔여 Gap으로 계속 남긴다. 그래서 `ForecastRevision`에는 forecast만 있고
 * target이 없다 — 회차마다 target을 들고 있으면 언젠가 누군가 그 값을 고치게 된다.
 */

export type ActionStatus = "not-started" | "in-progress" | "at-risk" | "done";

export const ACTION_STATUS_LABEL: Record<ActionStatus, string> = {
  "not-started": "미착수",
  "in-progress": "진행 중",
  "at-risk": "지연 위험",
  done: "완료",
};

/**
 * 실행 과제 하나 (루프 4단계 Management Action 산출물).
 *
 * 담당·기한·목표 회수액이 없는 과제는 만들지 않는다 — 추적할 수 없는 과제는
 * 실행되지 않은 것과 같다.
 */
export interface ActionItem {
  id: string;
  title: string;
  owner: string;
  due: string;
  division: string;
  /** 목표 회수액(억원). */
  targetRecovery: number;
  /** 현재까지 확정된 회수액(억원). */
  realizedRecovery: number;
  status: ActionStatus;
  /**
   * 이 과제의 효과가 이미 현재 Forecast에 반영되어 있는가.
   *
   * 반영된 과제를 또 더하면 Gap이 이중으로 메워진 것처럼 보인다. 이 화면에서 가장
   * 틀리기 쉬운 지점이므로 과제마다 명시적으로 들고 간다.
   */
  reflectedInForecast: boolean;
  /** 연결된 Cockpit RiskSignal id. */
  sourceRiskId?: string;
}

/** Rolling 갱신 한 회차. */
export interface ForecastRevision {
  id: string;
  /** 회차 라벨 (예: "9월 Rolling"). */
  label: string;
  date: string;
  /** 갱신 후 영업이익 Forecast(억원). */
  forecast: number;
  /** 이번 회차에서 반영한 내용. */
  drivers: string[];
}

/** 분기별 영업이익. 마감된 분기의 forecast는 확정 실적이다. */
export interface QuarterPoint {
  quarter: string;
  target: number;
  forecast: number;
  /** 마감 완료 분기인가. */
  closed: boolean;
}

export interface RollingPlan {
  /** 확정 목표 영업이익(억원). 절대 바뀌지 않는다. */
  target: number;
  /** 최신 Forecast(억원). */
  forecast: number;
  /** 최신 갱신 시점 표시용. */
  updatedAt: string;
  quarters: QuarterPoint[];
  revisions: ForecastRevision[];
  actions: ActionItem[];
}
