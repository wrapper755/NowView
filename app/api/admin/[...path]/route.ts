import { adminConfigured, sessionOf } from "@/lib/admin-session";

/**
 * 관리 API 중계 — 관리자 세션이 있을 때만 엔진 `/admin/*`로 보낸다. 엔진 키(`NOWVIEW_ADMIN_KEY`)는 여기서만 싣는다 —
 * 브라우저는 그 키를 모른다. 공개 BFF(`/api/engine/*`)는 `/admin`을 중계하지 않는다.
 */

const ENGINE_URL = process.env.ENGINE_URL ?? "http://localhost:8077";

export const dynamic = "force-dynamic";

type Context = { params: Promise<{ path: string[] }> };

async function relay(request: Request, { params }: Context): Promise<Response> {
  if (!adminConfigured()) return Response.json({ error: "관리자 모드가 꺼져 있다" }, { status: 503 });
  if (!sessionOf(request)) return Response.json({ error: "관리자 로그인이 필요하다" }, { status: 401 });
  const { path } = await params;
  const target = `${ENGINE_URL}/admin/${path.map(encodeURIComponent).join("/")}`;
  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        "x-admin-key": process.env.NOWVIEW_ADMIN_KEY ?? "",
      },
      body: request.method === "GET" ? undefined : await request.text(),
      cache: "no-store",
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch (cause) {
    return Response.json({ error: `엔진에 연결할 수 없다 (${ENGINE_URL})`, detail: String(cause) }, { status: 503 });
  }
}

export const GET = relay;
export const PUT = relay;
