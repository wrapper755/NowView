"use client";

/**
 * 엔진 인스턴스를 클라이언트에서 가져온다.
 *
 * **서버 컴포넌트에서 부르지 않는 이유가 있다.** 서버에서 가져오면 다섯 화면이
 * 정적 프리렌더(`○`)를 잃고 동적(`ƒ`)이 되어 초기 로딩이 느려진다. 페이지 껍데기는
 * 정적으로 두고 엔진 데이터만 클라이언트에서 채우면 둘 다 얻는다 — 엔진을 쓰지 않는
 * 사람은 이전과 똑같은 속도로 화면을 받는다.
 *
 * **실패가 일상이다.** 엔진이 꺼져 있을 수 있고, LLM 모드는 노드마다 10초 이상 걸리며,
 * 계약 위반으로 502가 날 수 있다. 그래서 이 훅은 성공만 다루지 않는다.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { AgentMode, EngineSnapshot } from "@/services/engine-client";

export interface EngineError {
  message: string;
  detail?: string;
  status?: number;
}

export interface EngineInstanceState {
  snapshot: EngineSnapshot | null;
  /** 첫 조회 중. 껍데기는 이미 그려져 있으므로 전체 화면을 가리지 않는다. */
  loading: boolean;
  /** 생성·재개처럼 사람이 일으킨 요청이 진행 중. 버튼을 잠그는 데 쓴다. */
  pending: boolean;
  error: EngineError | null;
}

async function callApi<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error: EngineError = {
      message: body?.error ?? `요청이 실패했다 (HTTP ${response.status})`,
      detail: typeof body?.detail === "string" ? body.detail : undefined,
      status: response.status,
    };
    throw error;
  }
  return body as T;
}

/** 진행 중인 상태에서만 폴링한다 — 멈춰 있는 인스턴스를 계속 긁을 이유가 없다. */
const POLL_INTERVAL_MS = 3000;

export function useEngineInstance(instanceId: string | null) {
  const [state, setState] = useState<EngineInstanceState>({
    snapshot: null,
    loading: false,
    pending: false,
    error: null,
  });

  // 응답이 늦게 도착했을 때 이미 다른 인스턴스로 옮겼다면 버린다 —
  // 그러지 않으면 이전 인스턴스의 상태가 새 화면에 덮어써진다.
  const activeId = useRef<string | null>(instanceId);
  activeId.current = instanceId;

  const refresh = useCallback(async (id: string, quiet = false) => {
    if (!quiet) setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const snapshot = await callApi<EngineSnapshot>(
        `/api/engine/instances/${encodeURIComponent(id)}`,
      );
      if (activeId.current !== id) return;
      setState((s) => ({ ...s, snapshot, loading: false, error: null }));
    } catch (cause) {
      if (activeId.current !== id) return;
      setState((s) => ({ ...s, loading: false, error: cause as EngineError }));
    }
  }, []);

  useEffect(() => {
    if (!instanceId) {
      setState({ snapshot: null, loading: false, pending: false, error: null });
      return;
    }
    void refresh(instanceId);
  }, [instanceId, refresh]);

  // 실행 중일 때만 주기적으로 다시 읽는다. "Live" 트래커가 이름값을 하는 지점이다.
  const status = state.snapshot?.status;
  useEffect(() => {
    if (!instanceId || status !== "running") return;
    const timer = setInterval(() => void refresh(instanceId, true), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [instanceId, status, refresh]);

  const create = useCallback(
    async (scenarioId: string, agentMode: AgentMode): Promise<EngineSnapshot | null> => {
      setState((s) => ({ ...s, pending: true, error: null }));
      try {
        // LLM 모드에서는 Agent 노드마다 10초 이상이라 이 요청이 길게 걸린다.
        const snapshot = await callApi<EngineSnapshot>("/api/engine/instances", {
          method: "POST",
          body: JSON.stringify({ scenarioId, agentMode }),
        });
        activeId.current = snapshot.instanceId;
        setState({ snapshot, loading: false, pending: false, error: null });
        return snapshot;
      } catch (cause) {
        setState((s) => ({ ...s, pending: false, error: cause as EngineError }));
        return null;
      }
    },
    [],
  );

  const resume = useCallback(
    async (id: string, payload: unknown): Promise<EngineSnapshot | null> => {
      setState((s) => ({ ...s, pending: true, error: null }));
      try {
        const snapshot = await callApi<EngineSnapshot>(
          `/api/engine/instances/${encodeURIComponent(id)}/resume`,
          { method: "POST", body: JSON.stringify(payload) },
        );
        if (activeId.current !== id) return snapshot;
        // 입력이 반려되면 오류가 아니라 `pendingApproval.error`가 달린 정상 응답이다 —
        // 같은 지점에 다시 멈춘 것이므로 상태로 다룬다.
        setState((s) => ({ ...s, snapshot, pending: false, error: null }));
        return snapshot;
      } catch (cause) {
        setState((s) => ({ ...s, pending: false, error: cause as EngineError }));
        return null;
      }
    },
    [],
  );

  const remove = useCallback(async (id: string): Promise<boolean> => {
    setState((s) => ({ ...s, pending: true, error: null }));
    try {
      await fetch(`/api/engine/instances/${encodeURIComponent(id)}`, { method: "DELETE" });
      setState({ snapshot: null, loading: false, pending: false, error: null });
      return true;
    } catch (cause) {
      setState((s) => ({ ...s, pending: false, error: cause as EngineError }));
      return false;
    }
  }, []);

  return {
    ...state,
    create,
    resume,
    remove,
    refresh: useCallback(
      () => (instanceId ? refresh(instanceId) : Promise.resolve()),
      [instanceId, refresh],
    ),
  };
}
