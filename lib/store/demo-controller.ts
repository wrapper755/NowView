import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { DEFAULT_SCENARIO_ID, scenarioById, scenarios } from "@/lib/mock-data/scenarios";
import { evolutionLab } from "@/lib/mock-data/evolution-lab";
import type { ReviewDecision } from "@/lib/types/workspace";
import { clampStepIndex, maxStepIndex } from "@/services/bpm-engine";

/**
 * 승인 시 프로세스가 이동할 지점.
 *
 * 시나리오마다 다르다 — 수익성 안건은 Management Action, 납기 안건은 현업 통제 이후의
 * 효과 확인 단계다. 노드 id를 고정하지 않고 승인 노드의 **다음** 지점으로 잡는다.
 */
function approvalStepIndex(scenarioId: string): number {
  const { process } = scenarioById(scenarioId);
  const decisionNode = process.nodes.find((n) => n.kind === "user-task");
  const at = decisionNode ? process.sequence.indexOf(decisionNode.id) : -1;
  return at >= 0 ? at + 1 : 0;
}

function lastSceneIndex(scenarioId: string): number {
  return scenarioById(scenarioId).scenes.length - 1;
}

/** 튜닝하지 않은 상태 = 각 KRI의 현행 임계치. */
const DEFAULT_KRI_THRESHOLDS: Record<string, number> = Object.fromEntries(
  evolutionLab.kris.map((k) => [k.id, k.currentThreshold]),
);
const DEFAULT_ACTIVE_KRI = evolutionLab.kris[0].id;

function clampScene(scenarioId: string, index: number): number {
  return Math.min(Math.max(index, 0), lastSceneIndex(scenarioId));
}

/** 시나리오별 기본 진행 지점. */
const DEFAULT_STEPS: Record<string, number> = Object.fromEntries(
  scenarios.map((s) => [s.id, s.process.defaultStepIndex]),
);

/**
 * 데모 시나리오 컨트롤러 상태.
 *
 * BPM 진행 지점, 사람의 결정, 데모 재생 위치, KRI 튜닝 값을 들고 있다. 노드·Agent 상태와
 * Gap 계산은 전부 여기서 파생된다(`services/`).
 *
 * 전역인 이유: 화면 다섯 개가 같은 안건을 다루고, 플로팅 플레이어가 화면 밖에서 이들을
 * 함께 조작한다. KRI 임계치도 시나리오가 직접 움직여야 해서 화면 로컬 상태에서 올려왔다.
 */
interface DemoControllerState {
  /** 지금 보고 있는 시나리오. */
  activeScenarioId: string;
  /**
   * 시나리오별 상태를 따로 들고 있다.
   *
   * 하나만 들고 있으면 시나리오를 바꿀 때 앞 시나리오의 진행·결정이 딸려 가거나
   * 초기화된다. 둘을 오가며 비교하는 것이 두 번째 시나리오를 붙인 이유 중 하나이므로
   * 각자의 상태가 남아야 한다.
   */
  stepByScenario: Record<string, number>;
  decisionByScenario: Record<string, ReviewDecision | null>;
  sceneByScenario: Record<string, number>;
  /** 자동 재생 중인가. 영속화하지 않는다 — 새로고침하자마자 화면이 움직이면 곤란하다. */
  isPlaying: boolean;
  /** 플레이어가 펼쳐져 있는가 (접으면 작은 알약 형태로 남는다). */
  isPlayerExpanded: boolean;

  /** KRI별 감지 임계치. 화면이 아니라 여기서 소유해야 시나리오가 값을 지정할 수 있다. */
  kriThresholds: Record<string, number>;
  /** ⑤ 화면에서 보고 있는 KRI. */
  activeKriId: string;

  setScenario: (scenarioId: string) => void;

  next: () => void;
  prev: () => void;
  reset: () => void;
  setStep: (index: number) => void;

  approve: (decision: ReviewDecision) => void;
  clearDecision: () => void;

  /**
   * 장면으로 이동한다. 화면 전환(라우팅)은 훅이 필요하므로 컴포넌트가 맡는다.
   *
   * 장면이 선언한 **목표 상태를 그대로 적용**한다 — 증분이 아니라 절대 상태라서
   * 어느 장면으로 건너뛰어도 앞뒤가 맞는다.
   */
  goToScene: (index: number) => void;
  nextScene: () => void;
  prevScene: () => void;
  setPlaying: (playing: boolean) => void;
  togglePlayer: () => void;
  /** 데모 종료 — 재생을 멈추고 첫 장면 상태로 되돌린다. */
  exitDemo: () => void;

  setKriThreshold: (kriId: string, value: number) => void;
  setActiveKri: (kriId: string) => void;

  isAtEnd: () => boolean;
  isAtStart: () => boolean;
}

export const useDemoController = create<DemoControllerState>()(
  persist(
    (set, get) => ({
      activeScenarioId: DEFAULT_SCENARIO_ID,
      stepByScenario: DEFAULT_STEPS,
      decisionByScenario: {},
      sceneByScenario: {},

      isPlaying: false,
      isPlayerExpanded: true,

      kriThresholds: DEFAULT_KRI_THRESHOLDS,
      activeKriId: DEFAULT_ACTIVE_KRI,

      setScenario: (activeScenarioId) => set({ activeScenarioId, isPlaying: false }),

      next: () =>
        set((state) => {
          const id = state.activeScenarioId;
          const process = scenarioById(id).process;
          return {
            stepByScenario: {
              ...state.stepByScenario,
              [id]: clampStepIndex(process, (state.stepByScenario[id] ?? 0) + 1),
            },
          };
        }),
      prev: () =>
        set((state) => {
          const id = state.activeScenarioId;
          const process = scenarioById(id).process;
          return {
            stepByScenario: {
              ...state.stepByScenario,
              [id]: clampStepIndex(process, (state.stepByScenario[id] ?? 0) - 1),
            },
          };
        }),
      reset: () =>
        set((state) => ({
          stepByScenario: { ...state.stepByScenario, [state.activeScenarioId]: 0 },
        })),
      setStep: (index) =>
        set((state) => {
          const id = state.activeScenarioId;
          return {
            stepByScenario: {
              ...state.stepByScenario,
              [id]: clampStepIndex(scenarioById(id).process, index),
            },
          };
        }),

      approve: (decision) =>
        set((state) => {
          const id = state.activeScenarioId;
          return {
            decisionByScenario: { ...state.decisionByScenario, [id]: decision },
            stepByScenario: {
              ...state.stepByScenario,
              [id]: clampStepIndex(scenarioById(id).process, approvalStepIndex(id)),
            },
          };
        }),
      clearDecision: () =>
        set((state) => {
          const id = state.activeScenarioId;
          return {
            decisionByScenario: { ...state.decisionByScenario, [id]: null },
            stepByScenario: {
              ...state.stepByScenario,
              [id]: scenarioById(id).process.defaultStepIndex,
            },
          };
        }),

      goToScene: (index) =>
        set((state) => {
          const id = state.activeScenarioId;
          const scenario = scenarioById(id);
          const sceneIndex = clampScene(id, index);
          const scene = scenario.scenes[sceneIndex];
          return {
            sceneByScenario: { ...state.sceneByScenario, [id]: sceneIndex },
            stepByScenario: {
              ...state.stepByScenario,
              [id]: clampStepIndex(scenario.process, scene.step),
            },
            decisionByScenario: {
              ...state.decisionByScenario,
              [id]: scene.decided ? scenario.demoDecision : null,
            },
            // 장면이 KRI를 지정하지 않으면 전부 현행값으로 되돌린다(목표 상태 선언 원칙).
            kriThresholds: scene.kri
              ? { ...DEFAULT_KRI_THRESHOLDS, [scene.kri.id]: scene.kri.threshold }
              : DEFAULT_KRI_THRESHOLDS,
            activeKriId: scene.kri?.id ?? DEFAULT_ACTIVE_KRI,
            // 마지막 장면에 닿으면 자동 재생을 멈춘다. 처음으로 되감지 않는다.
            isPlaying: sceneIndex === lastSceneIndex(id) ? false : state.isPlaying,
          };
        }),

      nextScene: () =>
        get().goToScene((get().sceneByScenario[get().activeScenarioId] ?? 0) + 1),
      prevScene: () =>
        get().goToScene((get().sceneByScenario[get().activeScenarioId] ?? 0) - 1),

      setPlaying: (isPlaying) => set({ isPlaying }),
      togglePlayer: () => set((state) => ({ isPlayerExpanded: !state.isPlayerExpanded })),

      exitDemo: () => {
        set({ isPlaying: false });
        get().goToScene(0);
      },

      setKriThreshold: (kriId, value) =>
        set((state) => ({ kriThresholds: { ...state.kriThresholds, [kriId]: value } })),
      setActiveKri: (activeKriId) => set({ activeKriId }),

      isAtEnd: () => {
        const id = get().activeScenarioId;
        return (get().stepByScenario[id] ?? 0) >= maxStepIndex(scenarioById(id).process);
      },
      isAtStart: () => (get().stepByScenario[get().activeScenarioId] ?? 0) <= 0,
    }),
    {
      name: "nowview-demo",
      // 저장 구조가 시나리오별 맵으로 바뀌었다. 올리지 않으면 예전 구조가 복원돼 터진다.
      version: 2,
      storage: createJSONStorage(() => localStorage),

      /**
       * **`skipHydration: true`가 핵심이다.**
       *
       * 화면들은 정적 프리렌더라 서버 HTML은 항상 기본 상태다. persist가 모듈 로드 시점에
       * 자동 복원하면 첫 클라이언트 렌더가 서버 HTML과 달라져 하이드레이션이 깨진다.
       * 그래서 자동 복원을 끄고 `StoreHydrator`가 mount 이후에 명시적으로 복원한다.
       */
      skipHydration: true,

      /** 함수와 `isPlaying`은 저장하지 않는다. */
      partialize: (state) => ({
        activeScenarioId: state.activeScenarioId,
        stepByScenario: state.stepByScenario,
        decisionByScenario: state.decisionByScenario,
        sceneByScenario: state.sceneByScenario,
        isPlayerExpanded: state.isPlayerExpanded,
        kriThresholds: state.kriThresholds,
        activeKriId: state.activeKriId,
      }),
    },
  ),
);

/** 활성 시나리오의 상태를 읽는 선택자. 원시값/안정 참조만 돌려준다. */
export const selectScenario = (s: DemoControllerState) => scenarioById(s.activeScenarioId);
export const selectStepIndex = (s: DemoControllerState) =>
  s.stepByScenario[s.activeScenarioId] ?? 0;
export const selectDecision = (s: DemoControllerState) =>
  s.decisionByScenario[s.activeScenarioId] ?? null;
export const selectSceneIndex = (s: DemoControllerState) =>
  s.sceneByScenario[s.activeScenarioId] ?? 0;
