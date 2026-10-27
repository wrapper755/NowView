/**
 * SC05 표기 — 계산하지 않는다. 단위만 바꾼다. 기본 화면은 **백만원 소수 둘째 자리**이고 상세는 원 단위다(구현명세
 * 2장). NULL은 「미확인」, 확인된 0은 0, 적용 대상 없음은 「비해당」이다 — 셋을 섞지 않는다. 목표 부족이 음수이면
 * **목표 초과**로 쓴다.
 */

import type { Activity } from "@/lib/sc05/types";

export { formatMillion } from "@/lib/sc03/format";
export { gapWord } from "@/lib/sc04/format";

/** 비율(0~1 Decimal 문자열) → "8.33%". 분모 0(null)은 비해당이다 — 0%가 아니다. */
export function formatRate(value: string | null | undefined): string {
  if (value === null || value === undefined) return "비해당";
  return `${(Number(value) * 100).toLocaleString("ko-KR", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}%`;
}

/** 분(Decimal 문자열) → "26.7분". 없으면 미확인. */
export function formatMinutes(value: string | null | undefined): string {
  if (value === null || value === undefined) return "미확인";
  return `${Number(value).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}분`;
}

/** 건수 — null은 미확인(정상 0건과 다르다, T518). */
export function formatCount(value: number | null | undefined, unit = "건"): string {
  return value === null || value === undefined ? "미확인" : `${value.toLocaleString("ko-KR")}${unit}`;
}

/**
 * 활동 → 결재 폼의 활동 목록 글(번호|활동|담당|시작|종료|선행|협조|비용|완료근거|근거ID). Agent 초안을 불러올 때 쓴다 —
 * 협조·비용이 비어 있으면 빈 칸으로 둔다(사람이 채운다. 0으로 메우지 않는다).
 */
export function activityLines(activities: Activity[], nameOf: (id: string | null | undefined) => string): string {
  return activities
    .map((a) =>
      [
        a.activity_id,
        a.name,
        a.owner ? nameOf(a.owner) : "",
        a.start ?? "",
        a.end ?? "",
        a.predecessors.join(",") || "-",
        a.cooperation ?? "",
        a.cost ?? "",
        a.completion ?? "",
        a.evidence ?? "",
      ].join(" | "),
    )
    .join("\n");
}

export const SCENE_STATE_LABEL: Record<string, string> = {
  PENDING: "미착수",
  PLAN_PENDING: "상세 계획 작성 중",
  PREPARING: "계획 확정 · 조건·품의 준비",
  OPERATING: "운영 적용 중",
  ROLLING_REVIEW: "월간 Rolling 검토",
  FORECAST_PUBLISHED: "새 공식 전망 게시",
  SC05_COMPLETED: "결정 실행·계획 갱신 완료",
};

export const PLAN_STATE_LABEL: Record<string, string> = {
  DRAFT: "초안",
  COORDINATED: "생산 협조 확인",
  CONFIRMED: "임원 확정",
  CHANGE_REQUESTED: "변경 요청",
  NEEDS_SEPARATE_APPROVAL: "범위 이탈 — 별도 승인 필요(시행 보류)",
  REWORK_REQUIRED: "보완 필요",
  SUPERSEDED: "대체됨",
};

export const CHECK_LABEL: Record<string, string> = {
  PENDING: "경영관리 확인 대기",
  VERIFIED: "경영관리 확인",
  REWORK_REQUIRED: "경영관리 이견 — 보완",
};

export const CONDITION_STATE_LABEL: Record<string, string> = {
  OPEN: "미충족",
  EVIDENCE_READY: "근거 등록 — 확인 대기",
  COORDINATED: "양 부서 준비 확인 — 충족 확인 대기",
  SATISFIED: "충족 확인",
  VERIFIED: "이행 확인",
  REWORK_REQUIRED: "보완 필요",
};

export const REQUEST_STATE_LABEL: Record<string, string> = {
  SUBMITTED: "상신 — 현업 승인 대기",
  FUNCTION_APPROVED: "현업 승인 — 예산 승인 대기",
  APPROVED: "승인 · 약정",
  RETURNED: "반려",
};

export const OPERATION_STATE_LABEL: Record<string, string> = {
  WAIT: "착수 대기",
  START_ALLOWED: "착수 가능",
  OPERATING: "운영 적용 중",
  OPERATING_MONITORING: "정규 운영 인계 · 성과 추적",
};

export const CHANGE_STATE_LABEL: Record<string, string> = {
  RECEIVED: "접수",
  SHARED: "공유 — 구매 확인 대기",
  ACKNOWLEDGED: "구매 확인",
  NORMAL_DECIDED: "정상 대응 결정",
  URGENT_SUBMITTED: "긴급 기안 — 승인 대기",
  APPROVED: "긴급 승인",
  EXECUTED: "발주·처리 기록",
};

export const FORECAST_STATE_LABEL: Record<string, string> = {
  DRAFT: "검토안 작성",
  REVIEWED: "부서 확인 완료",
  SUBMITTED: "대표 승인 요청",
  APPROVED: "승인 — 게시 대기",
  PUBLISHED: "게시",
  RETURNED: "반려 — 종전 공식본 유지",
  STALE: "입력 변경 — 다시 확인",
};

export const REVIEW_STATUS_LABEL: Record<string, string> = {
  UNREVIEWED: "미검토",
  REVIEWED: "사람 검토",
  MODIFIED_BY_HUMAN: "사람이 수정해 사용",
  ACCEPTED_BY_HUMAN: "사람이 대조 후 사용",
};

export const CAUSE_LABEL: Record<string, string> = {
  urgent: "긴급구매 건수·비용",
  support: "운영지원비",
  one_off: "일회성 준비·전환비",
  volume: "과제 적용 물량",
  basis: "그 외 기간·비과제 요인",
};

export const TASK_NAME: Record<string, string> = {
  ACT41: "부분 공정·외주 조정",
  ACT42: "긴급구매 축소",
  ACT43: "대체 공급업체 활용",
};
