import { bpmProcess } from "@/lib/mock-data/bpm-process";
import { badRequest, ok, readJson } from "@/lib/api/response";
import {
  clampStepIndex,
  currentStage,
  deriveNodeStatuses,
  isAwaitingHuman,
  maxStepIndex,
} from "@/services/bpm-engine";

const ACTIONS = ["next", "prev", "reset", "goto"] as const;
type TransitionAction = (typeof ACTIONS)[number];

interface TransitionRequest {
  /** 현재 진행 지점. 서버가 상태를 들고 있지 않으므로 요청이 가져와야 한다. */
  step: number;
  action: TransitionAction;
  /** `goto`일 때의 목표 지점. */
  target?: number;
}

function parse(body: unknown): { ok: true; value: TransitionRequest } | { ok: false; message: string } {
  if (typeof body !== "object" || body === null) {
    return { ok: false, message: "본문은 객체여야 한다" };
  }
  const { step, action, target } = body as Record<string, unknown>;

  if (!Number.isInteger(step)) return { ok: false, message: "step은 정수여야 한다" };
  if (typeof action !== "string" || !ACTIONS.includes(action as TransitionAction)) {
    return { ok: false, message: `action은 ${ACTIONS.join(" | ")} 중 하나여야 한다` };
  }
  if (action === "goto" && !Number.isInteger(target)) {
    return { ok: false, message: "goto에는 정수 target이 필요하다" };
  }

  return {
    ok: true,
    value: { step: step as number, action: action as TransitionAction, target: target as number | undefined },
  };
}

function nextStep(req: TransitionRequest): number {
  switch (req.action) {
    case "next":
      return req.step + 1;
    case "prev":
      return req.step - 1;
    case "reset":
      return 0;
    case "goto":
      return req.target as number;
  }
}

/**
 * POST /api/bpm/transition — 상태 전이 계산.
 *
 * 저장하지 않고 **다음 상태를 계산해 돌려줄 뿐이다**(`/api/bpm/state`와 같은 이유).
 * 범위를 벗어난 지점은 400이 아니라 `clampStepIndex`로 잘라내고 `clamped: true`로 알린다 —
 * 마지막 단계에서 next를 누르는 것은 오류가 아니라 정상적인 UI 동작이다.
 */
export async function POST(request: Request) {
  const body = await readJson(request);
  if (!body.ok) return badRequest(body.message);

  const parsed = parse(body.data);
  if (!parsed.ok) return badRequest(parsed.message, body.data);

  const max = maxStepIndex(bpmProcess);
  if (parsed.value.step < 0 || parsed.value.step > max) {
    return badRequest(`step은 0 이상 ${max} 이하여야 한다`, { received: parsed.value.step });
  }

  const requested = nextStep(parsed.value);
  const step = clampStepIndex(bpmProcess, requested);

  return ok({
    processId: bpmProcess.id,
    previousStep: parsed.value.step,
    step,
    clamped: step !== requested,
    maxStep: max,
    stage: currentStage(bpmProcess, step),
    awaitingHuman: isAwaitingHuman(bpmProcess, step),
    nodeStatuses: deriveNodeStatuses(bpmProcess, step),
  });
}
