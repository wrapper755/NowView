"use client";

import { useMemo } from "react";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { ActionTracker } from "@/components/rolling/action-tracker";
import { ForecastTrendChart } from "@/components/rolling/forecast-trend-chart";
import { GapPanel } from "@/components/rolling/gap-panel";
import { PlanPanel } from "@/components/rolling/plan-panel";
import { RevisionHistory } from "@/components/rolling/revision-history";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { EngineErrorBanner } from "@/components/engine/engine-panel";
import { useEngineSnapshots } from "@/components/engine/use-engine-snapshots";
import { scenarioById, scenarios } from "@/lib/mock-data/scenarios";
import { useDemoController } from "@/lib/store/demo-controller";
import type { RollingPlan } from "@/lib/types/rolling";
import {
  assertQuartersBalance,
  decisionToAction,
  mergeDecisions,
  planView,
  summarizeGap,
} from "@/services/rolling-plan";
import { engineDecisionsFrom } from "@/services/engine-view";

/**
 * Rolling Plan 화면의 클라이언트 경계.
 *
 * ③ 협업 스테이션에서 승인한 결정이 있으면 그것을 실행 과제로 변환해 목록에 더한다 —
 * 승인이 곧바로 추적 가능한 과제가 되는 것이 루프 4→5단계의 연결 지점이다.
 *
 * **Mock 승인과 엔진 승인을 함께 받는다.** 한 시나리오에 엔진 인스턴스가 붙어 있으면
 * 그 시나리오의 권위는 엔진에 있다 — 둘을 다 더하면 같은 승인이 두 번 잡힌다
 * (`mergeDecisions`). 이 화면은 정적 프리렌더를 유지하므로 엔진 결정은 클라이언트에서
 * 채운다(②·③과 같은 방식).
 */
export function RollingShell({ plan }: { plan: RollingPlan }) {
  const mockDecisions = useDemoController((s) => s.decisionByScenario);
  const engine = useEngineSnapshots();

  // 스냅샷에서 결정만 뽑는다 — 같은 스냅샷이 ①의 소요시간·단계, ⑤의 산출물에도 쓰인다.
  const engineDecisions = useMemo(
    () => engineDecisionsFrom(engine.snapshotByScenario, (id) => scenarioById(id).reviewCase),
    [engine.snapshotByScenario],
  );

  const decisionByScenario = useMemo(
    () =>
      mergeDecisions(mockDecisions, {
        engagedScenarioIds: engine.engagedScenarioIds,
        decisionByScenario: engineDecisions,
      }),
    [mockDecisions, engine.engagedScenarioIds, engineDecisions],
  );

  /**
   * **Rolling Plan은 전사 자산이라 모든 시나리오의 승인 과제를 함께 받는다.**
   *
   * 시나리오마다 Plan을 복제하면 재사용이 아니라 복사가 된다. 전사 Gap은 하나이고
   * 두 안건이 그것을 나눠 메우므로, 과제도 한 목록에 모여야 합산이 맞는다.
   */
  const actions = useMemo(() => {
    // 분기 합이 전사 수치와 어긋난 Rolling Plan은 보고서로 쓸 수 없다.
    assertQuartersBalance(plan);

    const approved = scenarios.flatMap((scenario) => {
      const decision = decisionByScenario[scenario.id];
      if (!decision) return [];
      const alternative = scenario.reviewCase.alternatives.find(
        (a) => a.id === decision.alternativeId,
      );
      if (!alternative) return [];
      return [decisionToAction(decision, alternative, scenario.reviewCase.riskId)];
    });

    // 승인 직후 과제는 아직 Forecast 미반영이므로 목록 맨 앞에 둔다.
    return [...approved, ...plan.actions];
  }, [decisionByScenario, plan]);

  const approvedCount = actions.length - plan.actions.length;

  const summary = useMemo(() => summarizeGap(plan, actions), [plan, actions]);
  // 승인 전에는 조정 후 계획을 유효한 값으로 보여주지 않는다.
  const planItems = useMemo(() => planView(plan, approvedCount > 0), [plan, approvedCount]);

  return (
    <div className="space-y-4">
      {/* 엔진 인스턴스를 못 읽으면 그 시나리오의 과제가 목록에서 빠진다. 조용히 넘기면
          Gap이 실제보다 덜 메워진 것으로 보이는데, 숫자가 그럴듯해 눈으로 안 잡힌다. */}
      {engine.error ? (
        <div className="rounded-lg border">
          <EngineErrorBanner error={engine.error} />
          <p className="px-3 pb-3 text-xs text-muted-foreground">
            엔진이 소유한 안건 {engine.engagedScenarioIds.length}건의 승인 과제가 아래 목록에
            빠져 있다. 아래 수치는 그만큼 덜 메워진 상태다.
          </p>
        </div>
      ) : null}

      {engine.engagedScenarioIds.length > 0 && !engine.error ? (
        <p className="text-xs text-muted-foreground">
          엔진 모드 안건 {engine.engagedScenarioIds.length}건이 포함되어 있다 — 그 안건은
          Mock 승인이 아니라 엔진에 기록된 결정을 쓴다(같은 승인이 두 번 잡히지 않게).
        </p>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="viz-root lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-base">Gap 관리</CardTitle>
            <CardDescription>
              목표는 고정하고 전망만 갱신한다. 남은 차이는 명시한다.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <GapPanel summary={summary} />
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">분기별 Target vs Forecast</CardTitle>
            <CardDescription>
              1~3Q는 마감 확정, 4Q는 전망이다. 분기 합은 전사 Target·Forecast와 일치한다.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ForecastTrendChart quarters={plan.quarters} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            실행 과제 {actions.length}건
            {approvedCount > 0 ? (
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                승인 {approvedCount}건 신규 반영
              </span>
            ) : null}
          </CardTitle>
          <CardDescription>
            {approvedCount > 0 ? (
              <>
                승인 결과가 과제로 배포되었다. 아직 Forecast에 반영되지
                않았으므로 다음 Rolling 회차에서 갱신된다.
              </>
            ) : (
              <>
                담당·기한·목표 회수액이 없는 과제는 만들지 않는다. 추적할 수 없는 과제는
                실행되지 않은 것과 같다.{" "}
                <Link
                  href="/workspace"
                  className="inline-flex items-center gap-0.5 font-medium text-foreground hover:underline"
                >
                  Management Review에서 대안 승인하기
                  <ArrowUpRight aria-hidden className="size-3" />
                </Link>
              </>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ActionTracker actions={actions} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">실행계획 (Plan)</CardTitle>
          <CardDescription>
            Target은 고정하고 Forecast는 갱신하며, Plan은 승인된 대응안과 운영 여건 변화를
            반영해 <strong className="font-medium text-foreground">조정</strong>한다.
            승인 전에는 조정 후 값을 확정된 계획으로 보여주지 않는다.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <PlanPanel items={planItems} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Rolling 갱신 이력</CardTitle>
          <CardDescription>
            회차마다 움직이는 것은 Forecast뿐이다. Target {plan.target}억은 모든 회차에서
            동일하다.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <RevisionHistory revisions={plan.revisions} target={plan.target} />
        </CardContent>
      </Card>
    </div>
  );
}
