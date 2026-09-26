/**
 * 표기 유틸과 경영 수행 성과 산출.
 *
 * 경영 수행 성과의 절반은 실제 데이터에서 계산한다(CLAUDE.md 4.9). 계산 경로가 끊겨
 * 기준값 파일의 자리표시자가 그대로 화면에 나가도 **숫자가 그럴듯해서 눈으로는 안 잡힌다.**
 * 그래서 "계산값이 원본과 같은가"를 직접 확인한다.
 */

import { describe, expect, it } from "vitest";

import { bpmProcess } from "@/lib/mock-data/bpm-process";
import { rollingPlan } from "@/lib/mock-data/rolling-plan";
import {
  formatAxisEok,
  formatEok,
  formatEokPrecise,
  formatEokSigned,
  formatPercent,
  formatPpSigned,
} from "@/lib/format";
import { improvementOf, meetsTarget } from "@/lib/types/execution-performance";
import {
  actionOnTimeRate,
  agentHoursOf,
  executionMetrics,
  parseDurationMinutes,
  recoveryRealizationRate,
  totalAgentHours,
} from "@/services/execution-performance";

describe("억원 표기", () => {
  it("1조 이상은 조 단위로 끊는다", () => {
    expect(formatEok(10200)).toBe("1조 200억");
    expect(formatEok(9940)).toBe("9,940억");
    expect(formatEok(20000)).toBe("2조");
  });

  it("음수 부호를 잃지 않는다", () => {
    expect(formatEok(-69)).toBe("-69억");
    expect(formatEok(-10200)).toBe("-1조 200억");
  });

  it("부호 표기는 양수에 +를 붙이고 0은 붙이지 않는다", () => {
    expect(formatEokSigned(18)).toBe("+18억");
    expect(formatEokSigned(-48)).toBe("-48억");
    expect(formatEokSigned(0)).toBe("0억");
  });

  it("소수 표기는 정수일 때 소수점을 붙이지 않는다", () => {
    // formatEok는 반올림이라 5.2가 "5억"이 된다 — 진척 차이가 사라지는 것을 막는 함수다.
    expect(formatEok(5.2)).toBe("5억");
    expect(formatEokPrecise(5.2)).toBe("5.2억");
    expect(formatEokPrecise(5)).toBe("5억");
  });

  it("축 눈금은 천 단위만 끊는다", () => {
    expect(formatAxisEok(428)).toBe("428");
    expect(formatAxisEok(10200)).toBe("10,200");
  });
});

describe("퍼센트 표기", () => {
  it("소수 1자리로 맞춘다", () => {
    expect(formatPercent(3.6)).toBe("3.6%");
    expect(formatPercent(61.53, 0)).toBe("62%");
  });

  it("퍼센트포인트는 부호를 항상 붙인다", () => {
    expect(formatPpSigned(3.2)).toBe("+3.2%p");
    expect(formatPpSigned(-0.6)).toBe("-0.6%p");
  });
});

describe("소요시간 파싱", () => {
  it("시간·분·초 조합을 분으로 바꾼다", () => {
    expect(parseDurationMinutes("4분 12초")).toBeCloseTo(4.2, 6);
    expect(parseDurationMinutes("11분 04초")).toBeCloseTo(11 + 4 / 60, 6);
    expect(parseDurationMinutes("2시간")).toBe(120);
    expect(parseDurationMinutes("1시간 30분")).toBe(90);
  });

  it("읽을 수 없는 형식은 0이 아니라 throw한다", () => {
    // 조용히 0이 되면 소요시간이 실제보다 짧게 보인다.
    expect(() => parseDurationMinutes("즉시")).toThrow();
    expect(() => parseDurationMinutes("")).toThrow();
  });

  it("Agent 실행 기록 전체가 파싱된다", () => {
    for (const run of bpmProcess.runs) {
      expect(() => parseDurationMinutes(run.duration)).not.toThrow();
    }
  });
});

describe("경영 수행 성과 산출", () => {
  it("Agent 분석 소요시간이 실행 기록의 합이다", () => {
    const expected =
      bpmProcess.runs.reduce((sum, r) => sum + parseDurationMinutes(r.duration), 0) / 60;
    expect(totalAgentHours()).toBeCloseTo(expected, 6);
  });

  it("과제 이행률이 반영 완료 과제만 분모로 쓴다", () => {
    const tracked = rollingPlan.actions.filter((a) => a.reflectedInForecast);
    const onTrack = tracked.filter(
      (a) => a.status === "done" || a.status === "in-progress",
    );
    expect(actionOnTimeRate()).toBeCloseTo((onTrack.length / tracked.length) * 100, 6);
  });

  it("회수 실현율이 목표 대비 실제 회수액이다", () => {
    const tracked = rollingPlan.actions.filter((a) => a.reflectedInForecast);
    const target = tracked.reduce((s, a) => s + a.targetRecovery, 0);
    const realized = tracked.reduce((s, a) => s + a.realizedRecovery, 0);
    expect(recoveryRealizationRate()).toBeCloseTo((realized / target) * 100, 6);
  });

  it("시스템 산출값이 기준값 파일의 자리표시자가 아니다", () => {
    // 계산 경로가 끊기면 자리표시자가 그대로 나가는데 숫자가 그럴듯해 눈으로는 안 잡힌다.
    const metrics = executionMetrics();
    const computed = metrics.filter((m) => m.provenance === "system");
    expect(computed.length).toBeGreaterThan(0);

    const onTime = computed.find((m) => m.id === "mp-action-ontime")!;
    expect(onTime.current).toBeCloseTo(actionOnTimeRate(), 6);
    // 자리표시자는 67, 실제 계산은 66.666…이다.
    expect(onTime.current).not.toBe(67);
  });

  it("모든 지표에 정의와 직전 주기 값이 있다", () => {
    for (const metric of executionMetrics()) {
      expect(metric.definition.length).toBeGreaterThan(0);
      expect(Number.isFinite(metric.previous)).toBe(true);
    }
  });
});

describe("개선 방향 판정", () => {
  it("낮을수록 좋은 지표는 값이 줄어야 개선이다", () => {
    const base = {
      id: "x",
      category: "speed",
      label: "x",
      unit: "일",
      provenance: "scenario",
      definition: "x",
    } as const;
    const lower = { ...base, current: 3, previous: 5, higherIsBetter: false };
    const higher = { ...base, current: 5, previous: 3, higherIsBetter: true };
    expect(improvementOf(lower as never)).toBeGreaterThan(0);
    expect(improvementOf(higher as never)).toBeGreaterThan(0);
    expect(improvementOf({ ...lower, current: 7 } as never)).toBeLessThan(0);
  });

  it("목표가 없으면 달성 여부를 판단하지 않는다", () => {
    const metric = executionMetrics().find((m) => m.target === undefined);
    if (metric) expect(meetsTarget(metric)).toBeUndefined();
  });

  it("목표 달성 판정이 방향을 따른다", () => {
    for (const metric of executionMetrics()) {
      if (metric.target === undefined) continue;
      const hit = metric.higherIsBetter
        ? metric.current >= metric.target
        : metric.current <= metric.target;
      expect(meetsTarget(metric)).toBe(hit);
    }
  });
});

describe("엔진 실측값 반영 (4.17)", () => {
  const engineRuns = [{ duration: "10분 00초" }, { duration: "5분 30초" }];

  it("엔진 실행 기록을 주면 소요시간이 실측값으로 바뀐다", () => {
    const metric = executionMetrics(engineRuns).find((m) => m.id === "mp-analysis-time")!;
    expect(metric.current).toBeCloseTo(15.5 / 60, 6);
    // Mock 계산과 실측은 근거가 다르다 — 같은 배지로 묶으면 기획안 2.3의 구분이 이름만 남는다.
    expect(metric.provenance).toBe("measured");
  });

  it("빈 배열은 무시하고 Mock 계산을 유지한다", () => {
    // 엔진을 켰지만 아직 Agent가 안 돌았을 때 0시간으로 덮으면
    // "분석이 즉시 끝났다"고 말하는 셈이 된다.
    const metric = executionMetrics([]).find((m) => m.id === "mp-analysis-time")!;
    expect(metric.current).toBeCloseTo(totalAgentHours(), 6);
    expect(metric.provenance).toBe("system");
  });

  it("다른 지표의 출처는 그대로다", () => {
    const withEngine = executionMetrics(engineRuns);
    const baseline = executionMetrics();
    for (const metric of withEngine) {
      if (metric.id === "mp-analysis-time") continue;
      const same = baseline.find((m) => m.id === metric.id)!;
      expect(metric.provenance).toBe(same.provenance);
      expect(metric.current).toBeCloseTo(same.current, 6);
    }
  });

  it("agentHoursOf가 소요시간을 시간 단위로 합한다", () => {
    expect(agentHoursOf([{ duration: "1시간 30분" }])).toBeCloseTo(1.5, 6);
    expect(agentHoursOf([])).toBe(0);
  });
});
