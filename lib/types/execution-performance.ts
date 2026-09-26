/**
 * 경영 수행 성과 — 경영 활동 자체의 속도·정확성·실행력.
 *
 * 기획안 2.3은 성과를 **두 관점**으로 나눈다:
 *   · 사업 성과      — 수익성·손익, 납기, 품질, 재고 (Cockpit의 나머지 전부)
 *   · 경영 수행 성과 — 문제 인지 시간, 분석·의사결정 소요시간, 과제 이행률, 효과 검증 여부
 *
 * 둘을 섞으면 "손익은 나빠졌지만 대응은 빨라졌다" 같은 판단을 할 수 없다. 전자는 결과이고
 * 후자는 그 결과를 만드는 경영 활동의 품질이다.
 */

/** 기획안 2.3의 "속도·정확성·실행력"을 그대로 축으로 쓴다. */
export type ExecutionCategory = "speed" | "accuracy" | "execution";

export const EXECUTION_CATEGORY_LABEL: Record<ExecutionCategory, string> = {
  speed: "속도",
  accuracy: "정확성",
  execution: "실행력",
};

/**
 * 값의 출처.
 *
 * 기획안 2.3: "시나리오에서 설정한 결과와 시스템 실행으로 확인한 결과를 구분한다."
 * 데모에서 이 구분이 없으면 어디까지가 실제로 돌아간 것이고 어디부터가 설정값인지
 * 알 수 없다. 화면에서 배지로 구분해 표시한다.
 *
 * **`system`과 `measured`를 나눈 이유.** 둘 다 코드가 계산한 값이지만 근거가 다르다 —
 * `system`은 Mock 데이터에서 계산한 것이고, `measured`는 BPM 엔진이 실제로 실행하며
 * 잰 것이다(예: Agent 소요시간은 ollama가 돌려준 실제 경과 시간이다). 이 둘을 같은
 * 배지로 묶으면 "시스템 산출값"이 실측을 뜻하는지 Mock 계산을 뜻하는지 알 수 없어,
 * 기획안이 요구한 구분이 이름만 남는다.
 */
export type Provenance = "scenario" | "system" | "measured";

export const PROVENANCE_LABEL: Record<Provenance, string> = {
  scenario: "시나리오 설정값",
  system: "시스템 산출값",
  measured: "엔진 실측값",
};

export interface ExecutionMetric {
  id: string;
  category: ExecutionCategory;
  label: string;
  /** 이번 경영주기 값. */
  current: number;
  /**
   * 직전 경영주기 값.
   *
   * 경영 수행 성과는 절대 수준보다 **개선 여부**가 핵심이다(기획안 2.3의 "개선").
   * 비교 대상이 없으면 3.0일이 좋은지 나쁜지 말할 수 없다.
   */
  previous: number;
  /** 관리 목표. 없을 수도 있다. */
  target?: number;
  unit: string;
  /** 값이 클수록 좋은 지표인가. 소요시간·오탐은 false다. */
  higherIsBetter: boolean;
  /** 이번 주기 값의 출처. */
  provenance: Provenance;
  /** 무엇을 재는 지표인지. 정의 없는 지표는 해석이 갈린다. */
  definition: string;
}

/** 직전 주기 대비 개선량. 부호는 "좋아진 쪽이 양수"가 되도록 방향을 맞춘다. */
export function improvementOf(metric: ExecutionMetric): number {
  const delta = metric.current - metric.previous;
  return metric.higherIsBetter ? delta : -delta;
}

/** 목표 대비 달성 여부. 목표가 없으면 판단하지 않는다. */
export function meetsTarget(metric: ExecutionMetric): boolean | undefined {
  if (metric.target === undefined) return undefined;
  return metric.higherIsBetter
    ? metric.current >= metric.target
    : metric.current <= metric.target;
}
