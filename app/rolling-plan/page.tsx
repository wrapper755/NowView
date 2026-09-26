import { RollingShell } from "@/components/rolling/rolling-shell";
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

      <p className="pb-2 text-xs text-muted-foreground">
        본 화면의 전망·과제 데이터는 Mock이다. 승인된 과제는 브라우저 메모리에만 남으므로
        새로고침하면 초기화된다.
      </p>
    </main>
  );
}
