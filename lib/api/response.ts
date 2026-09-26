/**
 * Route Handler 공통 응답 형태.
 *
 * 오류 응답의 모양을 한곳에서 고정한다 — 라우트마다 제각각이면 호출부가 분기를 만들게 된다.
 * 성공은 페이로드를 그대로 내보내고, 실패는 항상 `{ error, detail? }`이다.
 */

import { NextResponse } from "next/server";

export function ok<T>(payload: T, init?: ResponseInit): NextResponse {
  return NextResponse.json(payload, init);
}

export function fail(status: number, error: string, detail?: unknown): NextResponse {
  return NextResponse.json(detail === undefined ? { error } : { error, detail }, { status });
}

/** 잘못된 요청. 무엇이 왜 틀렸는지 호출부가 알 수 있게 detail을 붙인다. */
export const badRequest = (error: string, detail?: unknown) => fail(400, error, detail);
export const notFound = (error: string, detail?: unknown) => fail(404, error, detail);

/**
 * 요청 본문을 JSON으로 읽는다.
 *
 * 본문이 비었거나 JSON이 아니면 파싱 단계에서 터지는데, 그 예외를 그대로 두면 500이 나간다.
 * 호출부 잘못이므로 400으로 돌려주기 위해 결과를 감싼다.
 */
export async function readJson(
  request: Request,
): Promise<{ ok: true; data: unknown } | { ok: false; message: string }> {
  try {
    return { ok: true, data: await request.json() };
  } catch {
    return { ok: false, message: "요청 본문이 올바른 JSON이 아니다" };
  }
}

/** 정수 쿼리 파라미터를 읽는다. 없으면 fallback, 숫자가 아니면 null(호출부가 400 처리). */
export function readIntParam(
  url: URL,
  name: string,
  fallback: number,
): number | null {
  const raw = url.searchParams.get(name);
  if (raw === null) return fallback;
  const parsed = Number(raw);
  return Number.isInteger(parsed) ? parsed : null;
}
