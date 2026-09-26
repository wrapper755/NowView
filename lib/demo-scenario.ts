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

import { reviewCase } from "@/lib/mock-data/review-case";
import type { ManagementStage } from "@/lib/types/cockpit";
import type { ReviewDecision } from "@/lib/types/workspace";
import { simulateAlternative } from "@/services/agent-orchestrator";

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

const recommended = reviewCase.alternatives.find(
  (a) => a.id === reviewCase.recommendedAlternativeId,
);
if (!recommended) {
  throw new Error("데모 시나리오: Agent 권고안을 찾을 수 없다");
}

/**
 * 데모가 자동으로 적용하는 결정.
 *
 * 금액은 `simulateAlternative`로 계산해 화면·API와 같은 값이 되게 한다(하드코딩 금지).
 * `decidedAt`은 **고정 문자열**이다 — 스토어가 모듈 로드 시점에 만들어지므로 `new Date()`를
 * 쓰면 서버와 클라이언트 값이 달라져 하이드레이션이 깨진다.
 */
export const DEMO_DECISION: ReviewDecision = {
  alternativeId: recommended.id,
  leverValue: recommended.lever.base,
  profitImpact: simulateAlternative(recommended, recommended.lever.base).profitImpact,
  rationale:
    "가동률 회복이 구조적 문제에 대한 정면 대응이라 판단한다. 전환 기간 중 납기 리스크는 2개 라인으로 제한해 감수한다.",
  decidedAt: "2026-09-30 15:20",
};

export const demoScenario: DemoScene[] = [
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

/** 자동 재생 시 장면 전환 간격(ms). 내레이션을 읽을 시간을 기준으로 잡았다. */
export const DEMO_SCENE_INTERVAL_MS = 7000;
