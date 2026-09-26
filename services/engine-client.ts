/**
 * Python BPM 엔진(FastAPI/LangGraph) 클라이언트.
 *
 * **서버에서만 호출한다.** 브라우저가 엔진을 직접 부르면 CORS가 생기고 엔진 주소가
 * 노출되며, LLM 자격증명을 클라이언트에 둘 수 없다. Next의 `/api/engine/*`가
 * 프록시(BFF)로 앞에 선다 — 화면은 계속 `/api/*`만 알면 된다.
 *
 * **엔진이 떠 있지 않은 것은 예외 상황이 아니다.** 이 프로젝트는 Mock만으로도
 * 전부 동작하고, 엔진은 선택적으로 붙는다. 그래서 연결 실패를 throw하지 않고
 * `{ ok: false }`로 돌려 호출부가 판단하게 한다 — 500으로 터뜨리면 엔진을 켜지 않은
 * 사람에게 고장으로 보인다.
 */

import type { EngineProcessSpec } from "@/services/engine-spec";

export const ENGINE_URL = process.env.ENGINE_URL ?? "http://localhost:8077";

/** 엔진 호출 결과. 실패도 정상적인 결과값이다. */
export type EngineResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; error: string; detail?: unknown };

export type AgentMode = "mock" | "llm";

export interface EngineSnapshot {
  instanceId: string;
  scenarioId: string;
  subject: string;
  riskId: string;
  agentMode: AgentMode;
  status: "created" | "running" | "waiting" | "done";
  visited: string[];
  next: string[];
  /** 노드 id → `BpmNodeStatus`. 같은 어휘를 쓰므로 화면이 그대로 소비할 수 있다. */
  nodeStatuses: Record<string, string>;
  runs: {
    agentId: string;
    nodeId: string;
    output: string;
    sources: { name: string; quality: string; caveat?: string }[];
    duration: string;
    confidence: "high" | "medium" | "low";
    confidenceNote?: string | null;
    escalations: { question: string; reason: string; owner: string; ifUnanswered: string }[];
    /** `mock` · `mock-missing` · `llm:<model>`. 산출물의 출처를 화면이 구분할 수 있다. */
    provenance: string;
  }[];
  flags: Record<string, boolean>;
  decision: {
    nodeId: string;
    alternativeId: string;
    leverValue?: number;
    rationale: string;
    decidedBy?: string;
    /** 엔진이 찍는다 — 화면이 찍으면 새로고침할 때마다 값이 달라진다. */
    decidedAt?: string;
  } | null;
  acknowledged: string[];
  pendingApproval: {
    kind: "decision" | "acknowledgement";
    nodeId: string;
    label: string;
    actor?: string;
    note?: string;
    alternatives?: { id: string; title: string; recommended: boolean }[];
    rationaleMinLength?: number;
    /** 직전 입력이 반려된 이유. 있으면 같은 지점에 다시 멈춘 것이다. */
    error?: string;
  } | null;
  /** 명세 자체의 문제. 조용히 삼키지 않고 그대로 올린다. */
  specWarnings: string[];
}

async function call<T>(
  path: string,
  init?: RequestInit & { timeoutMs?: number },
): Promise<EngineResult<T>> {
  const { timeoutMs = 300_000, ...rest } = init ?? {};
  // LLM 모드에서는 Agent 노드마다 10초 이상 걸리고 재시도가 붙을 수 있다.
  // 기본 fetch 타임아웃에 맡기면 정상 실행이 중간에 끊긴다.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${ENGINE_URL}${path}`, {
      ...rest,
      signal: controller.signal,
      headers: { "content-type": "application/json", ...(rest.headers ?? {}) },
      cache: "no-store",
    });
    if (response.status === 204) return { ok: true, data: undefined as T };
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        error: typeof body?.detail === "string" ? body.detail : "엔진이 요청을 거부했다",
        detail: body,
      };
    }
    return { ok: true, data: body as T };
  } catch (cause) {
    const aborted = cause instanceof Error && cause.name === "AbortError";
    return {
      ok: false,
      status: aborted ? 504 : 503,
      error: aborted
        ? `엔진 응답이 ${Math.round(timeoutMs / 1000)}초 안에 오지 않았다`
        : `엔진에 연결할 수 없다 (${ENGINE_URL})`,
      detail: cause instanceof Error ? cause.message : String(cause),
    };
  } finally {
    clearTimeout(timer);
  }
}

export function engineHealth() {
  return call<{ ok: boolean; ollama: { url: string; model: string }; instances: number }>(
    "/health",
    { method: "GET", timeoutMs: 5_000 },
  );
}

export function createInstance(spec: EngineProcessSpec, agentMode: AgentMode) {
  return call<EngineSnapshot>("/instances", {
    method: "POST",
    body: JSON.stringify({ spec, agentMode, advance: true }),
  });
}

export function listInstances() {
  return call<{
    instances: { instanceId: string; scenarioId: string; agentMode: string; createdAt: string }[];
  }>("/instances", { method: "GET", timeoutMs: 10_000 });
}

export function getInstance(instanceId: string) {
  return call<EngineSnapshot>(`/instances/${encodeURIComponent(instanceId)}`, {
    method: "GET",
    timeoutMs: 10_000,
  });
}

export function resumeInstance(instanceId: string, payload: unknown) {
  return call<EngineSnapshot>(`/instances/${encodeURIComponent(instanceId)}/resume`, {
    method: "POST",
    body: JSON.stringify({ payload }),
  });
}

export function deleteInstance(instanceId: string) {
  return call<void>(`/instances/${encodeURIComponent(instanceId)}`, {
    method: "DELETE",
    timeoutMs: 10_000,
  });
}
