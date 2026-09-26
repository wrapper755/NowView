/**
 * Rolling Plan Mock.
 *
 * **수치 연동 규칙 (CLAUDE.md 4.3):**
 *   · target 428 / forecast 359 는 `next-automotive.ts`의 전사 영업이익과 같아야 한다.
 *   · 분기 합이 각각 428, 359 여야 한다 (100+106+108+114 / 96+88+82+93).
 *   · `reflectedInForecast: true`인 과제의 목표 회수액 합 20억은 `next-automotive.ts`의
 *     `committedActionRecovery` 및 Cockpit 브릿지의 "확정 Action 회수 효과 +20억"과 같다.
 *   · 마지막 revision의 forecast는 `forecast`와 같아야 한다.
 */

import type { RollingPlan } from "@/lib/types/rolling";

export const rollingPlan: RollingPlan = {
  target: 428,
  forecast: 359,
  updatedAt: "2026-09-30",

  quarters: [
    { quarter: "1Q", target: 100, forecast: 96, closed: true },
    { quarter: "2Q", target: 106, forecast: 88, closed: true },
    { quarter: "3Q", target: 108, forecast: 82, closed: true },
    { quarter: "4Q", target: 114, forecast: 93, closed: false },
  ],

  // Target 428은 모든 회차에서 그대로다. 움직이는 것은 Forecast뿐이다.
  revisions: [
    {
      id: "rev-06",
      label: "6월 Rolling",
      date: "2026-06-30",
      forecast: 412,
      drivers: ["내연 부품 발주 예보 하향 반영", "1Q 실적 확정 반영"],
    },
    {
      id: "rev-07",
      label: "7월 Rolling",
      date: "2026-07-31",
      forecast: 395,
      drivers: ["알루미늄 잉곳 구매단가 인상 반영", "판관비 집행률 통제 효과 반영"],
    },
    {
      id: "rev-08",
      label: "8월 Rolling",
      date: "2026-08-31",
      forecast: 371,
      drivers: ["BMS 라인 수율 미달 반영", "전장 ECU 신규 수주 일부 반영", "2Q 실적 확정 반영"],
    },
    {
      id: "rev-09",
      label: "9월 Rolling",
      date: "2026-09-30",
      forecast: 359,
      drivers: [
        "파워트레인 가동률 하락 반영",
        "완성차 2026 CR 요구 -3.2% 반영",
        "확정 Action 회수 효과 +20억 반영",
        "3Q 실적 확정 반영",
      ],
    },
  ],

  actions: [
    {
      id: "act-yield-tf",
      title: "전장 라인 직행률 개선 TF",
      owner: "전장기술팀 이도현",
      due: "2026-11-30",
      division: "친환경/전장",
      targetRecovery: 8,
      realizedRecovery: 5.2,
      status: "in-progress",
      reflectedInForecast: true,
      sourceRiskId: "risk-bms-yield",
    },
    {
      id: "act-price-renegotiation",
      title: "알루미늄 원자재가 연동 조항 재협상",
      owner: "구매본부 최민서",
      due: "2026-10-31",
      division: "전사",
      targetRecovery: 7,
      realizedRecovery: 2.1,
      status: "at-risk",
      reflectedInForecast: true,
      sourceRiskId: "risk-aluminum",
    },
    {
      id: "act-sga-control",
      title: "판관비 집행률 통제",
      owner: "재무팀 한지훈",
      due: "2026-09-30",
      division: "전사",
      targetRecovery: 5,
      realizedRecovery: 5,
      status: "done",
      reflectedInForecast: true,
    },
  ],
};
