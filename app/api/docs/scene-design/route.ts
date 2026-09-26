import { scenarios } from "@/lib/mock-data/scenarios";
import { badRequest, ok } from "@/lib/api/response";
import { sceneDesignMarkdown, sceneDesignRows } from "@/services/scene-design";

/**
 * GET /api/docs/scene-design — 장면별 설계표 (기획안 4.2).
 *
 * 기본은 마크다운이며 `?format=json`이면 구조화된 행을 돌려준다.
 * `?scenario=<id>`로 한 시나리오만 뽑을 수 있다.
 *
 * **문서를 손으로 쓰지 않고 여기서 생성하는 이유**: 설계표는 Business 설계를 BPM·Agent
 * 구현으로 잇는 공통 명세다. 손으로 쓰면 구현이 바뀔 때 문서만 낡아 명세로서 쓸모가 없어진다.
 */
export function GET(request: Request) {
  const url = new URL(request.url);
  const scenarioId = url.searchParams.get("scenario");
  const format = url.searchParams.get("format") ?? "md";

  const selected = scenarioId
    ? scenarios.filter((s) => s.id === scenarioId)
    : scenarios;

  if (selected.length === 0) {
    return badRequest(`알 수 없는 시나리오: ${scenarioId}`, {
      available: scenarios.map((s) => s.id),
    });
  }

  if (format === "json") {
    return ok(
      selected.map((scenario) => ({
        scenarioId: scenario.id,
        title: scenario.title,
        rows: sceneDesignRows(scenario),
      })),
    );
  }

  return new Response(sceneDesignMarkdown(selected), {
    headers: { "content-type": "text/markdown; charset=utf-8" },
  });
}
