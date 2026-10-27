/**
 * SC03 표기 — 계산하지 않는다. 단위만 바꾼다. 장면 3 기본 화면은 **백만원 소수 둘째 자리**이고 상세는 원
 * 단위다(구현명세 2장 공통 화면 규칙). NULL은 「미설정·미산정·미확인」으로 쓴다 — 0으로 보이지 않는다.
 */

/** 원 → "3,299.99" (백만원). null이면 대신 쓸 글자. */
export function formatMillion(won: string | number | null | undefined, empty = "—"): string {
  if (won === null || won === undefined || won === "") return empty;
  const v = Number(won) / 1_000_000;
  const sign = v < 0 ? "−" : "";
  return `${sign}${Math.abs(v).toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export const REVIEW_STATE_LABEL: Record<string, string> = {
  PENDING: "미착수",
  ANALYSIS_IN_PROGRESS: "분석 중",
  CONFIRMATION_PENDING: "부서 확인 중",
  MEETING_READY: "회의 준비 완료",
  IN_REVIEW: "수시회의 검토 중",
  REWORK_REQUIRED: "보완 후 재검토",
  REVIEWED: "검토 결론 확정",
  TASKS_ASSIGNED: "과제 인수 대기",
  SC03_COMPLETED: "장면 3 완료",
};

export const OUTCOME_LABEL: Record<string, string> = {
  ACCEPTED: "수용",
  CONDITIONAL_ACCEPT: "조건부 수용",
  REWORK_REQUIRED: "보완 후 재검토",
};

export const CATEGORY_LABEL: Record<string, string> = { FACT: "사실", ASSUMPTION: "가정", UNCONFIRMED: "미확인" };

export const DEPT_STATE_LABEL: Record<string, string> = {
  PENDING: "미회신",
  RESPONDED: "회신 완료",
  DISPUTED: "이견",
  STALE: "재확인 필요",
};

export const QUESTION_STATE_LABEL: Record<string, string> = {
  OPEN: "판단 전",
  OPEN_FOLLOWUP: "비차단 · 후속 확인",
  BLOCKING: "차단",
  REVISED: "보완됨 · 재확인 대기",
  RESOLVED: "해제",
};

export const TASK_STATE_LABEL: Record<string, string> = {
  DRAFT: "초안",
  ASSIGNED: "인수 대기",
  RETURNED: "반려",
  ACCEPTED: "인수 완료",
};

export const DEPT_LABEL: Record<string, string> = { SALES: "영업", BUY: "구매", PROD: "생산", FIN: "경영관리" };
