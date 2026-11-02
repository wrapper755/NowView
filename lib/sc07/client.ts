/**
 * SC07 엔진 호출 — BFF(`/api/engine/sc07/*`). 장면 1~6 클라이언트와 같은 태도다: 실패를 throw하지 않고 `{ ok: false }`로
 * 돌려 화면이 상태로 말한다. 조회 오류는 `code`(ACCESS_DENIED·NOT_FOUND·VERSION_MISMATCH·DATA_INVALID)를 싣는다 — 로딩·
 * 조회 실패를 갈라 보이고, 실패를 「검증 통과」로 대신하지 않는다(구현명세 6장).
 *
 * 조회는 멱등이다 — 쓰기는 「관리모델 개선 열기」(적재)와 **확인·적용 절차**(착수·결재 답·각본·초기화)뿐이다. 절차는 BPM이다
 * (`engine/processes/sc07.bpmn`). 설정 확인의 「일치」가 연결된 레코드와 어긋나면 남은 항목(`blockingItems`)을 준다.
 */

import { afterPreparation, type Preparation } from "@/lib/preparation";
import type { ProcessTopology } from "@/lib/sc01/types";
import type { Application, EvidenceView, Improvement, Sc07Executor, Sc07Meta, Sc07ScriptStep, Verification } from "@/lib/sc07/types";

export const SC07_BASE = "/api/engine/sc07";

export type Result<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; error: string; code?: string; blockingItems?: string[] };

async function call<T>(path: string, init?: RequestInit & { actor?: string; key?: string }): Promise<Result<T>> {
  const { actor, key, ...rest } = init ?? {};
  try {
    const response = await fetch(`${SC07_BASE}${path}`, {
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

const q = (dataset: string) => `?dataset_version=${encodeURIComponent(dataset)}`;

export const sc07Api = {
  /** 같은 데모 실행을 이어 장면 7을 연다. 장면 6이 대표 보고 전이면 각본으로 끝까지 실행한 뒤 IMP71을 적재한다. */
  open: async (
    sc01DemoRunId: string | null,
    executor: "center" | "studio" = "center",
    onProgress?: (p: Preparation) => void,
  ) =>
    // 장면 6까지 돌리느라 오래 걸리면 엔진이 202(준비 중)로 답한다 — 끝날 때까지 기다려 머리를 받는다.
    afterPreparation(
      SC07_BASE,
      await call<Sc07Meta | Preparation>("/demo-runs", {
        method: "POST",
        body: JSON.stringify({ ...(sc01DemoRunId ? { sc01DemoRunId } : {}), executor }),
        actor: "u-demo",
      }),
      (id) => call<Sc07Meta>(`/demo-runs/${id}`),
      onProgress,
    ),
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
  script: () => call<Sc07ScriptStep[]>("/script"),
  start: (id: string, actor: string, key?: string) => call<Sc07Meta>(`/demo-runs/${id}/start`, { method: "POST", body: "{}", actor, key }),
  act: (id: string, nodeId: string, answer: Record<string, unknown>, actor: string, key?: string) =>
    call<Sc07Meta>(`/demo-runs/${id}/actions/${nodeId}`, { method: "POST", body: JSON.stringify({ answer }), actor, key }),
  step: (id: string, index: number) => call<Sc07Meta>(`/demo-runs/${id}/script/${index}`, { method: "POST", body: "{}" }),
  reset: (id: string, executor?: Sc07Executor) =>
    call<Sc07Meta>(`/demo-runs/${id}/reset`, { method: "POST", body: JSON.stringify(executor ? { executor } : {}), actor: "u-demo" }),
  eventsUrl: (id: string) => `${SC07_BASE}/demo-runs/${id}/events`,
};
