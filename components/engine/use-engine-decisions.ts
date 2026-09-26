"use client";

/**
 * 전 시나리오의 엔진 결정을 모은다 — ④ Rolling Plan 전용.
 *
 * **④는 성격이 다르다.** ②·③은 지금 보고 있는 한 시나리오의 인스턴스를 다루지만,
 * Rolling Plan은 전사 자산이라 **모든 시나리오의 승인 과제를 함께** 받는다
 * (CLAUDE.md 4.13). 전사 Gap은 하나이고 여러 안건이 그것을 나눠 메우므로, 인스턴스가
 * 여럿이면 여럿을 다 읽어야 합산이 맞는다.
 *
 * **이중 계상을 여기서 막는다.** 한 시나리오에 엔진 인스턴스가 붙어 있으면 그 시나리오의
 * 권위는 엔진에 있다 — Mock 스토어의 결정과 함께 더하면 같은 승인이 두 번 잡힌다.
 * 그 판단에 필요한 것이 `engagedScenarioIds`다.
 */

import { useEffect, useMemo, useState } from "react";

import type { EngineError } from "@/components/engine/use-engine-instance";
import { useEngineSession } from "@/lib/store/engine-session";
import { scenarioById } from "@/lib/mock-data/scenarios";
import type { ReviewDecision } from "@/lib/types/workspace";
import type { EngineSnapshot } from "@/services/engine-client";
import { engineDecisionToReview } from "@/services/engine-view";

export interface EngineDecisions {
  /** 엔진이 소유한 시나리오 id. 결정이 아직 없어도 여기 들어간다. */
  engagedScenarioIds: string[];
  /** 시나리오 id → 승인된 결정. 아직 승인 전이면 없다. */
  decisionByScenario: Record<string, ReviewDecision>;
  loading: boolean;
  error: EngineError | null;
}

/**
 * 비동기로 받아 온 것만 상태에 둔다.
 *
 * `engagedScenarioIds`와 `loading`은 **파생값**이다 — 어떤 인스턴스가 붙어 있는지는
 * 스토어가 이미 알고, 로딩 여부는 "받아 온 결과가 지금 구성의 것인가"로 계산된다.
 * 이것들을 상태에 두면 effect 본문에서 동기로 `setState`를 하게 되고
 * `react-hooks/set-state-in-effect`에 걸린다(CLAUDE.md의 그 규칙).
 */
interface FetchedDecisions {
  /** 이 결과가 어떤 인스턴스 구성에서 나왔는가. `loading` 판정의 근거다. */
  forKey: string;
  decisions: Record<string, ReviewDecision>;
  error: EngineError | null;
}

const NOTHING_FETCHED: FetchedDecisions = { forKey: "", decisions: {}, error: null };

export function useEngineDecisions(): EngineDecisions {
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
  const [fetched, setFetched] = useState<FetchedDecisions>(NOTHING_FETCHED);

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

        const decisions: Record<string, ReviewDecision> = {};
        for (const { scenarioId, snapshot } of snapshots) {
          // 스냅샷이 다른 시나리오의 것이면 쓰지 않는다. 대안 id가 맞지 않아
          // 엉뚱한 금액이 Gap에 더해질 수 있다.
          if (snapshot.scenarioId !== scenarioId) continue;
          const converted = engineDecisionToReview(
            scenarioById(scenarioId).reviewCase,
            snapshot.decision,
          );
          if (converted) decisions[scenarioId] = converted;
        }
        setFetched({ forKey: key, decisions, error: null });
      } catch (cause) {
        if (cancelled) return;
        // 실패해도 `engagedScenarioIds`는 스토어에서 파생되므로 그대로 남는다 —
        // 엔진이 소유한 시나리오를 놓치면 Mock 결정이 되살아나 승인이 두 번 잡힌다.
        setFetched({ forKey: key, decisions: {}, error: cause as EngineError });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [key, attached]);

  return {
    engagedScenarioIds,
    // 지금 구성의 결과가 아직 없으면 쓰지 않는다 — 옛 인스턴스의 결정을 보여주면
    // 과제 목록이 실제와 어긋난다.
    decisionByScenario: fetched.forKey === key ? fetched.decisions : {},
    loading: key !== "" && fetched.forKey !== key,
    error: fetched.forKey === key ? fetched.error : null,
  };
}
