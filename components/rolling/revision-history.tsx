import { formatEok, formatEokSigned } from "@/lib/format";
import type { ForecastRevision } from "@/lib/types/rolling";

/**
 * Rolling 갱신 이력.
 *
 * 이 목록의 요점은 **Target 열이 없다는 것**이다. 회차마다 움직이는 것은 Forecast뿐이고,
 * 목표는 고정되어 있으므로 회차 단위로 들고 다닐 이유가 없다.
 */
export function RevisionHistory({
  revisions,
  target,
}: {
  revisions: ForecastRevision[];
  /** 고정 Target. 각 회차의 Gap을 계산하는 데만 쓴다. */
  target: number;
}) {
  // 최신 회차가 위로 오도록 뒤집는다. 원본 순서(과거→최신)는 건드리지 않는다.
  const ordered = [...revisions].reverse();

  return (
    <ol className="space-y-0">
      {ordered.map((revision, index) => {
        const previous = ordered[index + 1];
        const delta = previous ? revision.forecast - previous.forecast : null;
        const isLatest = index === 0;

        return (
          <li key={revision.id} className="flex gap-3 border-b py-3 last:border-0">
            <div className="flex flex-col items-center pt-1">
              <span
                aria-hidden
                className="size-1.5 shrink-0 rounded-full"
                style={{
                  backgroundColor: isLatest
                    ? "var(--viz-series-1)"
                    : "var(--color-muted-foreground)",
                }}
              />
            </div>

            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="text-sm font-medium text-foreground">{revision.label}</span>
                <span className="text-[10px] text-muted-foreground tabular-nums">
                  {revision.date}
                </span>
                {isLatest ? (
                  <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                    최신
                  </span>
                ) : null}
              </div>

              <p className="mt-1 text-xs text-foreground tabular-nums">
                Forecast {formatEok(revision.forecast)}
                {delta !== null ? (
                  <span className="ml-1.5 text-muted-foreground">
                    ({formatEokSigned(delta)})
                  </span>
                ) : null}
                <span className="mx-1.5 text-muted-foreground/60">·</span>
                <span className="text-muted-foreground">
                  잔여 Gap {formatEokSigned(revision.forecast - target)}
                </span>
              </p>

              <ul className="mt-1.5 space-y-0.5">
                {revision.drivers.map((driver) => (
                  <li
                    key={driver}
                    className="flex gap-1.5 text-[11px] leading-relaxed text-muted-foreground"
                  >
                    <span aria-hidden>·</span>
                    {driver}
                  </li>
                ))}
              </ul>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
