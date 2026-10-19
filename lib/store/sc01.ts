/**
 * SC01 화면 상태 — 데모 실행 하나를 화면 전체가 함께 본다.
 *
 * * **엔진이 원천이다.** 여기 있는 `live`는 엔진 문서의 사본이고, 변경은 엔진이 SSE로 밀어 준
 *   것으로만 바뀐다(조작 응답도 즉시 반영한다 — SSE를 기다리면 누른 뒤 잠깐 옛 상태가 보인다).
 * * **지난 시점(`past`)은 덮어쓰기만 한다.** 데모 플레이어가 뒤로 가면 그 시점의 이력을 읽어
 *   여기 둔다. `live`는 그대로이고, 화면은 `past ?? live`를 본다. 지난 시점에서는 조작할 수 없다.
 * * 저장하는 것은 데모 실행 id·행위자·플레이어 펼침뿐이다. 문서를 저장하면 새로고침 때 낡은
 *   값이 먼저 보인다 — 엔진에서 다시 받는다.
 */

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { DemoRunView, DemoUser, ProcessTopology } from "@/lib/sc01/types";

export type Connection = "connecting" | "live" | "polling" | "offline";

interface Sc01State {
  demoRunId: string | null;
  actor: string;
  live: DemoRunView | null;
  past: { seq: number; view: DemoRunView } | null;
  /** live가 바뀔 때마다 오른다 — 대시보드 같은 파생 조회가 다시 읽는 신호다. */
  revision: number;
  connection: Connection;
  error: string | null;
  topology: ProcessTopology | null;
  users: DemoUser[];
  /** R01-v1 임계값(엔진 시드). 화면이 기준을 따로 적지 않는다. */
  rules: Record<string, string>;
  sceneIndex: number;
  isPlaying: boolean;
  isPlayerExpanded: boolean;

  setDemoRunId: (id: string | null) => void;
  setActor: (actor: string) => void;
  setLive: (view: DemoRunView) => void;
  setPast: (past: { seq: number; view: DemoRunView } | null) => void;
  setConnection: (c: Connection) => void;
  setError: (e: string | null) => void;
  setStatic: (
    topology: ProcessTopology | null,
    users: DemoUser[],
    rules: Record<string, string>,
  ) => void;
  setScene: (index: number) => void;
  setPlaying: (playing: boolean) => void;
  togglePlayer: () => void;
}

export const useSc01 = create<Sc01State>()(
  persist(
    (set) => ({
      demoRunId: null,
      actor: "u-sales",
      live: null,
      past: null,
      revision: 0,
      connection: "connecting",
      error: null,
      topology: null,
      users: [],
      rules: {},
      sceneIndex: 0,
      isPlaying: false,
      isPlayerExpanded: true,

      setDemoRunId: (demoRunId) => set({ demoRunId, live: null, past: null }),
      setActor: (actor) => set({ actor }),
      setLive: (view) =>
        set((s) =>
          // 다른 데모 실행의 늦은 응답이 섞여 들어오지 않게 한다.
          s.demoRunId && view.demoRunId !== s.demoRunId
            ? s
            : { live: view, revision: s.revision + 1, error: null },
        ),
      setPast: (past) => set((s) => ({ past, revision: s.revision + 1 })),
      setConnection: (connection) => set({ connection }),
      setError: (error) => set({ error }),
      setStatic: (topology, users, rules) => set({ topology, users, rules }),
      setScene: (sceneIndex) => set({ sceneIndex }),
      setPlaying: (isPlaying) => set({ isPlaying }),
      togglePlayer: () => set((s) => ({ isPlayerExpanded: !s.isPlayerExpanded })),
    }),
    {
      name: "nowview-sc01",
      version: 1,
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({
        demoRunId: s.demoRunId,
        actor: s.actor,
        sceneIndex: s.sceneIndex,
        isPlayerExpanded: s.isPlayerExpanded,
      }),
      // 화면이 정적 프리렌더라 서버 HTML은 항상 기본값이다 — 모듈 로드 시점에 복원하면
      // 하이드레이션이 깨진다(4.2). `Sc01SessionSync`가 mount 이후에 복원한다.
      skipHydration: true,
    },
  ),
);

/** 화면이 보는 문서 — 지난 시점을 보고 있으면 그것, 아니면 지금. */
export const selectView = (s: Sc01State): DemoRunView | null => s.past?.view ?? s.live;
