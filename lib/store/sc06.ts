/**
 * SC06 화면 상태 — 엔진이 원천이고 여기 있는 조회 결과는 사본이다. 데모 실행 id·행위자는 `useSc01`의 것 하나다.
 *
 * **선택 과제·상세 펼침은 화면 상태로 남긴다**(localStorage) — U602에서 U601로 돌아와도 펼친 상세가 그대로다(구현명세
 * 5장). 초기화는 이 화면 상태만 되돌린다 — 확정본·근거·확인 이력은 엔진에 있고 지우지 않는다(11장).
 *
 * 조회 결과는 저장하지 않는다 — 새로고침하면 다시 받는다(낡은 숫자가 먼저 보이지 않게, 4.2).
 */

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { Result } from "@/lib/sc06/client";
import type { Report, Sc06Meta, Summary, Variance } from "@/lib/sc06/types";

/** 조회 하나의 상태 — 로딩·결과·실패를 가른다. 실패를 0이나 이전 결과로 보이지 않는다. */
export type Load<T> =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "ok"; data: T }
  | { state: "error"; status: number; error: string; code?: string };

export const toLoad = <T>(r: Result<T>): Load<T> =>
  r.ok ? { state: "ok", data: r.data } : { state: "error", status: r.status, error: r.error, code: r.code };

interface Sc06State {
  meta: Sc06Meta | null;
  /** 이 데모 실행에 장면 6이 아직 없다(404) — 화면이 「장면 6 열기」를 보인다. */
  missing: boolean;
  metaError: string | null;
  summary: Load<Summary>;
  report: Load<Report>;
  variance: Load<Variance>;
  selectedTask: string;
  detailOpen: boolean;
  isPlaying: boolean;
  isPlayerExpanded: boolean;

  setMeta: (meta: Sc06Meta | null, missing?: boolean, error?: string | null) => void;
  setSummary: (s: Load<Summary>) => void;
  setReport: (s: Load<Report>) => void;
  setVariance: (s: Load<Variance>) => void;
  openDetail: (task: string) => void;
  closeDetail: () => void;
  setPlaying: (playing: boolean) => void;
  togglePlayer: () => void;
  /** 화면 상태만 처음으로 — 엔진 기록은 그대로다 */
  resetView: () => void;
}

export const useSc06 = create<Sc06State>()(
  persist(
    (set) => ({
      meta: null,
      missing: false,
      metaError: null,
      summary: { state: "idle" },
      report: { state: "idle" },
      variance: { state: "idle" },
      selectedTask: "ACT42",
      detailOpen: false,
      isPlaying: false,
      isPlayerExpanded: true,

      setMeta: (meta, missing = false, error = null) =>
        set((s) => ({
          meta,
          missing,
          metaError: error,
          // 다른 데모 실행·보고본이면 이전 조회를 버린다 — 다른 버전의 숫자를 섞지 않는다
          ...(meta?.demoRunId !== s.meta?.demoRunId || meta?.reportVersion !== s.meta?.reportVersion
            ? { summary: { state: "idle" }, report: { state: "idle" }, variance: { state: "idle" } }
            : {}),
        })),
      setSummary: (summary) => set({ summary }),
      setReport: (report) => set({ report }),
      setVariance: (variance) => set({ variance }),
      openDetail: (selectedTask) => set({ selectedTask, detailOpen: true }),
      closeDetail: () => set({ detailOpen: false }),
      setPlaying: (isPlaying) => set({ isPlaying }),
      togglePlayer: () => set((s) => ({ isPlayerExpanded: !s.isPlayerExpanded })),
      resetView: () => set({ selectedTask: "ACT42", detailOpen: false, isPlaying: false }),
    }),
    {
      name: "nowview-sc06",
      version: 1,
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({
        selectedTask: s.selectedTask,
        detailOpen: s.detailOpen,
        isPlayerExpanded: s.isPlayerExpanded,
      }),
      skipHydration: true,
    },
  ),
);
