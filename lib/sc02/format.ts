/**
 * SC02 표기 — 상태 코드의 한글 이름. 숫자 표기는 SC01 `format.ts`를 그대로 쓴다(원 단위 → 억·만 단위만 바꾼다).
 *
 * **상태를 칩 하나로 뭉치지 않는다**(구현명세 10장) — 요청·승인·원가·인계·위험·전망은 서로 다른 말이다.
 * 「단가안 승인 완료」는 위험 해소도, 전망 승인도 아니다(SCOPE-01).
 */

export const REQUEST_STATUS_LABEL: Record<string, string> = {
  RECEIVED: "접수 — 원문 확인 전",
  VERIFIED: "원문 확인 완료",
  NEEDS_INFO: "자료 보완 대기",
  PRE_REVIEW: "사전 검토 착수",
  CLOSED: "검토 종결",
  NEGOTIATION_READY: "협상 준비",
  TENTATIVE_AGREEMENT: "잠정합의 — 재분석 필요",
  NEGOTIATION_UNRESOLVED: "협상 미합의",
  PROPOSAL_READY: "기안 준비",
};

export const APPROVAL_STATUS_LABEL: Record<string, string> = {
  TEAM_APPROVAL_PENDING: "구매팀장 승인 대기",
  EXEC_APPROVAL_PENDING: "구매임원 승인 대기",
  EXEC_APPROVED: "대표 대상 판정 중",
  CEO_APPROVAL_PENDING: "대표이사 승인 대기",
  APPROVED: "단가안 승인 완료",
  RETURNED: "보완 — 재상신 대기",
  REJECTED: "반려 종결",
  NEEDS_RENEGOTIATION: "재협상 대기 — 미승인",
};

export const COST_STATUS_LABEL: Record<string, string> = {
  REGISTERED_FUTURE: "적용 예정",
  EFFECTIVE: "적용 중",
};

export const HANDOFF_STATUS_LABEL: Record<string, string> = {
  FINANCE_PENDING: "경영관리 인수 대기",
  HANDED_OFF: "경영관리 인수 완료",
};

export const SCENE2_LABEL: Record<string, string> = {
  READY: "요청 접수 전",
  ACTIVE: "진행 중",
  HANDED_OFF: "인계 완료 · 수익성 통합 분석 손익 검토 대기",
  CLOSED: "검토 종결",
  UNRESOLVED: "협상 미합의 — 팀장 협의",
  REJECTED: "반려 종결",
  RENEGOTIATION: "재협상 대기",
};

export const KIND_LABEL: Record<string, string> = {
  REQUEST: "요청안",
  OFFER: "내부 제시안",
  NEGOTIATION: "1차 협상안",
  PROPOSAL: "기안안",
  APPROVED: "승인안",
};

export const STEP_LABEL: Record<string, string> = {
  TEAM: "구매팀장",
  EXEC: "구매임원",
  CEO: "대표이사",
};

export const TASK2_LABEL: Record<string, string> = {
  VERIFY: "요청 원문 확인",
  REPORT: "팀장 보고 기록",
  ANALYSIS: "요청안 영향분석",
  NEGOTIATION: "1차 협상",
  REANALYSIS: "협상안 재분석",
  PROPOSAL: "가격인상 기안",
  APPROVE_TEAM: "구매팀장 승인",
  APPROVE_EXEC: "구매임원 승인",
  APPROVE_CEO: "대표이사 승인",
  COST: "원가 적용 등록",
  HANDOFF: "수익성 통합 분석 인계 요청",
  ACCEPT: "경영관리 인수",
  RENEG: "추가 협상(2차) — 후속 범위",
};

export const AGENT_KIND_LABEL: Record<string, string> = {
  AG21: "AG21 사전 검토",
  AG22: "AG22 협상 비교·기안 초안",
  AG24: "AG24 인계 요약",
};

/** 「2027-07-01」 → 「2027-07」, 기간의 끝(종료 제외)은 한 달 앞으로 — 「2027-07~2028-06」. */
export function formatPeriod(from: string, to: string): string {
  const end = new Date(`${to}T00:00:00Z`);
  end.setUTCMonth(end.getUTCMonth() - 1);
  return `${from.slice(0, 7)}~${end.toISOString().slice(0, 7)}`;
}
