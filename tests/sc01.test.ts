/**
 * SC01 화면 쪽 순수 로직 — 배치·노드 상태·되감기 지점·표기.
 *
 * 업무 규칙과 숫자는 엔진 테스트(`engine/tests/test_sc01_*.py`)가 잠근다. 여기서는 화면이
 * 엔진 응답을 **잘못 읽는** 종류만 본다: 판정 보류를 정상으로, 누락을 0으로, 지난 장면을
 * 다음 장면의 시각으로 보여 주는 것.
 */

import { describe, expect, it } from "vitest";

import topology from "./fixtures/sc01-process.json";
import {
  formatKrw,
  formatKrwSigned,
  formatQty,
  formatRatio,
  riskLabel,
} from "@/lib/sc01/format";
import { layoutProcess, nodeStates } from "@/lib/sc01/process-layout";
import { historySeqFor, SC01_SCENES } from "@/lib/sc01/scenes";
import type { DemoRunView, HistoryEntry, ProcessTopology } from "@/lib/sc01/types";

const process = topology as ProcessTopology;

describe("BPMN 배치", () => {
  const placed = layoutProcess(process);
  const at = (id: string) => placed.find((p) => p.id === id)!;

  it("모든 노드를 놓는다", () => {
    expect(placed).toHaveLength(process.nodes.length);
  });

  it("되돌아가는 흐름(보완 → 재검증)은 층 계산에서 빠진다", () => {
    // 빠지지 않으면 순환이라 층이 끝없이 늘거나 검증이 보완 뒤로 밀린다.
    expect(at("Task_Validate").rank).toBeLessThan(at("Wait_Correction").rank);
    expect(at("Start").rank).toBe(0);
  });

  it("생산·자재는 같은 층에 나란히 선다", () => {
    expect(at("Accept_PROD").rank).toBe(at("Accept_MAT").rank);
    expect(at("Accept_PROD").y).not.toBe(at("Accept_MAT").y);
  });

  it("층이 많으면 여러 줄로 접는다 — 한 줄로 펴면 글자가 읽히지 않는다", () => {
    const columns = new Set(placed.map((p) => p.x));
    expect(columns.size).toBeLessThanOrEqual(5);
    expect(at("End").y).toBeGreaterThan(at("Start").y);
  });
});

describe("노드 상태", () => {
  const bpm = (over: Partial<NonNullable<DemoRunView["bpm"]>>): DemoRunView["bpm"] => ({
    runId: "r",
    state: "waiting",
    waiting: [],
    position: [],
    visited: [],
    ...over,
  });

  it("실행 중에는 안 간 분기를 미실행으로 칠하지 않는다", () => {
    const s = nodeStates(process, bpm({ visited: ["Start", "Task_Validate"], position: ["Approve_DQ"],
      waiting: [{ nodeId: "Approve_DQ", title: "", role: "영업담당", review: {}, fields: [], taskId: "TASK-DQ" }] }));
    expect(s.Approve_DQ).toBe("waiting");
    expect(s.Wait_Correction).toBe("pending");
  });

  it("끝나면 안 간 노드는 미실행, 종료 이벤트는 완료다", () => {
    const s = nodeStates(process, bpm({ state: "done", visited: ["Start", "Approve_DQ"] }));
    expect(s.Wait_Correction).toBe("skipped");
    expect(s.End).toBe("done");
  });
});

describe("되감기 지점", () => {
  const history: HistoryEntry[] = [
    { seq: 1, event: "S0", clock: "2027-06-15T18:00:00+09:00", scriptIndex: -1 },
    { seq: 2, event: "EV01", clock: "2027-06-16T09:00:00+09:00", scriptIndex: -1 },
    { seq: 3, event: "EV01", clock: "2027-06-16T09:00:00+09:00", scriptIndex: 0 },
    // 다음 단계 실행 전 가상시계 이동 — 지점은 아직 0이다.
    { seq: 4, event: "EV02", clock: "2027-06-16T10:00:00+09:00", scriptIndex: 0 },
    { seq: 5, event: "EV02", clock: "2027-06-16T10:00:00+09:00", scriptIndex: 1 },
  ];

  it("그 지점에 처음 도달한 기록을 고른다 — 마지막 기록은 다음 장면의 시각이다", () => {
    expect(historySeqFor(history, 0)).toBe(3);
    expect(historySeqFor(history, -1)).toBe(1);
  });

  it("아직 가지 않은 지점은 없다", () => {
    expect(historySeqFor(history, 5)).toBeNull();
  });

  it("장면은 각본 순서를 거스르지 않는다", () => {
    const scripts = SC01_SCENES.map((s) => s.script);
    expect(scripts).toEqual([...scripts].sort((a, b) => a - b));
    expect(scripts[0]).toBe(-1);
  });
});

describe("표기", () => {
  it("원 → 억·만", () => {
    expect(formatKrw("3309351000")).toBe("33.09억");
    expect(formatKrw("14000000")).toBe("1,400만");
    expect(formatKrwSigned(-14_000_000)).toBe("−1,400만");
    expect(formatKrwSigned(-167_939_000)).toBe("−1.68억");
  });

  it("비율은 소수 둘째 자리, 미산출은 0%가 아니다", () => {
    expect(formatRatio("0.07368421")).toBe("7.37%");
    expect(formatRatio(null)).toBe("미산출");
  });

  it("누락은 0이 아니고, 판정 보류는 정상이 아니다", () => {
    expect(formatQty(null)).toBe("누락");
    expect(formatQty(0)).toBe("0");
    expect(riskLabel(null)).toBe("판정 보류");
    expect(riskLabel("NORMAL")).toBe("기준 이내");
  });
});
