/**
 * SC03 화면 상태 — 장면 2 스토어(`lib/store/sc02.ts`)와 같은 원칙이다. 엔진이 원천이고 `live`는 사본이다.
 * 읽기 전용이라 저장(persist)할 것이 없다 — 데모 플레이어 위치를 저장하던 자리는 플레이어와 함께 걷었다.
 *
 * **데모 실행 id는 따로 두지 않는다** — 장면 3은 장면 1·2와 같은 데모 실행 id다. 역할 전환도 `useSc01`의 것
 * 하나다. 여기에는 장면 3 문서만 있다.
 */

import { create } from "zustand";

import type { ProcessTopology } from "@/lib/sc01/types";
import type { Sc03View } from "@/lib/sc03/types";
import type { Connection } from "@/lib/store/sc01";

interface Sc03State {
  live: Sc03View | null;
  past: { seq: number; view: Sc03View } | null;
  /** 이 데모 실행에 장면 3이 아직 없다(404) — 회사 사이트의 시연 조작에서 연다. */
  missing: boolean;
  connection: Connection;
  error: string | null;
  topology: ProcessTopology | null;

  setLive: (view: Sc03View) => void;
  clearLive: (missing: boolean) => void;
  setPast: (past: { seq: number; view: Sc03View } | null) => void;
  setConnection: (c: Connection) => void;
  setError: (e: string | null) => void;
  setStatic: (topology: ProcessTopology | null) => void;
}

export const useSc03 = create<Sc03State>()((set) => ({
  live: null,
  past: null,
  missing: false,
  connection: "connecting",
  error: null,
  topology: null,

  setLive: (view) =>
    set((s) => {
      // 더 오래된 문서로 덮지 않는다 — 감사 이력은 늘기만 한다(장면 1 setLive와 같은 이유).
      if (s.live && s.live.demoRunId === view.demoRunId && view.audit.length < s.live.audit.length) {
        return s;
      }
      return { live: view, missing: false, error: null };
    }),
  clearLive: (missing) => set({ live: null, past: null, missing }),
  setPast: (past) => set({ past }),
  setConnection: (connection) => set({ connection }),
  setError: (error) => set({ error }),
  setStatic: (topology) => set({ topology }),
}));

export const selectView3 = (s: Sc03State): Sc03View | null => s.past?.view ?? s.live;
