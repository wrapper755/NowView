import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { DEMO_DECISION, demoScenario } from "@/lib/demo-scenario";
import { bpmProcess } from "@/lib/mock-data/bpm-process";
import { evolutionLab } from "@/lib/mock-data/evolution-lab";
import type { ReviewDecision } from "@/lib/types/workspace";
import { clampStepIndex, maxStepIndex } from "@/services/bpm-engine";

/** 승인 시 프로세스가 이동할 지점 — Management Action 배포 단계. */
const ACTION_STEP_INDEX = bpmProcess.sequence.indexOf("action");

const LAST_SCENE_INDEX = demoScenario.length - 1;

/** 튜닝하지 않은 상태 = 각 KRI의 현행 임계치. */
const DEFAULT_KRI_THRESHOLDS: Record<string, number> = Object.fromEntries(
  evolutionLab.kris.map((k) => [k.id, k.currentThreshold]),
);
const DEFAULT_ACTIVE_KRI = evolutionLab.kris[0].id;

function clampScene(index: number): number {
  return Math.min(Math.max(index, 0), LAST_SCENE_INDEX);
}

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
  /** `bpmProcess.sequence`의 인덱스. */
  stepIndex: number;
  /** 사람이 내린 Management Review 결정. 승인 전에는 null. */
  decision: ReviewDecision | null;

  /** 데모 시나리오 장면 인덱스. */
  sceneIndex: number;
  /** 자동 재생 중인가. 영속화하지 않는다 — 새로고침하자마자 화면이 움직이면 곤란하다. */
  isPlaying: boolean;
  /** 플레이어가 펼쳐져 있는가 (접으면 작은 알약 형태로 남는다). */
  isPlayerExpanded: boolean;

  /** KRI별 감지 임계치. 화면이 아니라 여기서 소유해야 시나리오가 값을 지정할 수 있다. */
  kriThresholds: Record<string, number>;
  /** ⑤ 화면에서 보고 있는 KRI. */
  activeKriId: string;

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
      stepIndex: bpmProcess.defaultStepIndex,
      decision: null,

      sceneIndex: 0,
      isPlaying: false,
      isPlayerExpanded: true,

      kriThresholds: DEFAULT_KRI_THRESHOLDS,
      activeKriId: DEFAULT_ACTIVE_KRI,

      next: () =>
        set((state) => ({ stepIndex: clampStepIndex(bpmProcess, state.stepIndex + 1) })),
      prev: () =>
        set((state) => ({ stepIndex: clampStepIndex(bpmProcess, state.stepIndex - 1) })),
      reset: () => set({ stepIndex: 0 }),
      setStep: (index) => set({ stepIndex: clampStepIndex(bpmProcess, index) }),

      approve: (decision) =>
        set({ decision, stepIndex: clampStepIndex(bpmProcess, ACTION_STEP_INDEX) }),
      clearDecision: () =>
        set({ decision: null, stepIndex: bpmProcess.defaultStepIndex }),

      goToScene: (index) => {
        const sceneIndex = clampScene(index);
        const scene = demoScenario[sceneIndex];
        set({
          sceneIndex,
          stepIndex: clampStepIndex(bpmProcess, scene.step),
          decision: scene.decided ? DEMO_DECISION : null,
          // 장면이 KRI를 지정하지 않으면 전부 현행값으로 되돌린다(목표 상태 선언 원칙).
          kriThresholds: scene.kri
            ? { ...DEFAULT_KRI_THRESHOLDS, [scene.kri.id]: scene.kri.threshold }
            : DEFAULT_KRI_THRESHOLDS,
          activeKriId: scene.kri?.id ?? DEFAULT_ACTIVE_KRI,
          // 마지막 장면에 닿으면 자동 재생을 멈춘다. 처음으로 되감지 않는다.
          isPlaying: sceneIndex === LAST_SCENE_INDEX ? false : get().isPlaying,
        });
      },

      nextScene: () => get().goToScene(get().sceneIndex + 1),
      prevScene: () => get().goToScene(get().sceneIndex - 1),

      setPlaying: (isPlaying) => set({ isPlaying }),
      togglePlayer: () => set((state) => ({ isPlayerExpanded: !state.isPlayerExpanded })),

      exitDemo: () => {
        set({ isPlaying: false });
        get().goToScene(0);
      },

      setKriThreshold: (kriId, value) =>
        set((state) => ({ kriThresholds: { ...state.kriThresholds, [kriId]: value } })),
      setActiveKri: (activeKriId) => set({ activeKriId }),

      isAtEnd: () => get().stepIndex >= maxStepIndex(bpmProcess),
      isAtStart: () => get().stepIndex <= 0,
    }),
    {
      name: "nowview-demo",
      version: 1,
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
        stepIndex: state.stepIndex,
        decision: state.decision,
        sceneIndex: state.sceneIndex,
        isPlayerExpanded: state.isPlayerExpanded,
        kriThresholds: state.kriThresholds,
        activeKriId: state.activeKriId,
      }),
    },
  ),
);

export { LAST_SCENE_INDEX };
