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
      id: "prop-control-escalation",
      kind: "process-rule",
      title: "예방 통제 미수행의 자동 에스컬레이션",
      triggeredBy: "risk-utilization",
      rationale:
        "라인 재배치 사전 검토(월간 예방 통제)가 3개월 연속 물량 하향에도 착수되지 않았는데, 통제 미수행은 월간 통제 보고에만 기록되어 경영 검토로 올라오지 않았다. 이번 건이 늦어진 실질적 원인이다.",
      before: "통제 미수행은 월간 통제 보고에 기록만 한다",
      after: "예방 통제 2회 연속 미수행 시 Management Review 안건으로 자동 등록",
      expectedEffect: "통제 공백이 실적 악화로 드러나기 전에 경영 검토로 올라온다.",
      tradeoff:
        "Review 안건이 늘어 경영진 검토 부하가 커진다. 자동 등록 건은 요약 보고로 먼저 올리고 필요 시에만 정식 안건화한다.",
      owner: "사업기획팀 정하윤",
    },
    {
      id: "prop-effect-verification",
      kind: "process-rule",
      title: "효과 검증을 Management Action 종료 조건에 포함",
      triggeredBy: "효과 검증 완료율 33%",
      rationale:
        "과제 상태가 완료/미완료로만 관리되어, 목표 회수액을 실제로 회수했는지 확인하지 않은 채 종료된 과제가 있다. 반영 완료 과제 3건 중 검증이 끝난 것은 1건뿐이다.",
      before: "과제 완료 = 실행 종료. 회수 실적은 별도 집계만 한다",
      after: "목표 회수액 대비 실현액 검증까지 마쳐야 완료 처리",
      expectedEffect:
        "예상 효과와 실현 효과의 차이가 과제 단위로 남아 다음 대안 산정의 근거가 된다.",
      tradeoff:
        "검증까지 완료 처리가 미뤄져 과제 이행률이 일시적으로 낮아 보인다. 이행률과 검증 완료율을 분리해 본다.",
      owner: "재무팀 한지훈",
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
