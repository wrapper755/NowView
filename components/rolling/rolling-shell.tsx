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
import { scenarios } from "@/lib/mock-data/scenarios";
import { useDemoController } from "@/lib/store/demo-controller";
import type { RollingPlan } from "@/lib/types/rolling";
import {
  assertQuartersBalance,
  decisionToAction,
  planView,
  summarizeGap,
} from "@/services/rolling-plan";

/**
 * Rolling Plan 화면의 클라이언트 경계.
 *
 * ③ 협업 스테이션에서 승인한 결정이 있으면 그것을 실행 과제로 변환해 목록에 더한다 —
 * 승인이 곧바로 추적 가능한 과제가 되는 것이 루프 4→5단계의 연결 지점이다.
 * 스토어는 메모리에만 있으므로 전체 새로고침하면 이 과제는 사라진다.
 */
export function RollingShell({ plan }: { plan: RollingPlan }) {
  const decisionByScenario = useDemoController((s) => s.decisionByScenario);

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
