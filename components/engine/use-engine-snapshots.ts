"use client";

/**
 * 전 시나리오의 엔진 스냅샷을 모은다 — 전사 화면(①④⑤) 전용.
 *
 * **②·③과 성격이 다르다.** 그쪽은 지금 보고 있는 한 시나리오의 인스턴스를 다루지만,
 * 전사 화면은 **모든 시나리오를 함께** 본다(CLAUDE.md 4.13). 전사 Gap은 하나이고
 * 여러 안건이 그것을 나눠 메우므로, 인스턴스가 여럿이면 여럿을 다 읽어야 합산이 맞는다.
 *
 * **한 번 가져와 여러 파생을 만든다.** 승인 결정(④), Agent 실행 기록(①), 현재 단계(①),
 * Evolution Agent 산출물(⑤)이 모두 같은 스냅샷에서 나온다. 화면마다 따로 가져오면
 * 같은 순간을 서로 다르게 본 값이 한 화면에 섞인다.
 *
 * `engagedScenarioIds`가 중요하다 — 엔진이 소유한 시나리오를 알아야 Mock 값과 겹쳐
 * 이중 계상하는 것을 막을 수 있다.
 */

import { useEffect, useMemo, useState } from "react";

import type { EngineError } from "@/components/engine/use-engine-instance";
import { useEngineSession } from "@/lib/store/engine-session";
import type { EngineSnapshot } from "@/services/engine-client";

export interface EngineSnapshots {
  /** 엔진이 소유한 시나리오 id. 스냅샷을 아직 못 읽었어도 여기 들어간다. */
  engagedScenarioIds: string[];
  /** 시나리오 id → 스냅샷. 조회에 실패하면 비어 있다. */
  snapshotByScenario: Record<string, EngineSnapshot>;
  loading: boolean;
  error: EngineError | null;
  /** 갱신 카운터. 파생 memo의 의존성에 넣으면 seek 후에도 다시 계산된다. */
  revision: number;
}

/**
 * 비동기로 받아 온 것만 상태에 둔다.
 *
 * `engagedScenarioIds`와 `loading`은 **파생값**이다 — 어떤 인스턴스가 붙어 있는지는
 * 스토어가 이미 알고, 로딩 여부는 "받아 온 결과가 지금 구성의 것인가"로 계산된다.
 * 이것들을 상태에 두면 effect 본문에서 동기로 `setState`를 하게 되고
 * `react-hooks/set-state-in-effect`에 걸린다(CLAUDE.md의 그 규칙).
 */
interface Fetched {
  /** 이 결과가 어떤 인스턴스 구성에서 나왔는가. `loading` 판정의 근거다. */
  forKey: string;
  snapshots: Record<string, EngineSnapshot>;
  error: EngineError | null;
}

const NOTHING_FETCHED: Fetched = { forKey: "", snapshots: {}, error: null };

export function useEngineSnapshots(): EngineSnapshots {
  const instanceByScenario = useEngineSession((s) => s.instanceByScenario);

  // 붙어 있는 것만 읽는다. 객체 참조가 아니라 내용으로 비교해야 매 렌더마다 다시 긁지 않는다.
  const attached = useMemo(
    () =>
      Object.entries(instanceByScenario)
        .filter(([, id]) => Boolean(id))
        .map(([scenarioId, id]) => ({ scenarioId, instanceId: id as string }))
        .sort((a, b) => a.scenarioId.localeCompare(b.scenarioId)),
    [instanceByScenario],
  );
  const key = attached.map((a) => `${a.scenarioId}:${a.instanceId}`).join("|");

  const engagedScenarioIds = useMemo(() => attached.map((a) => a.scenarioId), [attached]);
  // 플레이어가 seek하면 ①④⑤도 같은 변화를 봐야 한다.
  const revision = useEngineSession((s) => s.revision);
  const [fetched, setFetched] = useState<Fetched>(NOTHING_FETCHED);

  useEffect(() => {
    if (!key) return;
    // 인스턴스 구성이 바뀌면 진행 중이던 응답을 버린다 — 옛 결과로 덮으면 합산이
    // 어긋난다. ref를 렌더 중에 쓰면 `react-hooks/refs`에 걸리므로 정리 함수를 쓴다.
    let cancelled = false;

    void (async () => {
      try {
        const snapshots = await Promise.all(
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
        if (cancelled) return;

        const byScenario: Record<string, EngineSnapshot> = {};
        for (const { scenarioId, snapshot } of snapshots) {
          // 스냅샷이 다른 시나리오의 것이면 쓰지 않는다. 노드·대안 id가 맞지 않아
          // 엉뚱한 값이 화면에 섞인다.
          if (snapshot.scenarioId !== scenarioId) continue;
          byScenario[scenarioId] = snapshot;
        }
        setFetched({ forKey: key, snapshots: byScenario, error: null });
      } catch (cause) {
        if (cancelled) return;
        // 실패해도 `engagedScenarioIds`는 스토어에서 파생되므로 그대로 남는다 —
        // 엔진이 소유한 시나리오를 놓치면 Mock 값이 되살아나 이중 계상된다.
        setFetched({ forKey: key, snapshots: {}, error: cause as EngineError });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [key, attached, revision]);

  return {
    engagedScenarioIds,
    // 지금 구성의 결과가 아직 없으면 쓰지 않는다 — 옛 인스턴스의 값을 보여주면
    // 화면이 실제와 어긋난다.
    snapshotByScenario: fetched.forKey === key ? fetched.snapshots : {},
    loading: key !== "" && fetched.forKey !== key,
    revision,
    error: fetched.forKey === key ? fetched.error : null,
  };
}
