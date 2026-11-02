/**
 * SC07 데모 단계 — **확인·적용 절차 다섯 단계(엔진 각본 D701~D705)** + 화면구성·시연순서 v0.2 「시연순서」 두 동작(합계 120초).
 *
 * * **확인·적용 절차는 엔진 각본이다**(`engine/app/sc07/demo.py`) — 착수(검증 실행) → 구매 임원 확인 → 경영관리 임원 확인 →
 *   운영 설정 반영 → 설정 반영 확인. 장면 1~6처럼 「앞으로는 실행」 — 그 단계까지 `POST …/script/{i}`로 실제로 결재한다. 화면·
 *   회사 사이트에서 직접 답해도 엔진이 상태로 각본 위치를 따라간다(`scriptIndex`).
 * * **두 동작은 조회다** — U701의 보기 A(개선 전후) → B(검증·적용). 보기 전환은 승인·배포·적용 이벤트를 만들지 않는다(AT712).
 */

export interface Sc07View {
  id: string;
  view: "A" | "B";
  seconds: number;
  title: string;
  narration: string;
}

export const SC07_VIEWS: Sc07View[] = [
  {
    id: "U701-A",
    view: "A",
    seconds: 60,
    title: "① 개선 내용 확인",
    narration:
      "담당자가 뒤늦게 보완하던 대행 확인과 공급 근거를 다음 검토에서는 Agent가 함께 확인합니다. 같은 120분 기준을 유지하면서 판단 근거를 개선합니다.",
  },
  {
    id: "U701-B",
    view: "B",
    seconds: 60,
    title: "② 검증과 적용 확인",
    narration:
      "대표 사례와 예외 사례로 개선 버전을 검증하고 담당 임원과 경영관리 임원이 확인한 뒤 다음 운영 설정에 반영합니다. 실제 운영에서의 효과는 후속 점검 대상입니다.",
  },
];

/** 확인·적용 절차 — 엔진 각본(D701~D705)과 같은 순서다. 시간은 시연순서에 없다(구현용 — 다른 장면의 자동 재생과 같다). */
export interface Sc07ConfirmStep {
  code: string;
  scriptIndex: number;
  title: string;
  narration: string;
}

export const SC07_CONFIRM_STEPS: Sc07ConfirmStep[] = [
  {
    code: "D701",
    scriptIndex: 0,
    title: "확인 착수 · 검증 실행",
    narration:
      "경영관리 담당이 개선건(IMP71)의 확인을 착수합니다. 개선 버전을 대표 사례와 예외 사례로 검증합니다 — 정답과 사람의 보정 문구는 Agent 입력에 넣지 않습니다.",
  },
  {
    code: "D702",
    scriptIndex: 1,
    title: "구매 임원 업무 확인",
    narration: "구매 임원이 대행 인정 기준과 원인 후보 방식이 구매 업무에 맞는지 확인합니다. 확인은 검증한 버전에만 합니다.",
  },
  {
    code: "D703",
    scriptIndex: 2,
    title: "경영관리 임원 정합성 확인",
    narration: "경영관리 임원이 측정 기준이 그대로이고 완료·성과 검토의 보고본·초안·보정·성과 수치가 바뀌지 않았는지 확인합니다.",
  },
  {
    code: "D704",
    scriptIndex: 3,
    title: "운영 설정 반영",
    narration: "운영 담당이 다음 성과 검토 설정의 사용 버전을 개선 버전으로 바꾸고 설정 스냅샷을 남깁니다. 예약만으로는 반영이 아닙니다.",
  },
  {
    code: "D705",
    scriptIndex: 4,
    title: "운영 설정 반영 확인",
    narration: "경영관리 담당이 설정을 읽어 버전·범위·증적을 확인합니다. 설정 반영 확인은 운영 실행 확인이 아닙니다 — 다음 점검은 2/11입니다.",
  },
];

/** 플레이어의 한 단계 — 확인·적용 절차(엔진 실행)거나 조회(보기 A·B). */
export type Sc07PlayerStep =
  | ({ kind: "confirm"; route: "/sc07/confirm"; seconds: number } & Sc07ConfirmStep)
  | ({ kind: "view"; route: "/sc07" } & Sc07View);

export const SC07_PLAYER: Sc07PlayerStep[] = [
  ...SC07_CONFIRM_STEPS.map((s) => ({ ...s, kind: "confirm" as const, route: "/sc07/confirm" as const, seconds: 30 })),
  ...SC07_VIEWS.map((s) => ({ ...s, kind: "view" as const, route: "/sc07" as const })),
];

/**
 * 지금 플레이어 단계 — 확인·적용 절차 화면·BPM 흐름이면 엔진 각본 위치(착수 전이면 0), U701이면 보기 A·B다.
 */
export function playerIndexFor(pathname: string, view: "A" | "B", scriptIndex: number): number {
  if (pathname.startsWith("/sc07/confirm") || pathname.startsWith("/sc07/process")) {
    return Math.min(Math.max(scriptIndex, 0), SC07_CONFIRM_STEPS.length - 1);
  }
  return SC07_CONFIRM_STEPS.length + (view === "B" ? 1 : 0);
}
