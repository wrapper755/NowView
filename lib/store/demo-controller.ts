import { create } from "zustand";

import { bpmProcess } from "@/lib/mock-data/bpm-process";
import type { ReviewDecision } from "@/lib/types/workspace";
import { clampStepIndex, maxStepIndex } from "@/services/bpm-engine";

/** 승인 시 프로세스가 이동할 지점 — Management Action 배포 단계. */
const ACTION_STEP_INDEX = bpmProcess.sequence.indexOf("action");

/**
 * 데모 시나리오 컨트롤러 상태.
 *
 * 프로세스 진행 지점과 사람의 결정 하나씩만 들고 있고, 노드·Agent 상태는 전부 여기서
 * 파생된다 (`services/bpm-engine.ts`, `services/agent-orchestrator.ts`).
 *
 * 전역 스토어인 이유: ② 트래커와 ③ 협업 스테이션이 같은 안건을 다루므로, 협업 화면에서
 * 승인하면 트래커의 진행 지점도 함께 움직여야 한다. 향후 플로팅 데모 플레이어
 * (`components/demo/`)도 같은 지점을 조작한다.
 */
interface DemoControllerState {
  /** `bpmProcess.sequence`의 인덱스. */
  stepIndex: number;
  /** 사람이 내린 Management Review 결정. 승인 전에는 null. */
  decision: ReviewDecision | null;

  next: () => void;
  prev: () => void;
  reset: () => void;
  setStep: (index: number) => void;

  /** 승인. 결정을 기록하고 프로세스를 Management Action 단계로 넘긴다. */
  approve: (decision: ReviewDecision) => void;
  /** 결정 취소 — 데모를 다시 돌리기 위한 것이며, 실제 시스템의 철회와는 다르다. */
  clearDecision: () => void;

  isAtEnd: () => boolean;
  isAtStart: () => boolean;
}

export const useDemoController = create<DemoControllerState>((set, get) => ({
  stepIndex: bpmProcess.defaultStepIndex,
  decision: null,

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

  isAtEnd: () => get().stepIndex >= maxStepIndex(bpmProcess),
  isAtStart: () => get().stepIndex <= 0,
}));
