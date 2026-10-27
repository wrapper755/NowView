/**
 * SC03 엔진 호출 — BFF(`/api/engine/sc03/*`). 장면 1·2 클라이언트와 같은 태도다: 실패를 throw하지 않고
 * `{ ok: false }`로 돌려 화면이 배너로 말한다. 완료 조건 미충족(422)은 남은 항목(`blockingItems`)을 함께 준다.
 */

import type { HistoryEntry, ProcessTopology } from "@/lib/sc01/types";
import type { Sc03Case, Sc03ScriptStep, Sc03View } from "@/lib/sc03/types";

export const SC03_BASE = "/api/engine/sc03";

/** 화면이 고르는 실행 위치 — 내장은 고르지 않는다(2026-10-27). */
export type Sc03Executor = "center" | "studio";

export type Result<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; error: string; code?: string; blockingItems?: string[] };

async function call<T>(path: string, init?: RequestInit & { actor?: string; idempotencyKey?: string }): Promise<Result<T>> {
  const { actor, idempotencyKey, ...rest } = init ?? {};
  try {
    const response = await fetch(`${SC03_BASE}${path}`, {
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
      if (detail && typeof detail === "object") {
        return {
          ok: false,
          status: response.status,
          error: String(detail.message ?? `엔진 오류 (${response.status})`),
          code: detail.error_code,
          blockingItems: detail.blocking_items,
        };
      }
      return { ok: false, status: response.status, error: typeof detail === "string" ? detail : `엔진 오류 (${response.status})` };
    }
    return { ok: true, data: body as T };
  } catch (cause) {
    return { ok: false, status: 503, error: `엔진에 연결할 수 없다 — ${String(cause)}` };
  }
}

const post = <T>(path: string, body: unknown, actor?: string, idempotencyKey?: string) =>
  call<T>(path, { method: "POST", body: JSON.stringify(body ?? {}), actor, idempotencyKey });

export const sc03Api = {
  process: () => call<ProcessTopology>("/process"),
  cases: () => call<Sc03Case[]>("/cases"),
  script: (caseId: string) => call<Sc03ScriptStep[]>(`/script?case_id=${encodeURIComponent(caseId)}`),
  /** 같은 데모 실행을 이어 장면 3을 시작한다. 장면 2가 인수 전이면 각본으로 인수까지 실행한다. */
  create: (sc01DemoRunId: string | null, caseId = "BASE", executor: Sc03Executor = "center") =>
    post<Sc03View>("/demo-runs", { ...(sc01DemoRunId ? { sc01DemoRunId } : {}), caseId, executor }, "u-demo"),
  get: (id: string) => call<Sc03View>(`/demo-runs/${id}`),
  history: (id: string) => call<HistoryEntry[]>(`/demo-runs/${id}/history`),
  at: (id: string, seq: number) => call<Sc03View>(`/demo-runs/${id}/history/${seq}`),
  start: (id: string, actor: string, key?: string) => post<Sc03View>(`/demo-runs/${id}/start`, {}, actor, key),
  act: (id: string, nodeId: string, answer: Record<string, unknown>, actor: string, expect?: Record<string, unknown>, key?: string) =>
    post<Sc03View>(`/demo-runs/${id}/actions/${nodeId}`, { answer, expect }, actor, key),
  record: (id: string, body: { type: string; subject: string; content: string; related: string }, actor: string) =>
    post<Sc03View>(`/demo-runs/${id}/meetings/MT31/records`, body, actor),
  agent: (id: string, kind: string, actor: string) => post<Sc03View>(`/demo-runs/${id}/agent-drafts`, { kind }, actor),
  adopt: (id: string, outputId: string, actor: string) => post<Sc03View>(`/demo-runs/${id}/agent-outputs/${outputId}/adopt`, {}, actor),
  editTask: (id: string, taskId: string, changes: Record<string, unknown>, reason: string, actor: string) =>
    post<Sc03View>(`/demo-runs/${id}/tasks/${taskId}/draft`, { changes, reason }, actor),
  clock: (id: string, at: string) => post<Sc03View>(`/demo-runs/${id}/clock`, { at }, "u-demo"),
  step: (id: string, index: number) => post<Sc03View>(`/demo-runs/${id}/script/${index}`, {}),
  reset: (id: string, executor?: Sc03Executor) => post<Sc03View>(`/demo-runs/${id}/reset`, executor ? { executor } : {}, "u-demo"),
  eventsUrl: (id: string) => `${SC03_BASE}/demo-runs/${id}/events`,
};
