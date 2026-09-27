import { RollingShell } from "@/components/rolling/rolling-shell";
import { Commentary } from "@/components/shared/commentary";
import { rollingPlan } from "@/lib/mock-data/rolling-plan";

export const metadata = {
  title: "NowView — Rolling Plan & Action Tracker",
};

export default function RollingPlanPage() {
  return (
    <main className="mx-auto w-full max-w-7xl space-y-5 px-4 py-6 sm:px-6 lg:px-8">
      <header className="space-y-2">
        <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
          <h1 className="text-xl font-semibold">Rolling Plan &amp; Action Tracker</h1>
          <span className="text-sm text-muted-foreground">
            FY2026 영업이익 전망 및 실행 과제
          </span>
        </div>
        <p className="text-xs text-muted-foreground tabular-nums">
          최종 갱신 {rollingPlan.updatedAt}
        </p>
      </header>

      <RollingShell plan={rollingPlan} />

      <Commentary block>
        <p className="pb-2 text-xs text-muted-foreground">
          전망 데이터는 Mock이다. 승인 과제는 세 시나리오의 것을 함께 받는다 — Mock 승인은
          브라우저에, 엔진 승인은 서버에 남으므로 엔진 모드로 승인한 과제는 새로고침해도
          유지된다. 같은 안건에 둘이 겹치면 엔진 쪽만 센다(이중 계상 방지).
        </p>
      </Commentary>
    </main>
  );
}
