"use client";

import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import type { KriTuning } from "@/lib/types/evolution";

/**
 * 임계치 트레이드오프 곡선.
 *
 * 감지 건수와 오탐 건수는 **같은 단위(건)** 이므로 한 축에 둔다 — 단위가 다른 두 계열을
 * 축 두 개로 겹쳐 그리면 없는 상관관계를 만들어낸다. 조기 감지일(일)은 단위가 다르므로
 * 이 차트에 넣지 않고 지표 타일로 따로 보여 준다.
 */
const DETECTION_COLOR = "var(--viz-series-1)";
const FALSE_POSITIVE_COLOR = "var(--viz-series-2)";

function BacktestTooltip({
  active,
  payload,
  unit,
}: {
  active?: boolean;
  payload?: Array<{ payload?: { threshold: number; detections: number; falsePositives: number } }>;
  unit: string;
}) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;

  return (
    <div className="rounded-lg border bg-popover p-3 text-popover-foreground shadow-md">
      <p className="text-sm font-medium tabular-nums">
        임계치 {point.threshold}
        {unit}
      </p>
      <dl className="mt-1.5 space-y-0.5 text-xs tabular-nums">
        <div className="flex justify-between gap-4">
          <dt className="text-muted-foreground">감지</dt>
          <dd>{point.detections}건</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-muted-foreground">오탐</dt>
          <dd>{point.falsePositives}건</dd>
        </div>
      </dl>
    </div>
  );
}

export function BacktestChart({
  kri,
  selectedThreshold,
}: {
  kri: KriTuning;
  selectedThreshold: number;
}) {
  const [showTable, setShowTable] = useState(false);

  return (
    <div className="viz-root">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
          <li className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span
              aria-hidden
              className="h-0.5 w-4 rounded-full"
              style={{ backgroundColor: DETECTION_COLOR }}
            />
            감지 건수
          </li>
          <li className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span
              aria-hidden
              className="h-0.5 w-4 rounded-full"
              style={{ backgroundColor: FALSE_POSITIVE_COLOR }}
            />
            오탐 건수
          </li>
        </ul>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowTable((v) => !v)}
          aria-expanded={showTable}
        >
          {showTable ? "차트 보기" : "표로 보기"}
        </Button>
      </div>

      {showTable ? (
        <BacktestTable kri={kri} selectedThreshold={selectedThreshold} />
      ) : (
        <div className="mt-4 h-[220px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={kri.backtest} margin={{ top: 12, right: 12, bottom: 4, left: 4 }}>
              <CartesianGrid vertical={false} stroke="var(--viz-grid)" strokeWidth={1} />
              <XAxis
                dataKey="threshold"
                tickLine={false}
                axisLine={{ stroke: "var(--viz-baseline)" }}
                tick={{ fill: "var(--color-muted-foreground)", fontSize: 11 }}
                tickFormatter={(v: number) => `${v}${kri.unit}`}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                width={30}
                tick={{
                  fill: "var(--color-muted-foreground)",
                  fontSize: 11,
                  style: { fontVariantNumeric: "tabular-nums" },
                }}
              />
              <Tooltip content={<BacktestTooltip unit={kri.unit} />} />

              {/* 선택 중인 임계치를 세로선으로 표시한다. 곡선 위 어디에 서 있는지가 이 차트의 요점이다. */}
              <ReferenceLine
                x={selectedThreshold}
                stroke="var(--viz-anchor)"
                strokeWidth={1.5}
                label={{
                  value: "선택",
                  position: "top",
                  fill: "var(--color-muted-foreground)",
                  fontSize: 10,
                }}
              />

              <Line
                type="monotone"
                dataKey="detections"
                stroke={DETECTION_COLOR}
                strokeWidth={2}
                dot={{ r: 3.5, fill: DETECTION_COLOR, strokeWidth: 0 }}
                activeDot={{ r: 5, strokeWidth: 2, stroke: "var(--color-card)" }}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="falsePositives"
                stroke={FALSE_POSITIVE_COLOR}
                strokeWidth={2}
                dot={{ r: 3.5, fill: FALSE_POSITIVE_COLOR, strokeWidth: 0 }}
                activeDot={{ r: 5, strokeWidth: 2, stroke: "var(--color-card)" }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function BacktestTable({
  kri,
  selectedThreshold,
}: {
  kri: KriTuning;
  selectedThreshold: number;
}) {
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[24rem] text-sm">
        <caption className="sr-only">임계치별 감지·오탐 백테스트 결과</caption>
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th scope="col" className="py-2 pr-3 font-medium">
              임계치
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">
              감지
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">
              오탐
            </th>
            <th scope="col" className="py-2 text-right font-medium">
              조기 감지
            </th>
          </tr>
        </thead>
        <tbody>
          {kri.backtest.map((point) => (
            <tr
              key={point.threshold}
              className={point.threshold === selectedThreshold ? "bg-muted/60" : undefined}
            >
              <th scope="row" className="py-2 pr-3 font-normal tabular-nums">
                {point.threshold}
                {kri.unit}
                {point.threshold === kri.currentThreshold ? (
                  <span className="ml-1.5 text-[10px] text-muted-foreground">현행</span>
                ) : null}
              </th>
              <td className="py-2 pr-3 text-right tabular-nums">{point.detections}건</td>
              <td className="py-2 pr-3 text-right tabular-nums">{point.falsePositives}건</td>
              <td className="py-2 text-right tabular-nums text-muted-foreground">
                {point.leadTimeDays > 0 ? "+" : ""}
                {point.leadTimeDays}일
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
