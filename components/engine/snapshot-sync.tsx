"use client";

/**
 * 엔진 스냅샷을 **레이아웃에서 한 번만** 받아 온다 — SSE로 밀어 받고, 안 되면 폴링한다.
 *
 * 화면마다 훅이 각자 가져오면 (1) 같은 화면의 두 패널이 서로 다른 순간을 볼 수 있고
 * (2) 요청이 화면·패널 수만큼 배로 늘어난다. 실제로 ①은 경영 수행 성과와 리스크 신호가
 * 각각 같은 훅을 불러 두 번 가져오고 있었다. 받는 곳은 이 컴포넌트뿐이고, 화면들은
 * `useEngineSnapshots`로 스토어를 읽는다.
 *
 * **SSE가 기본이고 폴링이 폴백이다.** 엔진에서 상태가 바뀌는 계기는 전부 우리 코드를
 * 지나가므로(생성·승인·장면 이동) 그 지점에서 밀어 줄 수 있다 — 승인 후 0.06초에 도착하는
 * 것을 확인했다. 다만 SSE는 프록시·네트워크 환경에 따라 막히므로, 연결이 서 있지 않은
 * 동안에는 폴링이 대신 돈다. 둘 다 없으면 새로고침해야 반영되는 상태로 돌아간다.
 *
 * **여러 인스턴스를 한 스트림으로 받는다.** 인스턴스마다 연결을 열면 브라우저의 동시
 * 연결 한도(HTTP/1.1에서 도메인당 6개)를 SSE가 잡아먹어 다른 요청이 굶는다.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { POLL_IDLE_MS, useVisiblePoll } from "@/components/engine/use-visible-poll";
import { useEngineSession } from "@/lib/store/engine-session";
import { useEngineSnapshotStore } from "@/lib/store/engine-snapshots";
import type { EngineError, EngineSnapshot } from "@/services/engine-client";

export function SnapshotSync() {
  const instanceByScenario = useEngineSession((s) => s.instanceByScenario);
  const revision = useEngineSession((s) => s.revision);
  const setResult = useEngineSnapshotStore((s) => s.setResult);
  const applyOne = useEngineSnapshotStore((s) => s.applyOne);
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
  const idList = attached.map((a) => a.instanceId).join(",");

  /**
   * SSE 연결이 서 있는가. 서 있으면 폴링하지 않는다.
   *
   * 인스턴스가 없을 때는 상태를 건드리지 않고 **파생**으로 판단한다 — effect 본문에서
   * `setState`를 하면 `react-hooks/set-state-in-effect`에 걸린다.
   */
  const [streamOpen, setStreamOpen] = useState(false);

  /**
   * 진행 중인 폴링 요청의 일련번호. 늦게 도착한 응답이 최신 결과를 덮지 않게 한다.
   * ref는 렌더 중이 아니라 콜백에서만 만진다(`react-hooks/refs`).
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

  /**
   * SSE 연결.
   *
   * `EventSource`는 끊기면 스스로 다시 붙는다. 그래서 `onerror`는 "영구 실패"가 아니라
   * "지금은 서 있지 않다"는 뜻이고, 그 동안만 폴링이 대신 돈다. 다시 붙으면 `ready`가
   * 또 오므로 폴링이 멈춘다.
   */
  useEffect(() => {
    if (!key) return;

    const source = new EventSource(`/api/engine/events?instances=${encodeURIComponent(idList)}`);
    // 초기 버스트는 모아 두고 `ready`에서 한 번에 넣는다 — 하나씩 넣으면 그 사이에
    // "일부만 받은" 상태가 화면에 보인다.
    let burst: Record<string, EngineSnapshot> = {};
    let ready = false;

    const accept = (raw: string) => {
      const snapshot = JSON.parse(raw) as EngineSnapshot;
      // 그 사이 인스턴스가 바뀌었으면 버린다. 스트림은 닫히는 중이어도 이벤트가
      // 하나 더 도착할 수 있다.
      if (instanceByScenario[snapshot.scenarioId] !== snapshot.instanceId) return;
      if (ready) applyOne(snapshot.scenarioId, snapshot);
      else burst[snapshot.scenarioId] = snapshot;
    };

    source.addEventListener("snapshot", (event) => accept((event as MessageEvent<string>).data));
    source.addEventListener("ready", () => {
      ready = true;
      setResult(key, burst, null, Date.now());
      setStreamOpen(true);
    });
    source.onerror = () => {
      // 다시 붙는 동안에는 폴링에 맡긴다. 여기서 close하면 재연결도 막힌다.
      ready = false;
      burst = {};
      setStreamOpen(false);
    };

    return () => {
      source.close();
      // 연결이 닫혔으니 폴백이 돌아야 한다. 정리 함수는 effect 본문이 아니라
      // 해제 시점에 불리므로 상태를 바꿔도 된다.
      setStreamOpen(false);
    };
  }, [key, idList, applyOne, setResult, instanceByScenario]);

  const streaming = Boolean(key) && streamOpen;

  // 스트림이 서 있지 않을 때만 읽는다. 누가 엔진 상태를 바꿨으면(`revision`) 즉시 한 번.
  useEffect(() => {
    if (!key || streaming) return;
    void load();
  }, [key, streaming, revision, load]);

  useVisiblePoll(
    useCallback(() => void load(), [load]),
    key && !streaming ? POLL_IDLE_MS : null,
  );

  return null;
}
