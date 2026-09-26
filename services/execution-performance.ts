/**
 * 경영 수행 성과 산출.
 *
 * **일곱 지표 중 넷은 실제 데이터에서 계산한다.** Agent 실행 기록, 실행 과제, 백테스트가
 * 이미 시스템 안에 있으므로 그 값을 다시 적어 넣을 이유가 없다 — 적어 넣으면 원본이
 * 바뀔 때 조용히 어긋난다. 나머지 셋은 시스템이 관측할 수 없는 값(사람의 결재 소요시간
 * 등)이라 시나리오 설정값이며, 화면에서 출처를 구분해 표시한다(기획안 2.3).
 */

import { evolutionLab } from "@/lib/mock-data/evolution-lab";
import { executionBaseline } from "@/lib/mock-data/execution-performance";
import { bpmProcess } from "@/lib/mock-data/bpm-process";
import { rollingPlan } from "@/lib/mock-data/rolling-plan";
import type { ExecutionMetric } from "@/lib/types/execution-performance";
import { tuningOutcome } from "@/services/evolution-lab";

/**
 * "4분 12초" 같은 표시용 문자열을 분 단위로 바꾼다.
 *
 * Agent 실행 기록이 사람이 읽는 형식으로만 저장돼 있어 파싱이 필요하다. 형식을 못 읽으면
 * 0으로 넘기지 않고 throw한다 — 조용히 0이 되면 소요시간이 실제보다 짧게 보인다.
 */
export function parseDurationMinutes(text: string): number {
  const match = text.match(/^(?:(\d+)시간\s*)?(?:(\d+)분\s*)?(?:(\d+)초)?$/);
  if (!match || (!match[1] && !match[2] && !match[3])) {
    throw new Error(`소요시간 형식을 읽을 수 없다: ${text}`);
  }
  const [, h, m, s] = match;
  return Number(h ?? 0) * 60 + Number(m ?? 0) + Number(s ?? 0) / 60;
}

/** Agent 실행 기록 전체의 소요시간 합(시간 단위). */
export function totalAgentHours(): number {
  const minutes = bpmProcess.runs.reduce(
    (sum, run) => sum + parseDurationMinutes(run.duration),
    0,
  );
  return minutes / 60;
}

/**
 * 과제 이행률(%).
 *
 * 분모는 **Forecast에 이미 반영된 과제**다. 승인 직후 과제는 아직 착수 기한도 오지
 * 않았으므로 이행 여부를 물을 수 없다.
 */
export function actionOnTimeRate(): number {
  const tracked = rollingPlan.actions.filter((a) => a.reflectedInForecast);
  if (tracked.length === 0) return 0;
  const onTrack = tracked.filter((a) => a.status === "done" || a.status === "in-progress");
  return (onTrack.length / tracked.length) * 100;
}

/** 회수 실현율(%) — 반영 완료 과제의 목표 회수액 대비 실제 회수액. */
export function recoveryRealizationRate(): number {
  const tracked = rollingPlan.actions.filter((a) => a.reflectedInForecast);
  const target = tracked.reduce((sum, a) => sum + a.targetRecovery, 0);
  if (target === 0) return 0;
  const realized = tracked.reduce((sum, a) => sum + a.realizedRecovery, 0);
  return (realized / target) * 100;
}

/** 현행 임계치에서의 감지 오탐 비율(%). 가동률 KRI를 대표로 쓴다. */
export function detectionFalsePositiveRate(): number {
  const kri = evolutionLab.kris.find((k) => k.id === "kri-utilization");
  if (!kri) throw new Error("가동률 KRI를 찾을 수 없다");
  return tuningOutcome(kri, kri.currentThreshold).falsePositiveRate;
}

/** 시나리오 설정값과 시스템 산출값을 합쳐 전체 지표 목록을 만든다. */
export function executionMetrics(): ExecutionMetric[] {
  const computed: Record<string, number> = {
    "mp-analysis-time": totalAgentHours(),
    "mp-false-positive": detectionFalsePositiveRate(),
    "mp-action-ontime": actionOnTimeRate(),
    "mp-recovery-rate": recoveryRealizationRate(),
  };

  return executionBaseline.map((metric) =>
    metric.provenance === "system"
      ? { ...metric, current: computed[metric.id] ?? metric.current }
      : metric,
  );
}
