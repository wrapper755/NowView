/**
 * Management Review 안건 Mock — BPM 트래커가 `review` 노드에서 멈춰 기다리는 바로 그 건.
 *
 * **수치 연동 규칙 (깨뜨리지 말 것):**
 * 각 대안의 `lever.base × profitPerUnit`은 `bpm-process.ts`의 Simulation Agent 산출물
 * 문구와 정확히 일치해야 한다. 지금 기준:
 *   1안 2라인 × 9억 = 18억, 가동률 2 × 1.6 = +3.2%p
 *   2안 20%p × 0.6억 = 12억
 *   3안 3개월 × 3억 = 9억
 * `profitGap`(-69억)은 `next-automotive.ts`의 영업이익 Gap과 같아야 한다.
 * 세 화면이 같은 사건을 다루므로 숫자가 어긋나면 데모 전체의 신뢰가 무너진다.
 */

import type { ReviewCase } from "@/lib/types/workspace";

export const reviewCase: ReviewCase = {
  id: "review-2026-0912-utilization",
  subject: "파워트레인 가동률 임계치 이탈 대응",
  processId: "proc-2026-0912-utilization",
  riskId: "risk-utilization",
  profitGap: -69,

  report: [
    {
      id: "detection",
      title: "감지",
      body: "설비 가동률이 82.1%로 감지 임계치 85%를 3일 연속 밑돌았다. 같은 기간 내연 부품 발주량은 전분기 대비 11.4% 줄었고, 고정비 흡수율은 91.4%로 떨어졌다.",
      sources: ["MES 설비 가동 로그", "ERP 수주 잔량", "월 결산 고정비 배부표"],
    },
    {
      id: "root-cause",
      title: "원인 분해",
      body: "기여도는 발주 축소 62%, 고정비 흡수율 하락 24%, 직행률 저하 9%, 기타 5%로 분해된다. 발주 축소는 전동화 전환에 따른 구조적 추세여서 단기 회복 가능성은 낮다고 본다.",
      sources: ["고객 발주 예보(3개월)", "라인별 가동 실적", "직행률 일별 추이"],
    },
    {
      id: "alternatives",
      title: "대안 도출",
      body: "가동률 회복(1안), 신규 물량 유입(2안), 비용 이연(3안) 세 축으로 대안을 구성했다. 1안은 효과가 가장 크지만 전환 기간 중 생산 차질을 동반하고, 3안은 손익 효과가 당기에 한정되며 설비 리스크가 이월된다.",
      sources: ["라인별 표준원가", "전장 수주 파이프라인", "설비 보전 이력"],
    },
  ],

  recommendedAlternativeId: "alt-line-reallocation",

  alternatives: [
    {
      id: "alt-line-reallocation",
      tag: "1안",
      name: "라인 재배치",
      summary: "저가동 내연 라인을 전장 조립 라인으로 전환해 가동률을 직접 끌어올린다.",
      lever: {
        id: "lines",
        label: "전환 라인 수",
        unit: "개",
        min: 0,
        max: 4,
        step: 1,
        base: 2,
        profitPerUnit: 9,
        utilizationPerUnit: 1.6,
      },
      riskBands: [
        { upTo: 2, severity: "good" },
        { upTo: 3, severity: "warning" },
        { upTo: 4, severity: "serious" },
      ],
      riskNote: "전환 기간 중 해당 라인 생산이 중단된다. 3개 라인을 넘기면 기존 고객 납기에 영향이 간다.",
      leadTime: "10~14주",
      owner: "생산본부 김상현",
    },
    {
      id: "alt-volume-transfer",
      tag: "2안",
      name: "전장 물량 이관",
      summary: "전장 사업부 신규 수주 물량 일부를 파워트레인 공정으로 이관해 가동률을 보완한다.",
      lever: {
        id: "transfer-ratio",
        label: "이관 비율",
        unit: "%",
        min: 0,
        max: 40,
        step: 5,
        base: 20,
        profitPerUnit: 0.6,
        utilizationPerUnit: 0.1,
      },
      riskBands: [
        { upTo: 10, severity: "good" },
        { upTo: 25, severity: "warning" },
        { upTo: 40, severity: "serious" },
      ],
      riskNote: "이관 비율이 높을수록 전장 라인 리드타임이 늘어난다. MCU 리드타임 26주 이슈와 겹치면 양산 일정이 밀린다.",
      leadTime: "6~8주",
      owner: "사업기획팀 정하윤",
    },
    {
      id: "alt-maintenance-deferral",
      tag: "3안",
      name: "보전비 이연",
      summary: "설비 예방보전 집행을 차기로 이연해 당기 고정비를 줄인다.",
      lever: {
        id: "months",
        label: "이연 기간",
        unit: "개월",
        min: 0,
        max: 6,
        step: 1,
        base: 3,
        profitPerUnit: 3,
        utilizationPerUnit: 0,
      },
      riskBands: [
        { upTo: 2, severity: "good" },
        { upTo: 4, severity: "warning" },
        { upTo: 6, severity: "critical" },
      ],
      riskNote: "가동률 자체는 개선되지 않는다. 이연 기간이 길수록 돌발 고장 위험이 누적되고 비용은 차기로 이월될 뿐이다.",
      leadTime: "즉시",
      owner: "생산본부 김상현",
    },
  ],
};
