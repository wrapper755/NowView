/**
 * SC04 화면 쪽 순수 로직 — 배치·표기. 업무 규칙과 숫자는 엔진 테스트(`engine/tests/test_sc04_*.py`)가
 * 잠근다. 여기서는 화면이 엔진 응답을 **잘못 읽는** 종류만 본다(장면 1~3 테스트와 같은 기준).
 */

import { describe, expect, it } from "vitest";

import topology from "./fixtures/sc04-process.json";
import { canvasTopology, layoutProcess, nodeStates } from "@/lib/sc01/process-layout";
import type { DemoRunView, ProcessTopology } from "@/lib/sc01/types";
import { formatMillion, gapWord } from "@/lib/sc04/format";

const process = topology as ProcessTopology;

describe("SC04 BPMN 배치", () => {
  it("기록 태스크와 그 오류 경계를 결재에 접고 흐름이 끊기지 않는다", () => {
    const { nodes, flows } = canvasTopology(process);
    const ids = new Set(nodes.map((n) => n.id));
    expect(nodes.some((n) => n.id.startsWith("Record_") || n.id.startsWith("Bnd_"))).toBe(false);
    expect(flows.every((f) => ids.has(f.source) && ids.has(f.target))).toBe(true);
    expect(flows.some((f) => f.source === "Verify_Effects" && f.target === "Gw_Verify")).toBe(true);
  });

  it("보완 요청·검증 보완·승인 보완·인수 반려로 되돌아가는 흐름은 층 계산에서 빠진다", () => {
    const placed = layoutProcess(process, 12);
    const rank = (id: string) => placed.find((p) => p.id === id)!.rank;
    expect(rank("Submit_AT31")).toBeLessThan(rank("Confirm_AT31"));
    expect(rank("Verify_Effects")).toBeLessThan(rank("Correct_Effects"));
    expect(rank("Draft_Approval")).toBeLessThan(rank("Finalize_Approval"));
    expect(rank("Accept_ACT43")).toBeLessThan(rank("Revise_ACT43"));
    expect(rank("Decide")).toBeLessThan(rank("Complete_Scene"));
  });

  it("실행 중에는 안 간 갈래(검증 보완·반려 보완)를 미실행으로 칠하지 않는다", () => {
    const bpm = {
      executor: "embedded",
      state: "running",
      waiting: [{ nodeId: "Recommend" }],
      position: [],
      visited: ["Start", "Task_Open", "Submit_AT31", "Confirm_AT31", "Verify_Effects"],
    } as unknown as DemoRunView["bpm"];
    const states = nodeStates(process, bpm);
    expect(states.Verify_Effects).toBe("done");
    expect(states.Correct_Effects).not.toBe("skipped");
    expect(states.Revise_ACT43).not.toBe("skipped");
  });
});

describe("SC04 표기", () => {
  it("음의 부족은 목표 초과다 — 0으로 자르지 않는다(T416)", () => {
    expect(gapWord("49503320")).toBe("부족");
    expect(gapWord("-34278880")).toBe("목표 초과");
    expect(gapWord(null)).toBe("—");
    expect(formatMillion("-34278880")).toBe("−34.28");
    expect(formatMillion("127800000")).toBe("127.80");
  });
});
