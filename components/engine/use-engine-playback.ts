"use client";

/**
 * 데모 플레이어의 엔진 연동 — 장면을 엔진 위에서 재현한다.
 *
 * 장면은 `sequence` 인덱스로 진행 지점을 선언한다(`DemoScene.step`). 엔진에는 그런
 * 인덱스가 없으므로 **그 인덱스가 가리키는 노드**로 옮긴다.
 *
 * **두 방향의 성격이 다르다.** 뒤로는 과거 체크포인트를 읽기만 하고(인스턴스는 그대로),
 * 앞으로는 실제로 진행한다. 앞으로 갈 때 승인 노드를 통과해야 하면 장면이 선언한 결정을
 * 함께 보낸다 — 엔진이 임의로 승인하면 Human-in-the-Loop이 무너진다.
 *
 * **엔진 인스턴스가 없으면 아무것도 하지 않는다.** 데모는 Mock 모드가 기본이고, 그때는
 * 기존 스토어 경로가 그대로 돈다.
 */

import { useCallback, useState } from "react";

import type { EngineError } from "@/components/engine/use-engine-instance";
import { useEngineSession } from "@/lib/store/engine-session";
import type { DemoScene } from "@/lib/demo-scenario";
import type { Scenario } from "@/lib/types/scenario";
import type { EngineSnapshot } from "@/services/engine-client";

export function useEnginePlayback() {
  const instanceByScenario = useEngineSession((s) => s.instanceByScenario);
  const setView = useEngineSession((s) => s.setView);
  const [error, setError] = useState<EngineError | null>(null);
  const [pending, setPending] = useState(false);

  /**
   * 장면을 엔진에 반영한다. 엔진 모드가 아니면 `false`를 돌려주고 아무것도 하지 않는다.
   */
  const applyScene = useCallback(
    async (scenario: Scenario, scene: DemoScene): Promise<boolean> => {
      const instanceId = instanceByScenario[scenario.id];
      if (!instanceId) return false;

      const targetNodeId = scenario.process.sequence[scene.step];
      if (!targetNodeId) {
        setError({ message: `장면이 가리키는 진행 지점이 프로세스 범위 밖이다 (${scene.step})` });
        return true;
      }

      setPending(true);
      setError(null);
      try {
        const response = await fetch(
          `/api/engine/instances/${encodeURIComponent(instanceId)}/seek`,
          {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              targetNodeId,
              // 승인 이전 장면에는 결정을 보내지 않는다 — 장면이 "아직 승인 전"이라고
              // 선언했는데 통과시켜 버리면 각본과 화면이 어긋난다.
              decision: scene.decided
                ? {
                    alternativeId: scenario.demoDecision.alternativeId,
                    leverValue: scenario.demoDecision.leverValue,
                    rationale: scenario.demoDecision.rationale,
                  }
                : undefined,
            }),
          },
        );
        const body = await response.json().catch(() => null);
        if (!response.ok) {
          setError({
            message: body?.error ?? `장면 이동에 실패했다 (HTTP ${response.status})`,
            detail: typeof body?.detail === "string" ? body.detail : undefined,
            status: response.status,
          });
          return true;
        }
        const snapshot = body as EngineSnapshot;
        // 과거 시점이면 화면이 그것을 그려야 하고, 현재 시점이면 override를 걷는다.
        setView(scenario.id, snapshot.historical ? snapshot : null);
        return true;
      } catch (cause) {
        setError({
          message: "엔진에 연결할 수 없다",
          detail: cause instanceof Error ? cause.message : String(cause),
        });
        return true;
      } finally {
        setPending(false);
      }
    },
    [instanceByScenario, setView],
  );

  return { applyScene, pending, error, clearError: useCallback(() => setError(null), []) };
}
