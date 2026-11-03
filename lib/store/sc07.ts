/**
 * SC07 화면 상태 — 엔진이 원천이고 여기 있는 조회 결과는 사본이다. 데모 실행 id·행위자는 `useSc01`의 것 하나다.
 *
 * **보기(A 개선 전후 · B 검증·적용)와 펼친 근거는 화면 상태다**(localStorage) — 새로고침해도 개선건·보기가 유지된다(UI710).
 * 조회 결과는 저장하지 않는다(4.2).
 */

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { ProcessTopology } from "@/lib/sc01/types";
import type { Result } from "@/lib/sc07/client";
import type { Application, Improvement, Sc07Meta, Verification } from "@/lib/sc07/types";

/** 조회 하나의 상태 — 로딩·결과·실패를 가른다. 실패를 「통과」나 이전 결과로 보이지 않는다. */
export type Load<T> =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "ok"; data: T }
  | { state: "error"; status: number; error: string; code?: string };

export const toLoad = <T>(r: Result<T>): Load<T> =>
  r.ok ? { state: "ok", data: r.data } : { state: "error", status: r.status, error: r.error, code: r.code };

interface Sc07State {
  meta: Sc07Meta | null;
  topology: ProcessTopology | null;
  connection: "connecting" | "live" | "polling" | "offline";
  /** 이 데모 실행에 장면 7이 아직 없다(404) — 화면이 「관리모델 개선 열기」를 보인다. */
  missing: boolean;
  metaError: string | null;
  improvement: Load<Improvement>;
  verification: Load<Verification>;
  application: Load<Application>;
  view: "A" | "B";

  setMeta: (meta: Sc07Meta | null, missing?: boolean, error?: string | null) => void;
  setTopology: (topology: ProcessTopology | null) => void;
  setConnection: (connection: Sc07State["connection"]) => void;
  setImprovement: (s: Load<Improvement>) => void;
  setVerification: (s: Load<Verification>) => void;
  setApplication: (s: Load<Application>) => void;
  setView: (view: "A" | "B") => void;
}

const IDLE = { improvement: { state: "idle" }, verification: { state: "idle" }, application: { state: "idle" } } as const;

export const useSc07 = create<Sc07State>()(
  persist(
    (set) => ({
      meta: null,
      topology: null,
      connection: "connecting",
      missing: false,
      metaError: null,
      ...IDLE,
      view: "A",

      setMeta: (meta, missing = false, error = null) =>
        set((s) => ({
          meta,
          missing,
          metaError: error,
          // 다른 데모 실행·데이터 버전이면 이전 조회를 버린다 — 혼합 버전으로 비교하지 않는다(구현명세 6장)
          ...(meta?.demoRunId !== s.meta?.demoRunId || meta?.datasetVersion !== s.meta?.datasetVersion ? IDLE : {}),
        })),
      setTopology: (topology) => set({ topology }),
      setConnection: (connection) => set({ connection }),
      setImprovement: (improvement) => set({ improvement }),
      setVerification: (verification) => set({ verification }),
      setApplication: (application) => set({ application }),
      setView: (view) => set({ view }),
    }),
    {
      name: "nowview-sc07",
      version: 1,
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ view: s.view }),
      skipHydration: true,
    },
  ),
);
