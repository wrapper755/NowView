/**
 * SC01 엔진 호출 — 브라우저에서 BFF(`/api/engine/sc01/*`)를 부른다.
 *
 * 엔진이 꺼져 있는 것은 고장이 아니라 상태다 — 실패를 throw하지 않고 `{ ok: false }`로
 * 돌려 화면이 배너로 말하게 한다(기존 엔진 클라이언트와 같은 태도).
 */

import type {
  CustomerPlanRow,
  Dashboard,
  DemoRunView,
  DemoUser,
  HistoryEntry,
  ProcessTopology,
  ScriptStep,
} from "@/lib/sc01/types";

export const SC01_BASE = "/api/engine/sc01";

export type Result<T> = { ok: true; data: T } | { ok: false; status: number; error: string };

async function call<T>(
  path: string,
  init?: RequestInit & { actor?: string; idempotencyKey?: string },
): Promise<Result<T>> {
  const { actor, idempotencyKey, ...rest } = init ?? {};
  try {
    const response = await fetch(`${SC01_BASE}${path}`, {
      ...rest,
      cache: "no-store",
      headers: {
        "content-type": "application/json",
        ...(actor ? { "x-demo-actor": actor } : {}),
        // 같은 키로 다시 보내면 엔진이 다시 실행하지 않는다 — 타임아웃 뒤 재시도가 두 번 실행되지 않게(AT13).
        ...(idempotencyKey ? { "idempotency-key": idempotencyKey } : {}),
        ...(rest.headers ?? {}),
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

export const sc01Api = {
  process: () => call<ProcessTopology>("/process"),
  users: () => call<DemoUser[]>("/users"),
  rules: () => call<Record<string, string>>("/rules"),
  script: () => call<ScriptStep[]>("/script"),
  customerPlan: (id: string) => call<CustomerPlanRow[]>(`/customer-plans/${id}`),
  create: () => post<DemoRunView>("/demo-runs", {}),
  get: (id: string) => call<DemoRunView>(`/demo-runs/${id}`),
  history: (id: string) => call<HistoryEntry[]>(`/demo-runs/${id}/history`),
  at: (id: string, seq: number) => call<DemoRunView>(`/demo-runs/${id}/history/${seq}`),
  dashboard: (id: string, q: { period: string; month: number; seq?: number | null }) => {
    const params = new URLSearchParams({ period: q.period, month: String(q.month) });
    if (q.seq != null) params.set("seq", String(q.seq));
    return call<Dashboard>(`/demo-runs/${id}/dashboard?${params}`);
  },
  receive: (id: string, fixtureId: string, actor: string, key?: string) =>
    post<DemoRunView>(`/demo-runs/${id}/sources/receive`, { fixtureId }, actor, key),
  act: (id: string, nodeId: string, answer: Record<string, unknown>, actor: string, key?: string) =>
    post<DemoRunView>(`/demo-runs/${id}/actions/${nodeId}`, { answer }, actor, key),
  regenerate: (id: string, runId: string, actor: string) =>
    post<DemoRunView>(`/demo-runs/${id}/agent/${runId}/regenerate`, {}, actor),
  adopt: (id: string, outputId: string, actor: string) =>
    post<DemoRunView>(`/demo-runs/${id}/agent-outputs/${outputId}/adopt`, {}, actor),
  clock: (id: string, at: string) => post<DemoRunView>(`/demo-runs/${id}/clock`, { at }, "u-demo"),
  step: (id: string, index: number) => post<DemoRunView>(`/demo-runs/${id}/script/${index}`, {}),
  reset: (id: string, caseId?: string) =>
    post<DemoRunView>(`/demo-runs/${id}/reset`, caseId ? { caseId } : {}, "u-demo"),
  eventsUrl: (id: string) => `${SC01_BASE}/demo-runs/${id}/events`,
};
