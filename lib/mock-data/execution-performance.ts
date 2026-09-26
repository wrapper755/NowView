/**
 * 경영 수행 성과 기준값.
 *
 * `provenance: "system"`인 지표의 `current`는 **여기 값이 쓰이지 않는다** —
 * `services/execution-performance.ts`가 실제 데이터에서 계산해 덮어쓴다. 이 파일의 값은
 * 계산이 불가능한 상황에서의 자리표시자일 뿐이므로, 실제 값과 맞추려 애쓰지 말 것.
 *
 * `previous`는 전부 시나리오 설정값이다. 직전 경영주기 기록이 시스템에 없기 때문이며,
 * 이것이 "시나리오에서 설정한 결과"와 "시스템 실행으로 확인한 결과"를 구분해야 하는
 * 이유이기도 하다(기획안 2.3).
 */

import type { ExecutionMetric } from "@/lib/types/execution-performance";

export const executionBaseline: ExecutionMetric[] = [
  {
    id: "mp-detection-lag",
    category: "speed",
    label: "문제 인지 시간",
    current: 3,
    previous: 5,
    target: 1,
    unit: "일",
    higherIsBetter: false,
    provenance: "scenario",
    definition:
      "KRI가 임계치를 벗어난 시점부터 경영 활동이 착수되기까지 걸린 일수. 이번 건은 3일 연속 미달 후 감지됐다.",
  },
  {
    id: "mp-analysis-time",
    category: "speed",
    label: "Agent 분석 소요시간",
    current: 0.4,
    previous: 16,
    unit: "시간",
    higherIsBetter: false,
    provenance: "system",
    definition:
      "감지부터 대안 시뮬레이션까지 Agent 실행 기록의 소요시간 합. 직전 주기는 사람이 수작업으로 분석했다.",
  },
  {
    id: "mp-decision-time",
    category: "speed",
    label: "의사결정 소요시간",
    current: 18,
    previous: 72,
    target: 24,
    unit: "시간",
    higherIsBetter: false,
    provenance: "scenario",
    definition:
      "Agent 보고서 제출부터 경영진 승인까지 걸린 시간. 시스템이 관측할 수 없어 시나리오에서 설정했다.",
  },
  {
    id: "mp-false-positive",
    category: "accuracy",
    label: "감지 오탐 비율",
    current: 20,
    previous: 35,
    target: 25,
    unit: "%",
    higherIsBetter: false,
    provenance: "system",
    definition:
      "가동률 KRI 현행 임계치에서 전체 알림 중 실제 문제가 아니었던 비율. 백테스트 결과에서 계산한다.",
  },
  {
    id: "mp-effect-verified",
    category: "accuracy",
    label: "효과 검증 완료율",
    current: 33,
    previous: 0,
    target: 100,
    unit: "%",
    higherIsBetter: true,
    provenance: "scenario",
    definition:
      "반영 완료 과제 중 기대 효과의 실현 여부까지 검증을 마친 비율. 3건 중 판관비 통제 1건만 검증이 끝났다.",
  },
  {
    id: "mp-action-ontime",
    category: "execution",
    label: "과제 이행률",
    current: 67,
    previous: 50,
    target: 90,
    unit: "%",
    higherIsBetter: true,
    provenance: "system",
    definition:
      "Forecast 반영 완료 과제 중 완료되었거나 정상 진행 중인 비율. 지연 위험 상태는 제외한다.",
  },
  {
    id: "mp-recovery-rate",
    category: "execution",
    label: "회수 실현율",
    current: 62,
    previous: 41,
    target: 100,
    unit: "%",
    higherIsBetter: true,
    provenance: "system",
    definition:
      "반영 완료 과제의 목표 회수액 대비 실제 회수액. 예상 효과와 실현 효과를 구분하는 지표다.",
  },
];
