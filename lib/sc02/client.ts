/**
 * SC02 엔진 호출 — BFF(`/api/engine/sc02/*`). SC01 클라이언트와 같은 태도다: 실패를 throw하지 않고
 * `{ ok: false }`로 돌려 화면이 배너로 말한다.
 */

import type { HistoryEntry, ProcessTopology } from "@/lib/sc01/types";
import type { Sc02Case, Sc02View } from "@/lib/sc02/types";

export const SC02_BASE = "/api/engine/sc02";

/** 화면이 고르는 실행 위치 — 내장은 고르지 않는다(2026-10-27). */
export type Sc02Executor = "center" | "studio";

export type Result<T> = { ok: true; data: T } | { ok: false; status: number; error: string };

async function call<T>(
  path: string,
  init?: RequestInit & { actor?: string; idempotencyKey?: string },
): Promise<Result<T>> {
  const { actor, idempotencyKey, ...rest } = init ?? {};
  try {
    const response = await fetch(`${SC02_BASE}${path}`, {
      ...rest,
      cache: "no-store",
      headers: {
        "content-type": "application/json",
        ...(actor ? { "x-demo-actor": actor } : {}),
        ...(idempotencyKey ? { "idempotency-key": idempotencyKey } : {}),
      },
    });
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = body?.detail ?? body?.error;
      return {
        ok: false,
        status: response.status,
        error: typeof detail === "string" ? detail : `엔진 오류 (${response.status})`,
      };
    }
    return { ok: true, data: body as T };
  } catch (cause) {
    return { ok: false, status: 503, error: `엔진에 연결할 수 없다 — ${String(cause)}` };
  }
}

const post = <T>(path: string, body: unknown, actor?: string, idempotencyKey?: string) =>
  call<T>(path, { method: "POST", body: JSON.stringify(body ?? {}), actor, idempotencyKey });

export const sc02Api = {
  process: () => call<ProcessTopology>("/process"),
  cases: () => call<Sc02Case[]>("/cases"),
  rules: () => call<Record<string, string>>("/rules"),
  parts: () => call<{ modelId: string; partId: string; supplierId: string; qtyPer: string }[]>("/parts"),
  /** 장면 1 데모 실행을 이어 장면 2를 시작한다. 없으면 장면 1을 새로 만들어 인계까지 돌린다. */
  create: (sc01DemoRunId: string | null, caseId = "BASE", executor: Sc02Executor = "center") =>
    post<Sc02View>(
      "/demo-runs",
      { ...(sc01DemoRunId ? { sc01DemoRunId } : {}), caseId, executor },
      "u-demo",
    ),
  get: (id: string) => call<Sc02View>(`/demo-runs/${id}`),
  history: (id: string) => call<HistoryEntry[]>(`/demo-runs/${id}/history`),
  at: (id: string, seq: number) => call<Sc02View>(`/demo-runs/${id}/history/${seq}`),
  receive: (id: string, fixtureId: string, actor: string, key?: string) =>
    post<Sc02View>(`/demo-runs/${id}/requests/receive`, { fixtureId }, actor, key),
  act: (
    id: string,
    nodeId: string,
    answer: Record<string, unknown>,
    actor: string,
    expect?: Record<string, string>,
    key?: string,
  ) => post<Sc02View>(`/demo-runs/${id}/actions/${nodeId}`, { answer, expect }, actor, key),
  changeDue: (id: string, due: string, reason: string, actor: string) =>
    post<Sc02View>(`/demo-runs/${id}/negotiation-due`, { due, reason }, actor),
  adopt: (id: string, outputId: string, actor: string) =>
    post<Sc02View>(`/demo-runs/${id}/agent-outputs/${outputId}/adopt`, {}, actor),
  clock: (id: string, at: string) => post<Sc02View>(`/demo-runs/${id}/clock`, { at }, "u-demo"),
  step: (id: string, index: number) => post<Sc02View>(`/demo-runs/${id}/script/${index}`, {}),
  reset: (id: string, executor?: Sc02Executor) =>
    post<Sc02View>(`/demo-runs/${id}/reset`, executor ? { executor } : {}, "u-demo"),
  eventsUrl: (id: string) => `${SC02_BASE}/demo-runs/${id}/events`,
};
