"use client";

import { Sparkles, TriangleAlert } from "lucide-react";

import { SeverityTag } from "@/components/shared/severity";
import { StatTile } from "@/components/shared/stat-tile";
import { BacktestChart } from "@/components/evolution/backtest-chart";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { formatPercent } from "@/lib/format";
import { useDemoController } from "@/lib/store/demo-controller";
import type { KriTuning } from "@/lib/types/evolution";
import { formatLeadTime, tuningOutcome, tuningRange } from "@/services/evolution-lab";

/**
 * KRI 임계치 튜닝.
 *
 * 임계치를 조이면 더 빨리 잡히지만 오탐이 늘어난다 — 이 트레이드오프를 숨기지 않는 것이
 * 이 패널의 전부다. 조기 감지일만 보여 주고 오탐을 감추면 임계치는 끝없이 올라간다.
 *
 * 임계치는 로컬 상태가 아니라 데모 스토어가 소유한다. 시나리오 장면이 값을 지정해
 * "87%로 올리면 이렇게 된다"를 말로만 하지 않고 실제로 보여 줄 수 있어야 하기 때문이다.
 */
export function KriTuningPanel({ kri }: { kri: KriTuning }) {
  const threshold = useDemoController(
    (s) => s.kriThresholds[kri.id] ?? kri.currentThreshold,
  );
  const setKriThreshold = useDemoController((s) => s.setKriThreshold);
  const setThreshold = (value: number) => setKriThreshold(kri.id, value);
  const { min, max } = tuningRange(kri);
  const outcome = tuningOutcome(kri, threshold);

  return (
    <div className="space-y-5">
      <div className="flex items-start gap-2 rounded-lg border p-2.5">
        <TriangleAlert
          aria-hidden
          className="mt-0.5 size-3.5 shrink-0 text-muted-foreground"
        />
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          {kri.observedIssue}
        </p>
      </div>

      <div className="space-y-2.5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <Label htmlFor={`kri-${kri.id}`} className="text-xs text-muted-foreground">
            감지 임계치 ({kri.detectBelow ? "미만 시 감지" : "초과 시 감지"})
          </Label>
          <span className="text-sm font-semibold text-foreground tabular-nums">
            {threshold}
            {kri.unit}
            <span className="ml-2 text-[10px] font-normal text-muted-foreground">
              현행 {kri.currentThreshold}
              {kri.unit}
            </span>
          </span>
        </div>

        <Slider
          id={`kri-${kri.id}`}
          min={min}
          max={max}
          step={kri.step}
          value={[threshold]}
          onValueChange={([v]) => setThreshold(v)}
          aria-label={`${kri.label} 감지 임계치`}
        />

        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-[10px] text-muted-foreground tabular-nums">
            {min}
            {kri.unit} ~ {max}
            {kri.unit}
          </span>
          <div className="flex items-center gap-1.5">
            {threshold !== kri.recommendedThreshold ? (
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-[11px]"
                onClick={() => setThreshold(kri.recommendedThreshold)}
              >
                <Sparkles aria-hidden className="size-3" />
                Agent 권고 {kri.recommendedThreshold}
                {kri.unit}
              </Button>
            ) : (
              <span className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                <Sparkles aria-hidden className="size-2.5" />
                Agent 권고값
              </span>
            )}
            {threshold !== kri.currentThreshold ? (
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-[11px]"
                onClick={() => setThreshold(kri.currentThreshold)}
              >
                현행값으로
              </Button>
            ) : null}
          </div>
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <StatTile
          label="감지 건수"
          value={`${outcome.detections}건`}
          delta={
            outcome.detectionDelta === 0
              ? undefined
              : {
                  text: `${outcome.detectionDelta > 0 ? "+" : ""}${outcome.detectionDelta}건`,
                  direction: outcome.detectionDelta > 0 ? "up" : "down",
                  isGood: outcome.detectionDelta > 0,
                }
          }
          caption="현행 대비"
        />
        <StatTile
          label="오탐 건수"
          value={`${outcome.falsePositives}건`}
          delta={
            outcome.falsePositiveDelta === 0
              ? undefined
              : {
                  text: `${outcome.falsePositiveDelta > 0 ? "+" : ""}${outcome.falsePositiveDelta}건`,
                  direction: outcome.falsePositiveDelta > 0 ? "up" : "down",
                  // 오탐은 늘어나는 쪽이 나쁘다.
                  isGood: outcome.falsePositiveDelta < 0,
                }
          }
          caption={`오탐 비율 ${formatPercent(outcome.falsePositiveRate, 0)}`}
        />
        <StatTile
          label="감지 시점"
          value={formatLeadTime(outcome.leadTimeDays)}
          caption="현행 임계치 기준"
        />
      </dl>

      <div className="flex items-center gap-2 rounded-lg border p-2.5">
        <SeverityTag severity={outcome.severity} />
        <p className="min-w-0 text-[11px] leading-relaxed text-muted-foreground">
          오탐 비율 {formatPercent(outcome.falsePositiveRate, 0)} — 임계치를 조일수록 더 빨리
          잡히지만 헛울림도 함께 늘어난다.
        </p>
      </div>

      <BacktestChart kri={kri} selectedThreshold={threshold} />
    </div>
  );
}
