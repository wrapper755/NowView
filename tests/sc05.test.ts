/**
 * SC05 화면 쪽 순수 로직 — 배치·표기. 업무 규칙과 숫자는 엔진 테스트(`engine/tests/test_sc05_*.py`)가 잠근다.
 * 여기서는 화면이 엔진 응답을 **잘못 읽는** 종류만 본다(장면 1~4 테스트와 같은 기준).
 */

import { describe, expect, it } from "vitest";

import topology from "./fixtures/sc05-process.json";
import { canvasTopology, layoutProcess, nodeStates } from "@/lib/sc01/process-layout";
import type { DemoRunView, ProcessTopology } from "@/lib/sc01/types";
import { formatCount, formatMillion, formatMinutes, formatRate, gapWord } from "@/lib/sc05/format";

const process = topology as ProcessTopology;

describe("SC05 BPMN 배치", () => {
  it("기록 태스크와 그 오류 경계를 결재에 접고 흐름이 끊기지 않는다", () => {
    const { nodes, flows } = canvasTopology(process);
    const ids = new Set(nodes.map((n) => n.id));
    expect(nodes.some((n) => n.id.startsWith("Record_") || n.id.startsWith("Bnd_"))).toBe(false);
    expect(flows.every((f) => ids.has(f.source) && ids.has(f.target))).toBe(true);
    expect(flows.some((f) => f.source === "Start_Operation" && f.target === "Receive_Change")).toBe(true);
  });

  it("보완·범위 이탈·반려·대표 변경 고리·대사 실패로 되돌아가는 흐름은 층 계산에서 빠진다", () => {
    const placed = layoutProcess(process, 12);
    const rank = (id: string) => placed.find((p) => p.id === id)!.rank;
    expect(rank("Draft_Plan")).toBeLessThan(rank("Verify_Plan"));
    expect(rank("Verify_Plan")).toBeLessThan(rank("Request_Change"));
    expect(rank("Request_Change")).toBeLessThan(rank("Verify_Change"));
    expect(rank("Submit_REQ51")).toBeLessThan(rank("Budget_REQ51"));
    expect(rank("Receive_Change")).toBeLessThan(rank("Execute_Order"));
    expect(rank("Execute_Order")).toBeLessThan(rank("Confirm_Observation"));
    expect(rank("Draft_Forecast")).toBeLessThan(rank("Approve_Forecast"));
    expect(rank("Approve_Forecast")).toBeLessThan(rank("Complete_Scene"));
  });

  it("실행 중에는 안 간 갈래(긴급 승인·보완)를 미실행으로 칠하지 않는다", () => {
    const bpm = {
      executor: "embedded",
      state: "running",
      waiting: [{ nodeId: "Execute_Order" }],
      position: [],
      visited: ["Start", "Task_Open", "Draft_Plan", "Respond_Change"],
    } as unknown as DemoRunView["bpm"];
    const states = nodeStates(process, bpm);
    expect(states.Draft_Plan).toBe("done");
    expect(states.Approve_Urgent).not.toBe("skipped");
    expect(states.Verify_Change).not.toBe("skipped");
  });
});

describe("SC05 표기", () => {
  it("미확인·비해당은 0과 다르다(T518)", () => {
    expect(formatCount(null)).toBe("미확인");
    expect(formatCount(0)).toBe("0건");
    expect(formatRate(null)).toBe("비해당");
    expect(formatRate("0.08333333333333333333")).toBe("8.33%");
    expect(formatMinutes(null)).toBe("미확인");
    expect(formatMinutes("26.66666666666666666667")).toBe("26.7분");
  });

  it("음의 부족은 목표 초과, 금액은 백만원 둘째 자리", () => {
    expect(gapWord("48303320")).toBe("부족");
    expect(gapWord("-6082120")).toBe("목표 초과");
    expect(formatMillion("3428986680")).toBe("3,428.99");
  });

});
