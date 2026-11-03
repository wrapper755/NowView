/**
 * SC01 화면 상태 — 데모 실행 하나를 화면 전체가 함께 본다.
 *
 * * **엔진이 원천이다.** 여기 있는 `live`는 엔진 문서의 사본이고, 변경은 엔진이 SSE로 밀어 준
 *   것으로만 바뀐다.
 * * **지난 시점(`past`)은 덮어쓰기만 한다.** 그 시점의 이력을 읽어 여기 둔다.
 *   `live`는 그대로이고, 화면은 `past ?? live`를 본다.
 * * 저장하는 것은 데모 실행 id·행위자뿐이다. 문서를 저장하면 새로고침 때 낡은
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
  /** 엔진에 데모 실행이 하나도 없다 — 회사 사이트가 세계를 만들어야 생긴다. */
  noRun: boolean;

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
  setNoRun: (noRun: boolean) => void;
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
      noRun: false,

      setDemoRunId: (demoRunId) => set({ demoRunId, live: null, past: null, noRun: false }),
      setActor: (actor) => set({ actor }),
      setLive: (view) =>
        set((s) => {
          // 다른 데모 실행의 늦은 응답이 섞여 들어오지 않게 한다.
          if (s.demoRunId && view.demoRunId !== s.demoRunId) return s;
          // **더 오래된 문서로 덮지 않는다.** 다시 읽기(HTTP)와 변경 알림(SSE)이 따로 와서 늦게 도착한
          // 쪽이 앞 문서로 되돌릴 수 있다(조작 응답이 SSE보다 늦게 와 초안이 "생성 중"으로 되돌았다). 감사 이력은
          // 변경마다 늘기만 하므로(초기화도 지우지 않는다) 그 길이가 문서의 순서다.
          if (s.live && s.live.demoRunId === view.demoRunId && view.audit.length < s.live.audit.length) {
            return s;
          }
          return { live: view, revision: s.revision + 1, error: null };
        }),
      setPast: (past) => set((s) => ({ past, revision: s.revision + 1 })),
      setConnection: (connection) => set({ connection }),
      setError: (error) => set({ error }),
      setStatic: (topology, users, rules) => set({ topology, users, rules }),
      setNoRun: (noRun) => set({ noRun }),
    }),
    {
      name: "nowview-sc01",
      version: 1,
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({
        demoRunId: s.demoRunId,
        actor: s.actor,
      }),
      // 화면이 정적 프리렌더라 서버 HTML은 항상 기본값이다 — 모듈 로드 시점에 복원하면
      // 하이드레이션이 깨진다(4.2). `Sc01SessionSync`가 mount 이후에 복원한다.
      skipHydration: true,
    },
  ),
);

/** 화면이 보는 문서 — 지난 시점을 보고 있으면 그것, 아니면 지금. */
export const selectView = (s: Sc01State): DemoRunView | null => s.past?.view ?? s.live;
