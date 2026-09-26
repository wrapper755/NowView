/**
 * 장면 이동 — 데모 플레이어가 부른다.
 *
 * **뒤로 가기는 읽기 전용이다.** 과거 체크포인트를 읽어 그 시점 스냅샷만 돌려주고
 * 인스턴스는 움직이지 않는다 — 실행으로 구현하면 스크러버를 움직일 때마다 LLM이
 * 다시 불리고 이미 내려진 승인이 사라진다.
 *
 * 앞으로 갈 때 승인 노드를 통과해야 하면 `decision`이 필요하다. 엔진이 임의로 승인하면
 * Human-in-the-Loop이 무너지므로, 무엇을 골랐는지는 장면이 선언한다.
 */

import { badRequest, fail, ok, readJson } from "@/lib/api/response";
import { seekInstance } from "@/services/engine-client";

type Context = { params: Promise<{ id: string }> };

export async function POST(request: Request, { params }: Context) {
  const { id } = await params;
  const body = await readJson(request);
  if (!body.ok) return badRequest(body.message);

  const { targetNodeId, decision, acknowledgedBy } = (body.data ?? {}) as {
    targetNodeId?: string;
    decision?: unknown;
    acknowledgedBy?: string;
  };
  if (typeof targetNodeId !== "string" || targetNodeId.length === 0) {
    return badRequest("targetNodeId가 필요하다");
  }

  const result = await seekInstance(id, { targetNodeId, decision, acknowledgedBy });
  if (!result.ok) return fail(result.status, result.error, result.detail);
  return ok(result.data);
}
