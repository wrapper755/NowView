/**
 * SC01 엔진 호출 — 브라우저에서 BFF(`/api/engine/sc01/*`)를 부른다.
 *
 * **읽기만 한다**(2026-11-03, `docs/role-split.md` §5.5) — 데모 실행(세계)은 회사 사이트가 기간계에 만들고 NowView 일꾼이
 * 같은 id로 장면 1을 연다. 결재 답·수신·시계·초기화도 회사 사이트에서 한다. BFF도 GET만 중계한다.
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
} from "@/lib/sc01/types";

export const SC01_BASE = "/api/engine/sc01";

export type Result<T> = { ok: true; data: T } | { ok: false; status: number; error: string };

async function call<T>(
  path: string,
  actor?: string,
): Promise<Result<T>> {
  try {
    const response = await fetch(`${SC01_BASE}${path}`, {
      cache: "no-store",
      headers: actor ? { "x-demo-actor": actor } : {},
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

export const sc01Api = {
  process: () => call<ProcessTopology>("/process"),
  users: () => call<DemoUser[]>("/users"),
  rules: () => call<Record<string, string>>("/rules"),
  customerPlan: (id: string) => call<CustomerPlanRow[]>(`/customer-plans/${id}`),
  /** 데모 실행 목록 — 최근 것이 먼저다. 저장된 id가 없거나 엔진에 없으면 가장 최근 것을 본다. */
  list: () => call<{ demoRunId: string; createdAt: string }[]>("/demo-runs"),
  get: (id: string) => call<DemoRunView>(`/demo-runs/${id}`),
  history: (id: string) => call<HistoryEntry[]>(`/demo-runs/${id}/history`),
  at: (id: string, seq: number) => call<DemoRunView>(`/demo-runs/${id}/history/${seq}`),
  dashboard: (id: string, q: { period: string; month: number; seq?: number | null }) => {
    const params = new URLSearchParams({ period: q.period, month: String(q.month) });
    if (q.seq != null) params.set("seq", String(q.seq));
    return call<Dashboard>(`/demo-runs/${id}/dashboard?${params}`);
  },
  eventsUrl: (id: string) => `${SC01_BASE}/demo-runs/${id}/events`,
};
