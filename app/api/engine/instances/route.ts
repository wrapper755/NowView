/**
 * 프로세스 인스턴스 생성·목록.
 *
 * 기존 `/api/bpm/*`와 성격이 다르다 — 그쪽은 진행 지점을 받아 계산해 돌려주는
 * 무상태 계산기이고, 여기는 **서버에 사는 인스턴스**를 다룬다(CLAUDE.md 5.2
 * "상태 소유권 이전"). 둘을 함께 두는 이유는 Mock 데모가 계속 계산기 쪽으로
 * 동작해야 하기 때문이다.
 *
 * 토폴로지는 클라이언트가 보내지 않는다 — 여기서 `lib/mock-data`를 읽어 만든다.
 * 클라이언트가 그래프를 보낼 수 있으면 아무 프로세스나 실행시킬 수 있다.
 */

import { badRequest, fail, ok, readJson } from "@/lib/api/response";
import { DEFAULT_SCENARIO_ID, scenarios } from "@/lib/mock-data/scenarios";
import { createInstance, listInstances, type AgentMode } from "@/services/engine-client";
import { buildEngineSpec } from "@/services/engine-spec";

const AGENT_MODES: AgentMode[] = ["mock", "llm"];

export async function GET() {
  const result = await listInstances();
  if (!result.ok) return fail(result.status, result.error, result.detail);
  return ok(result.data);
}

export async function POST(request: Request) {
  const body = await readJson(request);
  if (!body.ok) return badRequest(body.message);

  const { scenarioId = DEFAULT_SCENARIO_ID, agentMode = "mock" } =
    (body.data ?? {}) as { scenarioId?: string; agentMode?: string };

  const scenario = scenarios.find((item) => item.id === scenarioId);
  if (!scenario) {
    return badRequest("없는 시나리오다", {
      scenarioId,
      available: scenarios.map((item) => item.id),
    });
  }
  if (!AGENT_MODES.includes(agentMode as AgentMode)) {
    return badRequest("Agent 모드는 mock 또는 llm이다", { agentMode });
  }

  let spec;
  try {
    spec = buildEngineSpec(scenario);
  } catch (cause) {
    // 게이트웨이에 분기 규칙이 없는 등 Mock 데이터 자체의 문제다 — 엔진 잘못이 아니다.
    return fail(500, "프로세스 명세를 만들 수 없다", String(cause));
  }

  const result = await createInstance(spec, agentMode as AgentMode);
  if (!result.ok) return fail(result.status, result.error, result.detail);
  return ok(result.data, { status: 201 });
}
