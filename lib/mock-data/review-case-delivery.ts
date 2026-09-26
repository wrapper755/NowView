/**
 * 시나리오 2의 조치 선택 안건 — 전장 ECU 납기 준수율 하락.
 *
 * **시나리오 1과 결정 주체가 다르다.** 여기서는 경영진이 아니라 구매본부가 권한 내에서
 * 고른다(기획안 3.3: "사전에 정한 권한과 기준 안에서 처리할 수 있는 사항은 현업에서
 * 대응한다"). 화면과 타입은 그대로 재사용하고 담당자만 바뀐다 — 사람–Agent 협업 원칙은
 * 결재 층위와 무관하게 동일하기 때문이다.
 *
 * 수치 연동:
 *   · 각 대안 `lever.base × profitPerUnit`은 Simulation 없이 현업이 직접 고르는 값이다.
 *   · `profitGap`(-69억)은 전사 영업이익 Gap이며 시나리오 1과 같은 값이다 — 두 안건이
 *     같은 Gap을 나눠 메운다.
 *   · 1안 효과 +2.6%p를 94.2%에 더해도 96.8%로 임계 97%에 못 미친다. 조치 하나로는
 *     부족하다는 사실을 데이터에서부터 유지한다.
 */

import type { ReviewCase } from "@/lib/types/workspace";

export const deliveryReviewCase: ReviewCase = {
  id: "review-2026-0921-delivery",
  subject: "전장 ECU 납기 준수율 하락 대응",
  processId: "proc-2026-0921-delivery",
  riskId: "risk-delivery",
  profitGap: -69,

  report: [
    {
      id: "detection",
      title: "감지",
      body: "주간 납기 준수율이 94.2%로 임계 97%를 밑돌았다. 4주간 지연 출하 37건이 모두 전장 ECU 품번이며 평균 지연은 3.4일이다.",
      sources: [
        { name: "WMS 출하 실적", quality: "complete" },
        { name: "고객 납기 약정 마스터", quality: "complete" },
        {
          name: "긴급 오더 접수 이력",
          quality: "partial",
          caveat: "구두 접수분은 시스템에 남지 않아 실제 긴급 오더는 더 많을 수 있다.",
        },
      ],
      confidence: "high",
    },
    {
      id: "root-cause",
      title: "원인 분해",
      body: "기여도는 MCU 입고 지연 58%, 긴급 오더 우선순위 충돌 27%, 라인 전환 준비 9%, 기타 6%다. MCU 리드타임 26주 이슈가 납기로 전이된 형태다.",
      sources: [
        { name: "구매 입고 실적", quality: "complete" },
        {
          name: "공급사 납기 회신",
          quality: "estimated",
          caveat: "공급사 통보 예정일이며 실제 입고와 평균 4일 차이가 있었다.",
        },
        {
          name: "생산 계획 변경 이력",
          quality: "partial",
          caveat: "라인 전환 관련 변경은 시나리오 1 승인 이후분만 기록돼 있다.",
        },
      ],
      confidence: "medium",
      confidenceNote: "공급사 회신일이 추정치라 MCU 기여도 58%는 ±7%p 범위로 본다.",
    },
    {
      id: "alternatives",
      title: "대안 도출",
      body: "재고 완충(1안), 공급 다변화(2안), 수요 통제(3안) 세 축으로 구성했다. 셋 모두 구매·생산 권한 안에서 집행 가능해 경영 검토 없이 현업에서 결정한다.",
      sources: [
        { name: "안전재고 정책 기준", quality: "complete" },
        {
          name: "대체 소자 후보 목록",
          quality: "estimated",
          caveat: "품질 검증 전 후보이며 승인 통과율은 과거 기준 약 60%다.",
        },
      ],
      confidence: "medium",
      confidenceNote: "대체 소자 승인 통과 여부가 2안 효과를 좌우한다.",
    },
  ],

  escalations: [
    {
      id: "esc-emergency-order",
      question: "긴급 오더를 접수 단계에서 제한할 수 있는가?",
      reason:
        "구두 접수분이 시스템에 없어 Agent는 실제 긴급 오더 규모를 알 수 없다. 영업 운영 규칙은 데이터로 확인되지 않는다.",
      owner: "영업본부 박지우",
      ifUnanswered:
        "시스템 기록분만으로 27% 기여도를 산정했다. 구두 접수가 많다면 3안의 효과가 과소평가된다.",
    },
  ],

  recommendedAlternativeId: "alt-safety-stock",

  alternatives: [
    {
      id: "alt-safety-stock",
      tag: "1안",
      name: "MCU 안전재고 상향",
      summary: "핵심 소자 안전재고를 늘려 입고 지연이 출하 지연으로 전이되는 것을 막는다.",
      lever: {
        id: "stock-days",
        label: "안전재고 추가 일수",
        unit: "일",
        min: 0,
        max: 20,
        step: 1,
        base: 13,
        profitPerUnit: 0.4,
        secondaryLabel: "납기 준수율 개선",
        secondaryUnit: "%p",
        secondaryPerUnit: 0.2,
        costPerUnit: 0.3,
      },
      riskBands: [
        { upTo: 13, severity: "good" },
        { upTo: 17, severity: "warning" },
        { upTo: 20, severity: "serious" },
      ],
      riskNote:
        "재고 일수를 늘릴수록 운전자본이 묶이고 설계 변경 시 진부화 위험이 커진다. 현 재고 12일에 13일을 더하면 25일이다.",
      leadTime: "4~6주",
      owner: "구매본부 최민서",
      costNote: "운전자본 증가분의 금융비용(연간 환산). 일회성 지출이 아니라 지속 비용이다.",
      prerequisites: [
        "공급사 추가 물량 확보 확약",
        "전장 창고 보관 공간 확보",
      ],
    },
    {
      id: "alt-second-source",
      tag: "2안",
      name: "대체 소자 승인 가속",
      summary: "대체 MCU 승인 절차에 인력을 투입해 단일 공급 의존을 낮춘다.",
      lever: {
        id: "engineers",
        label: "투입 인력",
        unit: "명",
        min: 0,
        max: 6,
        step: 1,
        base: 3,
        profitPerUnit: 0.9,
        secondaryLabel: "납기 준수율 개선",
        secondaryUnit: "%p",
        secondaryPerUnit: 0.5,
        costPerUnit: 0.2,
      },
      riskBands: [
        { upTo: 3, severity: "good" },
        { upTo: 5, severity: "warning" },
        { upTo: 6, severity: "serious" },
      ],
      riskNote:
        "품질 검증에 12주가 걸리며 과거 승인 통과율은 약 60%다. 인력을 빼오면 BMS 수율 과제가 늦어진다.",
      leadTime: "12~16주",
      owner: "전장기술팀 이도현",
      costNote: "전담 인력 투입에 따른 인건비 배분 (기간 한정).",
      prerequisites: [
        "고객 설계 변경 승인 (대체 소자 적용)",
        "BMS 수율 개선 TF 일정 재조정",
      ],
    },
    {
      id: "alt-order-priority",
      tag: "3안",
      name: "긴급 오더 우선순위 규칙 재설정",
      summary: "긴급 오더가 일반 오더를 밀어내는 비율을 제한해 약정 납기를 보호한다.",
      lever: {
        id: "cap-ratio",
        label: "긴급 오더 제한 비율",
        unit: "%",
        min: 0,
        max: 40,
        step: 5,
        base: 20,
        profitPerUnit: 0.08,
        secondaryLabel: "납기 준수율 개선",
        secondaryUnit: "%p",
        secondaryPerUnit: 0.06,
        costPerUnit: 0,
      },
      riskBands: [
        { upTo: 20, severity: "good" },
        { upTo: 30, severity: "warning" },
        { upTo: 40, severity: "critical" },
      ],
      riskNote:
        "제한 비율이 높을수록 고객 긴급 요청 대응력이 떨어진다. 영업 합의 없이 올리면 고객 불만으로 전이된다.",
      leadTime: "즉시",
      owner: "구매본부 최민서",
      costNote: "추가 지출 없음. 다만 긴급 대응력 저하는 수치로 잡히지 않는 비용이다.",
      prerequisites: ["영업본부와 긴급 오더 접수 기준 합의"],
    },
  ],
};
