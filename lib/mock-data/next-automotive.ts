/**
 * (주)넥스트오토모티브 FY2026 Mock 스냅샷.
 *
 * CLAUDE.md 2.1의 가상 고객사 스펙(매출 1조 200억 / 목표 영업이익 428억 / 4.2%)을 그대로 따른다.
 *
 * 수치 정합성 — 데이터를 수정할 때 아래 항등식을 반드시 유지한다:
 *   · 사업부 매출 Target 합 = 전사 매출 Target      (7,650 + 2,550 = 10,200)
 *   · 사업부 매출 Forecast 합 = 전사 매출 Forecast  (7,320 + 2,620 = 9,940)
 *   · 사업부 영업이익 Target 합 = 428               (390 + 38)
 *   · 사업부 영업이익 Forecast 합 = 359             (337 + 22)
 *   · bridge의 delta 합 = 359 − 428 = −69
 * 마지막 항은 `assertBridgeBalances`가, 나머지는 단위 테스트 대신 이 주석이 근거다.
 */

import type { CompanySnapshot, Division } from "@/lib/types/cockpit";

const powertrainChassis: Division = {
  id: "powertrain-chassis",
  name: "파워트레인/샤시",
  kind: "legacy",
  tagline: "배기 시스템 · 컨트롤 암 (내연/하이브리드)",
  revenueShare: 75,
  revenue: { target: 7650, forecast: 7320 },
  operatingProfit: { target: 390, forecast: 337 },
  metrics: [
    {
      id: "utilization",
      label: "설비 가동률",
      value: 82.1,
      target: 88,
      unit: "%",
      higherIsBetter: true,
    },
    {
      id: "fixed-cost-absorption",
      label: "고정비 흡수율",
      value: 91.4,
      target: 100,
      unit: "%",
      higherIsBetter: true,
    },
    {
      id: "first-pass-yield",
      label: "직행률",
      value: 96.4,
      target: 98,
      unit: "%",
      higherIsBetter: true,
    },
  ],
  concerns: [
    "전동화 전환에 따른 물량 감소로 가동률 하락",
    "고정비 흡수율 방어 한계 도달",
    "완성차 2026 CR(단가 인하) 압박 확대",
  ],
};

const ecoElectronics: Division = {
  id: "eco-electronics",
  name: "친환경/전장",
  kind: "growth",
  tagline: "배터리 관리 시스템(BMS) · 전동식 조향 제어기(ECU)",
  revenueShare: 25,
  revenue: { target: 2550, forecast: 2620 },
  operatingProfit: { target: 38, forecast: 22 },
  metrics: [
    {
      id: "bms-yield",
      label: "BMS 라인 수율",
      value: 87.2,
      target: 95,
      unit: "%",
      higherIsBetter: true,
    },
    {
      id: "sop-adherence",
      label: "양산 일정 준수율",
      value: 78.0,
      target: 95,
      unit: "%",
      higherIsBetter: true,
    },
    {
      id: "critical-part-stock",
      label: "핵심 소자 재고",
      value: 12,
      target: 30,
      unit: "일",
      higherIsBetter: true,
    },
  ],
  concerns: [
    "신차 양산 시점 불확실성 (K-EV9 3주 지연)",
    "초기 수율 안정화 지연으로 손익 기여 미달",
    "차량용 반도체·핵심 소자 공급망 리스크",
  ],
};

export const nextAutomotive: CompanySnapshot = {
  name: "(주)넥스트오토모티브",
  englishName: "Next Automotive Corp.",
  period: "FY2026 · 9월 마감 실적 반영",

  revenue: { target: 10200, forecast: 9940 },
  operatingProfit: { target: 428, forecast: 359 },
  committedActionRecovery: 20,

  divisions: [powertrainChassis, ecoElectronics],

  bridge: [
    {
      id: "target",
      label: "Target 영업이익",
      kind: "anchor",
      value: 428,
      note: "FY2026 확정 목표 (영업이익률 4.2%)",
    },
    {
      id: "pt-volume",
      label: "파워트레인 물량 감소",
      kind: "delta",
      value: -48,
      driver: "volume",
      note: "전동화 전환으로 내연 부품 발주 축소, 가동률 88% → 82.1%",
    },
    {
      id: "oem-cr",
      label: "완성차 CR 단가 인하",
      kind: "delta",
      value: -35,
      driver: "price",
      note: "2026 CR 요구 -3.2% 통보 (기준 -1.5%)",
    },
    {
      id: "raw-material",
      label: "원자재·구매단가 상승",
      kind: "delta",
      value: -24,
      driver: "cost",
      note: "알루미늄 잉곳 +8.4% QoQ 외 사급 단가 인상",
    },
    {
      id: "bms-yield-loss",
      label: "BMS 초기 수율 손실",
      kind: "delta",
      value: -19,
      driver: "yield",
      note: "BMS 라인 수율 87.2% (목표 95%), 폐기·재작업 비용 증가",
    },
    {
      id: "ee-volume",
      label: "전장 신규 물량 증가",
      kind: "delta",
      value: 22,
      driver: "volume",
      note: "ECU 신규 수주 반영, 전장 매출 Target 대비 +70억",
    },
    {
      id: "fixed-cost-save",
      label: "고정비 절감·판관비 통제",
      kind: "delta",
      value: 15,
      driver: "cost",
      note: "설비 보전비 이연 및 판관비 집행률 통제",
    },
    {
      id: "action-recovery",
      label: "확정 Action 회수 효과",
      kind: "delta",
      value: 20,
      driver: "action",
      note: "Management Action 3건 확정분 (담당·기한 배포 완료)",
    },
    {
      id: "forecast",
      label: "Forecast 영업이익",
      kind: "anchor",
      value: 359,
      note: "최신 가정 반영 전망 (영업이익률 3.6%)",
    },
  ],

  risks: [
    {
      id: "risk-utilization",
      title: "파워트레인 가동률 임계치 이탈",
      detail:
        "내연 부품 발주 축소가 3개월 연속 이어지며 고정비 흡수율이 함께 하락. 라인 재배치 또는 전장 물량 이관 검토가 필요하다.",
      severity: "critical",
      division: "파워트레인/샤시",
      kri: { label: "설비 가동률", value: "82.1%", threshold: "85.0%" },
      stage: "management-review",
      owner: "생산본부 김상현",
      origin: "observed",
    },
    {
      id: "risk-oem-cr",
      title: "완성차 2026 CR 요구 기준 초과",
      detail:
        "주요 고객 2사가 -3.2% 단가 인하를 통보. 내부 기준(-1.5%) 대비 1.7%p 초과로 연간 영업이익 35억 잠식이 전망된다.",
      severity: "critical",
      division: "전사",
      kri: { label: "CR 요구율", value: "-3.2%", threshold: "-1.5%" },
      stage: "management-review",
      owner: "영업본부 박지우",
      origin: "leading",
      assumption:
        "통보된 -3.2%가 2026년 공급 물량 전량에 적용된다고 가정했다. 품번별 협상 결과에 따라 달라진다.",
    },
    {
      id: "risk-bms-yield",
      title: "BMS 라인 초기 수율 정착 지연",
      detail:
        "양산 6개월차에도 수율이 목표를 8%p 밑돌아 폐기·재작업 비용이 누적. 공정 파라미터 재설정 과제가 진행 중이다.",
      severity: "serious",
      division: "친환경/전장",
      kri: { label: "BMS 라인 수율", value: "87.2%", threshold: "95.0%" },
      stage: "management-action",
      owner: "전장기술팀 이도현",
      origin: "observed",
    },
    {
      id: "risk-mcu-leadtime",
      title: "차량용 MCU 리드타임 급증",
      detail:
        "핵심 소자 재고가 12일분으로 축소. 대체 소자 승인 절차를 병행하지 않으면 ECU 양산 차질로 전이될 수 있다.",
      severity: "serious",
      division: "친환경/전장",
      kri: { label: "MCU 리드타임", value: "26주", threshold: "18주" },
      stage: "operation-control",
      owner: "구매본부 최민서",
      origin: "leading",
      assumption:
        "현 리드타임 26주가 최소 2개 분기 지속된다고 가정했다. 대체 소자가 승인되면 성립하지 않는다.",
    },
    {
      id: "risk-aluminum",
      title: "알루미늄 잉곳 구매단가 상승",
      detail:
        "전분기 대비 8.4% 상승으로 감지 임계치를 초과. 고객 원자재가 연동 조항 적용 협의를 개시했다.",
      severity: "warning",
      division: "파워트레인/샤시",
      kri: { label: "구매단가 변동", value: "+8.4% QoQ", threshold: "+5.0% QoQ" },
      stage: "operation-control",
      owner: "구매본부 최민서",
      origin: "observed",
    },
    {
      id: "risk-sop-delay",
      title: "K-EV9 양산 일정 지연",
      detail:
        "고객 양산 시점이 3주 순연되어 전장 매출 인식 시점이 이동. 분기 배분 Forecast 재산정이 필요하다.",
      severity: "warning",
      division: "친환경/전장",
      kri: { label: "양산 일정 준수율", value: "78.0%", threshold: "95.0%" },
      stage: "rolling-plan",
      owner: "사업기획팀 정하윤",
      origin: "leading",
      assumption:
        "고객이 통보한 3주 순연에서 추가 변경이 없다고 가정했다. 양산 일정은 재차 이동한 전례가 있다.",
    },
  ],
};
