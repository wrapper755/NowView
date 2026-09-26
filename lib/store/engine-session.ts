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
import type { AgentMode } from "@/services/engine-client";

interface EngineSessionState {
  /** 시나리오 id → 인스턴스 id. 없으면 Mock 모드다. */
  instanceByScenario: Record<string, string | null>;
  /** 새 인스턴스를 만들 때 쓸 Agent 모드. 기존 인스턴스의 모드는 바꿀 수 없다. */
  agentMode: AgentMode;

  attach: (scenarioId: string, instanceId: string) => void;
  detach: (scenarioId: string) => void;
  setAgentMode: (mode: AgentMode) => void;
}

export const useEngineSession = create<EngineSessionState>()(
  persist(
    (set) => ({
      instanceByScenario: {},
      agentMode: "mock",

      attach: (scenarioId, instanceId) =>
        set((state) => ({
          instanceByScenario: { ...state.instanceByScenario, [scenarioId]: instanceId },
        })),

      detach: (scenarioId) =>
        set((state) => ({
          instanceByScenario: { ...state.instanceByScenario, [scenarioId]: null },
        })),

      setAgentMode: (mode) => set({ agentMode: mode }),
    }),
    {
      name: "nowview-engine-session",
      version: 1,
      storage: createJSONStorage(() => localStorage),
      // 데모 스토어와 같은 이유다 — 화면이 정적 프리렌더라 서버 HTML은 항상 기본
      // 상태인데, 모듈 로드 시점에 복원하면 첫 클라이언트 렌더가 달라져 하이드레이션이
      // 깨진다. `StoreHydrator`가 mount 이후에 복원한다.
      skipHydration: true,
    },
  ),
);

/** 원시값만 돌려주는 선택자 — 객체를 만들어 돌려주면 매 렌더마다 새 참조가 되어 리렌더가 샌다. */
export const selectInstanceId = (scenarioId: string) => (state: EngineSessionState) =>
  state.instanceByScenario[scenarioId] ?? null;

export const selectAgentMode = (state: EngineSessionState) => state.agentMode;

export const DEFAULT_ENGINE_SCENARIO_ID = DEFAULT_SCENARIO_ID;
