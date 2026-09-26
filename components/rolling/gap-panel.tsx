import { Lock } from "lucide-react";

import { StatTile } from "@/components/cockpit/stat-tile";
import { Separator } from "@/components/ui/separator";
import { formatEok, formatEokSigned, formatPercent } from "@/lib/format";
import type { GapSummary } from "@/services/rolling-plan";

/**
 * Gap 관리 패널.
 *
 * 이 화면의 주장은 하나다 — **Target은 잠겨 있고 Gap은 사라지지 않는다.**
 * 그래서 Target에 자물쇠 표시를 붙이고, 미반영 과제를 다 반영해도 남는 Gap을 함께 보여 준다.
 */
export function GapPanel({ summary }: { summary: GapSummary }) {
  const hasPending = summary.pendingRecovery > 0;

  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <dt className="flex items-center gap-1 text-xs text-muted-foreground">
            <Lock aria-hidden className="size-3" />
            Target (고정)
          </dt>
          <dd className="text-2xl leading-none font-semibold text-foreground">
            {formatEok(summary.target)}
          </dd>
          <dd className="text-xs text-muted-foreground">임의로 변경하지 않는다</dd>
        </div>

        <StatTile
          label="현재 Forecast"
          value={formatEok(summary.forecast)}
          delta={{
            text: formatEokSigned(summary.gap),
            direction: summary.gap >= 0 ? "up" : "down",
            isGood: summary.gap >= 0,
          }}
          caption="잔여 Gap"
        />
      </dl>

      <Separator />

      <dl className="space-y-2.5 text-xs">
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-muted-foreground">Forecast 반영 완료 과제</dt>
          <dd className="text-right text-foreground tabular-nums">
            {formatEok(summary.reflectedRecovery)}
            <span className="ml-1.5 text-[11px] text-muted-foreground">
              회수 {formatPercent(summary.realizationRate, 0)}
            </span>
          </dd>
        </div>

        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-muted-foreground">다음 Rolling 반영 예정</dt>
          <dd className="text-right text-foreground tabular-nums">
            {hasPending ? formatEokSigned(summary.pendingRecovery) : "없음"}
          </dd>
        </div>
      </dl>

      {hasPending ? (
        <div className="rounded-lg border p-2.5">
          <p className="text-xs text-foreground tabular-nums">
            반영 시 Forecast {formatEok(summary.projectedForecast)}
            <span className="mx-1.5 text-muted-foreground/60">·</span>
            <span className="text-muted-foreground">
              잔여 Gap {formatEokSigned(summary.projectedGap)}
            </span>
          </p>
          <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
            승인된 과제를 모두 반영해도 Gap은 남는다. 추가 대응이 필요하다는 뜻이며, 이를
            숨기지 않는 것이 Rolling 방식의 목적이다.
          </p>
        </div>
      ) : (
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          현재 잔여 Gap {formatEokSigned(summary.gap)}에 대응할 신규 승인 과제가 없다.
          Management Review에서 대안을 결정하면 여기에 반영 예정으로 잡힌다.
        </p>
      )}
    </div>
  );
}
