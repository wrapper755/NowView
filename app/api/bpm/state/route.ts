import { DEFAULT_SCENARIO_ID, scenarioById } from "@/lib/mock-data/scenarios";
import { badRequest, ok, readIntParam } from "@/lib/api/response";
import { agentActivities, runningAgentCount } from "@/services/agent-orchestrator";
import {
  currentNode,
  currentStage,
  deriveNodeStatuses,
  isAwaitingHuman,
  maxStepIndex,
  progressPercent,
} from "@/services/bpm-engine";

/**
 * GET /api/bpm/state?step=N — 주어진 진행 지점에서의 파생 상태.
 *
 * **상태를 서버에 저장하지 않는다.** 진행 지점은 요청이 들고 오고, 서버는 그 지점에서의
 * 노드 상태·Agent 활동을 계산해 돌려줄 뿐이다. 서버리스에서 인메모리 상태는 인스턴스마다
 * 갈라지고, 이 프로젝트는 이미 클라이언트(Zustand)가 진행 지점을 소유한다.
 *
 * 계산은 전부 `services/`를 그대로 호출한다 — 화면과 API가 같은 로직을 쓰므로 둘의 결과가
 * 어긋날 수 없다. API에서 로직을 다시 구현하면 그 순간부터 갈라진다.
 */
export function GET(request: Request) {
  const url = new URL(request.url);
  // 시나리오를 지정하지 않으면 첫 번째를 쓴다. 상태는 여전히 서버에 저장하지 않는다.
  const { process } = scenarioById(
    url.searchParams.get("scenario") ?? DEFAULT_SCENARIO_ID,
  );
  const step = readIntParam(url, "step", process.defaultStepIndex);

  if (step === null) {
    return badRequest("step은 정수여야 한다", { received: url.searchParams.get("step") });
  }

  const max = maxStepIndex(process);
  if (step < 0 || step > max) {
    return badRequest(`step은 0 이상 ${max} 이하여야 한다`, { received: step });
  }

  const node = currentNode(process, step);

  return ok({
    processId: process.id,
    step,
    maxStep: max,
    stage: currentStage(process, step),
    progressPercent: progressPercent(process, step),
    awaitingHuman: isAwaitingHuman(process, step),
    currentNode: node ? { id: node.id, label: node.label, kind: node.kind, actor: node.actor } : null,
    nodeStatuses: deriveNodeStatuses(process, step),
    runningAgents: runningAgentCount(process, step),
    agents: agentActivities(process, step),
  });
}
