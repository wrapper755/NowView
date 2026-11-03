/**
 * SC06 엔진 호출 — BFF(`/api/engine/sc06/*`). 장면 1~5 클라이언트와 같은 태도다: 실패를 throw하지 않고 `{ ok: false }`로
 * 돌려 화면이 상태로 말한다. 조회 오류는 `code`(ACCESS_DENIED·NOT_FOUND·VERSION_MISMATCH·DATA_INCOMPLETE)를 싣는다 —
 * 로딩·빈 결과·조회 실패를 갈라 보이고, 실패를 0이나 이전 합계로 보이지 않는다(구현명세 2장).
 *
 * 조회만 한다 — 「장면 6 열기」(적재)와 **확인 절차**(착수·결재 답·초기화)는 회사 사이트가 한다(role-split §5.5). 확인 절차는
 * BPM이다(`engine/processes/sc06.bpmn`).
 */

import type { ProcessTopology } from "@/lib/sc01/types";
import type { Evidence, Report, Sc06Meta, Summary, Variance } from "@/lib/sc06/types";

export const SC06_BASE = "/api/engine/sc06";

export type Result<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; error: string; code?: string; blockingItems?: string[] };

/** GET만 한다 — 화면은 읽기 전용이고 BFF도 쓰기를 405로 막는다(role-split §5.5). */
async function call<T>(path: string, init?: { actor?: string }): Promise<Result<T>> {
  const actor = init?.actor;
  try {
    const response = await fetch(`${SC06_BASE}${path}`, {
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
    return { ok: false, status: 503, error: `엔진에 연결할 수 없다 — ${String(cause)}`, code: "SERVICE_ERROR" };
  }
}

const q = (version: string) => `?report_version=${encodeURIComponent(version)}`;

export const sc06Api = {
  meta: (id: string) => call<Sc06Meta>(`/demo-runs/${id}`),
  summary: (id: string, version: string, actor: string) =>
    call<Summary>(`/demo-runs/${id}/reviews/RV61/summary${q(version)}`, { actor }),
  variance: (id: string, task: string, version: string, actor: string) =>
    call<Variance>(`/demo-runs/${id}/reviews/RV61/tasks/${task}/variance${q(version)}`, { actor }),
  evidence: (id: string, evidenceId: string, version: string, actor: string) =>
    call<Evidence>(`/demo-runs/${id}/evidence/${encodeURIComponent(evidenceId)}${q(version)}`, { actor }),
  report: (id: string, version: string, actor: string) => call<Report>(`/demo-runs/${id}/reports/${version}`, { actor }),
  process: () => call<ProcessTopology>("/process"),
  eventsUrl: (id: string) => `${SC06_BASE}/demo-runs/${id}/events`,
};
