"use client";

/**
 * ① Cockpit에서 **엔진이 소유하는 조각**만 클라이언트로 감싼 것.
 *
 * Cockpit 전체를 옮기지 않는다 — 전사 스냅샷(매출·영업이익·브릿지·사업부)과 Framework는
 * 엔진이 소유하지 않으므로 옮기면 정적 프리렌더만 잃는다(CLAUDE.md 4.16 규칙 소유권).
 * 엔진이 실제로 아는 것은 둘이다:
 *
 * 1. **Agent가 얼마나 걸렸는가** — 엔진 LLM 모드에서는 ollama가 돌려준 실제 경과 시간이다.
 *    Mock 기준 계산과 근거가 다르므로 출처 배지가 `measured`로 바뀐다.
 * 2. **안건이 지금 어느 단계에 있는가** — `RiskSignal.stage`는 Mock에 적힌 값인데, 엔진
 *    인스턴스가 있으면 진행 지점은 실행의 결과다. 감지 화면이 "어디까지 왔나"를 틀리게
 *    말하면 그 화면을 보는 이유가 없어진다.
 *
 * 페이지는 서버 컴포넌트로 남고 이 조각만 클라이언트에서 채운다 — 그래서 `/`는 여전히 `○`다.
 */

import { useMemo } from "react";

import { ExecutionPerformancePanel } from "@/components/cockpit/execution-performance-panel";
import { RiskSignalList } from "@/components/cockpit/risk-signal-list";
import { EngineErrorBanner } from "@/components/engine/engine-panel";
import { useEngineSnapshots } from "@/components/engine/use-engine-snapshots";
import { scenarioById } from "@/lib/mock-data/scenarios";
import type { RiskSignal } from "@/lib/types/cockpit";
import type { ExecutionMetric } from "@/lib/types/execution-performance";
import { engineRunsFrom, engineStagesByRisk } from "@/services/engine-view";
import { executionMetrics } from "@/services/execution-performance";

/**
 * 경영 수행 성과 — 엔진이 돌았으면 Agent 소요시간을 실측값으로 바꾼다.
 *
 * `fallback`은 서버에서 계산한 Mock 기준 목록이다. 엔진이 꺼져 있거나 아직 Agent가
 * 하나도 안 돌았으면 그대로 쓴다 — 0시간으로 덮으면 "분석이 즉시 끝났다"가 된다.
 */
export function ExecutionPerformanceSection({ fallback }: { fallback: ExecutionMetric[] }) {
  const engine = useEngineSnapshots();

  const runs = useMemo(
    () => engineRunsFrom(engine.snapshotByScenario, (id) => scenarioById(id).process),
    [engine.snapshotByScenario],
  );

  const metrics = useMemo(
    () => (runs.length > 0 ? executionMetrics(runs) : fallback),
    [runs, fallback],
  );

  return (
    <div className="space-y-3">
      {runs.length > 0 ? (
        <p className="text-xs text-muted-foreground">
          엔진이 실행한 Agent {runs.length}건의 실제 소요시간을 반영했다 — 해당 지표의 출처
          배지가 <span className="font-medium text-foreground">엔진 실측값</span>으로 바뀐다.
        </p>
      ) : null}
      <ExecutionPerformancePanel metrics={metrics} />
    </div>
  );
}

/** 리스크 신호 — 엔진 인스턴스가 있는 안건은 실제 진행 단계를 쓴다. */
export function RiskSignalSection({ risks }: { risks: RiskSignal[] }) {
  const engine = useEngineSnapshots();

  const stages = useMemo(
    () => engineStagesByRisk(engine.snapshotByScenario, (id) => scenarioById(id).process),
    [engine.snapshotByScenario],
  );

  const merged = useMemo(
    () => risks.map((risk) => (stages[risk.id] ? { ...risk, stage: stages[risk.id] } : risk)),
    [risks, stages],
  );

  const overridden = merged.filter((risk, index) => risk.stage !== risks[index].stage).length;

  return (
    <div className="space-y-3">
      {engine.error ? (
        <div className="rounded-lg border">
          <EngineErrorBanner error={engine.error} />
          <p className="px-3 pb-3 text-xs text-muted-foreground">
            아래 단계 표시는 Mock에 적힌 값이다 — 엔진이 실제로 어디까지 진행했는지는 알 수
            없다.
          </p>
        </div>
      ) : null}

      {overridden > 0 ? (
        <p className="text-xs text-muted-foreground">
          {overridden}건의 단계를 엔진 실행 상태로 갱신했다. Mock에 적힌 단계가 아니라
          인스턴스가 실제로 도달한 지점이다.
        </p>
      ) : null}

      <RiskSignalList risks={merged} />
    </div>
  );
}
