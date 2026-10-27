/**
 * SC05 화면 상태 — 장면 4 스토어(`lib/store/sc04.ts`)와 같은 원칙이다. 엔진이 원천이고 `live`는 사본이다.
 *
 * **데모 실행 id는 따로 두지 않는다** — 장면 5는 장면 1~4와 같은 데모 실행 id다. 역할 전환도 `useSc01`의 것
 * 하나다. 여기에는 장면 5 문서와 플레이어만 있다.
 */

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { ProcessTopology } from "@/lib/sc01/types";
import type { Sc05Case, Sc05ScriptStep, Sc05View } from "@/lib/sc05/types";
import type { Connection } from "@/lib/store/sc01";

interface Sc05State {
  live: Sc05View | null;
  past: { seq: number; view: Sc05View } | null;
  /** 이 데모 실행에 장면 5가 아직 없다(404) — 화면이 「장면 5 시작」을 보인다. */
  missing: boolean;
  connection: Connection;
  error: string | null;
  topology: ProcessTopology | null;
  cases: Sc05Case[];
  script: Sc05ScriptStep[];
  sceneIndex: number;
  isPlaying: boolean;
  isPlayerExpanded: boolean;

  setLive: (view: Sc05View) => void;
  clearLive: (missing: boolean) => void;
  setPast: (past: { seq: number; view: Sc05View } | null) => void;
  setConnection: (c: Connection) => void;
  setError: (e: string | null) => void;
  setStatic: (topology: ProcessTopology | null, cases: Sc05Case[]) => void;
  setScript: (script: Sc05ScriptStep[]) => void;
  setScene: (index: number) => void;
  setPlaying: (playing: boolean) => void;
  togglePlayer: () => void;
}

export const useSc05 = create<Sc05State>()(
  persist(
    (set) => ({
      live: null,
      past: null,
      missing: false,
      connection: "connecting",
      error: null,
      topology: null,
      cases: [],
      script: [],
      sceneIndex: 0,
      isPlaying: false,
      isPlayerExpanded: true,

      setLive: (view) =>
        set((s) => {
          // 더 오래된 문서로 덮지 않는다 — 감사 이력은 늘기만 한다(장면 1~4 setLive와 같은 이유).
          if (s.live && s.live.demoRunId === view.demoRunId && view.audit.length < s.live.audit.length) {
            return s;
          }
          return { live: view, missing: false, error: null };
        }),
      clearLive: (missing) => set({ live: null, past: null, missing }),
      setPast: (past) => set({ past }),
      setConnection: (connection) => set({ connection }),
      setError: (error) => set({ error }),
      setStatic: (topology, cases) => set({ topology, cases }),
      setScript: (script) => set({ script }),
      setScene: (sceneIndex) => set({ sceneIndex }),
      setPlaying: (isPlaying) => set({ isPlaying }),
      togglePlayer: () => set((s) => ({ isPlayerExpanded: !s.isPlayerExpanded })),
    }),
    {
      name: "nowview-sc05",
      version: 1,
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ sceneIndex: s.sceneIndex, isPlayerExpanded: s.isPlayerExpanded }),
      skipHydration: true,
    },
  ),
);

export const selectView5 = (s: Sc05State): Sc05View | null => s.past?.view ?? s.live;
