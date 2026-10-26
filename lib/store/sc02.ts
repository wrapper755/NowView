/**
 * SC02 화면 상태 — SC01 스토어(`lib/store/sc01.ts`)와 같은 원칙이다. 엔진이 원천이고 `live`는 사본이다.
 *
 * **데모 실행 id는 따로 두지 않는다** — 장면 2는 장면 1과 같은 데모 실행 id다(DATA-22). 화면 전체가
 * `useSc01`의 `demoRunId`·`actor`를 함께 쓴다(역할 전환도 하나다). 여기에는 장면 2 문서와 플레이어만 있다.
 */

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { ProcessTopology, ScriptStep } from "@/lib/sc01/types";
import type { Sc02Case, Sc02View } from "@/lib/sc02/types";
import type { Connection } from "@/lib/store/sc01";

interface Sc02State {
  live: Sc02View | null;
  past: { seq: number; view: Sc02View } | null;
  /** 이 데모 실행에 장면 2가 아직 없다(404) — 화면이 「장면 2 시작」을 보인다. */
  missing: boolean;
  connection: Connection;
  error: string | null;
  topology: ProcessTopology | null;
  rules: Record<string, string>;
  cases: Sc02Case[];
  script: ScriptStep[];
  sceneIndex: number;
  isPlaying: boolean;
  isPlayerExpanded: boolean;

  setLive: (view: Sc02View) => void;
  clearLive: (missing: boolean) => void;
  setPast: (past: { seq: number; view: Sc02View } | null) => void;
  setConnection: (c: Connection) => void;
  setError: (e: string | null) => void;
  setStatic: (topology: ProcessTopology | null, rules: Record<string, string>, cases: Sc02Case[]) => void;
  setScript: (script: ScriptStep[]) => void;
  setScene: (index: number) => void;
  setPlaying: (playing: boolean) => void;
  togglePlayer: () => void;
}

export const useSc02 = create<Sc02State>()(
  persist(
    (set) => ({
      live: null,
      past: null,
      missing: false,
      connection: "connecting",
      error: null,
      topology: null,
      rules: {},
      cases: [],
      script: [],
      sceneIndex: 0,
      isPlaying: false,
      isPlayerExpanded: true,

      setLive: (view) =>
        set((s) => {
          // 더 오래된 문서로 덮지 않는다 — 감사 이력은 늘기만 한다(SC01 setLive와 같은 이유).
          if (s.live && s.live.demoRunId === view.demoRunId && view.audit.length < s.live.audit.length) {
            return s;
          }
          return { live: view, missing: false, error: null };
        }),
      clearLive: (missing) => set({ live: null, past: null, missing }),
      setPast: (past) => set({ past }),
      setConnection: (connection) => set({ connection }),
      setError: (error) => set({ error }),
      setStatic: (topology, rules, cases) => set({ topology, rules, cases }),
      setScript: (script) => set({ script }),
      setScene: (sceneIndex) => set({ sceneIndex }),
      setPlaying: (isPlaying) => set({ isPlaying }),
      togglePlayer: () => set((s) => ({ isPlayerExpanded: !s.isPlayerExpanded })),
    }),
    {
      name: "nowview-sc02",
      version: 1,
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ sceneIndex: s.sceneIndex, isPlayerExpanded: s.isPlayerExpanded }),
      skipHydration: true,
    },
  ),
);

export const selectView2 = (s: Sc02State): Sc02View | null => s.past?.view ?? s.live;
