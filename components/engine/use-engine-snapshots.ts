"use client";

/**
 * 전 시나리오의 엔진 스냅샷을 **읽는다** — 가져오지는 않는다.
 *
 * 가져오는 곳은 `SnapshotPoller` 하나뿐이다(레이아웃에 상주). 훅이 각자 가져오면
 * (1) 같은 화면의 두 패널이 서로 다른 순간을 볼 수 있고 (2) 폴링을 붙이면 요청이
 * 화면·패널 수만큼 배로 늘어난다. 실제로 ①은 경영 수행 성과와 리스크 신호가 각각
 * 같은 훅을 불러 두 번 가져오고 있었다.
 *
 * `engagedScenarioIds`는 세션 스토어에서 파생한다 — **스냅샷 조회가 실패해도 남아야
 * 한다.** 엔진이 소유한 시나리오를 놓치면 Mock 값이 되살아나 승인이 두 번 잡힌다
 * (CLAUDE.md 4.17).
 */

import { useMemo } from "react";

import { useEngineSession } from "@/lib/store/engine-session";
import { useEngineSnapshotStore } from "@/lib/store/engine-snapshots";
import type { EngineError, EngineSnapshot } from "@/services/engine-client";

export interface EngineSnapshots {
  /** 엔진이 소유한 시나리오 id. 스냅샷을 아직 못 읽었어도 여기 들어간다. */
  engagedScenarioIds: string[];
  /** 시나리오 id → 스냅샷. 조회에 실패하면 비어 있다. */
  snapshotByScenario: Record<string, EngineSnapshot>;
  loading: boolean;
  error: EngineError | null;
  /** 마지막으로 읽은 시각(ms). */
  fetchedAt: number | null;
}

export function useEngineSnapshots(): EngineSnapshots {
  const instanceByScenario = useEngineSession((s) => s.instanceByScenario);
  const snapshots = useEngineSnapshotStore((s) => s.snapshots);
  const forKey = useEngineSnapshotStore((s) => s.forKey);
  const error = useEngineSnapshotStore((s) => s.error);
  const fetchedAt = useEngineSnapshotStore((s) => s.fetchedAt);

  // 폴러와 같은 방식으로 키를 만든다 — 다르게 만들면 `loading`이 영원히 true가 된다.
  const { engagedScenarioIds, key } = useMemo(() => {
    const attached = Object.entries(instanceByScenario)
      .filter(([, id]) => Boolean(id))
      .map(([scenarioId, id]) => ({ scenarioId, instanceId: id as string }))
      .sort((a, b) => a.scenarioId.localeCompare(b.scenarioId));
    return {
      engagedScenarioIds: attached.map((a) => a.scenarioId),
      key: attached.map((a) => `${a.scenarioId}:${a.instanceId}`).join("|"),
    };
  }, [instanceByScenario]);

  return {
    engagedScenarioIds,
    // 지금 구성의 결과가 아직 없으면 쓰지 않는다 — 옛 인스턴스의 값을 보여주면
    // 화면이 실제와 어긋난다.
    snapshotByScenario: forKey === key ? snapshots : {},
    loading: key !== "" && forKey !== key,
    error: forKey === key ? error : null,
    fetchedAt: forKey === key ? fetchedAt : null,
  };
}
