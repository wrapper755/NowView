/**
 * 엔진 프록시(BFF) — `/api/engine/companies/*` → 엔진 `/companies/*`. 공개 회사 목록(`/api/engine/companies` — 이름·설명·
 * 업무·회사 사이트 주소)과 회사 대시보드(`/api/engine/companies/{회사}/dashboard?world=`)만 연다. 관리 API(`/admin/*`)는 여기서
 * 중계하지 않는다 — 관리자 로그인 뒤의 `/api/admin/*`만 부른다(`app/api/admin`).
 *
 * **장면 경로(`sc01`~`sc07`)는 중계하지 않는다**(2026-11-03 4단계, `docs/role-split.md`) — 장면 화면을 걷었다. 업무 화면은 회사
 * 사이트가 기간계의 경영 기록으로 그린다. 엔진의 장면 읽기 경로는 엔진 시험과 기록 대조가 쓴다(127.0.0.1에서만 닿는다).
 *
 * **브라우저가 엔진을 직접 부르지 않는다.** CORS가 생기고 엔진 주소가 드러난다. 운영계에서 엔진은 127.0.0.1에만 바인딩되어
 * 있다(CLAUDE.md 5.4). **읽기만 중계한다** — GET뿐이고 POST·PUT·PATCH·DELETE는 405다.
 */

const ENGINE_URL = process.env.ENGINE_URL ?? "http://localhost:8077";

export const dynamic = "force-dynamic";

type Context = { params: Promise<{ scene: string; path?: string[] }> };

/** 열린 경로 — `companies` 하나와 그 아래 `{회사}/dashboard`. 목록 밖은 엔진에 보내지 않는다(`/health` 등이 열리지 않게). */
function allowed(scene: string, path: string[]): boolean {
  if (scene !== "companies") return false;
  return path.length === 0 || (path.length === 2 && path[1] === "dashboard");
}

async function relay(request: Request, { params }: Context): Promise<Response> {
  const { scene, path = [] } = await params;
  if (!allowed(scene, path)) return Response.json({ error: `없는 경로: ${[scene, ...path].join("/")}` }, { status: 404 });
  const url = new URL(request.url);
  const tail = path.length ? `/${path.map(encodeURIComponent).join("/")}` : "";
  const target = `${ENGINE_URL}/${scene}${tail}${url.search}`;

  let upstream: Response;
  try {
    upstream = await fetch(target, { headers: { accept: "application/json" }, signal: request.signal, cache: "no-store" });
  } catch (cause) {
    return Response.json({ error: `엔진에 연결할 수 없다 (${ENGINE_URL})`, detail: String(cause) }, { status: 503 });
  }
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}

/** 쓰기는 받지 않는다 — 시연 조작은 회사 사이트에서 한다. */
function readOnlyRefusal(): Response {
  return Response.json(
    { error: "NowView 화면은 읽기 전용이다 — 결재·시연 조작은 회사 사이트에서 한다" },
    { status: 405, headers: { allow: "GET" } },
  );
}

export const GET = relay;
export const POST = readOnlyRefusal;
export const PUT = readOnlyRefusal;
export const PATCH = readOnlyRefusal;
export const DELETE = readOnlyRefusal;
