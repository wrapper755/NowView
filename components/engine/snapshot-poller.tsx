"use client";

/**
 * 엔진 스냅샷을 **레이아웃에서 한 번만** 가져온다.
 *
 * 화면마다 훅이 각자 가져오면 (1) 같은 화면의 두 패널이 서로 다른 순간을 볼 수 있고
 * (2) 폴링을 붙이면 요청이 화면·패널 수만큼 배로 늘어난다. 실제로 ①은 경영 수행 성과와
 * 리스크 신호가 각각 같은 훅을 불러 두 번 가져오고 있었다.
 *
 * 그래서 가져오는 곳은 이 컴포넌트뿐이고, 화면들은 `useEngineSnapshots`로 스토어를 읽는다.
 *
 * **주기는 상태에 따라 다르다.** 실행 중이면 3초(값이 실제로 움직인다), 멈춰 있으면
 * 15초(변화가 다른 탭·다른 사람에게서 올 수 있다). 탭이 숨겨지면 멈추고 다시 보이면
 * 즉시 한 번 읽는다(`useVisiblePoll`).
 */

import { useCallback, useEffect, useMemo, useRef } from "react";

import {
  POLL_IDLE_MS,
  POLL_RUNNING_MS,
  useVisiblePoll,
} from "@/components/engine/use-visible-poll";
import { useEngineSession } from "@/lib/store/engine-session";
import { useEngineSnapshotStore } from "@/lib/store/engine-snapshots";
import type { EngineError, EngineSnapshot } from "@/services/engine-client";

export function SnapshotPoller() {
  const instanceByScenario = useEngineSession((s) => s.instanceByScenario);
  const revision = useEngineSession((s) => s.revision);
  const setResult = useEngineSnapshotStore((s) => s.setResult);
  const reset = useEngineSnapshotStore((s) => s.reset);

  const attached = useMemo(
    () =>
      Object.entries(instanceByScenario)
        .filter(([, id]) => Boolean(id))
        .map(([scenarioId, id]) => ({ scenarioId, instanceId: id as string }))
        .sort((a, b) => a.scenarioId.localeCompare(b.scenarioId)),
    [instanceByScenario],
  );
  const key = attached.map((a) => `${a.scenarioId}:${a.instanceId}`).join("|");

  /**
   * 진행 중인 요청의 일련번호. 늦게 도착한 응답이 최신 결과를 덮지 않게 한다.
   *
   * 폴링은 주기가 응답 시간보다 짧을 수 있어(LLM 모드) 겹치기 쉽다. ref는 렌더 중이
   * 아니라 콜백에서만 만진다(`react-hooks/refs`).
   */
  const ticketRef = useRef(0);

  const load = useCallback(async () => {
    if (!key) return;
    const ticket = ++ticketRef.current;
    try {
      const results = await Promise.all(
        attached.map(async ({ scenarioId, instanceId }) => {
          const response = await fetch(
            `/api/engine/instances/${encodeURIComponent(instanceId)}`,
            { headers: { "content-type": "application/json" } },
          );
          const body = await response.json().catch(() => null);
          if (!response.ok) {
            throw {
              message: body?.error ?? `인스턴스를 읽지 못했다 (HTTP ${response.status})`,
              detail: typeof body?.detail === "string" ? body.detail : undefined,
              status: response.status,
            } as EngineError;
          }
          return { scenarioId, snapshot: body as EngineSnapshot };
        }),
      );
      if (ticket !== ticketRef.current) return;

      const byScenario: Record<string, EngineSnapshot> = {};
      for (const { scenarioId, snapshot } of results) {
        // 스냅샷이 다른 시나리오의 것이면 쓰지 않는다 — 노드·대안 id가 맞지 않아
        // 엉뚱한 값이 화면에 섞인다.
        if (snapshot.scenarioId === scenarioId) byScenario[scenarioId] = snapshot;
      }
      setResult(key, byScenario, null, Date.now());
    } catch (cause) {
      if (ticket !== ticketRef.current) return;
      // 실패해도 어떤 시나리오가 엔진 소유인지는 세션 스토어에서 파생되므로 남는다 —
      // 놓치면 Mock 값이 되살아나 이중 계상된다(CLAUDE.md 4.17).
      setResult(key, {}, cause as EngineError, Date.now());
    }
  }, [key, attached, setResult]);

  // 붙어 있는 인스턴스가 없으면 남은 값을 비운다 — 안 그러면 Mock으로 돌아간 뒤에도
  // 옛 스냅샷이 화면에 남는다.
  useEffect(() => {
    if (!key) reset();
  }, [key, reset]);

  // 인스턴스 구성이 바뀌거나 누가 엔진 상태를 바꾸면(`revision`) 즉시 읽는다.
  useEffect(() => {
    void load();
  }, [load, revision]);

  const snapshots = useEngineSnapshotStore((s) => s.snapshots);
  const anyRunning = Object.values(snapshots).some((s) => s.status === "running");

  useVisiblePoll(
    useCallback(() => void load(), [load]),
    key ? (anyRunning ? POLL_RUNNING_MS : POLL_IDLE_MS) : null,
  );

  return null;
}
