"use client";

import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import { formatKrw, formatMonth, formatWonExact } from "@/lib/sc01/format";
import type { Dashboard } from "@/lib/sc01/types";

/**
 * 월별 공장관리손익 — Target·승인 전망 F01·(계산 후) 검토 전망 F02.
 *
 * * Target은 기준선이라 중립색(anchor)이다. **계열색은 버전에 고정 배정한다**(4.4):
 *   F01 = series-1, F02 = series-2. 순서·유무에 따라 다시 칠하지 않는다.
 * * 1~5월 확정실적·6월 누계+잔여·7월 이후 전망을 배경으로 가른다(UI01 "기간별 추이").
 * * 값이 툴팁에만 갇히지 않게 표 뷰를 둔다.
 */
const COLOR: Record<string, string> = {
  T01: "var(--viz-anchor)",
  F01: "var(--viz-series-1)",
  F02: "var(--viz-series-2)",
};
const LABEL: Record<string, string> = { T01: "Target T01", F01: "승인 전망 F01", F02: "검토 전망 F02" };
const BASIS: Record<string, string> = {
  ACTUAL: "확정실적",
  ACTUAL_PLUS_FORECAST: "6/15 누계+잔여",
  FORECAST: "전망",
};
const EOK = 100_000_000;

export function ProfitTrendChart({ dashboard }: { dashboard: Dashboard }) {
  const [showTable, setShowTable] = useState(false);
  const versions = dashboard.versions;
  const data = dashboard.trend.map((t) => ({
    month: formatMonth(t.month),
    basis: t.basis,
    ...Object.fromEntries(versions.map((v) => [v, Number(t[v]) / EOK])),
  }));

  return (
    <div className="viz-root">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
          {versions.map((v) => (
            <li key={v} className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span aria-hidden className="h-0.5 w-4 rounded-full" style={{ backgroundColor: COLOR[v] }} />
              {LABEL[v] ?? v}
            </li>
          ))}
        </ul>
        <Button variant="outline" size="sm" onClick={() => setShowTable((s) => !s)} aria-expanded={showTable}>
          {showTable ? "차트 보기" : "표로 보기"}
        </Button>
      </div>

      {showTable ? (
        <div className="mt-4 overflow-x-auto">
          {/* sr-only(position:absolute) caption은 스크롤 상자를 벗어나 좁은 화면의 문서 폭을 늘린다
              — 375px에서 555px로 늘었다. 표 이름은 aria-label로 준다. */}
          <table aria-label="월별 공장관리손익" className="w-full min-w-[32rem] text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th scope="col" className="py-2 pr-3 font-medium">월</th>
                <th scope="col" className="py-2 pr-3 font-medium">성격</th>
                {versions.map((v) => (
                  <th key={v} scope="col" className="py-2 pr-3 text-right font-medium">{LABEL[v] ?? v}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {dashboard.trend.map((t) => (
                <tr key={t.month} className="border-b last:border-0">
                  <th scope="row" className="text-left py-1.5 pr-3 font-normal">{formatMonth(t.month)}</th>
                  <td className="py-1.5 pr-3 text-xs text-muted-foreground">{BASIS[t.basis]}</td>
                  {versions.map((v) => (
                    <td key={v} className="py-1.5 pr-3 text-right tabular-nums" title={formatWonExact(t[v])}>
                      {formatKrw(t[v])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="mt-4 h-[260px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 12, right: 16, bottom: 4, left: 8 }}>
              <CartesianGrid vertical={false} stroke="var(--viz-grid)" />
              {/* 확정실적 구간 — 값이 아니라 기간의 성격이다. 아주 옅게 깐다. */}
              <ReferenceArea x1="1월" x2="5월" fill="var(--viz-track)" fillOpacity={0.35} ifOverflow="hidden" />
              <XAxis
                dataKey="month"
                tickLine={false}
                axisLine={{ stroke: "var(--viz-baseline)" }}
                tick={{ fill: "var(--color-muted-foreground)", fontSize: 11 }}
              />
              <YAxis
                domain={["auto", "auto"]}
                tickFormatter={(v: number) => `${v.toFixed(1)}억`}
                tickLine={false}
                axisLine={false}
                width={48}
                tick={{ fill: "var(--color-muted-foreground)", fontSize: 11 }}
              />
              <Tooltip
                formatter={(value: unknown, name: unknown) => [
                  typeof value === "number" ? `${value.toFixed(2)}억` : String(value),
                  LABEL[String(name)] ?? String(name),
                ]}
                labelFormatter={(label: unknown, payload: unknown) => {
                  const p = (payload as { payload?: { basis?: string } }[] | undefined)?.[0]?.payload;
                  return `${String(label)} · ${p?.basis ? BASIS[p.basis] : ""}`;
                }}
                contentStyle={{
                  background: "var(--color-popover)",
                  border: "1px solid var(--color-border)",
                  borderRadius: 8,
                  fontSize: 12,
                }}
              />
              {versions.map((v) => (
                <Line
                  key={v}
                  type="monotone"
                  dataKey={v}
                  stroke={COLOR[v]}
                  strokeWidth={2}
                  strokeDasharray={v === "T01" ? "4 3" : undefined}
                  dot={{ r: 3, fill: COLOR[v], strokeWidth: 0 }}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <p className="mt-2 text-[11px] text-muted-foreground">
        음영 = 1~5월 확정실적. 6월은 6/15 누계 + 잔여 전망, 7월 이후는 전망이다.
      </p>
    </div>
  );
}
