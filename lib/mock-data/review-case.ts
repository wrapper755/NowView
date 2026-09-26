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
      sources: [
        { name: "MES 설비 가동 로그", quality: "complete" },
        { name: "ERP 수주 잔량", quality: "complete" },
        {
          name: "월 결산 고정비 배부표",
          quality: "stale",
          caveat: "9월 마감 전 잠정치다. 확정 시 배부액이 ±2억 움직일 수 있다.",
        },
      ],
      confidence: "high",
    },
    {
      id: "root-cause",
      title: "원인 분해",
      body: "기여도는 발주 축소 62%, 고정비 흡수율 하락 24%, 직행률 저하 9%, 기타 5%로 분해된다. 발주 축소는 전동화 전환에 따른 구조적 추세여서 단기 회복 가능성은 낮다고 본다.",
      sources: [
        {
          name: "고객 발주 예보(3개월)",
          quality: "estimated",
          caveat: "확정 발주가 아니다. 과거 예보 대비 실적 편차는 ±6%였다.",
        },
        {
          name: "라인별 가동 실적",
          quality: "partial",
          caveat: "3·4라인은 센서 미연동으로 수동 집계분이 섞여 있다.",
        },
        { name: "직행률 일별 추이", quality: "complete" },
      ],
      confidence: "medium",
      confidenceNote: "발주 예보가 추정치여서 기여도 62%는 ±8%p 범위로 본다.",
    },
    {
      id: "alternatives",
      title: "대안 도출",
      body: "가동률 회복(1안), 신규 물량 유입(2안), 비용 이연(3안) 세 축으로 대안을 구성했다. 1안은 효과가 가장 크지만 전환 기간 중 생산 차질을 동반하고, 3안은 손익 효과가 당기에 한정되며 설비 리스크가 이월된다.",
      sources: [
        { name: "라인별 표준원가", quality: "complete" },
        {
          name: "전장 수주 파이프라인",
          quality: "estimated",
          caveat: "수주 확정 전 물량 포함. 확정분만 보면 1안 효과는 약 12억으로 줄어든다.",
        },
        {
          name: "설비 보전 이력",
          quality: "partial",
          caveat: "2024년 이전 이력은 시스템 이관 시 누락되었다.",
        },
      ],
      confidence: "medium",
      confidenceNote: "미확정 물량이 포함되어 1안 효과 18억은 상단 추정에 가깝다.",
    },
  ],

  /**
   * Agent가 답하지 못해 사람에게 넘긴 판단.
   * 둘 다 1안의 전제라서, 답이 달라지면 권고 자체가 바뀐다.
   */
  escalations: [
    {
      id: "esc-demand-structural",
      question: "내연 부품 발주 축소가 구조적 추세인가, 일시적 조정인가?",
      reason:
        "고객 중장기 물량 계획을 제공받지 못했다. Agent가 접근할 수 있는 데이터는 3개월 예보까지다.",
      owner: "영업본부 박지우",
      ifUnanswered:
        "구조적 추세로 가정하고 분석했다. 일시적 조정이라면 라인 재배치는 과잉 대응이 된다.",
    },
    {
      id: "esc-customer-approval",
      question: "전환 라인의 기존 품번을 고객이 이관 승인할 것인가?",
      reason: "고객 승인 이력은 시스템에 없다. 영업 협의 결과가 필요하다.",
      owner: "영업본부 박지우",
      ifUnanswered: "승인된다고 가정한 수치다. 거절되면 1안은 실행 자체가 불가하다.",
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
        costPerUnit: 11,
      },
      riskBands: [
        { upTo: 2, severity: "good" },
        { upTo: 3, severity: "warning" },
        { upTo: 4, severity: "serious" },
      ],
      riskNote: "전환 기간 중 해당 라인 생산이 중단된다. 3개 라인을 넘기면 기존 고객 납기에 영향이 간다.",
      leadTime: "10~14주",
      owner: "생산본부 김상현",
      costNote: "라인 전환 설비 투자비 (일회성). 연간 회수 기준 회수 기간 약 1.2년.",
      prerequisites: [
        "전환 라인의 기존 품번 이관에 대한 고객 승인",
        "전장 ECU 분기 18만 개 수주 물량 확정",
      ],
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
        costPerUnit: 0.3,
      },
      riskBands: [
        { upTo: 10, severity: "good" },
        { upTo: 25, severity: "warning" },
        { upTo: 40, severity: "serious" },
      ],
      riskNote: "이관 비율이 높을수록 전장 라인 리드타임이 늘어난다. MCU 리드타임 26주 이슈와 겹치면 양산 일정이 밀린다.",
      leadTime: "6~8주",
      owner: "사업기획팀 정하윤",
      costNote: "금형·치공구 이설 및 공정 검증 비용 (일회성).",
      prerequisites: [
        "MCU 리드타임 26주 → 20주 이하 단축",
        "전장 라인 여유 CAPA 확보",
      ],
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
        costPerUnit: 0,
      },
      riskBands: [
        { upTo: 2, severity: "good" },
        { upTo: 4, severity: "warning" },
        { upTo: 6, severity: "critical" },
      ],
      riskNote: "가동률 자체는 개선되지 않는다. 이연 기간이 길수록 돌발 고장 위험이 누적되고 비용은 차기로 이월될 뿐이다.",
      leadTime: "즉시",
      owner: "생산본부 김상현",
      costNote: "추가 지출 없음. 다만 이연된 보전비는 차기로 이월된다.",
      prerequisites: ["설비 고장 리스크 수용에 대한 생산본부 동의"],
    },
  ],
};
