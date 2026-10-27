/**
 * SC06 엔진 호출 — BFF(`/api/engine/sc06/*`). 장면 1~5 클라이언트와 같은 태도다: 실패를 throw하지 않고 `{ ok: false }`로
 * 돌려 화면이 상태로 말한다. 조회 오류는 `code`(ACCESS_DENIED·NOT_FOUND·VERSION_MISMATCH·DATA_INCOMPLETE)를 싣는다 —
 * 로딩·빈 결과·조회 실패를 갈라 보이고, 실패를 0이나 이전 합계로 보이지 않는다(구현명세 2장).
 *
 * 조회는 멱등이다 — 쓰기는 「장면 6 열기」(적재)와 **확인 절차**(착수·결재 답·각본·초기화)뿐이다. 확인 절차는 BPM이다
 * (`engine/processes/sc06.bpmn`) — 장면 1~5와 같은 경로를 쓴다. 확정의 요건 미충족은 남은 항목(`blockingItems`)을 준다.
 */

import { afterPreparation, type Preparation } from "@/lib/preparation";
import type { ProcessTopology } from "@/lib/sc01/types";
import type { Evidence, Report, Sc06Executor, Sc06Meta, Sc06ScriptStep, Summary, Variance } from "@/lib/sc06/types";

export const SC06_BASE = "/api/engine/sc06";

export type Result<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; error: string; code?: string; blockingItems?: string[] };

async function call<T>(path: string, init?: RequestInit & { actor?: string; key?: string }): Promise<Result<T>> {
  const { actor, key, ...rest } = init ?? {};
  try {
    const response = await fetch(`${SC06_BASE}${path}`, {
      ...rest,
      cache: "no-store",
      headers: {
        "content-type": "application/json",
        ...(actor ? { "x-demo-actor": actor } : {}),
        ...(key ? { "idempotency-key": key } : {}),
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
    return { ok: false, status: 503, error: `엔진에 연결할 수 없다 — ${String(cause)}`, code: "SERVICE_ERROR" };
  }
}

const q = (version: string) => `?report_version=${encodeURIComponent(version)}`;

export const sc06Api = {
  /** 같은 데모 실행을 이어 장면 6을 연다. 장면 5가 완료 전이면 각본으로 HANDOFF51까지 실행한 뒤 RV61을 적재한다. */
  open: async (
    sc01DemoRunId: string | null,
    executor: "center" | "studio" = "center",
    onProgress?: (p: Preparation) => void,
  ) =>
    // 장면 5까지 돌리느라 오래 걸리면 엔진이 202(준비 중)로 답한다 — 끝날 때까지 기다려 머리를 받는다.
    afterPreparation(
      SC06_BASE,
      await call<Sc06Meta | Preparation>("/demo-runs", {
        method: "POST",
        body: JSON.stringify({ ...(sc01DemoRunId ? { sc01DemoRunId } : {}), executor }),
        actor: "u-demo",
      }),
      (id) => call<Sc06Meta>(`/demo-runs/${id}`),
      onProgress,
    ),
  meta: (id: string) => call<Sc06Meta>(`/demo-runs/${id}`),
  summary: (id: string, version: string, actor: string) =>
    call<Summary>(`/demo-runs/${id}/reviews/RV61/summary${q(version)}`, { actor }),
  variance: (id: string, task: string, version: string, actor: string) =>
    call<Variance>(`/demo-runs/${id}/reviews/RV61/tasks/${task}/variance${q(version)}`, { actor }),
  evidence: (id: string, evidenceId: string, version: string, actor: string) =>
    call<Evidence>(`/demo-runs/${id}/evidence/${encodeURIComponent(evidenceId)}${q(version)}`, { actor }),
  report: (id: string, version: string, actor: string) => call<Report>(`/demo-runs/${id}/reports/${version}`, { actor }),
  process: () => call<ProcessTopology>("/process"),
  script: () => call<Sc06ScriptStep[]>("/script"),
  start: (id: string, actor: string, key?: string) => call<Sc06Meta>(`/demo-runs/${id}/start`, { method: "POST", body: "{}", actor, key }),
  act: (id: string, nodeId: string, answer: Record<string, unknown>, actor: string, key?: string) =>
    call<Sc06Meta>(`/demo-runs/${id}/actions/${nodeId}`, { method: "POST", body: JSON.stringify({ answer }), actor, key }),
  step: (id: string, index: number) => call<Sc06Meta>(`/demo-runs/${id}/script/${index}`, { method: "POST", body: "{}" }),
  reset: (id: string, executor?: Sc06Executor) =>
    call<Sc06Meta>(`/demo-runs/${id}/reset`, { method: "POST", body: JSON.stringify(executor ? { executor } : {}), actor: "u-demo" }),
  eventsUrl: (id: string) => `${SC06_BASE}/demo-runs/${id}/events`,
};
