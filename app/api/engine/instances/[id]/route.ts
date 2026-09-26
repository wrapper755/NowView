/**
 * 인스턴스 조회·종료.
 *
 * Next 16의 동적 세그먼트는 `params`가 Promise다 — await하지 않으면 런타임에 터진다.
 */

import { fail, ok } from "@/lib/api/response";
import { deleteInstance, getInstance } from "@/services/engine-client";

type Context = { params: Promise<{ id: string }> };

export async function GET(_request: Request, { params }: Context) {
  const { id } = await params;
  const result = await getInstance(id);
  if (!result.ok) return fail(result.status, result.error, result.detail);
  return ok(result.data);
}

export async function DELETE(_request: Request, { params }: Context) {
  const { id } = await params;
  const result = await deleteInstance(id);
  if (!result.ok) return fail(result.status, result.error, result.detail);
  return new Response(null, { status: 204 });
}
