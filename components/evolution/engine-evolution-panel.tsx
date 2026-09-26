"use client";

/**
 * ⑤에서 **엔진이 실제로 실행한 Evolution Agent의 산출물**을 보여 준다.
 *
 * 루프의 6단계는 "에이전트 룰 개선"인데, 그 일을 하는 `evolution` 노드가 엔진에서
 * 실제로 돌아도 이 화면에는 보이지 않았다 — 개선 제안은 전부 Mock이었다.
 *
 * **정식 개선 제안(`EvolutionProposal`)으로 바꾸지 않는다.** 그 타입은 before/after·
 * 기대효과·**트레이드오프**·담당자를 요구하는데 Agent 산출물에는 없다. 없는 값을 지어내면
 * "부작용 없는 제안은 검토가 아니라 홍보다"(CLAUDE.md 4.7)를 스스로 어긴다. 산출물은
 * 산출물로 보여 주고, 정식 제안으로 승격하는 것은 사람의 몫으로 남긴다 — 4.14의
 * "미정의 — 경영 판단 기준 작성 필요"와 같은 태도다.
 *
 * ⑤는 전역 상태를 바꾸지 않는다는 규칙(4.6)도 그대로다. 여기서는 읽기만 한다.
 */

import { useMemo } from "react";

import { DataSourceList, EscalationCard } from "@/components/shared/data-source";
import { EngineErrorBanner } from "@/components/engine/engine-panel";
import { useEngineSnapshots } from "@/components/engine/use-engine-snapshots";
import { scenarioById } from "@/lib/mock-data/scenarios";
import { CONFIDENCE_LABEL } from "@/lib/types/agent";
import { engineEvolutionOutputs } from "@/services/engine-view";

export function EngineEvolutionPanel() {
  const engine = useEngineSnapshots();

  const outputs = useMemo(
    () => engineEvolutionOutputs(engine.snapshotByScenario, (id) => scenarioById(id).process),
    [engine.snapshotByScenario],
  );

  if (engine.error) {
    return (
      <div className="rounded-lg border">
        <EngineErrorBanner error={engine.error} />
      </div>
    );
  }

  if (engine.engagedScenarioIds.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        엔진 모드로 실행 중인 안건이 없다. ② 트래커에서 &ldquo;엔진으로 실행&rdquo;을 누르면
        Evolution Agent가 실제로 돌고 그 산출물이 여기 나타난다.
      </p>
    );
  }

  if (outputs.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        엔진 모드 안건 {engine.engagedScenarioIds.length}건이 있지만 Evolution Agent는 아직
        실행되지 않았다 — 루프의 마지막 단계라 승인과 Forecast 갱신을 지나야 도달한다.
        {/* 미완료 Agent의 산출물은 어느 화면에서도 미리 보여주지 않는다(4.5). */}
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {outputs.map((output) => {
        const scenario = scenarioById(output.scenarioId);
        return (
          <div key={`${output.scenarioId}-${output.nodeId}`} className="space-y-2.5 rounded-lg border p-3">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
              <span className="rounded bg-muted px-1.5 py-0.5 font-medium text-foreground">
                {scenario.shortTitle}
              </span>
              <span className="text-muted-foreground">{output.agentName}</span>
              <span className="text-muted-foreground/60">·</span>
              <span className="text-muted-foreground tabular-nums">{output.run.duration}</span>
              <span className="text-muted-foreground/60">·</span>
              <span className="text-muted-foreground">
                신뢰도 {CONFIDENCE_LABEL[output.run.confidence]}
              </span>
              {/* 산출물이 Mock인지 실제 LLM 호출인지 구분해야 데모의 주장을 검증할 수 있다. */}
              <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                {output.provenance}
              </span>
            </div>

            <p className="text-sm leading-relaxed text-foreground">{output.run.output}</p>

            {output.run.confidenceNote ? (
              <p className="text-xs text-muted-foreground">— {output.run.confidenceNote}</p>
            ) : null}

            {output.run.sources.length > 0 ? (
              <DataSourceList sources={output.run.sources} />
            ) : (
              /* 근거가 비는 것은 Agent 잘못이 아니라 Mock의 공백이다 — `evolution` 노드에는
                 참조 데이터 정의가 없어 프롬프트에도 비어 간다. 빈 자리를 그냥 두면
                 "근거 없이 결론을 냈다"로 읽히므로 이유를 밝힌다. */
              <p className="text-xs text-muted-foreground">
                근거 데이터가 비어 있다 — 이 노드에는 참조 데이터가 정의되어 있지 않아
                Agent도 받지 못했다. 선행 Agent의 산출물만 보고 낸 제안이다.
              </p>
            )}

            {output.run.escalations?.map((escalation) => (
              <EscalationCard key={escalation.id} escalation={escalation} />
            ))}

            <p className="border-t pt-2 text-xs text-muted-foreground">
              이것은 Agent 산출물이다. 정식 개선 제안이 되려면 조정 전·후 값, 기대 효과,
              <strong className="font-medium text-foreground"> 감수할 트레이드오프</strong>,
              담당자가 필요하다 — 그 판단은 사람의 몫이라 지어내지 않았다.
            </p>
          </div>
        );
      })}
    </div>
  );
}
