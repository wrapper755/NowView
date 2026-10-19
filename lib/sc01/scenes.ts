/**
 * SC01 데모 장면 — SC01 설계서 2.10 「기본 시연 순서」.
 *
 * **장면은 엔진 각본의 한 지점(`script`)과 화면 하나를 가리킨다.** 상태를 화면이 지어내지
 * 않는다 — 앞으로 가면 엔진이 그 단계를 실제로 실행하고(`POST …/script/{i}`), 뒤로 가면
 * 그 시점의 이력을 읽기만 한다(`GET …/history/{seq}`). 각본(누가·언제·무엇을)은 엔진
 * `app/sc01/demo.py`에 있고 여기에는 화면 연출만 있다.
 */

import type { HistoryEntry } from "@/lib/sc01/types";

export interface Sc01Scene {
  id: string;
  /** 엔진 각본 지점. -1 = S0(사건 전 기준 적재). */
  script: number;
  route: string;
  stage: string;
  title: string;
  narration: string;
}

export const SC01_SCENES: Sc01Scene[] = [
  {
    id: "overview",
    script: -1,
    route: "/",
    stage: "성과·전망 모니터링",
    title: "전체 현황 확인",
    narration:
      "2027년 6월 15일 저녁. A제품·울산공장 a~e모델의 목표·실적·승인 전망(F01)이다. 7월 a·b모델은 이미 목표 대비 5% 부족해 관심 이슈가 열려 있다.",
  },
  {
    id: "receive",
    script: 0,
    route: "/plans",
    stage: "Risk 감지",
    title: "변경계획 수신",
    narration:
      "6/16 09:00 고객의 두 번째 월간 생산계획(CP02)이 들어온다. 15행 중 b모델 7월만 9,500→8,800대분으로 바뀌었다. 시스템이 자동 검증하고 영업담당에게 원천 확인을 배정한다.",
  },
  {
    id: "verify",
    script: 1,
    route: "/plans",
    stage: "Operation Control",
    title: "원천 확인 (CT01)",
    narration:
      "영업담당이 고객·모델·월, 월 전체 물량인지, 이미 당사 배정 물량인지를 확인한다. 공급 점유율 40%를 다시 곱하지 않는다. 확인은 전망 승인이 아니다.",
  },
  {
    id: "calculate",
    script: 2,
    route: "/risk",
    stage: "Risk 감지",
    title: "영향 확인 — 비교 계산",
    narration:
      "F01을 복제하고 확인된 7~9월만 덮어 검토 전망 F02를 만든다. b모델 7월: 달성률 88%, 추가 감소 700대분(7.37%), 공헌이익 감소 1,400만원 — 세 지표 모두 중요. 기존 ISSUE-B07이 관심에서 중요로 오른다.",
  },
  {
    id: "sales-review",
    script: 3,
    route: "/risk",
    stage: "Operation Control",
    title: "처리 경로 판단 (CT02)",
    narration:
      "영업팀장이 변경의 의미와 지속성을 검토하고 의견·근거를 남긴다. 경보는 바꾸지 않는다. 중요이므로 현업 검토와 Management Review가 함께 열린다.",
  },
  {
    id: "dispatch",
    script: 4,
    route: "/tasks",
    stage: "Operation Control",
    title: "현업 검토 배정 (CT03)",
    narration:
      "생산·자재 영향 검토를 각각 별도 업무로 배정한다. 기한은 다음 영업일 18시. 경보가 없었어도 이 검토는 했어야 한다.",
  },
  {
    id: "review-request",
    script: 5,
    route: "/tasks",
    stage: "Management Review 연결",
    title: "Management Review 요청",
    narration:
      "경영관리담당에게 통합 손익분석 보고를 요청한다. 기한은 두 번째 영업일 18시. 단가·운영비용 반영은 다음 장면의 일이다.",
  },
  {
    id: "accept-prod",
    script: 6,
    route: "/tasks",
    stage: "Operation Control",
    title: "생산 담당 인수",
    narration: "생산담당이 인수한다. 담당자만 인수할 수 있고, 인수자·시각이 기록된다.",
  },
  {
    id: "accept-mat",
    script: 7,
    route: "/tasks",
    stage: "Operation Control",
    title: "자재 담당 인수",
    narration: "자재담당도 인수한다. 경영관리 인수 전이라 장면은 아직 인계되지 않았다.",
  },
  {
    id: "handoff",
    script: 8,
    route: "/handoff",
    stage: "Management Review 연결",
    title: "인계 결과 확인",
    narration:
      "경영관리담당이 인수하자 장면 1이 인계된다. 위험이 해소된 것도, 전망이 승인된 것도 아니다 — F02는 검토 중, ISSUE-B07은 열린 중요, 후속 업무는 진행 중이다.",
  },
  {
    id: "overview-after",
    script: 8,
    route: "/",
    stage: "성과·전망 모니터링",
    title: "전체 현황 재확인",
    narration:
      "경영 현황에 검토 전망 F02가 승인 전망 F01과 나란히 나온다. 연간 목표 부족 1억 6,794만원 중 이번 사건분은 1,400만원이다. 진행 중 업무와 위험이 함께 보인다.",
  },
];

/**
 * 장면이 가리키는 시점의 이력 seq — 그 지점에 **처음 도달한** 기록이다.
 *
 * 마지막 기록을 쓰면 안 된다: 다음 단계를 실행하기 전에 가상시계를 먼저 옮기는데, 그 기록은
 * 아직 지점이 그대로라 "이 장면의 상태 + 다음 장면의 시각"이 보인다.
 */
export function historySeqFor(history: HistoryEntry[], script: number): number | null {
  return history.find((h) => h.scriptIndex === script)?.seq ?? null;
}
