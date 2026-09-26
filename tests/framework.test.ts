/**
 * Management Framework 연결 무결성 (CLAUDE.md 4.8).
 *
 * Value Driver → KPI → KRI → Control은 id로 느슨하게 이어져 있어 한쪽을 지우면 조용히
 * 끊긴다. `buildChains`가 throw하도록 만들어 뒀지만 그 화면을 열어야 터지므로 여기서 잠근다.
 */

import { describe, expect, it } from "vitest";

import { managementFramework } from "@/lib/mock-data/framework";
import { nextAutomotive } from "@/lib/mock-data/next-automotive";
import { isBreached } from "@/lib/types/framework";
import { buildChains, chainForRisk, summarize } from "@/services/framework";

describe("연결 무결성", () => {
  it("끊어진 참조 없이 전체 연결을 만들 수 있다", () => {
    expect(() => buildChains(managementFramework)).not.toThrow();
  });

  it("모든 KRI에 통제가 하나 이상 붙어 있다", () => {
    for (const chain of buildChains(managementFramework)) {
      expect(chain.controls.length).toBeGreaterThan(0);
    }
  });

  it("KRI가 실제 리스크 신호를 가리킨다", () => {
    const riskIds = new Set(nextAutomotive.risks.map((r) => r.id));
    for (const kri of managementFramework.kris) {
      expect(riskIds.has(kri.riskId)).toBe(true);
    }
  });

  it("KRI와 리스크 신호가 1:1로 대응한다", () => {
    const kriRiskIds = managementFramework.kris.map((k) => k.riskId);
    expect(new Set(kriRiskIds).size).toBe(kriRiskIds.length);
    expect(new Set(kriRiskIds)).toEqual(new Set(nextAutomotive.risks.map((r) => r.id)));
  });

  it("KRI 현재값·임계치가 리스크 신호의 표시값과 일치한다", () => {
    for (const kri of managementFramework.kris) {
      const risk = nextAutomotive.risks.find((r) => r.id === kri.riskId)!;
      // 리스크 쪽은 표시용 문자열이라 숫자만 뽑아 비교한다.
      const num = (text: string) => Number(text.replace(/[^\d.-]/g, ""));
      expect(num(risk.kri.value)).toBe(kri.current);
      expect(num(risk.kri.threshold)).toBe(kri.threshold);
    }
  });

  it("id가 중복되지 않는다", () => {
    const ids = [
      ...managementFramework.drivers.map((d) => d.id),
      ...managementFramework.kpis.map((k) => k.id),
      ...managementFramework.kris.map((k) => k.id),
      ...managementFramework.controls.map((c) => c.id),
    ];
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("고아 통제가 없다 — 모든 통제가 어떤 KRI에 연결돼 있다", () => {
    const used = new Set(managementFramework.kris.flatMap((k) => k.controlIds));
    for (const control of managementFramework.controls) {
      expect(used.has(control.id)).toBe(true);
    }
  });
});

describe("이탈 판정", () => {
  it("방향에 따라 미만·초과를 각각 이탈로 본다", () => {
    const below = { breachBelow: true, current: 82.1, threshold: 85 };
    const above = { breachBelow: false, current: 26, threshold: 18 };
    expect(isBreached(below as never)).toBe(true);
    expect(isBreached(above as never)).toBe(true);
    expect(isBreached({ ...below, current: 90 } as never)).toBe(false);
    expect(isBreached({ ...above, current: 12 } as never)).toBe(false);
  });

  it("음수 임계치에서도 방향이 맞는다 (CR 요구율)", () => {
    const cr = managementFramework.kris.find((k) => k.id === "kri-cr")!;
    expect(cr.current).toBeLessThan(cr.threshold);
    expect(isBreached(cr)).toBe(true);
  });
});

describe("요약", () => {
  it("이탈 건수가 실제 이탈 KRI 수와 같다", () => {
    const summary = summarize(managementFramework);
    const breached = managementFramework.kris.filter(isBreached).length;
    expect(summary.breachedCount).toBe(breached);
    expect(summary.kriCount).toBe(managementFramework.kris.length);
  });

  it("예방 통제가 없는 KRI를 정확히 센다", () => {
    const summary = summarize(managementFramework);
    const withoutPreventive = buildChains(managementFramework).filter(
      (c) => !c.controls.some((x) => x.kind === "preventive"),
    ).length;
    expect(summary.withoutPreventiveCount).toBe(withoutPreventive);
  });

  it("예외·미수행 통제 수가 실제와 같다", () => {
    const summary = summarize(managementFramework);
    const failing = managementFramework.controls.filter(
      (c) => c.status !== "effective",
    ).length;
    expect(summary.failingControlCount).toBe(failing);
  });
});

describe("리스크에서 연결 찾기", () => {
  it("모든 리스크 신호가 자기 연결을 찾을 수 있다", () => {
    for (const risk of nextAutomotive.risks) {
      const chain = chainForRisk(managementFramework, risk.id);
      expect(chain).toBeDefined();
      expect(chain!.kri.riskId).toBe(risk.id);
    }
  });

  it("없는 리스크는 undefined를 돌려준다", () => {
    expect(chainForRisk(managementFramework, "risk-does-not-exist")).toBeUndefined();
  });
});
