"use client";

import { RotateCcw, TriangleAlert } from "lucide-react";

import { SeverityTag } from "@/components/shared/severity";
import { StatTile } from "@/components/shared/stat-tile";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { formatEok, formatEokSigned, formatPpSigned } from "@/lib/format";
import type { Alternative } from "@/lib/types/workspace";
import { simulateAlternative } from "@/services/agent-orchestrator";

/**
 * 대안 시뮬레이터.
 *
 * 레버를 움직이면 손익·가동률·리스크가 즉시 다시 계산된다. Agent 제안값과 다르면
 * 그 사실을 명시한다 — 사람이 가정을 바꿨다는 것 자체가 결정 기록의 일부다.
 *
 * 잔여 Gap은 Cockpit의 영업이익 Gap에서 이 대안의 효과를 뺀 값이다. 대안 하나로 Gap이
 * 다 메워지지 않는다는 사실을 숨기지 않는 것이 이 화면의 요점이다.
 */
export function SimulatorPanel({
  alternative,
  leverValue,
  onLeverChange,
  profitGap,
  disabled,
}: {
  alternative: Alternative;
  leverValue: number;
  onLeverChange: (value: number) => void;
  /** 전사 영업이익 Gap(억원, 음수). */
  profitGap: number;
  disabled: boolean;
}) {
  const { lever } = alternative;
  const result = simulateAlternative(alternative, leverValue);
  const isAdjusted = leverValue !== lever.base;
  const remainingGap = profitGap + result.profitImpact;

  return (
    <div className="space-y-5">
      <div className="space-y-2.5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <Label htmlFor={`lever-${lever.id}`} className="text-xs text-muted-foreground">
            {lever.label}
          </Label>
          <span className="text-sm font-semibold text-foreground tabular-nums">
            {leverValue}
            {lever.unit}
            <span className="ml-2 text-[10px] font-normal text-muted-foreground">
              Agent 제안 {lever.base}
              {lever.unit}
            </span>
          </span>
        </div>

        <Slider
          id={`lever-${lever.id}`}
          min={lever.min}
          max={lever.max}
          step={lever.step}
          value={[leverValue]}
          onValueChange={([v]) => onLeverChange(v)}
          disabled={disabled}
          aria-label={`${alternative.name} ${lever.label}`}
        />

        <div className="flex items-center justify-between text-[10px] text-muted-foreground tabular-nums">
          <span>
            {lever.min}
            {lever.unit}
          </span>
          <span>
            {lever.max}
            {lever.unit}
          </span>
        </div>

        {isAdjusted ? (
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] text-muted-foreground">
              Agent 제안값에서 조정됨 — 결정 기록에 함께 남는다.
            </p>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-[11px]"
              onClick={() => onLeverChange(lever.base)}
              disabled={disabled}
            >
              <RotateCcw aria-hidden className="size-3" />
              제안값으로
            </Button>
          </div>
        ) : null}
      </div>

      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <StatTile
          label="영업이익 개선"
          value={formatEokSigned(result.profitImpact)}
          caption={`${alternative.tag} ${alternative.name}`}
        />
        <StatTile
          label="가동률 개선"
          value={
            result.utilizationImpact === 0 ? "효과 없음" : formatPpSigned(result.utilizationImpact)
          }
          caption="목표 88.0%"
        />
        <StatTile
          label="실행 비용"
          value={result.cost === 0 ? "추가 지출 없음" : formatEok(result.cost)}
          caption={
            result.paybackYears === null
              ? "회수되지 않는다"
              : result.paybackYears === 0
                ? "즉시 회수"
                : `회수 기간 ${result.paybackYears.toFixed(1)}년`
          }
        />
        <StatTile
          label="반영 후 잔여 Gap"
          value={formatEok(remainingGap)}
          delta={{
            text: formatEokSigned(result.profitImpact),
            direction: result.profitImpact > 0 ? "up" : "flat",
            isGood: result.profitImpact > 0,
          }}
          caption={`현재 ${formatEok(profitGap)}`}
        />
      </dl>

      <div className="flex items-start gap-2 rounded-lg border p-2.5">
        <TriangleAlert
          aria-hidden
          className="mt-0.5 size-3.5 shrink-0 text-muted-foreground"
        />
        <div className="min-w-0 space-y-1">
          <SeverityTag severity={result.severity} />
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            {alternative.riskNote}
          </p>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            {alternative.costNote}
          </p>
        </div>
      </div>

      {/* 실행 조건이 갖춰지지 않으면 위 수치는 성립하지 않는다 (기획안 2.1). */}
      <div className="space-y-1.5">
        <h4 className="text-xs font-medium text-muted-foreground">실행 조건</h4>
        <ul className="space-y-1">
          {alternative.prerequisites.map((condition) => (
            <li
              key={condition}
              className="flex gap-1.5 text-[11px] leading-relaxed text-foreground"
            >
              <span aria-hidden className="text-muted-foreground">
                ·
              </span>
              {condition}
            </li>
          ))}
        </ul>
        <p className="text-[10px] leading-relaxed text-muted-foreground">
          이 조건이 갖춰지지 않으면 위 효과는 실현되지 않는다.
        </p>
      </div>
    </div>
  );
}
