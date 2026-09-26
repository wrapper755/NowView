/**
 * 엔진 상태 점검.
 *
 * 엔진이 꺼져 있어도 200으로 응답하고 `reachable: false`를 알린다 — 이 프로젝트는
 * Mock만으로 전부 동작하므로 엔진 부재는 고장이 아니다. 503으로 터뜨리면 엔진을
 * 켜지 않은 사람에게 앱이 망가진 것처럼 보인다.
 */

import { ok } from "@/lib/api/response";
import { scenarios } from "@/lib/mock-data/scenarios";
import { ENGINE_URL, engineHealth } from "@/services/engine-client";

export async function GET() {
  const health = await engineHealth();
  return ok({
    engineUrl: ENGINE_URL,
    reachable: health.ok,
    ...(health.ok ? { engine: health.data } : { error: health.error }),
    scenarios: scenarios.map((scenario) => ({ id: scenario.id, title: scenario.shortTitle })),
    endpoints: {
      create: "POST /api/engine/instances  {scenarioId, agentMode: mock|llm}",
      list: "GET /api/engine/instances",
      read: "GET /api/engine/instances/{id}",
      resume: "POST /api/engine/instances/{id}/resume  {…승인 입력}",
      remove: "DELETE /api/engine/instances/{id}",
    },
  });
}
