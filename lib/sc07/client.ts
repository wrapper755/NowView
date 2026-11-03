/**
 * SC07 엔진 호출 — BFF(`/api/engine/sc07/*`). 장면 1~6 클라이언트와 같은 태도다: 실패를 throw하지 않고 `{ ok: false }`로
 * 돌려 화면이 상태로 말한다. 조회 오류는 `code`(ACCESS_DENIED·NOT_FOUND·VERSION_MISMATCH·DATA_INVALID)를 싣는다 — 로딩·
 * 조회 실패를 갈라 보이고, 실패를 「검증 통과」로 대신하지 않는다(구현명세 6장).
 *
 * 조회만 한다 — 「관리모델 개선 열기」(적재)와 **확인·적용 절차**(착수·결재 답·초기화)는 회사 사이트가 한다(role-split §5.5).
 * 절차는 BPM이다(`engine/processes/sc07.bpmn`).
 */

import type { ProcessTopology } from "@/lib/sc01/types";
import type { Application, EvidenceView, Improvement, Sc07Meta, Verification } from "@/lib/sc07/types";

export const SC07_BASE = "/api/engine/sc07";

export type Result<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; error: string; code?: string; blockingItems?: string[] };

/** GET만 한다 — 화면은 읽기 전용이고 BFF도 쓰기를 405로 막는다(role-split §5.5). */
async function call<T>(path: string, init?: { actor?: string }): Promise<Result<T>> {
  const actor = init?.actor;
  try {
    const response = await fetch(`${SC07_BASE}${path}`, {
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

const q = (dataset: string) => `?dataset_version=${encodeURIComponent(dataset)}`;

export const sc07Api = {
  meta: (id: string) => call<Sc07Meta>(`/demo-runs/${id}`),
  improvement: (id: string, dataset: string, actor: string) =>
    call<Improvement>(`/demo-runs/${id}/improvements/IMP71${q(dataset)}`, { actor }),
  verification: (id: string, dataset: string, actor: string) =>
    call<Verification>(`/demo-runs/${id}/improvements/IMP71/verification${q(dataset)}`, { actor }),
  application: (id: string, dataset: string, actor: string) =>
    call<Application>(`/demo-runs/${id}/applications/AP71${q(dataset)}`, { actor }),
  evidence: (id: string, evidenceId: string, actor: string) =>
    call<EvidenceView>(`/demo-runs/${id}/evidence/${encodeURIComponent(evidenceId)}`, { actor }),
  process: () => call<ProcessTopology>("/process"),
  eventsUrl: (id: string) => `${SC07_BASE}/demo-runs/${id}/events`,
};
