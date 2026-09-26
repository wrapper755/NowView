/**
 * 엔진 SSE 스트림을 브라우저로 중계한다.
 *
 * **브라우저가 엔진을 직접 부르지 않는다**(다른 엔진 라우트와 같은 이유) — CORS가 생기고
 * 엔진 주소가 노출된다. 여기서 상류 스트림의 본문을 그대로 흘려보낸다.
 *
 * `instances` 목록을 클라이언트가 보내지만 **인스턴스 id는 추측할 수 없는 값**이고
 * (uuid), 엔진이 없는 id에는 404를 준다. 목록을 검증하는 대신 상류의 판단을 그대로
 * 전달한다.
 */

import { ENGINE_URL } from "@/services/engine-client";
import { badRequest, fail } from "@/lib/api/response";

/**
 * 스트리밍이므로 정적 최적화를 끈다.
 *
 * 이 라우트는 어차피 `ƒ`(동적)이지만, 명시하지 않으면 빌드가 캐시 가능한 것으로
 * 오해할 여지를 남긴다.
 */
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const instances = new URL(request.url).searchParams.get("instances");
  if (!instances) return badRequest("instances 쿼리가 필요하다");

  let upstream: Response;
  try {
    upstream = await fetch(
      `${ENGINE_URL}/events?instances=${encodeURIComponent(instances)}`,
      {
        headers: { accept: "text/event-stream" },
        // 클라이언트가 연결을 닫으면 상류도 함께 끊는다 — 안 하면 엔진에 구독자가 쌓인다.
        signal: request.signal,
        cache: "no-store",
      },
    );
  } catch (cause) {
    return fail(503, `엔진에 연결할 수 없다 (${ENGINE_URL})`, String(cause));
  }

  if (!upstream.ok || !upstream.body) {
    const body = await upstream.json().catch(() => null);
    return fail(
      upstream.status,
      typeof body?.detail === "string" ? body.detail : "엔진이 스트림을 열지 못했다",
      body,
    );
  }

  return new Response(upstream.body, {
    headers: {
      "content-type": "text/event-stream; charset=utf-8",
      // 중간 캐시·프록시가 모으면 이벤트가 몰려서 늦게 도착한다.
      "cache-control": "no-cache, no-transform",
      connection: "keep-alive",
      "x-accel-buffering": "no",
    },
  });
}
