/**
 * Management Evolution 계산 (루프 6단계).
 *
 * 백테스트는 표 조회다 — 임계치별 결과를 값으로 들고 있고 여기서는 찾아 주기만 한다.
 * 표에 없는 임계치를 보간해서 만들어내지 않는다. 없는 근거를 지어내는 셈이기 때문이다.
 */

import { falsePositiveSeverity, type BacktestPoint, type KriTuning } from "@/lib/types/evolution";
import type { Severity } from "@/lib/types/cockpit";

export interface TuningOutcome extends BacktestPoint {
  /** 오탐 비율(%) — 전체 알림 중 헛울림의 비중. */
  falsePositiveRate: number;
  severity: Severity;
  /** 현행 임계치 대비 감지 건수 증감. */
  detectionDelta: number;
  /** 현행 임계치 대비 오탐 증감. */
  falsePositiveDelta: number;
  /** 현행 임계치인가. */
  isCurrent: boolean;
  /** Agent 권고 임계치인가. */
  isRecommended: boolean;
}

/** 표에서 해당 임계치의 결과를 찾는다. 없으면 가장 가까운 값으로 떨어뜨린다. */
function pointAt(kri: KriTuning, threshold: number): BacktestPoint {
  const exact = kri.backtest.find((p) => p.threshold === threshold);
  if (exact) return exact;

  return kri.backtest.reduce((closest, p) =>
    Math.abs(p.threshold - threshold) < Math.abs(closest.threshold - threshold) ? p : closest,
  );
}

export function tuningOutcome(kri: KriTuning, threshold: number): TuningOutcome {
  const point = pointAt(kri, threshold);
  const current = pointAt(kri, kri.currentThreshold);
  const total = point.detections + point.falsePositives;
  const falsePositiveRate = total === 0 ? 0 : (point.falsePositives / total) * 100;

  return {
    ...point,
    falsePositiveRate,
    severity: falsePositiveSeverity(falsePositiveRate),
    detectionDelta: point.detections - current.detections,
    falsePositiveDelta: point.falsePositives - current.falsePositives,
    isCurrent: point.threshold === kri.currentThreshold,
    isRecommended: point.threshold === kri.recommendedThreshold,
  };
}

/** 슬라이더 범위 — 백테스트가 있는 구간으로 제한한다. */
export function tuningRange(kri: KriTuning): { min: number; max: number } {
  const thresholds = kri.backtest.map((p) => p.threshold);
  return { min: Math.min(...thresholds), max: Math.max(...thresholds) };
}

/**
 * 조기 감지일 표기.
 *
 * 음수는 "현행보다 늦게 감지"라는 뜻이므로 부호를 숨기지 않는다 — 임계치를 낮추면
 * 감지가 늦어진다는 사실이 보여야 트레이드오프가 성립한다.
 */
export function formatLeadTime(days: number): string {
  if (days === 0) return "현행과 동일";
  return days > 0 ? `${days}일 조기 감지` : `${Math.abs(days)}일 지연 감지`;
}
