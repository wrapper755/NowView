import { createHmac, timingSafeEqual } from "node:crypto";

/**
 * 관리자 세션(서버 전용) — 관리자 모드(`/admin`)만 쓴다(`docs/worker-interfaces.md` §0.1 Q7).
 *
 * * 비밀번호는 환경 `NOWVIEW_ADMIN_PASSWORD`, 쿠키 서명 키는 `NOWVIEW_ADMIN_SECRET`에만 있다(`.env.local`·`/etc/nowview.env`).
 *   둘 중 하나라도 없으면 관리자 모드는 꺼져 있다 — 조용히 열리지 않는다.
 * * 엔진의 관리 API(`/admin/*`)는 BFF만 아는 키(`NOWVIEW_ADMIN_KEY`)로 막는다 — 브라우저는 그 키를 보지 못한다.
 * * 세션은 서명한 만료 시각 하나다(서버에 상태가 없다). 8시간.
 */

export const ADMIN_COOKIE = "nowview_admin";
const SESSION_S = 8 * 60 * 60;

function secret(): string | null {
  return process.env.NOWVIEW_ADMIN_SECRET || null;
}

export function adminConfigured(): boolean {
  return Boolean(process.env.NOWVIEW_ADMIN_PASSWORD && secret() && process.env.NOWVIEW_ADMIN_KEY);
}

function sign(value: string): string {
  return createHmac("sha256", secret() ?? "").update(value).digest("base64url");
}

function same(a: string, b: string): boolean {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  return left.length === right.length && timingSafeEqual(left, right);
}

export function passwordMatches(given: string): boolean {
  const expected = process.env.NOWVIEW_ADMIN_PASSWORD;
  return Boolean(expected) && same(given, expected ?? "");
}

/** 새 세션 쿠키 값과 수명(초). */
export function issueSession(now = Date.now()): { value: string; maxAge: number } {
  const expires = Math.floor(now / 1000) + SESSION_S;
  return { value: `${expires}.${sign(String(expires))}`, maxAge: SESSION_S };
}

export function validSession(value: string | undefined, now = Date.now()): boolean {
  if (!value || !secret()) return false;
  const [expires, mac] = value.split(".");
  if (!expires || !mac || !same(mac, sign(expires))) return false;
  return Number(expires) > Math.floor(now / 1000);
}

/** 요청의 쿠키에서 세션을 본다. */
export function sessionOf(request: Request): boolean {
  const cookie = request.headers.get("cookie") ?? "";
  const found = cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${ADMIN_COOKIE}=`));
  return validSession(found?.slice(ADMIN_COOKIE.length + 1));
}

export function cookieHeader(value: string, maxAge: number): string {
  const secure = process.env.NODE_ENV === "production" ? "; Secure" : "";
  return `${ADMIN_COOKIE}=${value}; Path=/; HttpOnly; SameSite=Strict; Max-Age=${maxAge}${secure}`;
}
