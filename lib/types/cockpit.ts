/**
 * Executive Cockpit 도메인 타입.
 *
 * 금액 단위는 전부 **억원**이다. 원 단위는 어디에도 쓰지 않는다.
 *
 * Target / Forecast 규칙 (CLAUDE.md 1장):
 * Target은 확정 후 임의로 변경하지 않는다. 실행 결과와 최신 가정은 Forecast에만 반영하고,
 * 둘의 차이(Gap)를 숨기지 않고 명시한다. 따라서 Gap은 저장하지 않고 항상 파생 계산한다.
 */

/** Target 대비 Forecast 한 쌍. Gap은 `gapOf()`로 파생한다. */
export interface TargetForecast {
  /** 확정 목표. 갱신하지 않는다. */
  target: number;
  /** 최신 전망. Rolling 방식으로 갱신된다. */
  forecast: number;
}

/** Forecast − Target. 음수면 목표 미달이다. */
export function gapOf({ target, forecast }: TargetForecast): number {
  return forecast - target;
}

/** 경영 작동모델 6단계 루프 (CLAUDE.md 2.2). */
export type ManagementStage =
  | "risk-sensing"
  | "operation-control"
  | "management-review"
  | "management-action"
  | "rolling-plan"
  | "management-evolution";

export const MANAGEMENT_STAGE_LABEL: Record<ManagementStage, string> = {
  "risk-sensing": "Risk Sensing",
  "operation-control": "Operation Control",
  "management-review": "Management Review",
  "management-action": "Management Action",
  "rolling-plan": "Rolling Plan Update",
  "management-evolution": "Management Evolution",
};

/**
 * 상태 등급. 전용 팔레트(--viz-status-*)를 쓰며 계열색과 섞지 않는다.
 * 색만으로 의미를 전달하지 않도록 항상 아이콘+라벨을 동반한다.
 */
export type Severity = "good" | "warning" | "serious" | "critical";

export const SEVERITY_LABEL: Record<Severity, string> = {
  good: "정상",
  warning: "주의",
  serious: "경고",
  critical: "심각",
};

/** 사업부 성격. 기존 사업과 신사업은 평가 지표 자체가 다르다. */
export type DivisionKind = "legacy" | "growth";

/** 운영 지표 하나. 재무가 아닌 선행/현장 지표. */
export interface OperatingMetric {
  id: string;
  label: string;
  value: number;
  /** 관리 목표치. */
  target: number;
  unit: "%" | "일" | "주";
  /** 값이 클수록 좋은 지표인가. 가동률=true, 리드타임=false. */
  higherIsBetter: boolean;
}

export interface Division {
  id: string;
  name: string;
  kind: DivisionKind;
  /** 카드 부제로 쓰는 한 줄 설명. */
  tagline: string;
  /** 전사 매출 대비 Target 비중(%). */
  revenueShare: number;
  revenue: TargetForecast;
  operatingProfit: TargetForecast;
  metrics: OperatingMetric[];
  /** 해당 사업부의 핵심 고민. */
  concerns: string[];
}

/**
 * 영업이익 Target → Forecast 브릿지(워터폴) 한 단계.
 *
 * `anchor`는 절대값 기둥(Target·Forecast), `delta`는 증감 요인이다.
 * delta 값의 합 = Forecast − Target 이어야 한다 (`assertBridgeBalances`가 검증).
 */
export interface BridgeStep {
  id: string;
  label: string;
  kind: "anchor" | "delta";
  /** anchor면 절대 금액, delta면 부호 있는 증감액(억원). */
  value: number;
  /** delta의 원인 분류. */
  driver?: "volume" | "price" | "cost" | "yield" | "action";
  /** 툴팁·표에 노출할 설명. */
  note?: string;
}

/**
 * 신호가 어디서 왔는가 (기획안 3.2의 두 경로).
 *
 * `observed` — 현재 실적에서 관측된 편차. 이미 일어난 사실이다.
 * `leading`  — 아직 실적에 충분히 나타나지 않은 선행 위험. 예측·가정이 섞여 있다.
 *
 * **둘을 구분하지 않으면 확정된 사실과 가정을 같은 무게로 읽게 된다.** 기획안 3.2가
 * "현재 실적의 편차와 미래 위험을 함께 보되, 관측된 사실과 예측·가정을 구분한다"고
 * 못 박은 이유다.
 */
export type SignalOrigin = "observed" | "leading";

export const SIGNAL_ORIGIN_LABEL: Record<SignalOrigin, string> = {
  observed: "관측된 사실",
  leading: "선행 위험",
};

/** 감지된 리스크 신호 하나 (루프 1단계 Risk Sensing 산출물). */
export interface RiskSignal {
  id: string;
  title: string;
  detail: string;
  severity: Severity;
  /** 소속 사업부명. 전사 공통이면 "전사". */
  division: string;
  kri: {
    label: string;
    /** 현재값. 단위를 포함한 표시용 문자열. */
    value: string;
    /** 감지 임계치. 단위를 포함한 표시용 문자열. */
    threshold: string;
  };
  /** 이 신호가 현재 올라가 있는 루프 단계. */
  stage: ManagementStage;
  owner: string;
  origin: SignalOrigin;
  /**
   * `leading`인 신호가 딛고 선 가정. 이 가정이 틀리면 위험 자체가 성립하지 않는다.
   *
   * `observed`에는 두지 않는다 — 관측된 사실에 가정을 붙이면 사실이 흐려진다.
   */
  assumption?: string;
}

export interface CompanySnapshot {
  name: string;
  englishName: string;
  /** 회계 기준 시점 표시용 (예: "FY2026 · 9월 마감 기준"). */
  period: string;
  revenue: TargetForecast;
  operatingProfit: TargetForecast;
  /** 확정된 Management Action의 목표 회수액 합계(억원). */
  committedActionRecovery: number;
  divisions: Division[];
  bridge: BridgeStep[];
  risks: RiskSignal[];
}

/** 영업이익률(%) — 반올림 전 원값. */
export function marginOf(revenue: number, operatingProfit: number): number {
  return (operatingProfit / revenue) * 100;
}

/**
 * 브릿지 정합성 검증: delta 합이 anchor 양 끝의 차이와 일치하는지 본다.
 *
 * 워터폴은 숫자가 하나만 틀려도 "합계가 안 맞는 차트"가 되어 경영 보고에서 신뢰를 잃는다.
 * mock 데이터를 손으로 수정하다 깨지는 경우가 실제로 잦으므로 개발 중 즉시 터지게 둔다.
 */
export function assertBridgeBalances(bridge: BridgeStep[]): void {
  const anchors = bridge.filter((s) => s.kind === "anchor");
  if (anchors.length !== 2) {
    throw new Error(`브릿지 anchor는 시작·종료 2개여야 한다 (현재 ${anchors.length}개)`);
  }
  const [start, end] = anchors;
  const deltaSum = bridge
    .filter((s) => s.kind === "delta")
    .reduce((sum, s) => sum + s.value, 0);
  const expected = end.value - start.value;
  if (Math.abs(deltaSum - expected) > 0.001) {
    throw new Error(
      `브릿지 불일치: delta 합 ${deltaSum}, anchor 차이 ${expected} (${start.label}→${end.label})`,
    );
  }
}
