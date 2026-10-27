/**
 * SC05 엔진 호출 — BFF(`/api/engine/sc05/*`). 장면 1~4 클라이언트와 같은 태도다: 실패를 throw하지 않고
 * `{ ok: false }`로 돌려 화면이 배너로 말한다. 요건 미충족(422 — PLAN_INCOMPLETE·START_BLOCKED·BUDGET_EXCEEDED·
 * RESULT_INCOMPLETE·FORECAST_INVALID·COMPLETION_BLOCKED)은 남은 항목(`blockingItems`)을 함께 준다.
 */

import type { HistoryEntry, ProcessTopology } from "@/lib/sc01/types";
import { afterPreparation, type Preparation } from "@/lib/preparation";
import type { Sc05Case, Sc05ScriptStep, Sc05View } from "@/lib/sc05/types";

export const SC05_BASE = "/api/engine/sc05";

/** 화면이 고르는 실행 위치 — 내장은 고르지 않는다(2026-10-27). */
export type Sc05Executor = "center" | "studio";

export type Result<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; error: string; code?: string; blockingItems?: string[] };

async function call<T>(path: string, init?: RequestInit & { actor?: string; idempotencyKey?: string }): Promise<Result<T>> {
  const { actor, idempotencyKey, ...rest } = init ?? {};
  try {
    const response = await fetch(`${SC05_BASE}${path}`, {
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

export const sc05Api = {
  process: () => call<ProcessTopology>("/process"),
  cases: () => call<Sc05Case[]>("/cases"),
  script: (caseId: string) => call<Sc05ScriptStep[]>(`/script?case_id=${encodeURIComponent(caseId)}`),
  /** 같은 데모 실행을 이어 장면 5를 시작한다. 장면 4가 완료 전이면 각본으로 완료(HANDOFF41)까지 실행한다. */
  create: async (
    sc01DemoRunId: string | null,
    caseId = "BASE",
    executor: Sc05Executor = "center",
    onProgress?: (p: Preparation) => void,
  ) =>
    // 앞 장면을 끝까지 돌리느라 오래 걸리면 엔진이 202(준비 중)로 답한다 — 끝날 때까지 기다려 문서를 받는다.
    afterPreparation(
      SC05_BASE,
      await post<Sc05View | Preparation>("/demo-runs", { ...(sc01DemoRunId ? { sc01DemoRunId } : {}), caseId, executor }, "u-demo"),
      (id) => call<Sc05View>(`/demo-runs/${id}`),
      onProgress,
    ),
  get: (id: string) => call<Sc05View>(`/demo-runs/${id}`),
  history: (id: string) => call<HistoryEntry[]>(`/demo-runs/${id}/history`),
  at: (id: string, seq: number) => call<Sc05View>(`/demo-runs/${id}/history/${seq}`),
  start: (id: string, actor: string, key?: string) => post<Sc05View>(`/demo-runs/${id}/start`, {}, actor, key),
  act: (id: string, nodeId: string, answer: Record<string, unknown>, actor: string, expect?: Record<string, unknown>, key?: string) =>
    post<Sc05View>(`/demo-runs/${id}/actions/${nodeId}`, { answer, expect }, actor, key),
  agent: (id: string, kind: string, actor: string) => post<Sc05View>(`/demo-runs/${id}/agent-drafts`, { kind }, actor),
  /** 제안 검토 기록 — 원 초안은 그대로다. 업무 확인·승인을 대신하지 않는다. */
  review: (id: string, outputId: string, actor: string, note = "") =>
    post<Sc05View>(`/demo-runs/${id}/agent-outputs/${outputId}/review`, { note }, actor),
  clock: (id: string, at: string) => post<Sc05View>(`/demo-runs/${id}/clock`, { at }, "u-demo"),
  step: (id: string, index: number) => post<Sc05View>(`/demo-runs/${id}/script/${index}`, {}),
  reset: (id: string, executor?: Sc05Executor) => post<Sc05View>(`/demo-runs/${id}/reset`, executor ? { executor } : {}, "u-demo"),
  eventsUrl: (id: string) => `${SC05_BASE}/demo-runs/${id}/events`,
};
