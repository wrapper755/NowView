/**
 * Management Framework — Value Driver · KPI · KRI · Control의 연결.
 *
 * 기획안 1.1: Framework는 "무엇을 보고 어떻게 판단할지에 대한 공통 기준"을 제공한다.
 * 그 공통 기준이 이 연결이다:
 *
 *   Value Driver (성과를 만드는 동인)
 *     └ KPI  결과 지표 — 이미 일어난 일을 잰다 (후행)
 *         └ KRI  위험 지표 — 아직 결과에 다 나타나지 않은 위험을 잰다 (선행)
 *             └ Control  통제 활동 — 그 위험을 예방·탐지·시정한다
 *
 * **KPI와 KRI를 같은 것으로 취급하지 않는다.** 가동률 82.1%는 결과(KPI)이면서 동시에
 * 임계치를 건 감지 신호(KRI)로도 쓰이지만, 전자는 "얼마나 나빠졌나"를, 후자는
 * "언제 손을 대야 하나"를 답한다. 임계치는 KRI에만 있다.
 */

/** 통제의 성격. 셋을 구분해야 "무엇이 비어 있는지"가 보인다. */
export type ControlKind = "preventive" | "detective" | "corrective";

export const CONTROL_KIND_LABEL: Record<ControlKind, string> = {
  preventive: "예방",
  detective: "탐지",
  corrective: "시정",
};

/** 통제 수행 상태. */
export type ControlStatus = "effective" | "exception" | "not-run";

export const CONTROL_STATUS_LABEL: Record<ControlStatus, string> = {
  effective: "정상 수행",
  exception: "예외 발생",
  "not-run": "미수행",
};

export interface Control {
  id: string;
  name: string;
  kind: ControlKind;
  owner: string;
  /** 수행 주기 (매일·주간·월간 등). */
  frequency: string;
  status: ControlStatus;
  /** 예외·미수행이면 그 사유. 상태만 있고 이유가 없으면 조치할 수 없다. */
  note?: string;
}

export interface ValueDriver {
  id: string;
  name: string;
  /** 이 동인이 손익에 닿는 경로. */
  description: string;
}

/** 결과 지표(후행). 임계치를 두지 않는다 — 감지는 KRI의 일이다. */
export interface Kpi {
  id: string;
  driverId: string;
  label: string;
  unit: string;
  current: number;
  target: number;
  /** 값이 클수록 좋은 지표인가. */
  higherIsBetter: boolean;
}

/** 위험 지표(선행). 임계치와 통제가 붙는다. */
export interface Kri {
  id: string;
  kpiId: string;
  label: string;
  unit: string;
  current: number;
  threshold: number;
  /**
   * 임계치 **미만**일 때 이탈인가 (가동률·수율).
   * false면 임계치 **초과**가 이탈이다 (리드타임·단가 상승률).
   */
  breachBelow: boolean;
  /** 연결된 Cockpit `RiskSignal.id`. 같은 사건을 Framework 관점으로 본 것이다. */
  riskId: string;
  controlIds: string[];
}

export interface ManagementFramework {
  drivers: ValueDriver[];
  kpis: Kpi[];
  kris: Kri[];
  controls: Control[];
}

/** 임계치 이탈 여부. 방향은 `breachBelow`가 정한다. */
export function isBreached(kri: Kri): boolean {
  return kri.breachBelow ? kri.current < kri.threshold : kri.current > kri.threshold;
}
