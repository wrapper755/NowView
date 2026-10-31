import { adminConfigured, cookieHeader, issueSession, passwordMatches } from "@/lib/admin-session";

/** 관리자 로그인 — 비밀번호가 맞으면 서명한 세션 쿠키를 준다. 로그아웃은 DELETE. */

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  if (!adminConfigured()) {
    return Response.json({ error: "관리자 모드가 꺼져 있다 — 서버 환경에 관리자 비밀번호·키가 없다" }, { status: 503 });
  }
  let password = "";
  try {
    password = String(((await request.json()) as { password?: unknown }).password ?? "");
  } catch {
    return Response.json({ error: "요청 본문이 JSON이 아니다" }, { status: 400 });
  }
  if (!passwordMatches(password)) {
    // 틀린 시도를 늦춰 대입 공격을 무디게 한다(횟수 제한은 아직 없다).
    await new Promise((resolve) => setTimeout(resolve, 800));
    return Response.json({ error: "비밀번호가 틀렸다" }, { status: 401 });
  }
  const session = issueSession();
  return Response.json({ ok: true }, { headers: { "set-cookie": cookieHeader(session.value, session.maxAge) } });
}

export async function DELETE(): Promise<Response> {
  return Response.json({ ok: true }, { headers: { "set-cookie": cookieHeader("", 0) } });
}
