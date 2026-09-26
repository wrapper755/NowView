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

import { useCallback, useRef, useState } from "react";

import type { EngineError } from "@/components/engine/use-engine-instance";
import { useEngineSession } from "@/lib/store/engine-session";
import type { DemoScene } from "@/lib/demo-scenario";
import type { Scenario } from "@/lib/types/scenario";
import type { EngineSnapshot } from "@/services/engine-client";

/**
 * 장면 반영 결과.
 *
 * `skipped`는 실패가 아니다 — 엔진 인스턴스가 없어서 Mock 경로로 돈 것이다.
 * 자동 재생이 이 셋을 구분해야 "엔진이 실패했는데 계속 넘어가는" 상황을 막는다.
 */
export type PlaybackResult = "skipped" | "ok" | "failed";

export function useEnginePlayback() {
  const instanceByScenario = useEngineSession((s) => s.instanceByScenario);
  const setView = useEngineSession((s) => s.setView);
  const [error, setError] = useState<EngineError | null>(null);
  const [pending, setPending] = useState(false);

  /**
   * 요청 일련번호. 늦게 도착한 응답이 최신 장면을 덮어쓰지 않게 한다.
   *
   * LLM 모드에서 장면 왕복이 수십 초라, 그 사이 사람이 다른 장면을 누르면 두 요청이
   * 겹친다. 순서를 보장하지 않으면 먼저 보낸 것이 나중에 도착해 화면이 뒤로 튄다.
   */
  const requestRef = useRef(0);

  /**
   * 장면을 엔진에 반영한다. 엔진 모드가 아니면 `skipped`를 돌려주고 아무것도 하지 않는다.
   *
   * **끝날 때까지 기다릴 수 있도록 Promise를 돌려준다.** 자동 재생이 이것을 기다렸다가
   * 머무름을 시작해야 LLM 모드에서 장면이 밀리지 않는다.
   */
  const applyScene = useCallback(
    async (scenario: Scenario, scene: DemoScene): Promise<PlaybackResult> => {
      const instanceId = instanceByScenario[scenario.id];
      if (!instanceId) return "skipped";

      const targetNodeId = scenario.process.sequence[scene.step];
      if (!targetNodeId) {
        setError({ message: `장면이 가리키는 진행 지점이 프로세스 범위 밖이다 (${scene.step})` });
        return "failed";
      }

      const ticket = ++requestRef.current;
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
        // 그 사이 더 최신 장면 요청이 나갔으면 이 응답은 버린다.
        if (ticket !== requestRef.current) return "ok";
        if (!response.ok) {
          setError({
            message: body?.error ?? `장면 이동에 실패했다 (HTTP ${response.status})`,
            detail: typeof body?.detail === "string" ? body.detail : undefined,
            status: response.status,
          });
          return "failed";
        }
        const snapshot = body as EngineSnapshot;
        // 과거 시점이면 화면이 그것을 그려야 하고, 현재 시점이면 override를 걷는다.
        setView(scenario.id, snapshot.historical ? snapshot : null);
        return "ok";
      } catch (cause) {
        if (ticket !== requestRef.current) return "ok";
        setError({
          message: "엔진에 연결할 수 없다",
          detail: cause instanceof Error ? cause.message : String(cause),
        });
        return "failed";
      } finally {
        // 최신 요청만 진행 표시를 내린다 — 겹쳤을 때 먼저 끝난 것이 표시를 꺼 버리면
        // 아직 도는 요청이 있는데도 끝난 것처럼 보인다.
        if (ticket === requestRef.current) setPending(false);
      }
    },
    [instanceByScenario, setView],
  );

  return { applyScene, pending, error, clearError: useCallback(() => setError(null), []) };
}
