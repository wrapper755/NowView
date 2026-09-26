/**
 * 사람의 입력으로 멈춘 워크플로를 재개한다.
 *
 * **기존 `/api/bpm/decision`과 다르다.** 그쪽은 결정을 받아 과제·Gap 변화를 계산해
 * 돌려주는 순수 함수다. 여기는 LangGraph `interrupt`로 실제로 멈춰 있는 실행을
 * `resume`한다 — 승인이 워크플로를 움직이는 경로가 처음으로 생긴 것이다.
 *
 * 사유 10자 검사는 엔진이 한다(UI 버튼 비활성은 강제가 아니다). 반려되면 400이
 * 아니라 `pendingApproval.error`가 달린 200이 온다 — 같은 지점에 다시 멈춘 것이므로
 * 오류가 아니라 상태다. 클라이언트는 그 상태를 그리고 다시 보내면 된다.
 */

import { badRequest, fail, ok, readJson } from "@/lib/api/response";
import { resumeInstance } from "@/services/engine-client";

type Context = { params: Promise<{ id: string }> };

export async function POST(request: Request, { params }: Context) {
  const { id } = await params;
  const body = await readJson(request);
  if (!body.ok) return badRequest(body.message);

  const payload = (body.data ?? {}) as Record<string, unknown>;
  if (typeof payload !== "object" || Array.isArray(payload)) {
    return badRequest("재개 입력은 객체여야 한다");
  }

  const result = await resumeInstance(id, payload);
  if (!result.ok) return fail(result.status, result.error, result.detail);
  return ok(result.data);
}
