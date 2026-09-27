/**
 * 화면 표시 설정 — 시나리오와 무관한 개인 취향.
 *
 * **데모·엔진 스토어와 분리한다.** 저 둘은 "지금 어떤 안건이 어디까지 갔는가"를 들고
 * 있고 시나리오별로 갈라져 있다. 해설을 켜 두었는지는 안건과 아무 상관이 없으므로
 * 섞으면 시나리오를 바꿀 때 표시 설정까지 흔들릴 여지를 만든다.
 */

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

interface UiPrefsState {
  /**
   * 카드 해설을 보여줄 것인가.
   *
   * **기본은 꺼짐이다.** 이 화면들은 방법론을 설명하는 자료와 경영자가 쓰는 화면을
   * 겸하는데, 해설이 상시로 박혀 있으면 정작 봐야 할 수치가 문장에 묻힌다. 시연할
   * 때 켜고 평소에는 끈다 — 지우는 것이 아니라 모드로 가른 것이다.
   */
  showCommentary: boolean;
  setCommentary: (show: boolean) => void;
}

export const useUiPrefs = create<UiPrefsState>()(
  persist(
    (set) => ({
      showCommentary: false,
      setCommentary: (show) => set({ showCommentary: show }),
    }),
    {
      name: "nowview-ui-prefs",
      version: 1,
      storage: createJSONStorage(() => localStorage),
      // 화면이 정적 프리렌더라 서버 HTML은 항상 기본값(꺼짐)이다. 모듈 로드 시점에
      // 복원하면 첫 클라이언트 렌더가 서버와 달라져 하이드레이션이 깨진다.
      // `components/demo/store-hydrator.tsx`가 mount 이후에 복원한다.
      skipHydration: true,
    },
  ),
);
