/**
 * SC01 표기 — 엔진이 원 단위·정밀 비율 문자열로 준 값을 화면 단위로 바꾼다.
 *
 * **계산하지 않는다. 단위만 바꾼다**(CALC-02: 원 단위로 계산하고 표시 단위만 변경).
 * 정밀값은 항상 `title`이나 상세 표에서 다시 볼 수 있게 원값 문자열도 함께 쓴다.
 */

import type { Risk, SourceStatus, TaskStatus } from "@/lib/sc01/types";

const EOK = 100_000_000;
const MAN = 10_000;

/** 원 → "33.09억" / "1,400만" / "−1,400만". 억 이상은 소수 둘째 자리까지. */
export function formatKrw(won: string | number | null | undefined): string {
  if (won === null || won === undefined || won === "") return "—";
  const v = Number(won);
  const sign = v < 0 ? "−" : "";
  const abs = Math.abs(v);
  if (abs >= EOK) return `${sign}${(abs / EOK).toLocaleString("ko-KR", { maximumFractionDigits: 2 })}억`;
  if (abs >= MAN) return `${sign}${Math.round(abs / MAN).toLocaleString("ko-KR")}만`;
  return `${sign}${abs.toLocaleString("ko-KR")}`;
}

/** 부호를 항상 붙인다. 0은 부호 없이. */
export function formatKrwSigned(won: string | number): string {
  const v = Number(won);
  if (v === 0) return "0";
  return v > 0 ? `+${formatKrw(v)}` : formatKrw(v);
}

/** 원 단위 전체 값 — 상세 확인용(UI01-05). */
export function formatWonExact(won: string | number | null | undefined): string {
  if (won === null || won === undefined) return "—";
  return `${Number(won).toLocaleString("ko-KR")}원`;
}

/** 물량(대분). null은 누락이다 — 0과 다르게 보여야 한다. */
export function formatQty(qty: number | string | null | undefined): string {
  if (qty === null || qty === undefined) return "누락";
  return Number(qty).toLocaleString("ko-KR");
}

/** 비율 문자열("0.07368421") → "7.37%". 화면은 소수 둘째 자리(CALC-02). */
export function formatRatio(value: string | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "미산출";
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

export const RISK_LABEL: Record<Risk, string> = {
  NORMAL: "기준 이내",
  ATTENTION: "관심",
  CRITICAL: "중요",
};

/** 판정 보류는 "정상"이 아니다(CALC-03). */
export function riskLabel(risk: Risk | null): string {
  return risk ? RISK_LABEL[risk] : "판정 보류";
}

export const SOURCE_STATUS_LABEL: Record<SourceStatus, string> = {
  RECEIVED: "수신 — 확인 전",
  NEEDS_INFO: "보완 필요",
  VERIFIED: "원천 확인 완료",
};

export const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  ASSIGNED: "배정 — 인수 전",
  IN_PROGRESS: "진행 중",
  NEEDS_INFO: "보완 중",
  COMPLETED: "완료",
};

export const TASK_TYPE_LABEL: Record<string, string> = {
  DQ: "원천 확인",
  SALES: "영업 검토",
  PROD: "생산계획 영향 검토",
  MAT: "소요자재·발주 영향 검토",
  FIN: "통합 손익분석 보고",
};

export const SCENE_LABEL: Record<string, string> = {
  READY: "사건 전",
  ACTIVE: "진행 중",
  HANDED_OFF: "인계 완료",
};

export const METRIC_LABEL: Record<string, string> = {
  KPI01: "공급물량 전망 달성률",
  M01: "이번 추가 감소물량",
  KRI01: "직전 대비 감소율",
  M03: "물량 변동 순손익 영향",
  KRI02: "예상 공헌이익 감소액",
  M02: "목표 대비 부족물량",
  KRI03: "목표 대비 부족률",
};

/** 지표 값을 단위에 맞게. */
export function formatMetric(unit: string, value: string | null): string {
  if (value === null) return "미산출";
  if (unit === "ratio") return formatRatio(value);
  if (unit === "krw") return `${formatKrw(value)}원`;
  return `${formatQty(value)}대분`;
}

/** "2027-06-16T11:05:00+09:00" → "6/16 11:05". 가상시각은 모두 KST다. */
export function formatClock(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${Number(m[2])}/${Number(m[3])} ${m[4]}:${m[5]}`;
}

/** "2027-07-01" → "7월". */
export function formatMonth(iso: string): string {
  return `${Number(iso.slice(5, 7))}월`;
}

/** "A-b" → "b모델". */
export function modelLabel(modelId: string): string {
  return `${modelId.slice(-1)}모델`;
}
