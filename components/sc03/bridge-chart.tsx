"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Button } from "@/components/ui/button";
import { formatWonExact } from "@/lib/sc01/format";
import { formatMillion } from "@/lib/sc03/format";
import type { Period } from "@/lib/sc03/types";

/**
 * 손익 브리지(U32 중앙) — Target → 기존 부족 → F01 → 장면 1 물량 → 장면 2 승인 단가 → 통합 전망.
 *
 * * 합계 막대는 중립(anchor), 변동 막대는 극성색이다 — 악화는 unfavorable, 개선은 favorable(4.4: 역할을 섞지 않는다).
 *   색 단독으로 말하지 않는다 — 막대 위에 부호 있는 값을 쓴다.
 * * **축은 0에서 시작하지 않는다** — 33억대에서 1,400만원 변동을 보이려면 잘라야 한다. 자른 것을 축 아래에 적는다.
 * * 커스텀 shape를 쓰지 않는다(애니메이션과 같이 쓰면 높이 0에 멈춘다 — CLAUDE.md 함정). 애니메이션은 끈다.
 * * 표 뷰를 둔다 — 값이 툴팁에만 갇히지 않게.
 * * 12개월은 Target이 미설정이라 F01부터 시작한다(부족은 미산정).
 */
const MN = 1_000_000;

interface Step {
  key: string;
  label: string;
  kind: "total" | "delta";
  value: string;
  from: number;
  to: number;
}

function steps(p: Period): Step[] {
  const n = (v: string | null | undefined) => Number(v ?? 0) / MN;
  const out: Step[] = [];
  if (p.target) {
    out.push({ key: "target", label: "Target", kind: "total", value: p.target, from: 0, to: n(p.target) });
    out.push({ key: "gap", label: "기존 부족", kind: "delta", value: String(-Number(p.existing_gap)), from: n(p.target), to: n(p.f01) });
  }
  const afterVolume = n(p.f01) + n(p.volume_effect);
  out.push({ key: "f01", label: "사건 전 F01", kind: "total", value: p.f01!, from: 0, to: n(p.f01) });
  out.push({ key: "volume", label: "물량(장면 1)", kind: "delta", value: p.volume_effect!, from: n(p.f01), to: afterVolume });
  out.push({ key: "cost", label: "승인 단가(장면 2)", kind: "delta", value: p.cost_effect!, from: afterVolume, to: n(p.combined) });
  out.push({ key: "combined", label: "통합 전망", kind: "total", value: p.combined!, from: 0, to: n(p.combined) });
  return out;
}

export function BridgeChart({ period }: { period: Period }) {
  const [showTable, setShowTable] = useState(false);
  if (!period.computable) return <p className="text-sm text-muted-foreground">미산출 — {period.reason}</p>;
  const all = steps(period);
  const tops = all.map((s) => Math.max(s.from, s.to)).filter((v) => v > 0);
  const lows = all.filter((s) => s.kind === "delta").map((s) => Math.min(s.from, s.to));
  // 축 바닥 — 가장 낮은 변동보다 조금 아래, 백만원 50 단위로 내림
  const floor = Math.floor((Math.min(...lows) - (Math.max(...tops) - Math.min(...lows)) * 0.6) / 50) * 50;
  const data = all.map((s) => {
    const lo = s.kind === "total" ? floor : Math.min(s.from, s.to);
    const hi = s.kind === "total" ? s.to : Math.max(s.from, s.to);
    return { ...s, base: lo - floor, size: Math.max(hi - lo, 0.0001), shown: formatMillion(s.value) };
  });
  const color = (s: Step) =>
    s.kind === "total" ? "var(--viz-anchor)" : Number(s.value) < 0 ? "var(--viz-unfavorable)" : "var(--viz-favorable)";

  return (
    <div className="viz-root">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
          <li className="flex items-center gap-1.5">
            <span aria-hidden className="size-2.5 rounded-sm" style={{ backgroundColor: "var(--viz-anchor)" }} />
            합계
          </li>
          <li className="flex items-center gap-1.5">
            <span aria-hidden className="size-2.5 rounded-sm" style={{ backgroundColor: "var(--viz-unfavorable)" }} />
            악화(−)
          </li>
        </ul>
        <Button variant="outline" size="sm" onClick={() => setShowTable((s) => !s)} aria-expanded={showTable}>
          {showTable ? "차트 보기" : "표로 보기"}
        </Button>
      </div>
      {showTable ? (
        <div className="mt-4 overflow-x-auto">
          <table aria-label={`손익 브리지 ${period.label}`} className="w-full min-w-[28rem] text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th scope="col" className="py-2 pr-3 font-medium">단계</th>
                <th scope="col" className="py-2 pr-3 text-right font-medium">백만원</th>
                <th scope="col" className="py-2 pr-3 text-right font-medium">원</th>
              </tr>
            </thead>
            <tbody>
              {all.map((s) => (
                <tr key={s.key} className="border-b last:border-0">
                  <th scope="row" className="py-1.5 pr-3 text-left font-normal">{s.label}</th>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{formatMillion(s.value)}</td>
                  <td className="py-1.5 pr-3 text-right text-xs tabular-nums text-muted-foreground">{formatWonExact(s.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="mt-4 h-[260px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 20, right: 8, bottom: 4, left: 8 }}>
              <CartesianGrid vertical={false} stroke="var(--viz-grid)" />
              <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: "var(--viz-baseline)" }} interval={0} tick={{ fill: "var(--color-muted-foreground)", fontSize: 11 }} />
              <YAxis
                tickFormatter={(v: number) => (v + floor).toLocaleString("ko-KR", { maximumFractionDigits: 0 })}
                tickLine={false}
                axisLine={false}
                width={52}
                tick={{ fill: "var(--color-muted-foreground)", fontSize: 11 }}
              />
              <Tooltip
                cursor={{ fill: "var(--viz-track)", fillOpacity: 0.3 }}
                formatter={(_v: unknown, _n: unknown, item: unknown) => {
                  const p = (item as { payload?: Step }).payload;
                  return [p ? `${formatMillion(p.value)} 백만원 (${formatWonExact(p.value)})` : "", ""];
                }}
                contentStyle={{ background: "var(--color-popover)", border: "1px solid var(--color-border)", borderRadius: 8, fontSize: 12 }}
              />
              <Bar dataKey="base" stackId="b" fill="transparent" isAnimationActive={false} />
              <Bar dataKey="size" stackId="b" isAnimationActive={false} radius={[3, 3, 0, 0]}>
                {data.map((d) => (
                  <Cell key={d.key} fill={color(d)} />
                ))}
                <LabelList dataKey="shown" position="top" style={{ fill: "var(--color-foreground)", fontSize: 11 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      <p className="mt-2 text-[11px] text-muted-foreground">
        단위 백만원 · 세로축은 {floor.toLocaleString("ko-KR")}부터 — 변동을 보이려고 잘랐다. 공장관리손익은 전사 영업이익이 아니다.
      </p>
    </div>
  );
}
