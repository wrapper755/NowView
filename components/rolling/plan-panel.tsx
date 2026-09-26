import { ArrowRight, Clock } from "lucide-react";

import { cn } from "@/lib/utils";
import { PLAN_DIMENSION_LABEL, type PlanDimension } from "@/lib/types/rolling";
import type { PlanItemView } from "@/services/rolling-plan";

const DIMENSION_ORDER: PlanDimension[] = ["activity", "volume", "schedule", "resource"];

/**
 * 실행계획(Plan) 패널 — Target·Forecast와 나란한 세 번째 축(기획안 3.4).
 *
 * Target은 고정, Forecast는 갱신, Plan은 **조정**된다. 조정의 근거는 승인된 대응안이므로
 * 어떤 항목이 승인 때문에 바뀌었는지 명시한다.
 *
 * 승인 전에는 조정 후 값을 유효한 계획으로 보여주지 않는다 — 결정되지 않은 계획을
 * 확정된 것처럼 표시하면, 아직 실행되지 않은 Agent 산출물을 미리 노출하는 것과 같은
 * 종류의 거짓말이 된다.
 */
export function PlanPanel({ items }: { items: PlanItemView[] }) {
  const adjustedCount = items.filter((v) => v.adjusted).length;
  const awaitingCount = items.filter((v) => v.awaitingDecision).length;

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground tabular-nums">
        계획 항목 {items.length}개 중{" "}
        {adjustedCount > 0 ? (
          <span className="font-medium text-foreground">{adjustedCount}개 조정됨</span>
        ) : (
          <span className="font-medium text-foreground">
            {awaitingCount}개가 승인을 기다린다
          </span>
        )}
      </p>

      {DIMENSION_ORDER.map((dimension) => {
        const group = items.filter((v) => v.item.dimension === dimension);
        if (group.length === 0) return null;

        return (
          <section key={dimension} className="space-y-2">
            <h4 className="text-xs font-medium text-muted-foreground">
              {PLAN_DIMENSION_LABEL[dimension]}
            </h4>
            <ul className="space-y-2">
              {group.map((view) => (
                <li
                  key={view.item.id}
                  className={cn(
                    "rounded-lg border p-3",
                    view.awaitingDecision && "border-dashed",
                  )}
                >
                  <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground">
                        {view.item.label}
                      </p>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        {view.item.owner} · {view.item.period}
                      </p>
                    </div>

                    {view.adjusted ? (
                      <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        승인 반영
                      </span>
                    ) : view.awaitingDecision ? (
                      <span className="inline-flex shrink-0 items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        <Clock aria-hidden className="size-2.5" />
                        승인 시 조정 예정
                      </span>
                    ) : null}
                  </div>

                  <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
                    <span
                      className={cn(
                        "rounded border px-1.5 py-1",
                        view.adjusted
                          ? "text-muted-foreground line-through decoration-muted-foreground/40"
                          : "font-medium text-foreground",
                      )}
                    >
                      {view.item.baseline}
                    </span>

                    {view.item.drivenByDecision ? (
                      <>
                        <ArrowRight
                          aria-hidden
                          className="size-3 shrink-0 text-muted-foreground"
                        />
                        <span
                          className={cn(
                            "rounded border px-1.5 py-1",
                            view.adjusted
                              ? "font-medium text-foreground"
                              : "border-dashed text-muted-foreground",
                          )}
                        >
                          {view.item.planned}
                        </span>
                      </>
                    ) : null}
                  </div>

                  {view.item.note ? (
                    <p className="mt-1.5 text-[10px] leading-relaxed text-muted-foreground">
                      {view.item.note}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
