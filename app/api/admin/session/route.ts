import { adminConfigured, sessionOf } from "@/lib/admin-session";

/** 관리자 세션이 살아 있나 — 관리자 화면이 로그인 폼을 보일지 정한다. */

export const dynamic = "force-dynamic";

export function GET(request: Request): Response {
  return Response.json({ configured: adminConfigured(), loggedIn: adminConfigured() && sessionOf(request) });
}
