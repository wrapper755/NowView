"use client";

import { useMemo } from "react";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { ActionTracker } from "@/components/rolling/action-tracker";
import { ForecastTrendChart } from "@/components/rolling/forecast-trend-chart";
import { GapPanel } from "@/components/rolling/gap-panel";
import { RevisionHistory } from "@/components/rolling/revision-history";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useDemoController } from "@/lib/store/demo-controller";
import type { RollingPlan } from "@/lib/types/rolling";
import type { ReviewCase } from "@/lib/types/workspace";
import { assertQuartersBalance, decisionToAction, summarizeGap } from "@/services/rolling-plan";

/**
 * Rolling Plan 화면의 클라이언트 경계.
 *
 * ③ 협업 스테이션에서 승인한 결정이 있으면 그것을 실행 과제로 변환해 목록에 더한다 —
 * 승인이 곧바로 추적 가능한 과제가 되는 것이 루프 4→5단계의 연결 지점이다.
 * 스토어는 메모리에만 있으므로 전체 새로고침하면 이 과제는 사라진다.
 */
export function RollingShell({
  plan,
  reviewCase,
}: {
  plan: RollingPlan;
  reviewCase: ReviewCase;
}) {
  const decision = useDemoController((s) => s.decision);

  const actions = useMemo(() => {
    // 분기 합이 전사 수치와 어긋난 Rolling Plan은 보고서로 쓸 수 없다.
    assertQuartersBalance(plan);

    if (!decision) return plan.actions;

    const alternative = reviewCase.alternatives.find((a) => a.id === decision.alternativeId);
    if (!alternative) return plan.actions;

    // 승인 직후 과제는 아직 Forecast 미반영이므로 목록 맨 앞에 둔다.
    return [decisionToAction(decision, alternative, reviewCase.riskId), ...plan.actions];
  }, [decision, plan, reviewCase]);

  const summary = useMemo(() => summarizeGap(plan, actions), [plan, actions]);

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
            {decision ? (
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                승인 1건 신규 반영
              </span>
            ) : null}
          </CardTitle>
          <CardDescription>
            {decision ? (
              <>
                Management Review 승인 결과가 과제로 배포되었다. 아직 Forecast에 반영되지
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
