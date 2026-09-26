"use client";

import { Sparkles } from "lucide-react";

import { SeverityTag } from "@/components/shared/severity";
import { cn } from "@/lib/utils";
import { formatEok, formatEokSigned, formatPpSigned } from "@/lib/format";
import type { Alternative } from "@/lib/types/workspace";
import { baselineResult } from "@/services/agent-orchestrator";

/**
 * 대안 비교표.
 *
 * 3개 대안을 여러 지표로 나란히 보는 일이라 표가 맞는 형태다 — 카드로 흩어 놓으면
 * 같은 지표끼리 눈으로 맞춰 봐야 한다. 열이 대안, 행이 지표다.
 *
 * 표시되는 수치는 **Agent 제안 기본값 기준**이다. 사람이 레버를 조정한 결과는
 * 시뮬레이터 쪽에서 따로 보여 준다 — 비교의 기준선이 흔들리면 안 된다.
 */
export function AlternativeComparison({
  alternatives,
  recommendedId,
  selectedId,
  onSelect,
  disabled,
}: {
  alternatives: Alternative[];
  recommendedId: string;
  selectedId: string;
  onSelect: (id: string) => void;
  disabled: boolean;
}) {
  const rows = [
    {
      key: "profit",
      label: "영업이익 개선",
      render: (alt: Alternative) => (
        <span className="font-medium text-foreground tabular-nums">
          {formatEokSigned(baselineResult(alt).profitImpact)}
        </span>
      ),
    },
    {
      key: "utilization",
      label: "가동률 개선",
      render: (alt: Alternative) => {
        const { utilizationImpact } = baselineResult(alt);
        return (
          <span className="tabular-nums">
            {utilizationImpact === 0 ? (
              <span className="text-muted-foreground">효과 없음</span>
            ) : (
              formatPpSigned(utilizationImpact)
            )}
          </span>
        );
      },
    },
    {
      key: "cost",
      label: "실행 비용",
      render: (alt: Alternative) => {
        const { cost } = baselineResult(alt);
        return (
          <span className="tabular-nums">
            {cost === 0 ? (
              <span className="text-muted-foreground">추가 지출 없음</span>
            ) : (
              <span className="font-medium text-foreground">{formatEok(cost)}</span>
            )}
          </span>
        );
      },
    },
    {
      key: "payback",
      label: "회수 기간",
      render: (alt: Alternative) => {
        const { paybackYears } = baselineResult(alt);
        if (paybackYears === null) return <span className="text-muted-foreground">—</span>;
        return (
          <span className="tabular-nums">
            {paybackYears === 0 ? "즉시" : `${paybackYears.toFixed(1)}년`}
          </span>
        );
      },
    },
    {
      key: "risk",
      label: "리스크",
      render: (alt: Alternative) => <SeverityTag severity={baselineResult(alt).severity} />,
    },
    {
      key: "prerequisites",
      label: "실행 조건",
      render: (alt: Alternative) => (
        <ul className="space-y-0.5">
          {alt.prerequisites.map((condition) => (
            <li key={condition} className="flex gap-1 leading-relaxed text-muted-foreground">
              <span aria-hidden>·</span>
              {condition}
            </li>
          ))}
        </ul>
      ),
    },
    { key: "leadTime", label: "실행 기간", render: (alt: Alternative) => alt.leadTime },
    { key: "owner", label: "담당", render: (alt: Alternative) => alt.owner },
  ];

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[40rem] text-xs">
        <caption className="sr-only">
          대안별 영업이익·가동률 효과와 리스크 비교 (Agent 제안 기본값 기준)
        </caption>
        <thead>
          <tr>
            <th scope="col" className="w-28 py-2 text-left font-medium text-muted-foreground">
              지표
            </th>
            {alternatives.map((alt) => {
              const isSelected = alt.id === selectedId;
              return (
                <th key={alt.id} scope="col" className="p-1.5 text-left align-top">
                  <button
                    type="button"
                    onClick={() => onSelect(alt.id)}
                    disabled={disabled}
                    aria-pressed={isSelected}
                    className={cn(
                      "w-full rounded-lg border p-2.5 text-left transition-colors",
                      isSelected
                        ? "border-foreground bg-muted"
                        : "hover:bg-muted/60 disabled:hover:bg-transparent",
                      disabled && "cursor-not-allowed opacity-70",
                    )}
                  >
                    <span className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[10px] text-muted-foreground">{alt.tag}</span>
                      {alt.id === recommendedId ? (
                        <span className="inline-flex items-center gap-1 rounded bg-background px-1 py-0.5 text-[10px] text-muted-foreground">
                          <Sparkles aria-hidden className="size-2.5" />
                          Agent 권고
                        </span>
                      ) : null}
                    </span>
                    <span className="mt-0.5 block text-sm font-semibold text-foreground">
                      {alt.name}
                    </span>
                    <span className="mt-1 block text-[11px] leading-relaxed font-normal text-muted-foreground">
                      {alt.summary}
                    </span>
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-t">
              <th scope="row" className="py-2 text-left align-top font-normal text-muted-foreground">
                {row.label}
              </th>
              {alternatives.map((alt) => (
                <td
                  key={alt.id}
                  className={cn(
                    "px-2.5 py-2 align-top text-foreground",
                    alt.id === selectedId && "bg-muted/50",
                  )}
                >
                  {row.render(alt)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
