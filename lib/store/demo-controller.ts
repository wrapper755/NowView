import { create } from "zustand";

import { DEMO_DECISION, demoScenario } from "@/lib/demo-scenario";
import { bpmProcess } from "@/lib/mock-data/bpm-process";
import type { ReviewDecision } from "@/lib/types/workspace";
import { clampStepIndex, maxStepIndex } from "@/services/bpm-engine";

/** 승인 시 프로세스가 이동할 지점 — Management Action 배포 단계. */
const ACTION_STEP_INDEX = bpmProcess.sequence.indexOf("action");

const LAST_SCENE_INDEX = demoScenario.length - 1;

function clampScene(index: number): number {
  return Math.min(Math.max(index, 0), LAST_SCENE_INDEX);
}

/**
 * 데모 시나리오 컨트롤러 상태.
 *
 * 세 가지를 들고 있다 — BPM 진행 지점, 사람의 결정, 데모 재생 위치. 노드·Agent 상태와
 * Gap 계산은 전부 여기서 파생된다(`services/`).
 *
 * 전역인 이유: 화면 다섯 개가 같은 안건을 다루고, 플로팅 플레이어가 화면 밖에서 이들을
 * 함께 조작한다. 협업 스테이션에서 승인하면 트래커와 Rolling Plan이 같이 움직인다.
 */
interface DemoControllerState {
  /** `bpmProcess.sequence`의 인덱스. */
  stepIndex: number;
  /** 사람이 내린 Management Review 결정. 승인 전에는 null. */
  decision: ReviewDecision | null;

  /** 데모 시나리오 장면 인덱스. */
  sceneIndex: number;
  /** 자동 재생 중인가. */
  isPlaying: boolean;
  /** 플레이어가 펼쳐져 있는가 (접으면 작은 알약 형태로 남는다). */
  isPlayerExpanded: boolean;

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

  isAtEnd: () => boolean;
  isAtStart: () => boolean;
}

export const useDemoController = create<DemoControllerState>((set, get) => ({
  stepIndex: bpmProcess.defaultStepIndex,
  decision: null,

  sceneIndex: 0,
  isPlaying: false,
  isPlayerExpanded: true,

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

  isAtEnd: () => get().stepIndex >= maxStepIndex(bpmProcess),
  isAtStart: () => get().stepIndex <= 0,
}));

export { LAST_SCENE_INDEX };
