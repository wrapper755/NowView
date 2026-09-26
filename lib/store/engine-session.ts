/**
 * 엔진 세션 — 지금 어떤 프로세스 인스턴스를 보고 있는가.
 *
 * **데모 스토어와 분리한다.** 데모(`demo-controller`)는 장면을 절대 상태로 선언하고
 * 어느 장면으로든 건너뛴다. 실행 중인 그래프에서는 그 모델이 성립하지 않는다 —
 * 시간을 되감을 수 없다. 두 모드가 한 스토어에 있으면 "처음으로" 같은 동작이
 * 서버 인스턴스와 어긋난다.
 *
 * 인스턴스 id를 **시나리오별**로 들고 있는 이유는 데모 스토어와 같다 — 하나만
 * 들고 있으면 시나리오를 오갈 때 앞 시나리오의 인스턴스가 딸려 간다.
 */

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { DEFAULT_SCENARIO_ID } from "@/lib/mock-data/scenarios";
import type { AgentMode, EngineSnapshot } from "@/services/engine-client";

interface EngineSessionState {
  /** 시나리오 id → 인스턴스 id. 없으면 Mock 모드다. */
  instanceByScenario: Record<string, string | null>;
  /** 새 인스턴스를 만들 때 쓸 Agent 모드. 기존 인스턴스의 모드는 바꿀 수 없다. */
  agentMode: AgentMode;

  /**
   * 데모가 보여주고 있는 스냅샷 — 라이브 상태 대신 이것을 그린다.
   *
   * **되감기가 읽기 전용이라 필요하다.** 과거 시점을 보여줄 때 다시 조회하면 "지금"이
   * 와 버린다. 서버에 없는 상태가 아니라 **서버가 돌려준 과거 스냅샷**을 들고 있는
   * 것이므로 지어낸 값이 아니다. 저장하지 않는다(새로고침하면 라이브로 돌아간다).
   */
  viewByScenario: Record<string, EngineSnapshot | null>;

  /**
   * 엔진 상태를 바꾼 횟수. 화면들이 이 값을 구독해 다시 읽는다.
   *
   * 플레이어가 seek하면 트래커·협업 스테이션·Rolling Plan이 모두 같은 변화를 봐야
   * 하는데, 훅마다 상태를 따로 들고 있으면 한 화면만 갱신된다.
   */
  revision: number;

  attach: (scenarioId: string, instanceId: string) => void;
  detach: (scenarioId: string) => void;
  setAgentMode: (mode: AgentMode) => void;
  setView: (scenarioId: string, snapshot: EngineSnapshot | null) => void;
  bumpRevision: () => void;
}

export const useEngineSession = create<EngineSessionState>()(
  persist(
    (set) => ({
      instanceByScenario: {},
      agentMode: "mock",
      viewByScenario: {},
      revision: 0,

      attach: (scenarioId, instanceId) =>
        set((state) => ({
          instanceByScenario: { ...state.instanceByScenario, [scenarioId]: instanceId },
          viewByScenario: { ...state.viewByScenario, [scenarioId]: null },
          revision: state.revision + 1,
        })),

      detach: (scenarioId) =>
        set((state) => ({
          instanceByScenario: { ...state.instanceByScenario, [scenarioId]: null },
          viewByScenario: { ...state.viewByScenario, [scenarioId]: null },
          revision: state.revision + 1,
        })),

      setAgentMode: (mode) => set({ agentMode: mode }),

      setView: (scenarioId, snapshot) =>
        set((state) => ({
          viewByScenario: { ...state.viewByScenario, [scenarioId]: snapshot },
          revision: state.revision + 1,
        })),

      bumpRevision: () => set((state) => ({ revision: state.revision + 1 })),
    }),
    {
      name: "nowview-engine-session",
      version: 1,
      storage: createJSONStorage(() => localStorage),
      // 데모 스토어와 같은 이유다 — 화면이 정적 프리렌더라 서버 HTML은 항상 기본
      // 상태인데, 모듈 로드 시점에 복원하면 첫 클라이언트 렌더가 달라져 하이드레이션이
      // 깨진다. `StoreHydrator`가 mount 이후에 복원한다.
      skipHydration: true,
      // 표시용 스냅샷과 갱신 카운터는 저장하지 않는다 — 스냅샷은 크고, 새로고침하면
      // 라이브 상태로 돌아가는 편이 맞다.
      partialize: (state) => ({
        instanceByScenario: state.instanceByScenario,
        agentMode: state.agentMode,
      }),
    },
  ),
);

/** 원시값만 돌려주는 선택자 — 객체를 만들어 돌려주면 매 렌더마다 새 참조가 되어 리렌더가 샌다. */
export const selectInstanceId = (scenarioId: string) => (state: EngineSessionState) =>
  state.instanceByScenario[scenarioId] ?? null;

export const selectAgentMode = (state: EngineSessionState) => state.agentMode;

export const DEFAULT_ENGINE_SCENARIO_ID = DEFAULT_SCENARIO_ID;
