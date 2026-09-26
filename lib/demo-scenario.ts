/**
 * 데모 시나리오 각본.
 *
 * 다섯 화면을 6단계 루프 순서로 잇는다. Mock 데이터가 아니라 **연출 설정**이므로
 * `lib/mock-data/`가 아니라 여기에 둔다.
 *
 * 각 장면은 도달했을 때의 **상태를 전부 선언한다**(화면·BPM 지점·승인 여부).
 * 이전 장면에서의 변화량이 아니라 목표 상태를 적기 때문에, 어느 장면으로 건너뛰어도
 * 같은 결과가 된다 — 스크러버로 아무 데나 찍어도 앞뒤가 맞는다.
 */

import type { ManagementStage } from "@/lib/types/cockpit";

export interface DemoScene {
  id: string;
  /** 이동할 화면 경로. */
  route: string;
  /** 이 장면에서의 BPM 진행 지점(`bpmProcess.sequence` 인덱스). */
  step: number;
  stage: ManagementStage;
  title: string;
  /**
   * 이 장면에서 무엇을 보아야 하는지.
   *
   * **2줄 이내로 유지할 것.** 플레이어 높이가 늘어나면 `app/layout.tsx`의 본문 하단 여백
   * (`pb-48`, 192px)을 넘어 페이지 맨 아래 콘텐츠를 가린다. 현재 최대 높이는 170px다.
   */
  narration: string;
  /** 이 장면에서 Management Review 승인이 이미 이루어진 상태인가. */
  decided: boolean;
  /**
   * 이 장면에서 보여 줄 KRI 튜닝 상태 (⑤ Evolution Lab).
   *
   * 없으면 모든 KRI를 현행 임계치로 되돌린다 — 장면은 증분이 아니라 목표 상태를
   * 선언하므로, 이 필드가 없다는 것은 "튜닝하지 않은 상태"를 뜻한다.
   */
  kri?: { id: string; threshold: number };
}


export const profitabilityScenes: DemoScene[] = [
  {
    id: "sensing",
    route: "/",
    step: 0,
    stage: "risk-sensing",
    title: "이상 징후 감지",
    narration:
      "Cockpit이 영업이익 Gap -69억과 심각 등급 신호 2건을 띄운다. 파워트레인 가동률이 82.1%로 임계치 85%를 밑돌았다.",
    decided: false,
  },
  {
    id: "agent-analysis",
    route: "/bpm-tracker",
    step: 2,
    stage: "risk-sensing",
    title: "Agent 데이터 수집·원인 분석",
    narration:
      "Risk Sensing Agent가 시계열을 모으고 Root Cause Agent가 기여도를 분해한다. 아직 실행 중인 Agent의 산출물은 표시되지 않는다.",
    decided: false,
  },
  {
    id: "escalation",
    route: "/bpm-tracker",
    step: 4,
    stage: "management-review",
    title: "에스컬레이션 · 대안 시뮬레이션",
    narration:
      "게이트웨이가 부서 간 조정이 필요하다고 판단해 현업 통제 경로(점선)를 건너뛴다. Simulation Agent가 대안 3안의 손익 영향을 산출한다.",
    decided: false,
  },
  {
    id: "review",
    route: "/workspace",
    step: 5,
    stage: "management-review",
    title: "사람의 판단",
    narration:
      "여기서 프로세스가 멈춘다. Agent는 분석까지만 하고, 대안 선택과 승인은 경영진의 책임이다. 사유 없이는 승인 버튼이 눌리지 않는다.",
    decided: false,
  },
  {
    id: "action",
    route: "/bpm-tracker",
    step: 6,
    stage: "management-action",
    title: "승인 · 실행 과제 배포",
    narration:
      "1안 라인 재배치가 승인되어 프로세스가 Management Action으로 넘어갔다. 결정 사유가 과제에 함께 실린다.",
    decided: true,
  },
  {
    id: "rolling",
    route: "/rolling-plan",
    step: 7,
    stage: "rolling-plan",
    title: "Forecast 갱신 · 잔여 Gap",
    narration:
      "승인 과제 18억은 아직 미반영이라 현재 Forecast 359억은 그대로다. 반영 시 377억, 잔여 Gap -51억. Target 428억은 바뀌지 않는다.",
    decided: true,
  },
  {
    id: "evolution",
    route: "/evolution",
    step: 8,
    stage: "management-evolution",
    title: "감지 체계 개선",
    narration:
      "이번 건에서 감지가 늦었다는 사실이 드러났다. 임계치를 87%로 올려 두었다 — 8일 앞서 잡히지만 오탐은 1건에서 6건으로 늘어난다.",
    decided: true,
    kri: { id: "kri-utilization", threshold: 87 },
  },
  {
    id: "next-loop",
    route: "/",
    step: 9,
    stage: "management-evolution",
    title: "루프 종료 · 다음 사이클",
    narration:
      "한 바퀴가 끝났다. 목표는 그대로 두고 전망과 실행계획만 갱신했으며, 남은 Gap은 다음 루프가 이어받는다.",
    decided: true,
  },
];

/**
 * 시나리오 2 — 납기 준수. 게이트웨이에서 **현업 통제 경로가 선택되는** 흐름이다.
 * 시나리오 1이 에스컬레이션 경로였으므로, 둘을 합쳐야 기획안 3.3의 두 경로가 모두 보인다.
 */
export const deliveryScenes: DemoScene[] = [
  {
    id: "d-sensing",
    route: "/",
    step: 0,
    stage: "risk-sensing",
    title: "납기 이탈 감지",
    narration:
      "주간 납기 준수율이 94.2%로 임계 97%를 밑돌았다. 4주간 지연 출하 37건이 모두 전장 ECU 품번이다.",
    decided: false,
  },
  {
    id: "d-analysis",
    route: "/bpm-tracker",
    step: 2,
    stage: "risk-sensing",
    title: "공급망 기인 원인 분해",
    narration:
      "Supply Risk Agent가 MCU 입고 지연 58%, 긴급 오더 충돌 27%로 기여도를 나눈다. 공급사 회신일이 추정치라 신뢰도는 보통이다.",
    decided: false,
  },
  {
    id: "d-gateway",
    route: "/bpm-tracker",
    step: 3,
    stage: "operation-control",
    title: "현업 처리 경로 선택",
    narration:
      "이번에는 게이트웨이가 구매·생산 권한 내라고 판단해 경영 검토를 건너뛴다. 시나리오 1과 반대 경로이며, 점선이 반대쪽으로 간다.",
    decided: false,
  },
  {
    id: "d-control",
    route: "/workspace",
    step: 4,
    stage: "operation-control",
    title: "현업의 조치 선택",
    narration:
      "결정 주체가 경영진이 아니라 구매본부다. 권한 층위는 달라도 근거 제시와 사유 기록 규칙은 똑같이 적용된다.",
    decided: false,
  },
  {
    id: "d-verify",
    route: "/bpm-tracker",
    step: 5,
    stage: "operation-control",
    title: "통제 효과 확인",
    narration:
      "안전재고 상향 적용 2주 후 납기 준수율이 96.1%로 회복됐다. 다만 임계 97%에는 아직 못 미친다.",
    decided: true,
  },
  {
    id: "d-rolling",
    route: "/rolling-plan",
    step: 6,
    stage: "rolling-plan",
    title: "두 안건이 같은 Plan에 모인다",
    narration:
      "수익성 안건과 납기 안건의 승인 과제가 같은 Rolling Plan에 함께 잡힌다. 전사 Gap은 두 시나리오가 나눠 메운다.",
    decided: true,
  },
];

/**
 * 시나리오 3 — 재원 배분. 앞 둘이 "무엇을 고칠 것인가"였다면 이번은
 * "한정된 재원을 어디에 둘 것인가"다. 어느 안을 골라도 반대편이 준다.
 */
export const allocationScenes: DemoScene[] = [
  {
    id: "a-sensing",
    route: "/",
    step: 0,
    stage: "risk-sensing",
    title: "투자회수 지연 감지",
    narration:
      "전장 누적 투자 840억 대비 회수가 58.0%로 임계 75%를 밑돈다. 사업부 편차가 아니라 전사 포트폴리오 신호다.",
    decided: false,
  },
  {
    id: "a-analysis",
    route: "/bpm-tracker",
    step: 2,
    stage: "risk-sensing",
    title: "회수 지연 원인 분해",
    narration:
      "Portfolio Agent가 양산 시점 이동 46%로 기여도를 나눈다. 3년 전망을 분기 예보로 추정해 신뢰도는 낮음이다.",
    decided: false,
  },
  {
    id: "a-escalation",
    route: "/bpm-tracker",
    step: 4,
    stage: "management-review",
    title: "전사 배분으로 에스컬레이션",
    narration:
      "사업부 권한을 넘는 재원 이동이라 전사 경영 검토로 올라간다. Simulation Agent가 배분 대안 3안을 산출한다.",
    decided: false,
  },
  {
    id: "a-review",
    route: "/workspace",
    step: 5,
    stage: "management-review",
    title: "배분 결정 — 비용 0인 안이 없다",
    narration:
      "어느 안을 골라도 반대편 재원이 준다. 회수가 가장 빠른 2안은 신사업 시점 경쟁력을 포기하는 선택이기도 하다.",
    decided: false,
  },
  {
    id: "a-action",
    route: "/bpm-tracker",
    step: 6,
    stage: "management-action",
    title: "투자·운영계획 반영",
    narration:
      "3안 조건부 분할이 승인됐다. 회수 전망의 불확실성이 큰 상황에서 틀렸을 때의 손실이 가장 작은 선택이다.",
    decided: true,
  },
  {
    id: "a-rolling",
    route: "/rolling-plan",
    step: 7,
    stage: "rolling-plan",
    title: "세 안건이 한 Plan에 모인다",
    narration:
      "수익성·납기·배분 세 안건의 승인 과제가 같은 Rolling Plan에 잡힌다. 전사 Gap은 셋이 나눠 메운다.",
    decided: true,
  },
];

/** 자동 재생 시 장면 전환 간격(ms). 내레이션을 읽을 시간을 기준으로 잡았다. */
export const DEMO_SCENE_INTERVAL_MS = 7000;
