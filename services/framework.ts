/**
 * Management Framework 조회·집계.
 *
 * Value Driver → KPI → KRI → Control은 id로 느슨하게 연결돼 있다. 화면이 매번 조인하면
 * 같은 조인이 여러 곳에 흩어지므로 여기서 한 번에 엮어 준다.
 *
 * **끊어진 연결은 조용히 넘기지 않고 throw한다.** 존재하지 않는 KPI를 가리키는 KRI나
 * 통제가 하나도 없는 KRI는 Framework의 구멍이지 표시상의 문제가 아니다.
 */

import {
  isBreached,
  type Control,
  type Kpi,
  type Kri,
  type ManagementFramework,
  type ValueDriver,
} from "@/lib/types/framework";

export interface FrameworkChain {
  driver: ValueDriver;
  kpi: Kpi;
  kri: Kri;
  controls: Control[];
  breached: boolean;
  /** 이 KRI에 예방 통제가 하나라도 있는가. 없으면 탐지만 하고 막지는 못한다는 뜻이다. */
  hasPreventive: boolean;
  /** 예외·미수행 상태인 통제. 이탈보다 먼저 손봐야 할 것들이다. */
  failingControls: Control[];
}

export function buildChains(framework: ManagementFramework): FrameworkChain[] {
  return framework.kris.map((kri) => {
    const kpi = framework.kpis.find((k) => k.id === kri.kpiId);
    if (!kpi) throw new Error(`KRI ${kri.id}가 존재하지 않는 KPI ${kri.kpiId}를 가리킨다`);

    const driver = framework.drivers.find((d) => d.id === kpi.driverId);
    if (!driver) {
      throw new Error(`KPI ${kpi.id}가 존재하지 않는 Value Driver ${kpi.driverId}를 가리킨다`);
    }

    const controls = kri.controlIds.map((id) => {
      const control = framework.controls.find((c) => c.id === id);
      if (!control) throw new Error(`KRI ${kri.id}가 존재하지 않는 통제 ${id}를 가리킨다`);
      return control;
    });
    if (controls.length === 0) {
      throw new Error(`KRI ${kri.id}에 연결된 통제가 없다 — 감지만 하고 대응 경로가 없다`);
    }

    return {
      driver,
      kpi,
      kri,
      controls,
      breached: isBreached(kri),
      hasPreventive: controls.some((c) => c.kind === "preventive"),
      failingControls: controls.filter((c) => c.status !== "effective"),
    };
  });
}

/** 특정 리스크 신호에 대응하는 연결. Cockpit 리스크 목록에서 Framework로 건너갈 때 쓴다. */
export function chainForRisk(
  framework: ManagementFramework,
  riskId: string,
): FrameworkChain | undefined {
  return buildChains(framework).find((c) => c.kri.riskId === riskId);
}

export interface FrameworkSummary {
  kriCount: number;
  breachedCount: number;
  controlCount: number;
  /** 예외·미수행 통제 수. 이탈 건수보다 이쪽이 먼저다. */
  failingControlCount: number;
  /** 예방 통제가 없는 KRI 수. Framework의 구조적 공백을 드러낸다. */
  withoutPreventiveCount: number;
}

export function summarize(framework: ManagementFramework): FrameworkSummary {
  const chains = buildChains(framework);
  return {
    kriCount: chains.length,
    breachedCount: chains.filter((c) => c.breached).length,
    controlCount: framework.controls.length,
    failingControlCount: framework.controls.filter((c) => c.status !== "effective").length,
    withoutPreventiveCount: chains.filter((c) => !c.hasPreventive).length,
  };
}
