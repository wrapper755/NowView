import { Check, CircleDashed, Clock, TriangleAlert, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { formatEokPrecise } from "@/lib/format";
import { ACTION_STATUS_LABEL, type ActionItem, type ActionStatus } from "@/lib/types/rolling";

const STATUS_ICON: Record<ActionStatus, LucideIcon> = {
  "not-started": CircleDashed,
  "in-progress": Clock,
  "at-risk": TriangleAlert,
  done: Check,
};

/**
 * 과제 상태 색.
 *
 * `at-risk`만 상태 팔레트(serious)를 쓴다 — 조치가 필요한 유일한 상태이기 때문이다.
 * 진행 중은 좋음/나쁨이 아닌 중립 진행이라 계열색을, 미착수는 무채색을 쓴다.
 * 색 단독으로 읽히지 않도록 아이콘과 한글 라벨이 항상 함께 나간다.
 */
const STATUS_COLOR: Record<ActionStatus, string> = {
  "not-started": "var(--color-muted-foreground)",
  "in-progress": "var(--viz-series-1)",
  "at-risk": "var(--viz-status-serious)",
  done: "var(--viz-status-good)",
};

/**
 * 실행 과제 목록.
 *
 * 과제마다 Forecast 반영 여부를 표시한다 — 반영된 과제와 미반영 과제를 섞어 합산하면
 * Gap이 이중으로 메워진 것처럼 보이므로, 목록 단계에서부터 구분해 둔다.
 */
export function ActionTracker({ actions }: { actions: ActionItem[] }) {
  if (actions.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">등록된 실행 과제가 없다.</p>
    );
  }

  return (
    <ul className="space-y-2.5">
      {actions.map((action) => {
        const Icon = STATUS_ICON[action.status];
        const percent =
          action.targetRecovery === 0
            ? 0
            : Math.min(100, (action.realizedRecovery / action.targetRecovery) * 100);

        return (
          <li key={action.id} className="rounded-lg border p-3">
            <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="inline-flex items-center gap-1.5 text-xs font-medium text-foreground">
                    <Icon
                      aria-hidden
                      className="size-3.5 shrink-0"
                      style={{ color: STATUS_COLOR[action.status] }}
                    />
                    {ACTION_STATUS_LABEL[action.status]}
                  </span>
                  <span className="text-sm font-medium text-foreground">
                    {action.title}
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  {action.division} · {action.owner} · 기한 {action.due}
                </p>
              </div>

              <span
                className={cn(
                  "shrink-0 rounded px-1.5 py-0.5 text-[10px]",
                  action.reflectedInForecast
                    ? "bg-muted text-muted-foreground"
                    : "border text-foreground",
                )}
              >
                {action.reflectedInForecast ? "Forecast 반영 완료" : "다음 Rolling에 반영"}
              </span>
            </div>

            <div className="mt-2.5 flex items-center gap-2.5">
              <div
                className="h-1.5 flex-1 overflow-hidden rounded-full"
                style={{ backgroundColor: "var(--viz-track)" }}
                role="meter"
                aria-valuenow={action.realizedRecovery}
                aria-valuemin={0}
                aria-valuemax={action.targetRecovery}
                aria-label={`${action.title} 회수 진척`}
              >
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${percent}%`,
                    backgroundColor: STATUS_COLOR[action.status],
                  }}
                />
              </div>
              <span className="shrink-0 text-[11px] text-muted-foreground tabular-nums">
                <span className="font-medium text-foreground">
                  {formatEokPrecise(action.realizedRecovery)}
                </span>
                {" / 목표 "}
                {formatEokPrecise(action.targetRecovery)}
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
