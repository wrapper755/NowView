"use client";

// Recharts는 브라우저 전용 API에 의존하므로 반드시 클라이언트 컴포넌트다.

import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Rectangle,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import { formatAxisEok, formatEok, formatEokSigned } from "@/lib/format";
import { assertBridgeBalances, type BridgeStep } from "@/lib/types/cockpit";

/** 워터폴 한 칸의 렌더 좌표. `base`는 투명 받침, `span`이 실제로 보이는 막대다. */
interface BridgeRow {
  step: BridgeStep;
  label: string;
  base: number;
  span: number;
  /** 이 단계까지의 누계. 표·툴팁에 노출한다. */
  cumulative: number;
  tone: "anchor" | "favorable" | "unfavorable";
}

/**
 * anchor는 0에서 자라고, delta는 이전 누계 위에 떠 있는 막대로 바꾼다.
 * 음수 delta는 `base = 누계 + value`(즉 내려간 자리)에서 시작해 `|value|` 만큼 위로 그린다.
 */
function toRows(bridge: BridgeStep[]): BridgeRow[] {
  let cumulative = 0;

  return bridge.map((step) => {
    if (step.kind === "anchor") {
      cumulative = step.value;
      return {
        step,
        label: step.label,
        base: 0,
        span: step.value,
        cumulative,
        tone: "anchor",
      };
    }

    const base = step.value >= 0 ? cumulative : cumulative + step.value;
    cumulative += step.value;
    return {
      step,
      label: step.label,
      base,
      span: Math.abs(step.value),
      cumulative,
      tone: step.value >= 0 ? "favorable" : "unfavorable",
    };
  });
}

const TONE_COLOR: Record<BridgeRow["tone"], string> = {
  anchor: "var(--viz-anchor)",
  favorable: "var(--viz-favorable)",
  unfavorable: "var(--viz-unfavorable)",
};

/** anchor는 바닥(0)에 붙으므로 아래는 각지게, delta는 떠 있으므로 네 귀를 모두 둥글게. */
const TONE_RADIUS: Record<BridgeRow["tone"], [number, number, number, number]> = {
  anchor: [4, 4, 0, 0],
  favorable: [4, 4, 4, 4],
  unfavorable: [4, 4, 4, 4],
};

/**
 * 막대 하나를 직접 그린다.
 *
 * `<Cell radius>`는 Recharts 타입이 단일 숫자만 받아 "데이터 끝만 둥글게" 규칙을 표현할 수 없다.
 * Rectangle은 모서리별 배열을 받으므로 shape를 직접 넘긴다.
 */
function BridgeBar(props: {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  payload?: BridgeRow;
}) {
  const { x, y, width, height, payload } = props;
  if (!payload || x === undefined || y === undefined) return null;

  return (
    <Rectangle
      x={x}
      y={y}
      width={width}
      height={height}
      radius={TONE_RADIUS[payload.tone]}
      fill={TONE_COLOR[payload.tone]}
    />
  );
}

/** 축 라벨을 최대 3줄로 접는다. 한국어 라벨은 회전시키면 읽기 어렵다. */
function wrapLabel(label: string, maxChars = 8, maxLines = 3): string[] {
  const words = label.split(" ");
  const lines: string[] = [];
  let current = "";

  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length <= maxChars || !current) {
      current = candidate;
    } else {
      lines.push(current);
      current = word;
    }
  }
  if (current) lines.push(current);

  if (lines.length <= maxLines) return lines;
  // 넘치면 마지막 줄에 합쳐서 잘림(clipping) 대신 축약 표기로 처리한다.
  return [...lines.slice(0, maxLines - 1), `${lines[maxLines - 1]}…`];
}

function WrappedTick({
  x,
  y,
  payload,
}: {
  x?: number;
  y?: number;
  payload?: { value?: string };
}) {
  const lines = wrapLabel(String(payload?.value ?? ""));
  return (
    <text
      x={x}
      y={y}
      textAnchor="middle"
      fill="var(--color-muted-foreground)"
      fontSize={11}
    >
      {lines.map((line, i) => (
        <tspan key={line} x={x} dy={i === 0 ? 14 : 13}>
          {line}
        </tspan>
      ))}
    </text>
  );
}

function BridgeTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload?: BridgeRow }>;
}) {
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;

  return (
    <div className="max-w-64 rounded-lg border bg-popover p-3 text-popover-foreground shadow-md">
      <p className="text-sm font-medium">{row.label}</p>
      <p className="mt-1 text-sm tabular-nums">
        {row.step.kind === "anchor"
          ? formatEok(row.step.value)
          : formatEokSigned(row.step.value)}
        <span className="ml-2 text-xs text-muted-foreground">
          누계 {formatEok(row.cumulative)}
        </span>
      </p>
      {row.step.note ? (
        <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
          {row.step.note}
        </p>
      ) : null}
    </div>
  );
}

const LEGEND: Array<{ tone: BridgeRow["tone"]; label: string }> = [
  { tone: "anchor", label: "합계 (Target·Forecast)" },
  { tone: "unfavorable", label: "악화 요인" },
  { tone: "favorable", label: "개선 요인" },
];

export function OpBridgeChart({ bridge }: { bridge: BridgeStep[] }) {
  const [showTable, setShowTable] = useState(false);

  const rows = useMemo(() => {
    // 합계가 어긋난 워터폴은 경영 보고에서 신뢰를 잃으므로 개발 중 즉시 드러낸다.
    assertBridgeBalances(bridge);
    return toRows(bridge);
  }, [bridge]);

  const axisMax = useMemo(() => {
    const peak = Math.max(...rows.map((r) => r.base + r.span));
    return Math.ceil(peak / 100) * 100;
  }, [rows]);

  const ticks = useMemo(
    () => Array.from({ length: axisMax / 100 + 1 }, (_, i) => i * 100),
    [axisMax],
  );

  return (
    <div className="viz-root">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
          {LEGEND.map(({ tone, label }) => (
            <li
              key={tone}
              className="flex items-center gap-1.5 text-xs text-muted-foreground"
            >
              <span
                aria-hidden
                className="size-2.5 rounded-sm"
                style={{ backgroundColor: TONE_COLOR[tone] }}
              />
              {label}
            </li>
          ))}
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
        <BridgeTable rows={rows} />
      ) : (
        <>
          {/* 축 라벨 밴드(70px)를 컨테이너 높이에 포함시켜 카드 안에 스크롤이 생기지 않게 한다. */}
          <div className="mt-4 h-[360px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={rows}
                margin={{ top: 24, right: 8, bottom: 0, left: 8 }}
                barCategoryGap="22%"
              >
                <CartesianGrid
                  vertical={false}
                  stroke="var(--viz-grid)"
                  strokeWidth={1}
                />
                <XAxis
                  dataKey="label"
                  interval={0}
                  height={70}
                  tickLine={false}
                  axisLine={{ stroke: "var(--viz-baseline)" }}
                  tick={<WrappedTick />}
                />
                <YAxis
                  domain={[0, axisMax]}
                  ticks={ticks}
                  tickFormatter={formatAxisEok}
                  tickLine={false}
                  axisLine={false}
                  width={44}
                  tick={{
                    fill: "var(--color-muted-foreground)",
                    fontSize: 11,
                    style: { fontVariantNumeric: "tabular-nums" },
                  }}
                />
                <Tooltip
                  content={<BridgeTooltip />}
                  cursor={{ fill: "var(--color-muted)", opacity: 0.4 }}
                />
                {/* 투명 받침 — 막대를 누계 위로 띄우는 역할만 한다. */}
                <Bar dataKey="base" stackId="bridge" fill="transparent" />
                {/* 커스텀 shape + entrance 애니메이션을 함께 쓰면 Recharts 16/v3에서
                    막대가 height 0에 멈춘 채 렌더된다. 경영 보고 화면에 등장 모션이
                    필요하지도 않으므로 애니메이션을 끈다. */}
                <Bar
                  dataKey="span"
                  stackId="bridge"
                  maxBarSize={24}
                  isAnimationActive={false}
                  shape={<BridgeBar />}
                >
                  <LabelList
                    dataKey={(entry: unknown) => {
                      const row = entry as BridgeRow;
                      return row.step.kind === "anchor"
                        ? formatEok(row.step.value)
                        : formatEokSigned(row.step.value);
                    }}
                    position="top"
                    offset={8}
                    fill="var(--color-foreground)"
                    fontSize={11}
                    style={{ fontVariantNumeric: "tabular-nums" }}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="sr-only">
            Target 영업이익 {formatEok(rows[0].step.value)}에서 시작해 증감 요인을 거쳐
            Forecast 영업이익 {formatEok(rows[rows.length - 1].cumulative)}에 도달한다.
            단계별 수치는 &ldquo;표로 보기&rdquo; 버튼으로 확인할 수 있다.
          </p>
        </>
      )}
    </div>
  );
}

function BridgeTable({ rows }: { rows: BridgeRow[] }) {
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[32rem] text-sm">
        <caption className="sr-only">
          영업이익 Target → Forecast 브릿지 단계별 금액
        </caption>
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th scope="col" className="py-2 pr-3 font-medium">
              단계
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              구분
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">
              금액
            </th>
            <th scope="col" className="py-2 text-right font-medium">
              누계
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.step.id} className="border-b last:border-0">
              <th scope="row" className="py-2 pr-3 font-normal">
                {row.label}
              </th>
              <td className="py-2 pr-3 text-xs text-muted-foreground">
                {row.step.kind === "anchor" ? "합계" : DRIVER_LABEL[row.step.driver!]}
              </td>
              <td className="py-2 pr-3 text-right tabular-nums">
                {row.step.kind === "anchor"
                  ? formatEok(row.step.value)
                  : formatEokSigned(row.step.value)}
              </td>
              <td className="py-2 text-right tabular-nums text-muted-foreground">
                {formatEok(row.cumulative)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const DRIVER_LABEL: Record<NonNullable<BridgeStep["driver"]>, string> = {
  volume: "물량",
  price: "단가",
  cost: "원가",
  yield: "수율",
  action: "Action",
};
