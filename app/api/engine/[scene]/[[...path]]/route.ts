/**
 * 엔진 프록시(BFF) — `/api/engine/{장면}/*` → 엔진 `/{장면}/*`. 장면은 `sc01`~`sc07`이고, 그 밖에 공개 회사 목록
 * (`/api/engine/companies` — 이름·설명·업무)과 회사 운영 현황(`/api/engine/companies/{회사}/works`)만 연다. 관리 API(`/admin/*`)는 여기서 중계하지 않는다 — 관리자 로그인 뒤의
 * `/api/admin/*`만 부른다(`app/api/admin`).
 *
 * **브라우저가 엔진을 직접 부르지 않는다.** CORS가 생기고 엔진 주소가 드러난다. 운영계에서
 * 엔진은 127.0.0.1에만 바인딩되어 있다(CLAUDE.md 5.4).
 *
 * **읽기만 중계한다**(2026-11-03, `docs/role-split.md` §5.5) — GET(SSE 포함)뿐이고 POST·PUT·PATCH·DELETE는 405다. 결재 답·장면 열기·
 * 시계·초기화 같은 시연 조작은 회사 사이트가 기간계·Center로 하고, NowView 일꾼이 그것을 따라간다. 엔진의 쓰기 경로는 시험 전용이다.
 *
 * 경로를 하나씩 옮겨 적지 않고 그대로 중계한다 — 업무 규칙(권한·상태 충돌·입력 검증)은 전부
 * 엔진에 있고, 여기서 같은 검사를 다시 하면 두 곳이 갈라진다. 넘기는 헤더는 행위자뿐이다(장면 6·7 조회가 참여자만 받는다).
 * 바깥 Chaeksas가 여기를 부르는 길은 없다 — 서비스 태스크의 일감은 엔진의 C15 일꾼이 Center에서
 * 가져간다(engine/app/consumer.py).
 * SSE(`…/events`)는 본문 스트림을 그대로 흘린다.
 */

const ENGINE_URL = process.env.ENGINE_URL ?? "http://localhost:8077";

export const dynamic = "force-dynamic";

/** 중계할 장면. 목록 밖의 경로는 엔진에 보내지 않는다 — 엔진의 다른 경로(`/health` 등)가 열리지 않게. */
const SCENES = new Set(["sc01", "sc02", "sc03", "sc04", "sc05", "sc06", "sc07"]);
/** 장면이 아닌 읽기 경로 — GET만, 하위 경로는 회사 운영 현황(`{회사}/works`) 하나뿐이다. */
const READ_ONLY = new Set(["companies"]);

type Context = { params: Promise<{ scene: string; path?: string[] }> };

async function relay(request: Request, { params }: Context): Promise<Response> {
  const { scene, path = [] } = await params;
  const readOnly = READ_ONLY.has(scene) && (path.length === 0 || (path.length === 2 && path[1] === "works"));
  if (!SCENES.has(scene) && !readOnly) return Response.json({ error: `없는 경로: ${scene}` }, { status: 404 });
  if (SCENES.has(scene) && path.length === 0) return Response.json({ error: "장면 아래 경로가 없다" }, { status: 404 });
  const url = new URL(request.url);
  const tail = path.length ? `/${path.map(encodeURIComponent).join("/")}` : "";
  const target = `${ENGINE_URL}/${scene}${tail}${url.search}`;
  const isStream = path.at(-1) === "events";

  const headers: Record<string, string> = { accept: isStream ? "text/event-stream" : "application/json" };
  const actor = request.headers.get("x-demo-actor");
  if (actor) headers["x-demo-actor"] = actor;

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      headers,
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
