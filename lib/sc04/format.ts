/**
 * SC04 표기 — 계산하지 않는다. 단위만 바꾼다. 장면 3과 같이 기본 화면은 **백만원 소수 둘째 자리**이고 상세는 원
 * 단위다(구현명세 2장). 목표 부족이 음수이면 **목표 초과**로 쓴다 — 0으로 자르지 않고 위험처럼 보이지 않게 한다.
 * NULL은 「미산정」이다 — 0으로 보이지 않는다(DIR41 기대효과).
 */

export { formatMillion } from "@/lib/sc03/format";

/** 목표 부족 — 양수는 「부족」, 음수는 「목표 초과」(기간을 함께 쓴다, T416). */
export function gapWord(gap: string | null | undefined): "부족" | "목표 초과" | "—" {
  if (gap === null || gap === undefined || gap === "") return "—";
  return Number(gap) < 0 ? "목표 초과" : "부족";
}

export const SCENE_STATE_LABEL: Record<string, string> = {
  PENDING: "미착수",
  PREPARING: "분석 결과 준비 중",
  REPORT_READY: "보고본 확정 · 회의 대기",
  IN_REVIEW: "월간회의 검토 중",
  DECIDED: "대표 결정 · 승인서 대기",
  APPROVED: "승인서 확정 · 과제 등록 대기",
  AWAITING_ACCEPTANCE: "책임 인수 대기",
  SC04_COMPLETED: "개선안 검토·실행 승인 완료",
};

export const RESULT_STATE_LABEL: Record<string, string> = {
  AWAITING: "미제출",
  SUBMITTED: "제출 · 임원 확인 대기",
  CONFIRMED: "임원 확인 완료",
  REWORK_REQUESTED: "보완 요청",
};

export const OUTCOME_LABEL: Record<string, string> = {
  APPROVED: "승인",
  CONDITIONAL: "조건부 승인",
  HOLD: "보류",
  REJECTED: "미승인",
};

export const ASSIGNMENT_STATE_LABEL: Record<string, string> = {
  ASSIGNED: "인수 대기",
  RETURNED: "반려",
  ACCEPTED: "인수 완료",
};

export const DIRECTIVE_KIND_LABEL: Record<string, string> = {
  CONDITION: "선행조건",
  SUPPORT: "지원 지시",
  DISCOVERY: "추가 발굴",
};

export const RECORD_TYPE_LABEL: Record<string, string> = {
  QUESTION: "대표 질의",
  ANSWER: "현업 답변",
  DIRECTIVE: "지원·수정 지시",
  NOTE: "메모",
};

export const GATE_LABEL: Record<string, string> = {
  PLAN_AND_APPROVAL_REQUIRED: "상세 계획·정상 품의 후 착수",
  BLOCKED_BY_CON41: "CON41 충족 전 실행 착수 제한",
};

export const FIELD_LABEL: Record<string, string> = {
  start: "효과 시작",
  monthly_qty: "월 대상량",
  avoid_price: "회피단가",
  outsource_price: "추가단가",
  logistics_price: "물류단가",
  emergency_after: "긴급 후",
  per_event_cost: "건당비용",
  monthly_support: "월지원비",
  one_off_cost: "일회성비",
  one_off_month: "일회성월",
};
