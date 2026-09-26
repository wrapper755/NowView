import { Bot, Check, Hourglass, Minus, type LucideIcon } from "lucide-react";

import {
  ConfidenceTag,
  DataSourceList,
  EscalationCard,
} from "@/components/shared/data-source";
import { cn } from "@/lib/utils";
import type { AgentActivity, AgentActivityStatus } from "@/services/agent-orchestrator";

const STATUS_LABEL: Record<AgentActivityStatus, string> = {
  done: "완료",
  running: "실행 중",
  queued: "대기",
  skipped: "미실행",
};

const STATUS_ICON: Record<AgentActivityStatus, LucideIcon> = {
  done: Check,
  running: Bot,
  queued: Minus,
  skipped: Minus,
};

const STATUS_COLOR: Record<AgentActivityStatus, string> = {
  done: "var(--viz-status-good)",
  running: "var(--viz-series-1)",
  queued: "var(--color-muted-foreground)",
  skipped: "var(--color-muted-foreground)",
};

/**
 * Agent 실행 현황.
 *
 * 산출물과 함께 **참조한 데이터 소스**를 항상 같이 보여준다 — 최종 판단은 사람이 지므로
 * (CLAUDE.md 1장 Human-in-the-Loop) 근거를 되짚을 수 없는 분석 결과는 쓸모가 없다.
 */
export function AgentActivityPanel({ activities }: { activities: AgentActivity[] }) {
  return (
    <ol className="space-y-3">
      {activities.map((activity) => {
        const Icon = STATUS_ICON[activity.status];
        const dimmed = activity.status === "queued" || activity.status === "skipped";

        return (
          <li
            key={activity.nodeId}
            className={cn("rounded-lg border p-3", dimmed && "opacity-60")}
          >
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="inline-flex items-center gap-1.5 text-xs font-medium text-foreground">
                <Icon
                  aria-hidden
                  className="size-3.5 shrink-0"
                  style={{ color: STATUS_COLOR[activity.status] }}
                />
                {STATUS_LABEL[activity.status]}
              </span>
              <span className="text-sm font-medium text-foreground">
                {activity.agent.name}
              </span>
            </div>

            <p className="mt-1 text-[11px] text-muted-foreground">
              {activity.agent.role} · {activity.agent.capability}
            </p>

            {activity.run ? (
              <>
                <p className="mt-2 text-xs leading-relaxed text-foreground">
                  {activity.run.output}
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="text-[10px] text-muted-foreground tabular-nums">
                    {activity.run.duration}
                  </span>
                  <ConfidenceTag
                    confidence={activity.run.confidence}
                    note={activity.run.confidenceNote}
                  />
                </div>
                <div className="mt-1.5">
                  <DataSourceList sources={activity.run.sources} />
                </div>
                {activity.run.escalations?.length ? (
                  <ul className="mt-2 space-y-2">
                    {activity.run.escalations.map((escalation) => (
                      <EscalationCard key={escalation.id} escalation={escalation} />
                    ))}
                  </ul>
                ) : null}
              </>
            ) : activity.status === "running" ? (
              <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                <Hourglass aria-hidden className="size-3" />
                {activity.nodeLabel} 수행 중 — 산출물 확정 전
              </p>
            ) : (
              <p className="mt-2 text-xs text-muted-foreground">
                {activity.nodeLabel} 단계에서 실행 예정
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}
