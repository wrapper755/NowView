import { Check, CircleAlert, CircleSlash, ShieldOff, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  CONTROL_KIND_LABEL,
  CONTROL_STATUS_LABEL,
  type Control,
  type ControlStatus,
} from "@/lib/types/framework";
import type { FrameworkChain } from "@/services/framework";

const CONTROL_STATUS_ICON: Record<ControlStatus, LucideIcon> = {
  effective: Check,
  exception: CircleAlert,
  "not-run": CircleSlash,
};

/**
 * 통제 상태 색. `effective`만 좋음이고 나머지는 조치가 필요한 상태다.
 * 색 단독으로 읽히지 않도록 아이콘과 한글 라벨이 항상 함께 나간다.
 */
const CONTROL_STATUS_COLOR: Record<ControlStatus, string> = {
  effective: "var(--viz-status-good)",
  exception: "var(--viz-status-serious)",
  "not-run": "var(--viz-status-critical)",
};

/** 지표 값 + 목표/임계 병기. 기준 없이 값만 보여 주면 판단할 수 없다. */
function Measure({
  value,
  reference,
  unit,
  referenceLabel,
  breached,
}: {
  value: number;
  reference: number;
  unit: string;
  referenceLabel: string;
  breached?: boolean;
}) {
  /**
   * 값과 기준을 각각 **줄바꿈 불가 단위**로 묶는다.
   *
   * 단위에 공백이 있으면("% QoQ") 그 사이에서 줄이 끊겨 `임계 5%` / `QoQ`처럼 갈라진다.
   * 오류처럼 읽히므로 각 덩어리는 통째로 넘기고, 값과 기준 사이에서만 줄을 바꾼다.
   */
  return (
    <span className="tabular-nums">
      <span
        className="font-medium whitespace-nowrap text-foreground"
        style={breached ? { color: "var(--viz-status-critical)" } : undefined}
      >
        {value}
        {unit}
      </span>{" "}
      <span className="text-[10px] whitespace-nowrap text-muted-foreground">
        {referenceLabel} {reference}
        {unit}
      </span>
    </span>
  );
}

function ControlChip({ control }: { control: Control }) {
  const Icon = CONTROL_STATUS_ICON[control.status];
  return (
    <span
      className="inline-flex max-w-full items-center gap-1 rounded border px-1.5 py-0.5 text-[10px]"
      title={control.note ?? CONTROL_STATUS_LABEL[control.status]}
    >
      <Icon
        aria-hidden
        className="size-2.5 shrink-0"
        style={{ color: CONTROL_STATUS_COLOR[control.status] }}
      />
      <span className="truncate text-foreground">{control.name}</span>
      <span className="shrink-0 text-muted-foreground">
        {CONTROL_KIND_LABEL[control.kind]}
      </span>
    </span>
  );
}

/**
 * Value Driver → KPI → KRI → Control 연결표.
 *
 * 기획안 1.1의 "무엇을 보고 어떻게 판단할지에 대한 공통 기준"이 이 표다. 지표를 나열하는
 * 것이 목적이 아니라 **연결이 어디서 끊기는지**를 보이는 것이 목적이다 —
 * 임계치를 벗어났는데 예방 통제가 없거나, 통제가 예외·미수행이면 그 자리가 구멍이다.
 *
 * 항목이 여럿이고 축이 넷이라 표가 맞는 형태다. 카드로 흩으면 같은 열끼리 비교할 수 없다.
 */
export function FrameworkChainTable({ chains }: { chains: FrameworkChain[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[52rem] text-xs">
        <caption className="sr-only">
          Value Driver·KPI·KRI·Control 연결과 이탈 현황
        </caption>
        <thead>
          <tr className="border-b text-left text-[10px] text-muted-foreground">
            <th scope="col" className="py-2 pr-3 font-medium">
              Value Driver
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              KPI <span className="font-normal">(결과·후행)</span>
            </th>
            <th scope="col" className="py-2 pr-3 font-medium">
              KRI <span className="font-normal">(위험·선행)</span>
            </th>
            <th scope="col" className="py-2 font-medium">
              Control <span className="font-normal">(통제 활동)</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {chains.map((chain, index) => {
            // 같은 Value Driver·KPI가 이어지면 라벨을 반복하지 않는다 (읽는 축이 흐려진다).
            const previous = chains[index - 1];
            const sameDriver = previous?.driver.id === chain.driver.id;
            const sameKpi = previous?.kpi.id === chain.kpi.id;

            return (
              <tr key={chain.kri.id} className={cn("border-b last:border-0", !sameDriver && "border-t")}>
                <td className="py-2.5 pr-3 align-top">
                  {sameDriver ? null : (
                    <>
                      <span className="block font-medium text-foreground">
                        {chain.driver.name}
                      </span>
                      <span className="mt-0.5 block text-[10px] leading-relaxed text-muted-foreground">
                        {chain.driver.description}
                      </span>
                    </>
                  )}
                </td>

                <td className="py-2.5 pr-3 align-top">
                  {sameKpi ? null : (
                    <>
                      <span className="block text-foreground">{chain.kpi.label}</span>
                      <span className="mt-0.5 block">
                        <Measure
                          value={chain.kpi.current}
                          reference={chain.kpi.target}
                          unit={chain.kpi.unit}
                          referenceLabel="목표"
                        />
                      </span>
                    </>
                  )}
                </td>

                <td className="py-2.5 pr-3 align-top">
                  <span className="block text-foreground">{chain.kri.label}</span>
                  <span className="mt-0.5 block">
                    <Measure
                      value={chain.kri.current}
                      reference={chain.kri.threshold}
                      unit={chain.kri.unit}
                      referenceLabel="임계"
                      breached={chain.breached}
                    />
                  </span>
                  {chain.breached ? (
                    <span className="mt-1 inline-flex items-center gap-1 text-[10px] font-medium text-foreground">
                      <CircleAlert
                        aria-hidden
                        className="size-2.5"
                        style={{ color: "var(--viz-status-critical)" }}
                      />
                      임계치 이탈
                    </span>
                  ) : null}
                </td>

                <td className="py-2.5 align-top">
                  <div className="flex flex-wrap gap-1">
                    {chain.controls.map((control) => (
                      <ControlChip key={control.id} control={control} />
                    ))}
                  </div>
                  {!chain.hasPreventive ? (
                    <span className="mt-1.5 inline-flex items-center gap-1 text-[10px] text-muted-foreground">
                      <ShieldOff aria-hidden className="size-2.5" />
                      예방 통제 없음 — 탐지·시정만 가능
                    </span>
                  ) : null}
                  {chain.failingControls.map((control) => (
                    <p
                      key={control.id}
                      className="mt-1 text-[10px] leading-relaxed text-muted-foreground"
                    >
                      <span className="text-foreground">{control.name}</span>{" "}
                      {CONTROL_STATUS_LABEL[control.status]} — {control.note}
                    </p>
                  ))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** 표 위에 얹는 한 줄 요약. 이탈보다 통제 공백이 먼저다. */
export function FrameworkSummaryLine({
  kriCount,
  breachedCount,
  controlCount,
  failingControlCount,
  withoutPreventiveCount,
}: {
  kriCount: number;
  breachedCount: number;
  controlCount: number;
  failingControlCount: number;
  withoutPreventiveCount: number;
}) {
  return (
    <p className="text-xs text-muted-foreground tabular-nums">
      KRI {kriCount}개 중{" "}
      <span className="font-medium text-foreground">{breachedCount}개 이탈</span>
      <span className="mx-1.5 text-muted-foreground/60">·</span>
      통제 {controlCount}개 중{" "}
      <span className="font-medium text-foreground">
        {failingControlCount}개 예외·미수행
      </span>
      {withoutPreventiveCount > 0 ? (
        <>
          <span className="mx-1.5 text-muted-foreground/60">·</span>
          예방 통제가 없는 KRI{" "}
          <span className="font-medium text-foreground">{withoutPreventiveCount}개</span>
        </>
      ) : null}
    </p>
  );
}
