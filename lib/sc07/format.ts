/**
 * SC07 표기 — 계산하지 않는다. 코드를 화면 말로 바꾼다(구현명세 1장 「공통 표시와 예외」). 누락은 0분·정상이 아니다 —
 * 「미확인」으로 쓴다.
 */

export { shortClock } from "@/lib/sc06/format";

export const CAUSE_LABEL: Record<string, string> = {
  SUPPLY: "조달 제약",
  INTERNAL: "내부 지연",
  MIXED: "복합 제약",
  NEED_EVIDENCE: "근거 보완 필요",
  NO_CONSTRAINT: "제약 미확인",
  EXCLUDED: "정답 차단",
  UNCHANGED: "원본 불변",
};

export const STATUS3_LABEL: Record<string, string> = { OVER: "초과", WITHIN: "기준 내", UNKNOWN: "미확인" };

export const CASE_STATUS_LABEL: Record<string, string> = { PASS: "충족", FAIL: "미충족", NOT_RUN: "미실행" };

export const PROCEDURE_LABEL: Record<string, string> = {
  PENDING: "착수 전",
  CONFIRMING: "확인 중",
  NEEDS_WORK: "보완 필요",
  APPLIED: "완료",
};

export const EXECUTION_LABEL: Record<string, string> = { NOT_CONFIRMED: "운영 실행 미확인" };

/** 원인 후보 코드 → 말. 모르는 코드는 그대로(검증 값 AGT71-v2 등). null은 「판단 유보」. */
export function causeText(code: string | null | undefined): string {
  if (code === null || code === undefined) return "판단 유보";
  return CAUSE_LABEL[code] ?? code;
}

/** 분. null은 미확인(0분 아님). */
export function minutes(n: number | null | undefined): string {
  return n === null || n === undefined ? "미확인" : `${n}분`;
}
