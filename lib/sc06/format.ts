/**
 * SC06 표기 — 계산하지 않는다. 단위만 바꾼다. 기본은 **백만원 소수 둘째 자리**, 상세는 원 단위다(구현명세 2장). 차이는
 * 늘 「실현 − 기대」 부호로 쓴다. null은 0이 아니다 — 금액은 「미확인」·「산정 보류」·「미산정」·「비해당」으로 갈라 쓴다.
 */

import { formatMillion } from "@/lib/sc03/format";
import type { Estimation } from "@/lib/sc06/types";

export { formatMillion };

/** 원 → 백만원. null이면 이유를 쓴다(기본 「미확인」) — 0이나 빈칸으로 보이지 않는다. */
export function million(won: number | null | undefined, empty = "미확인"): string {
  return won === null || won === undefined ? empty : formatMillion(won);
}

/** 차이 — 부호를 늘 붙인다(+ 초과 · − 미달). 0은 부호 없이. */
export function signedMillion(won: number | null | undefined, empty = "산정 보류"): string {
  if (won === null || won === undefined) return empty;
  if (won === 0) return "0.00";
  return won > 0 ? `+${formatMillion(won)}` : formatMillion(won);
}

/** 효과·예산의 산정 상태 — 확인된 0만 0이다(X61-06: 미산정을 0원 승인으로 읽히게 두지 않는다). */
export function estimationText(e: Estimation): string {
  if (e.estimation_status === "CONFIRMED") return `${formatMillion(e.krw)}백만원`;
  return e.estimation_status === "NOT_APPLICABLE" ? "비해당" : "미산정";
}

export const CAUSE_LABEL: Record<string, string> = {
  INTERNAL: "내부 확인 지연",
  SUPPLY: "적시 공유 후 조달 제약",
  MIXED: "내부 지연·조달 제약 복합",
  UNKNOWN: "원인 미확정",
  NORMAL: "정상 조달",
};

export const ACTIVITY_LABEL: Record<string, string> = {
  COMPLETION_CONFIRMED: "완료 확인",
  REVIEWED: "검토 완료",
  HOLD: "판단 보류",
};

export const JUDGMENT_LABEL: Record<string, string> = { REVIEWABLE: "검토 가능", HOLD: "판단 보류" };
export const COLLECTION_LABEL: Record<string, string> = { COMPLETE: "수집 완료", PARTIAL: "일부 보완 중" };

export const FOLLOWUP_STATE_LABEL: Record<string, string> = {
  IN_PROGRESS: "보완 진행 중",
  PROPOSED: "발의 · 검토 예정",
  OPEN: "열림",
};

export const RECORD_STATE_LABEL: Record<string, string> = {
  DRAFT: "초안",
  CONFIRMED: "확인",
  FINALIZED: "확정",
  REPORTED: "보고",
  OPEN: "열림",
};

export const AGENT_STATE_LABEL: Record<string, string> = { HUMAN_REVIEWED: "사람 확인", CANDIDATE: "후보 · 사람 확인 전" };

/** 분 → 「40분」·「2일」. null은 미확인(0분 아님). */
export function formatDuration(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "미확인";
  if (minutes >= 1440 && minutes % 1440 === 0) return `${minutes / 1440}일`;
  if (minutes >= 60 && minutes % 60 === 0) return `${minutes / 60}시간`;
  return `${minutes}분`;
}

/** 「2027-11-12T09:20:00+09:00」 → 「11/12 09:20」 — 같은 분기 안의 시각을 짧게. */
export function shortClock(iso: string | null | undefined): string {
  if (!iso) return "미확인";
  const [d, t] = iso.split("T");
  const [, m, day] = d.split("-");
  return `${Number(m)}/${Number(day)} ${t.slice(0, 5)}`;
}

/** 「2027-10-01」 → 「10월」. */
export function monthLabel(iso: string): string {
  return `${Number(iso.slice(5, 7))}월`;
}
