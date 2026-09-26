import { create } from "zustand";

import { bpmProcess } from "@/lib/mock-data/bpm-process";
import { clampStepIndex, maxStepIndex } from "@/services/bpm-engine";

/**
 * 데모 시나리오 컨트롤러 상태.
 *
 * 프로세스 진행 지점 하나만 들고 있고, 노드·Agent 상태는 전부 여기서 파생된다
 * (`services/bpm-engine.ts`, `services/agent-orchestrator.ts`).
 *
 * 전역 스토어인 이유: 향후 플로팅 데모 플레이어(`components/demo/`)가 화면 밖에서
 * 같은 진행 지점을 조작해야 한다. 화면 로컬 상태로 두면 그때 들어내야 한다.
 */
interface DemoControllerState {
  /** `bpmProcess.sequence`의 인덱스. */
  stepIndex: number;
  next: () => void;
  prev: () => void;
  reset: () => void;
  setStep: (index: number) => void;
  /** 마지막 지점에 도달했는지 (버튼 비활성 판단용). */
  isAtEnd: () => boolean;
  isAtStart: () => boolean;
}

export const useDemoController = create<DemoControllerState>((set, get) => ({
  stepIndex: bpmProcess.defaultStepIndex,

  next: () =>
    set((state) => ({ stepIndex: clampStepIndex(bpmProcess, state.stepIndex + 1) })),
  prev: () =>
    set((state) => ({ stepIndex: clampStepIndex(bpmProcess, state.stepIndex - 1) })),
  reset: () => set({ stepIndex: 0 }),
  setStep: (index) => set({ stepIndex: clampStepIndex(bpmProcess, index) }),

  isAtEnd: () => get().stepIndex >= maxStepIndex(bpmProcess),
  isAtStart: () => get().stepIndex <= 0,
}));
