/**
 * 엔진 스냅샷 공유 저장소 — **한 곳에서 가져와 모두가 같은 것을 본다.**
 *
 * 훅마다 따로 가져오면 두 가지가 깨진다:
 *
 * 1. **같은 화면의 두 패널이 서로 다른 순간을 본다.** ①은 경영 수행 성과와 리스크 신호가
 *    각각 스냅샷을 쓰는데, 각자 가져오면 한쪽은 승인 전, 다른 쪽은 승인 후를 그릴 수 있다.
 * 2. **요청이 화면마다 배로 늘어난다.** 폴링을 붙이면 그 배수가 그대로 초당 요청이 된다.
 *
 * 그래서 `SnapshotPoller` 하나만 가져오고, 화면들은 이 스토어를 읽는다.
 * 저장(persist)하지 않는다 — 서버 상태의 사본이므로 새로고침하면 다시 읽는 편이 맞다.
 */

import { create } from "zustand";

import type { EngineError, EngineSnapshot } from "@/services/engine-client";

interface EngineSnapshotsState {
  /** 시나리오 id → 스냅샷. */
  snapshots: Record<string, EngineSnapshot>;
  /**
   * 이 결과가 어떤 인스턴스 구성에서 나왔는가.
   *
   * `loading` 판정의 근거다 — 지금 붙어 있는 인스턴스 구성과 다르면 아직 못 읽은 것이다.
   */
  forKey: string;
  error: EngineError | null;
  /** 마지막으로 읽은 시각(ms). 화면이 "얼마나 오래된 값인가"를 말할 수 있어야 한다. */
  fetchedAt: number | null;

  setResult: (
    forKey: string,
    snapshots: Record<string, EngineSnapshot>,
    error: EngineError | null,
    fetchedAt: number,
  ) => void;
  /**
   * 한 시나리오의 스냅샷만 갈아 끼운다 — 승인·생성 직후에 쓴다.
   *
   * 폴링 주기를 기다리면 승인했는데 화면이 한동안 옛 상태를 보여 준다. `forKey`는
   * 건드리지 않는다 — 인스턴스 구성이 바뀐 것이 아니라 그 안의 상태만 움직였다.
   */
  applyOne: (scenarioId: string, snapshot: EngineSnapshot) => void;
  reset: () => void;
}

export const useEngineSnapshotStore = create<EngineSnapshotsState>()((set) => ({
  snapshots: {},
  forKey: "",
  error: null,
  fetchedAt: null,

  setResult: (forKey, snapshots, error, fetchedAt) =>
    set({ forKey, snapshots, error, fetchedAt }),

  applyOne: (scenarioId, snapshot) =>
    set((state) => ({
      snapshots: { ...state.snapshots, [scenarioId]: snapshot },
      error: null,
      fetchedAt: Date.now(),
    })),

  reset: () => set({ snapshots: {}, forKey: "", error: null, fetchedAt: null }),
}));
