"use client";

import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import { formatAxisEok, formatEok, formatEokSigned } from "@/lib/format";
import type { QuarterPoint } from "@/lib/types/rolling";

/**
 * 분기별 Target vs Forecast.
 *
 * "기준선 대비 편차"를 읽는 차트이므로 Target은 중립색 기준선으로, Forecast만 계열색으로
 * 그린다 — 둘 다 화려하게 칠하면 무엇이 기준인지 사라진다.
 *
 * 값 라벨은 끝점에만 붙이고 나머지는 축과 표가 담당한다.
 */
const TARGET_COLOR = "var(--viz-anchor)";
const FORECAST_COLOR = "var(--viz-series-1)";

function TrendTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload?: QuarterPoint }>;
}) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;

  const gap = point.forecast - point.target;
  return (
    <div className="rounded-lg border bg-popover p-3 text-popover-foreground shadow-md">
      <p className="text-sm font-medium">
        {point.quarter}
        <span className="ml-2 text-[10px] font-normal text-muted-foreground">
          {point.closed ? "마감 확정" : "전망"}
        </span>
      </p>
      <dl className="mt-1.5 space-y-0.5 text-xs tabular-nums">
        <div className="flex justify-between gap-4">
          <dt className="text-muted-foreground">Target</dt>
          <dd>{formatEok(point.target)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-muted-foreground">Forecast</dt>
          <dd>{formatEok(point.forecast)}</dd>
        </div>
        <div className="flex justify-between gap-4 border-t pt-0.5">
          <dt className="text-muted-foreground">Gap</dt>
          <dd>{formatEokSigned(gap)}</dd>
        </div>
      </dl>
    </div>
  );
}

export function ForecastTrendChart({ quarters }: { quarters: QuarterPoint[] }) {
  const [showTable, setShowTable] = useState(false);

  const axisMax = useMemo(() => {
    const peak = Math.max(...quarters.flatMap((q) => [q.target, q.forecast]));
    return Math.ceil(peak / 20) * 20;
  }, [quarters]);

  return (
    <div className="viz-root">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
          <li className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span
              aria-hidden
              className="h-0.5 w-4 rounded-full"
              style={{ backgroundColor: TARGET_COLOR }}
            />
            Target (고정)
          </li>
          <li className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span
              aria-hidden
              className="h-0.5 w-4 rounded-full"
              style={{ backgroundColor: FORECAST_COLOR }}
            />
            Forecast (Rolling 갱신)
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
        <QuarterTable quarters={quarters} />
      ) : (
        <div className="mt-4 h-[260px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={quarters}
              margin={{ top: 20, right: 40, bottom: 4, left: 8 }}
            >
              <CartesianGrid vertical={false} stroke="var(--viz-grid)" strokeWidth={1} />
              <XAxis
                dataKey="quarter"
                tickLine={false}
                axisLine={{ stroke: "var(--viz-baseline)" }}
                tick={{ fill: "var(--color-muted-foreground)", fontSize: 11 }}
              />
              <YAxis
                domain={[0, axisMax]}
                tickFormatter={formatAxisEok}
                tickLine={false}
                axisLine={false}
                width={40}
                tick={{
                  fill: "var(--color-muted-foreground)",
                  fontSize: 11,
                  style: { fontVariantNumeric: "tabular-nums" },
                }}
              />
              <Tooltip content={<TrendTooltip />} />
              <Line
                type="monotone"
                dataKey="target"
                stroke={TARGET_COLOR}
                strokeWidth={2}
                dot={{ r: 4, fill: TARGET_COLOR, strokeWidth: 0 }}
                activeDot={{ r: 5, strokeWidth: 2, stroke: "var(--color-card)" }}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="forecast"
                stroke={FORECAST_COLOR}
                strokeWidth={2}
                dot={{ r: 4, fill: FORECAST_COLOR, strokeWidth: 0 }}
                activeDot={{ r: 5, strokeWidth: 2, stroke: "var(--color-card)" }}
                isAnimationActive={false}
                // Recharts의 LabelFormatter는 number를 보장하지 않으므로 좁혀서 쓴다.
                label={{
                  position: "top",
                  offset: 10,
                  fill: "var(--color-foreground)",
                  fontSize: 11,
                  formatter: (value: unknown) =>
                    typeof value === "number" ? formatAxisEok(value) : "",
                }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function QuarterTable({ quarters }: { quarters: QuarterPoint[] }) {
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[26rem] text-sm">
        <caption className="sr-only">분기별 Target·Forecast·Gap</caption>
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th scope="col" className="py-2 pr-3 font-medium">
              분기
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">
              Target
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">
              Forecast
            </th>
            <th scope="col" className="py-2 text-right font-medium">
              Gap
            </th>
          </tr>
        </thead>
        <tbody>
          {quarters.map((q) => (
            <tr key={q.quarter} className="border-b last:border-0">
              <th scope="row" className="py-2 pr-3 font-normal">
                {q.quarter}
                <span className="ml-1.5 text-[10px] text-muted-foreground">
                  {q.closed ? "마감" : "전망"}
                </span>
              </th>
              <td className="py-2 pr-3 text-right tabular-nums">{formatEok(q.target)}</td>
              <td className="py-2 pr-3 text-right tabular-nums">{formatEok(q.forecast)}</td>
              <td className="py-2 text-right tabular-nums text-muted-foreground">
                {formatEokSigned(q.forecast - q.target)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
