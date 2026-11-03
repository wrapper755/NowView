/**
 * SC04 엔진 호출 — BFF(`/api/engine/sc04/*`). 장면 1~3 클라이언트와 같은 태도다: 실패를 throw하지 않고
 * `{ ok: false }`로 돌려 화면이 배너로 말한다.
 */

import type { HistoryEntry, ProcessTopology } from "@/lib/sc01/types";
import type { Sc04View } from "@/lib/sc04/types";

export const SC04_BASE = "/api/engine/sc04";


export type Result<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; error: string; code?: string; blockingItems?: string[] };

/** GET만 한다 — 화면은 읽기 전용이고 BFF도 쓰기를 405로 막는다(role-split §5.5). */
async function call<T>(path: string, init?: { actor?: string }): Promise<Result<T>> {
  const actor = init?.actor;
  try {
    const response = await fetch(`${SC04_BASE}${path}`, {
      cache: "no-store",
      headers: actor ? { "x-demo-actor": actor } : {},
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

export const sc04Api = {
  process: () => call<ProcessTopology>("/process"),
  get: (id: string) => call<Sc04View>(`/demo-runs/${id}`),
  history: (id: string) => call<HistoryEntry[]>(`/demo-runs/${id}/history`),
  at: (id: string, seq: number) => call<Sc04View>(`/demo-runs/${id}/history/${seq}`),
  eventsUrl: (id: string) => `${SC04_BASE}/demo-runs/${id}/events`,
};
