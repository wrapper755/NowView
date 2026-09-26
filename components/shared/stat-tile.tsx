import { ArrowDown, ArrowUp, Minus } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Stat tile — 한 개의 headline 숫자.
 *
 * 값은 비례 자간(proportional figures)을 쓴다. tabular-nums는 세로로 정렬해야 하는
 * 표·축 눈금 전용이며, 큰 단독 숫자에 쓰면 자간이 헐렁해 보인다.
 */
export function StatTile({
  label,
  value,
  delta,
  caption,
  className,
}: {
  label: string;
  value: string;
  /** 증감 표기. 방향과 "그 방향이 좋은지"를 함께 넘긴다. */
  delta?: { text: string; direction: "up" | "down" | "flat"; isGood: boolean };
  caption?: string;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-2xl leading-none font-semibold text-foreground">
        {value}
      </span>
      {delta ? <DeltaLine {...delta} /> : null}
      {caption ? (
        <span className="text-xs text-muted-foreground">{caption}</span>
      ) : null}
    </div>
  );
}

/**
 * 증감 한 줄. 방향 화살표(아이콘)와 텍스트가 항상 함께 나가므로
 * 색을 못 보는 경우에도 부호를 읽을 수 있다.
 */
export function DeltaLine({
  text,
  direction,
  isGood,
}: {
  text: string;
  direction: "up" | "down" | "flat";
  isGood: boolean;
}) {
  const Icon =
    direction === "up" ? ArrowUp : direction === "down" ? ArrowDown : Minus;
  const color =
    direction === "flat"
      ? "var(--color-muted-foreground)"
      : isGood
        ? "var(--viz-delta-good)"
        : "var(--viz-status-critical)";

  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-medium tabular-nums"
      style={{ color }}
    >
      <Icon aria-hidden className="size-3 shrink-0" />
      {text}
    </span>
  );
}
