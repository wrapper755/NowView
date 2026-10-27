/**
 * SC06 데모 단계 — **확인 절차 일곱 단계(엔진 각본 D601~D607)** + 화면구성·시연순서 v0.2 「시연순서」 세 동작(합계 210초).
 *
 * * **확인 절차는 엔진 각본이다**(`engine/app/sc06/demo.py`) — 착수 → 생산·구매 임원 확인 → 경영관리 종합 확인 → 보고 결론
 *   → 보고본 확정 → 대표 보고. 장면 1~5처럼 「앞으로는 실행」 — 그 단계까지 `POST …/script/{i}`로 실제로 결재한다(역할 검사·
 *   확정 요건 그대로). 화면에서 직접 답해도 엔진이 상태로 각본 위치를 따라간다(`scriptIndex`).
 * * **세 동작은 조회다** — 확인이 끝난 보고본(RPT61-v1)을 본다. 앞뒤로 움직여도 승인·확인·과제 등록이 생기지 않는다
 *   (AT61-09). 그래서 그 셋은 엔진이 아니라 여기서 고정된다.
 */

export interface Sc06Scene {
  id: string;
  route: "/sc06" | "/sc06/report";
  /** 동작 ②만 ACT42 차이 상세를 펼친다 */
  detail: boolean;
  seconds: number;
  title: string;
  narration: string;
}

export const SC06_SCENES: Sc06Scene[] = [
  {
    id: "U601-summary",
    route: "/sc06",
    detail: false,
    seconds: 60,
    title: "① 준비된 검토 요약 열기",
    narration:
      "예전에는 부서별 자료를 받아 맞추는 데 시간이 들었습니다. 이제 근거와 비교자료가 준비되어 중요한 차이부터 검토합니다. 남은 자료도 영향과 대체 근거를 보고 담당자가 판단합니다.",
  },
  {
    id: "U601-variance",
    route: "/sc06",
    detail: true,
    seconds: 90,
    title: "② ACT42 주요 차이 한 건 열기",
    narration:
      "Agent는 원인 후보와 근거를 정리합니다. 담당자는 실제 공유·확인 시각과 공급 가능일을 대조해 설명을 바로잡습니다. 내부 지연과 공급 제약은 대응이 다릅니다.",
  },
  {
    id: "U602-report",
    route: "/sc06/report",
    detail: true,
    seconds: 60,
    title: "③ 후속 대응 보고 요약 보기",
    narration:
      "성과 개선은 확인했지만 일부 차이가 남습니다. 내부 지연은 운영을 보완하고, 반복 조달 제약은 공급조건 개선 과제로 검토합니다. 다음 월간 보고에서 보완 결과와 검토안을 확인합니다.",
  },
];

/** 확인 절차 — 엔진 각본(D601~D607)과 같은 순서다. 시간은 시연순서에 없다(구현용 — 다른 장면의 자동 재생과 같은 7초). */
export interface Sc06ConfirmStep {
  code: string;
  scriptIndex: number;
  title: string;
  narration: string;
}

export const SC06_CONFIRM_STEPS: Sc06ConfirmStep[] = [
  {
    code: "D601",
    scriptIndex: 0,
    title: "확인 착수",
    narration: "경영관리 담당이 Q4 검토건(RV61)의 확인을 착수합니다. 숫자는 자료 마감 뒤 규칙 계산으로 이미 준비되어 있습니다.",
  },
  {
    code: "D602",
    scriptIndex: 1,
    title: "생산 임원 성과 근거 확인",
    narration: "생산 임원이 ACT41 완료와 Q4 효과를 이 보고 버전 기준으로 확인합니다.",
  },
  {
    code: "D603",
    scriptIndex: 2,
    title: "구매 임원 성과 근거 확인",
    narration: "구매 임원이 ACT42·43 효과·원인과 JDG61 판단을 확인합니다. 서명본 보완 같은 미비는 지우지 않고 남깁니다.",
  },
  {
    code: "D604",
    scriptIndex: 3,
    title: "경영관리 종합 확인",
    narration: "경영관리 임원이 분기 기준·중복·합계·잔여 위험·후속 책임을 종합해 확인합니다. 이견이 있으면 두 확인을 다시 받습니다.",
  },
  {
    code: "D605",
    scriptIndex: 4,
    title: "보고 결론 작성",
    narration: "경영관리 담당이 보고 결론을 씁니다. 문장 속 숫자는 확정 때 산정과 대조됩니다.",
  },
  {
    code: "D606",
    scriptIndex: 5,
    title: "보고본 확정",
    narration: "보고 편성 책임자가 보고본을 확정합니다. 확정은 과제 실행이나 예산 승인이 아닙니다.",
  },
  {
    code: "D607",
    scriptIndex: 6,
    title: "대표 월간 보고",
    narration: "대표가 개선 기여와 남는 차이, 보완·발의, 다음 확인을 보고받습니다. 위험은 계속 관리합니다.",
  },
];

/** 플레이어의 한 단계 — 확인 절차(엔진 실행)거나 조회(화면 상태). */
export type Sc06PlayerStep =
  | ({ kind: "confirm"; route: "/sc06/confirm"; seconds: number } & Sc06ConfirmStep)
  | ({ kind: "view" } & Sc06Scene);

export const SC06_PLAYER: Sc06PlayerStep[] = [
  ...SC06_CONFIRM_STEPS.map((s) => ({ ...s, kind: "confirm" as const, route: "/sc06/confirm" as const, seconds: 30 })),
  ...SC06_SCENES.map((s) => ({ ...s, kind: "view" as const })),
];

/** 지금 화면·펼침이 가리키는 조회 동작 — 플레이어 밖(GNB·버튼)으로 움직여도 플레이어가 따라온다. */
export function sceneFor(pathname: string, detail: boolean): number {
  if (pathname.startsWith("/sc06/report")) return 2;
  return detail ? 1 : 0;
}

/**
 * 지금 플레이어 단계 — 확인 절차 화면·BPM 흐름이면 엔진 각본 위치(아직 착수 전이면 0), 그 밖이면 조회 동작이다.
 */
export function playerIndexFor(pathname: string, detail: boolean, scriptIndex: number): number {
  if (pathname.startsWith("/sc06/confirm") || pathname.startsWith("/sc06/process")) {
    return Math.min(Math.max(scriptIndex, 0), SC06_CONFIRM_STEPS.length - 1);
  }
  return SC06_CONFIRM_STEPS.length + sceneFor(pathname, detail);
}
