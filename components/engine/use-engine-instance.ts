"use client";

/**
 * 인스턴스를 **바꾸는** 동작만 담당한다 — 생성·재개·삭제.
 *
 * **조회는 하지 않는다.** 스냅샷을 가져오는 곳은 `SnapshotPoller` 하나뿐이고, 화면은
 * 스토어를 읽는다(`use-engine-snapshots`). 여기서도 가져오면 같은 인스턴스를 두 곳이
 * 폴링하게 되고, 두 결과가 어긋나면 ②·③이 ①·④·⑤와 다른 순간을 그린다.
 *
 * 변경에 성공하면 응답 스냅샷을 스토어에 **즉시 반영**하고 `revision`을 올린다 —
 * 폴링 주기를 기다리면 승인 직후 화면이 한동안 옛 상태를 보여 준다.
 *
 * **실패가 일상이다.** 엔진이 꺼져 있을 수 있고, LLM 모드는 노드마다 10초 이상 걸리며,
 * 계약 위반으로 502가 날 수 있다. 그래서 이 훅은 성공만 다루지 않는다.
 */

import { useCallback, useState } from "react";

import { useEngineSession } from "@/lib/store/engine-session";
import { useEngineSnapshotStore } from "@/lib/store/engine-snapshots";
import type { AgentMode, EngineError, EngineSnapshot } from "@/services/engine-client";

// 타입은 `services/engine-client`가 소유한다 — 스토어도 같은 것을 쓴다.
export type { EngineError };

export interface EngineInstanceState {
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

export function useEngineInstance(instanceId: string | null) {
  const bumpRevision = useEngineSession((s) => s.bumpRevision);
  const applySnapshot = useEngineSnapshotStore((s) => s.applyOne);
  const [state, setState] = useState<EngineInstanceState>({ pending: false, error: null });

  /** 변경 결과를 공유 스토어에 즉시 반영하고 다시 읽게 한다. */
  const publish = useCallback(
    (snapshot: EngineSnapshot) => {
      applySnapshot(snapshot.scenarioId, snapshot);
      bumpRevision();
    },
    [applySnapshot, bumpRevision],
  );

  const create = useCallback(
    async (scenarioId: string, agentMode: AgentMode): Promise<EngineSnapshot | null> => {
      setState({ pending: true, error: null });
      try {
        // LLM 모드에서는 Agent 노드마다 10초 이상이라 이 요청이 길게 걸린다.
        const snapshot = await callApi<EngineSnapshot>("/api/engine/instances", {
          method: "POST",
          body: JSON.stringify({ scenarioId, agentMode }),
        });
        publish(snapshot);
        setState({ pending: false, error: null });
        return snapshot;
      } catch (cause) {
        setState({ pending: false, error: cause as EngineError });
        return null;
      }
    },
    [publish],
  );

  const resume = useCallback(
    async (id: string, payload: unknown): Promise<EngineSnapshot | null> => {
      setState({ pending: true, error: null });
      try {
        const snapshot = await callApi<EngineSnapshot>(
          `/api/engine/instances/${encodeURIComponent(id)}/resume`,
          { method: "POST", body: JSON.stringify(payload) },
        );
        // 입력이 반려되면 오류가 아니라 `pendingApproval.error`가 달린 정상 응답이다 —
        // 같은 지점에 다시 멈춘 것이므로 상태로 다룬다.
        publish(snapshot);
        setState({ pending: false, error: null });
        return snapshot;
      } catch (cause) {
        setState({ pending: false, error: cause as EngineError });
        return null;
      }
    },
    [publish],
  );

  const remove = useCallback(async (id: string): Promise<boolean> => {
    setState({ pending: true, error: null });
    try {
      await fetch(`/api/engine/instances/${encodeURIComponent(id)}`, { method: "DELETE" });
      setState({ pending: false, error: null });
      bumpRevision();
      return true;
    } catch (cause) {
      setState({ pending: false, error: cause as EngineError });
      return false;
    }
  }, [bumpRevision]);

  return {
    ...state,
    create,
    resume,
    remove,
    // 수동 새로고침은 폴러에게 "지금 읽어라"라고 알리는 것이다.
    refresh: useCallback(() => {
      if (instanceId) bumpRevision();
    }, [instanceId, bumpRevision]),
  };
}
