"use client";

/**
 * 화면이 쓰는 엔진 연결 — 세션 스토어 + 인스턴스 조회 + 뷰 변환을 한 번에 묶는다.
 *
 * **트래커와 협업 스테이션이 같은 인스턴스를 본다.** 화면마다 따로 만들면 ②에서
 * 실행한 프로세스를 ③에서 승인할 수 없다 — 그러면 "한 사건을 여러 관점으로 본다"는
 * 이 프로젝트의 전제가 엔진 모드에서만 깨진다(CLAUDE.md 4.6).
 */

import { useCallback, useMemo } from "react";

import { useEngineInstance } from "@/components/engine/use-engine-instance";
import { useEngineSnapshots } from "@/components/engine/use-engine-snapshots";
import {
  selectAgentMode,
  useEngineSession,
} from "@/lib/store/engine-session";
import type { BpmProcessInstance } from "@/lib/types/bpm";
import { engineProcessView, type EngineProcessView } from "@/services/engine-view";

export function useEngineProcess(scenarioId: string, process: BpmProcessInstance) {
  // 선택자를 인라인으로 만들면 매 렌더마다 새 함수가 되어 구독이 다시 걸린다.
  const instanceId = useEngineSession(
    useCallback((s) => s.instanceByScenario[scenarioId] ?? null, [scenarioId]),
  );
  const agentMode = useEngineSession(selectAgentMode);
  const setAgentMode = useEngineSession((s) => s.setAgentMode);
  const attach = useEngineSession((s) => s.attach);
  const detach = useEngineSession((s) => s.detach);

  const instance = useEngineInstance(instanceId);
  const snapshots = useEngineSnapshots();

  /**
   * 라이브 스냅샷은 **공유 스토어**에서 읽는다 — 가져오는 곳은 `SnapshotPoller`뿐이다.
   * 여기서 따로 가져오면 ②·③이 ①·④·⑤와 다른 순간을 그릴 수 있다.
   */
  const live = snapshots.snapshotByScenario[scenarioId] ?? null;

  /**
   * 데모가 과거 시점을 보여주는 중이면 라이브 대신 그 스냅샷을 그린다.
   *
   * 되감기가 읽기 전용이라 다시 조회하면 "지금"이 온다 — 그래서 플레이어가 받아 둔
   * 과거 스냅샷을 스토어에서 읽는다. 서버가 돌려준 값이므로 지어낸 상태가 아니다.
   */
  const override = useEngineSession(
    useCallback((s) => s.viewByScenario[scenarioId] ?? null, [scenarioId]),
  );
  const snapshot = override ?? live;

  const view: EngineProcessView | null = useMemo(() => {
    if (!snapshot) return null;
    // 시나리오를 바꾸면 스냅샷이 잠시 이전 프로세스의 것일 수 있다. 그대로 변환하면
    // 없는 노드를 찾다가 터지므로, 같은 시나리오일 때만 뷰를 만든다.
    if (snapshot.scenarioId !== scenarioId) return null;
    return engineProcessView(process, snapshot);
  }, [snapshot, process, scenarioId]);

  const onStart = useCallback(async () => {
    const snapshot = await instance.create(scenarioId, agentMode);
    if (snapshot) attach(scenarioId, snapshot.instanceId);
  }, [instance, scenarioId, agentMode, attach]);

  const setView = useEngineSession((s) => s.setView);

  const onStop = useCallback(() => {
    // 인스턴스를 지우지 않고 화면만 Mock으로 되돌린다 — 서버에 남겨 두면 나중에
    // 다시 붙을 수 있고, 무엇보다 사람이 누른 "모드 전환"이 데이터 삭제를 뜻하면 안 된다.
    detach(scenarioId);
  }, [detach, scenarioId]);

  /** 데모가 보여주던 과거 시점을 걷고 라이브로 돌아온다. */
  const onLive = useCallback(() => setView(scenarioId, null), [setView, scenarioId]);

  return {
    view,
    snapshot: view ? snapshot : null,
    /** 과거 시점을 보고 있는가 — 승인 버튼을 잠그는 데 쓴다. */
    historical: Boolean(snapshot?.historical),
    instanceId,
    pending: instance.pending,
    error: instance.error,
    resume: instance.resume,
    panelProps: {
      snapshot: view ? snapshot : null,
      loading: snapshots.loading,
      pending: instance.pending,
      error: instance.error,
      agentMode,
      onAgentModeChange: setAgentMode,
      onStart,
      onStop,
      onRefresh: instance.refresh,
      historical: Boolean(snapshot?.historical),
      onLive,
    },
  };
}
