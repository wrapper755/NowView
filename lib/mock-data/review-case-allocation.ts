/**
 * 시나리오 3의 배분 결정 안건 — 기존 사업과 신사업 간 재원 배분.
 *
 * **앞 두 안건과 결정의 성격이 다르다.** 1·2번은 "무엇을 고칠 것인가"(조치)였고 이번은
 * "한정된 재원을 어디에 둘 것인가"(배분)다. 그래서:
 *   · 비용이 0인 대안이 없다 — 배분은 반드시 한쪽에서 빼 온다.
 *   · 회수 기간이 조치형보다 길다. 신사업 증액은 4년, 기존 사업 구조 개선은 0.5년이다.
 *     빠른 회수가 곧 좋은 선택이 아니라는 것이 이 안건의 요점이므로 숫자를 그렇게 뒀다.
 *   · Agent 신뢰도가 낮다(low). 3년 회수 전망을 분기 예보로 추정했기 때문이며,
 *     미답 질문 2건이 전부 배분 결정의 전제다.
 *
 * `profitGap`(-69억)은 전사 영업이익 Gap이며 세 시나리오가 같은 값을 공유한다.
 */

import type { ReviewCase } from "@/lib/types/workspace";

export const allocationReviewCase: ReviewCase = {
  id: "review-2026-0928-allocation",
  subject: "신사업 투자회수 지연에 따른 재원 배분 재검토",
  processId: "proc-2026-0928-allocation",
  riskId: "risk-newbiz-roi",
  profitGap: -69,

  report: [
    {
      id: "detection",
      title: "감지",
      body: "전장 사업 누적 투자 840억 대비 누적 회수는 487억(58.0%)으로 임계 75%를 밑돈다. 2023년 투자 심의 당시 3년차 계획은 75%였다.",
      sources: [
        { name: "투자 집행 원장", quality: "complete" },
        { name: "사업부별 손익 배부", quality: "complete" },
        {
          name: "투자 심의 계획서(2023)",
          quality: "stale",
          caveat: "심의 당시 가정이며 이후 전동화 속도 변화가 반영되지 않았다.",
        },
      ],
      confidence: "high",
    },
    {
      id: "root-cause",
      title: "원인 분해",
      body: "양산 시점 이동 46%, 초기 수율 미달 29%, 단가 협상 지연 18%, 기타 7%다. 셋 모두 앞선 두 안건에서 이미 대응이 진행 중이며, 이 안건은 그 대응의 속도를 재원으로 바꿀 것인지를 묻는다.",
      sources: [
        { name: "양산 일정 이력", quality: "complete" },
        {
          name: "고객 중장기 물량 계획",
          quality: "partial",
          caveat: "2개 고객사만 제공받았다. 나머지는 3개월 예보로 대체했다.",
        },
        {
          name: "경쟁사 전장 진입 동향",
          quality: "estimated",
          caveat: "공개 자료 기반 추정이며 실제 캐파 증설 규모는 확인되지 않았다.",
        },
      ],
      confidence: "low",
      confidenceNote:
        "3년 회수 전망을 분기 예보로 추정했다. 배분 결정의 근거로 쓰기에는 근거 기간이 짧다.",
    },
    {
      id: "alternatives",
      title: "대안 도출",
      body: "신사업 가속(1안), 기존 사업 구조 개선 우선(2안), 조건부 분할 집행(3안)으로 구성했다. 셋 다 같은 재원 풀에서 나오므로 어느 쪽을 고르든 반대편이 줄어든다. 회수 기간이 짧은 안이 곧 좋은 안은 아니다 — 2안은 빠르지만 신사업 시점 경쟁력을 포기한다.",
      sources: [
        { name: "라인별 표준원가", quality: "complete" },
        {
          name: "전장 수주 파이프라인",
          quality: "estimated",
          caveat: "수주 확정 전 물량 포함. 확정분만 보면 1안 회수는 연 4.6억으로 줄어든다.",
        },
        {
          name: "기존 사업 고정비 구조",
          quality: "partial",
          caveat: "공용 설비 배부 기준이 2025년에 바뀌어 이전 연도와 직접 비교되지 않는다.",
        },
      ],
      confidence: "medium",
      confidenceNote: "1안의 회수 기간은 파이프라인 가정에 민감하다. 확정 물량만으로는 6.5년이다.",
    },
  ],

  escalations: [
    {
      id: "esc-longterm-volume",
      question: "미확보 고객사의 중장기 물량 계획을 받을 수 있는가?",
      reason:
        "Agent가 접근할 수 있는 것은 3개월 예보뿐이다. 회수 전망은 3년 단위인데 근거는 분기 단위다.",
      owner: "영업본부 박지우",
      ifUnanswered:
        "확보된 2개 고객사 추세를 전체에 적용해 추정했다. 나머지가 다르게 움직이면 회수율 전망이 크게 달라진다.",
    },
    {
      id: "esc-investment-ceiling",
      question: "올해 추가 배분 가능한 재원의 상한은 얼마인가?",
      reason: "재무 승인 한도는 시스템에 없다. 자금 계획 담당의 확인이 필요하다.",
      owner: "재무팀 한지훈",
      ifUnanswered: "상한 없이 대안을 산출했다. 한도가 30억 미만이면 1안은 성립하지 않는다.",
    },
  ],

  recommendedAlternativeId: "alt-staged-allocation",

  alternatives: [
    {
      id: "alt-growth-boost",
      tag: "1안",
      name: "전장 투자 증액",
      summary: "전장 라인 증설을 앞당겨 양산 시점을 회복하고 회수 곡선을 끌어올린다.",
      lever: {
        id: "growth-capex",
        label: "추가 배분액",
        unit: "억",
        min: 0,
        max: 60,
        step: 10,
        base: 30,
        profitPerUnit: 0.25,
        secondaryLabel: "신사업 매출 비중",
        secondaryUnit: "%p",
        secondaryPerUnit: 0.08,
        costPerUnit: 1,
      },
      riskBands: [
        { upTo: 30, severity: "warning" },
        { upTo: 45, severity: "serious" },
        { upTo: 60, severity: "critical" },
      ],
      riskNote:
        "배분액 전액이 기존 사업 설비 보전·개선 예산에서 빠진다. 40억을 넘기면 파워트레인 가동률 대응 여력이 사라진다.",
      leadTime: "16~20주",
      owner: "경영진 (CEO 주재)",
      costNote:
        "배분액 자체가 비용이다 — 기존 사업에서 이전되는 금액이며 새로 생기는 재원이 아니다.",
      prerequisites: [
        "재무 승인 한도 확인 (30억 이상)",
        "미확보 고객사 중장기 물량 계획 확보",
      ],
    },
    {
      id: "alt-legacy-first",
      tag: "2안",
      name: "기존 사업 구조 개선 우선",
      summary: "고정비 구조를 먼저 손보고 회수된 재원으로 신사업을 나중에 늘린다.",
      lever: {
        id: "legacy-save",
        label: "구조 개선 목표액",
        unit: "억",
        min: 0,
        max: 40,
        step: 5,
        base: 20,
        profitPerUnit: 0.6,
        secondaryLabel: "신사업 매출 비중",
        secondaryUnit: "%p",
        secondaryPerUnit: 0,
        costPerUnit: 0.3,
      },
      riskBands: [
        { upTo: 20, severity: "good" },
        { upTo: 30, severity: "warning" },
        { upTo: 40, severity: "serious" },
      ],
      riskNote:
        "회수는 가장 빠르지만 신사업 양산 시점 경쟁력을 포기한다. 경쟁사가 먼저 캐파를 확보하면 되돌리기 어렵다.",
      leadTime: "8~12주",
      owner: "생산본부 김상현",
      costNote: "구조 개선 실행에 드는 일회성 비용 (컨설팅·설비 조정).",
      prerequisites: [
        "공용 설비 배부 기준 재정리",
        "노사 협의 (인력 재배치 포함 시)",
      ],
    },
    {
      id: "alt-staged-allocation",
      tag: "3안",
      name: "조건부 분할 집행",
      summary: "1차 배분을 제한하고, 수율·수주 지표가 기준을 넘으면 2차를 집행한다.",
      lever: {
        id: "first-tranche",
        label: "1차 집행 비율",
        unit: "%",
        min: 0,
        max: 100,
        step: 10,
        base: 40,
        profitPerUnit: 0.12,
        secondaryLabel: "신사업 매출 비중",
        secondaryUnit: "%p",
        secondaryPerUnit: 0.03,
        costPerUnit: 0.35,
      },
      riskBands: [
        { upTo: 40, severity: "good" },
        { upTo: 70, severity: "warning" },
        { upTo: 100, severity: "serious" },
      ],
      riskNote:
        "효과가 가장 작다. 다만 회수 전망의 불확실성이 큰 지금 상황에서는 틀렸을 때의 손실도 가장 작다.",
      leadTime: "6주 (1차) · 조건 충족 시 2차",
      owner: "재무팀 한지훈",
      costNote: "1차 집행분. 2차는 수율 92% 및 신규 수주 확정 시에만 집행한다.",
      prerequisites: [
        "2차 집행 조건 지표와 판정 시점 합의",
        "분할 집행에 대한 이사회 사전 보고",
      ],
    },
  ],
};
