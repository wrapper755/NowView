/**
 * Management Evolution Lab Mock.
 *
 * 제안은 전부 **앞 화면들에서 실제로 드러난 공백**에서 나온다 — 임의로 지어낸 개선 항목을
 * 두면 루프가 학습한다는 이 화면의 주장이 무너진다:
 *   · 가동률 임계치 85%는 3일 연속 미달 후에야 울렸다 (bpm-process.ts의 start 노드).
 *   · Root Cause Agent는 물량·단가·원가·수율 축만 본다 — MCU 리드타임 26주 같은
 *     공급망 리스크는 별도 신호로만 잡혔다 (next-automotive.ts의 risk-mcu-leadtime).
 *   · 고정비 흡수율은 Cockpit에 있지만 KRI 임계치가 없다.
 *
 * 백테스트는 공식이 아니라 임계치별 결과 표다. 값 사이의 단조성(임계치를 조일수록
 * 감지·오탐 모두 증가)은 유지할 것.
 */

import type { EvolutionLab } from "@/lib/types/evolution";

export const evolutionLab: EvolutionLab = {
  subject: "파워트레인 가동률 임계치 이탈 대응",
  riskId: "risk-utilization",

  kris: [
    {
      id: "kri-utilization",
      label: "설비 가동률",
      unit: "%",
      currentThreshold: 85,
      recommendedThreshold: 87,
      detectBelow: true,
      step: 1,
      observedIssue:
        "85% 임계치는 3일 연속 미달한 뒤에야 울렸다. 그 시점에는 이미 분기 손익에 반영되어 되돌릴 여지가 적었다.",
      backtest: [
        { threshold: 83, detections: 2, falsePositives: 0, leadTimeDays: -4 },
        { threshold: 84, detections: 3, falsePositives: 1, leadTimeDays: -2 },
        { threshold: 85, detections: 4, falsePositives: 1, leadTimeDays: 0 },
        { threshold: 86, detections: 6, falsePositives: 3, leadTimeDays: 5 },
        { threshold: 87, detections: 8, falsePositives: 6, leadTimeDays: 8 },
        { threshold: 88, detections: 11, falsePositives: 11, leadTimeDays: 11 },
        { threshold: 89, detections: 14, falsePositives: 18, leadTimeDays: 13 },
        { threshold: 90, detections: 17, falsePositives: 26, leadTimeDays: 15 },
      ],
    },
    {
      id: "kri-bms-yield",
      label: "BMS 라인 수율",
      unit: "%",
      currentThreshold: 90,
      recommendedThreshold: 92,
      detectBelow: true,
      step: 1,
      observedIssue:
        "양산 6개월차 라인에 안정화 라인과 같은 임계치를 적용했다. 초기 라인은 더 조인 기준이 필요하다.",
      backtest: [
        { threshold: 88, detections: 1, falsePositives: 0, leadTimeDays: -9 },
        { threshold: 89, detections: 2, falsePositives: 0, leadTimeDays: -5 },
        { threshold: 90, detections: 3, falsePositives: 1, leadTimeDays: 0 },
        { threshold: 91, detections: 5, falsePositives: 2, leadTimeDays: 6 },
        { threshold: 92, detections: 7, falsePositives: 4, leadTimeDays: 12 },
        { threshold: 93, detections: 10, falsePositives: 9, leadTimeDays: 16 },
        { threshold: 94, detections: 13, falsePositives: 16, leadTimeDays: 19 },
        { threshold: 95, detections: 16, falsePositives: 25, leadTimeDays: 21 },
      ],
    },
  ],

  proposals: [
    {
      id: "prop-utilization-threshold",
      kind: "kri-threshold",
      title: "설비 가동률 감지 임계치 85% → 87% 상향",
      triggeredBy: "risk-utilization",
      rationale:
        "현행 임계치는 손익 반영이 끝난 뒤에야 울린다. 백테스트상 87%로 올리면 평균 8일 앞서 감지된다.",
      before: "가동률 < 85%, 3일 연속",
      after: "가동률 < 87%, 2일 연속",
      expectedEffect: "감지 건수 4건 → 8건, 평균 8일 조기 감지",
      tradeoff: "오탐이 1건 → 6건으로 늘어난다. 현업 확인 부하가 커지므로 1차 확인은 Agent가 맡는다.",
      owner: "생산본부 김상현",
    },
    {
      id: "prop-supply-chain-axis",
      kind: "agent-rule",
      title: "Root Cause Agent에 공급망 축 추가",
      triggeredBy: "risk-mcu-leadtime",
      rationale:
        "현재 원인 분해는 물량·단가·원가·수율 4축뿐이다. MCU 리드타임 26주는 별도 신호로만 잡혀 원인 기여도에 들어오지 못했다.",
      before: "기여도 분해 축: 물량 / 단가 / 원가 / 수율",
      after: "기여도 분해 축: 물량 / 단가 / 원가 / 수율 / 공급망",
      expectedEffect: "공급망 기인 편차가 원인 분해에 직접 드러나 대안 도출 단계로 이어진다.",
      tradeoff: "축이 늘면 기여도가 분산되어 주 원인 판별이 흐려질 수 있다. 축별 최소 기여도 임계를 둔다.",
      owner: "전장기술팀 이도현",
    },
    {
      id: "prop-absorption-kri",
      kind: "metric-definition",
      title: "고정비 흡수율을 KRI로 승격",
      triggeredBy: "risk-utilization",
      rationale:
        "고정비 흡수율은 Cockpit에 표시되지만 감지 임계치가 없다. 이번 건에서 원인 기여도 24%를 차지했는데도 독립 신호를 내지 못했다.",
      before: "표시 지표 (임계치 없음)",
      after: "KRI 승격, 임계치 95% 미만 시 감지",
      expectedEffect: "가동률과 독립적으로 고정비 구조 악화를 감지한다.",
      tradeoff: "가동률 하락과 동반 발생하는 경우가 많아 중복 알림이 생긴다. 동일 원인 신호는 묶어서 올린다.",
      owner: "재무팀 한지훈",
    },
  ],

  applied: [
    {
      id: "applied-cr-threshold",
      date: "2026-07-15",
      kind: "kri-threshold",
      summary: "완성차 CR 요구율 감지 임계치 신설 (-1.5% 초과 시)",
      observedEffect: "9월 CR -3.2% 통보를 통보 당일 감지해 Management Review로 직행했다.",
    },
    {
      id: "applied-source-required",
      date: "2026-05-20",
      kind: "agent-rule",
      summary: "Agent 산출물에 참조 데이터 소스 명시 의무화",
      observedEffect: "경영진 검토 시 근거 확인 요청이 줄어 Review 소요 시간이 단축되었다.",
    },
  ],
};
