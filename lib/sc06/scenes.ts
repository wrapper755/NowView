/**
 * SC06 데모 장면 — 화면구성·시연순서 v0.2 「시연순서」 세 동작(합계 210초).
 *
 * 장면 1~5와 다르다: **엔진 각본이 없다.** 장면 6은 이미 확인된 보고본(RPT61-v1)을 조회하는 시점에서 시작하고
 * (구현명세 11장), 세 동작은 화면 상태(어느 화면·상세 펼침)만 바꾼다. 앞뒤로 움직여도 승인·확인·과제 등록이 생기지
 * 않는다(AT61-09). 그래서 장면은 엔진이 아니라 여기서 고정된다.
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

/** 지금 화면·펼침이 가리키는 장면 — 플레이어 밖(GNB·버튼)으로 움직여도 플레이어가 따라온다. */
export function sceneFor(pathname: string, detail: boolean): number {
  if (pathname.startsWith("/sc06/report")) return 2;
  return detail ? 1 : 0;
}
