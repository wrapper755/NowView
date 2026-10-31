/**
 * 엔진 프록시(BFF) — `/api/engine/{장면}/*` → 엔진 `/{장면}/*`. 장면은 `sc01`~`sc06`뿐이다.
 *
 * **브라우저가 엔진을 직접 부르지 않는다.** CORS가 생기고 엔진 주소가 드러난다. 운영계에서
 * 엔진은 127.0.0.1에만 바인딩되어 있다(CLAUDE.md 5.4).
 *
 * 경로를 하나씩 옮겨 적지 않고 그대로 중계한다 — 업무 규칙(권한·상태 충돌·입력 검증)은 전부
 * 엔진에 있고, 여기서 같은 검사를 다시 하면 두 곳이 갈라진다. 넘기는 헤더는 행위자·멱등키뿐이다.
 * 바깥 Chaeksas가 여기를 부르는 길은 없다 — 서비스 태스크의 일감은 엔진의 C15 일꾼이 Center에서
 * 가져간다(engine/app/consumer.py).
 * SSE(`…/events`)는 본문 스트림을 그대로 흘린다.
 */

const ENGINE_URL = process.env.ENGINE_URL ?? "http://localhost:8077";

export const dynamic = "force-dynamic";

/** 중계할 장면. 목록 밖의 경로는 엔진에 보내지 않는다 — 엔진의 다른 경로(`/health` 등)가 열리지 않게. */
const SCENES = new Set(["sc01", "sc02", "sc03", "sc04", "sc05", "sc06"]);

type Context = { params: Promise<{ scene: string; path: string[] }> };

async function relay(request: Request, { params }: Context): Promise<Response> {
  const { scene, path } = await params;
  if (!SCENES.has(scene)) return Response.json({ error: `없는 장면: ${scene}` }, { status: 404 });
  const url = new URL(request.url);
  const target = `${ENGINE_URL}/${scene}/${path.map(encodeURIComponent).join("/")}${url.search}`;
  const isStream = path.at(-1) === "events";

  const headers: Record<string, string> = { accept: isStream ? "text/event-stream" : "application/json" };
  for (const name of ["x-demo-actor", "idempotency-key"]) {
    const value = request.headers.get(name);
    if (value) headers[name] = value;
  }
  if (request.method !== "GET") headers["content-type"] = "application/json";

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" ? undefined : await request.text(),
      // 클라이언트가 끊으면 상류도 끊는다 — 안 하면 엔진에 SSE 구독자가 쌓인다.
      signal: request.signal,
      cache: "no-store",
    });
  } catch (cause) {
    return Response.json(
      { error: `엔진에 연결할 수 없다 (${ENGINE_URL})`, detail: String(cause) },
      { status: 503 },
    );
  }

  if (isStream && upstream.ok && upstream.body) {
    return new Response(upstream.body, {
      headers: {
        "content-type": "text/event-stream; charset=utf-8",
        // 중간 캐시·프록시가 모으면 이벤트가 몰려서 늦게 도착한다(4.9).
        "cache-control": "no-cache, no-transform",
        connection: "keep-alive",
        "x-accel-buffering": "no",
      },
    });
  }
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}

export const GET = relay;
export const POST = relay;
