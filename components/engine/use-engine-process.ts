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

  const view: EngineProcessView | null = useMemo(() => {
    if (!instance.snapshot) return null;
    // 시나리오를 바꾸면 스냅샷이 잠시 이전 프로세스의 것일 수 있다. 그대로 변환하면
    // 없는 노드를 찾다가 터지므로, 같은 시나리오일 때만 뷰를 만든다.
    if (instance.snapshot.scenarioId !== scenarioId) return null;
    return engineProcessView(process, instance.snapshot);
  }, [instance.snapshot, process, scenarioId]);

  const onStart = useCallback(async () => {
    const snapshot = await instance.create(scenarioId, agentMode);
    if (snapshot) attach(scenarioId, snapshot.instanceId);
  }, [instance, scenarioId, agentMode, attach]);

  const onStop = useCallback(() => {
    // 인스턴스를 지우지 않고 화면만 Mock으로 되돌린다 — 서버에 남겨 두면 나중에
    // 다시 붙을 수 있고, 무엇보다 사람이 누른 "모드 전환"이 데이터 삭제를 뜻하면 안 된다.
    detach(scenarioId);
  }, [detach, scenarioId]);

  return {
    view,
    snapshot: view ? instance.snapshot : null,
    instanceId,
    pending: instance.pending,
    error: instance.error,
    resume: instance.resume,
    panelProps: {
      snapshot: view ? instance.snapshot : null,
      loading: instance.loading,
      pending: instance.pending,
      error: instance.error,
      agentMode,
      onAgentModeChange: setAgentMode,
      onStart,
      onStop,
      onRefresh: instance.refresh,
    },
  };
}
