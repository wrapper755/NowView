/**
 * SC03 화면 쪽 순수 로직 — 배치·장면·표기. 업무 규칙과 숫자는 엔진 테스트(`engine/tests/test_sc03_*.py`)가
 * 잠근다. 여기서는 화면이 엔진 응답을 **잘못 읽는** 종류만 본다(장면 1·2 테스트와 같은 기준).
 */

import { describe, expect, it } from "vitest";

import topology from "./fixtures/sc03-process.json";
import { canvasTopology, layoutProcess, nodeStates } from "@/lib/sc01/process-layout";
import type { DemoRunView, ProcessTopology } from "@/lib/sc01/types";
import { formatMillion } from "@/lib/sc03/format";
import { ROUTE_OF_NODE, scenesFor } from "@/lib/sc03/scenes";
import type { Sc03ScriptStep } from "@/lib/sc03/types";

const process = topology as ProcessTopology;

describe("SC03 BPMN 배치", () => {
  it("기록 태스크와 그 오류 경계를 결재에 접고 흐름이 끊기지 않는다", () => {
    const { nodes, flows } = canvasTopology(process);
    const ids = new Set(nodes.map((n) => n.id));
    expect(nodes.some((n) => n.id.startsWith("Record_") || n.id.startsWith("Bnd_"))).toBe(false);
    expect(flows.every((f) => ids.has(f.source) && ids.has(f.target))).toBe(true);
    expect(flows.some((f) => f.source === "Confirm_Buy" && f.target === "Gw_Confirm_Buy")).toBe(true);
  });

  it("재분석·재확인·재배정으로 되돌아가는 흐름은 층 계산에서 빠진다", () => {
    const placed = layoutProcess(process, 8);
    const rank = (id: string) => placed.find((p) => p.id === id)!.rank;
    expect(rank("Save_Analysis")).toBeLessThan(rank("Request_Confirm"));
    expect(rank("Confirm_Buy")).toBeLessThan(rank("Revise_Buy"));
    expect(rank("Accept_AT31")).toBeLessThan(rank("Reassign_AT31"));
    expect(rank("Decide_Review")).toBeLessThan(rank("Complete_Scene"));
  });

  it("실행 중에는 안 간 갈래(이견 보완·재배정)를 미실행으로 칠하지 않는다", () => {
    const bpm = {
      executor: "embedded",
      state: "running",
      waiting: [{ nodeId: "Confirm_Prod" }],
      position: [],
      visited: ["Start", "Task_Open", "Save_Analysis", "Confirm_Sales", "Confirm_Buy"],
    } as unknown as DemoRunView["bpm"];
    const states = nodeStates(process, bpm);
    expect(states.Confirm_Buy).toBe("done");
    expect(states.Revise_Buy).not.toBe("skipped");
  });
});

describe("SC03 장면", () => {
  const step = (index: number, code: string, kind: Sc03ScriptStep["kind"], nodeId: string | null, label = ""): Sc03ScriptStep => ({
    index,
    code,
    at: "2027-06-24T10:05:00+09:00",
    actor: "u-fin",
    kind,
    nodeId,
    label,
    event: null,
  });

  it("엔진 각본 → 장면. D30이 맨 앞이고 노드·종류가 화면을 정한다", () => {
    const scenes = scenesFor([
      step(0, "D31", "start", null, "검토 착수"),
      step(1, "D32", "act", "Save_Analysis"),
      step(2, "D37", "record", null, "QA31"),
      step(3, "D40", "act", "Accept_AT31"),
      step(4, "E37", "clock", null, "7/6 18:01"),
    ]);
    expect(scenes.map((s) => s.route)).toEqual(["/sc03", "/sc03", "/sc03/analysis", "/sc03/meeting", "/sc03/tasks", "/sc03/handoff"]);
    expect(scenes[0].script).toBe(-1);
    expect(scenes[5].narration).toContain("기본 시연과 다른 갈래");
  });

  it("모든 사람 노드에 화면이 있다", () => {
    const users = process.nodes.filter((n) => n.kind === "userTask").map((n) => n.id);
    expect(users.filter((id) => !ROUTE_OF_NODE[id])).toEqual([]);
  });
});

describe("SC03 표기", () => {
  it("백만원 소수 둘째 자리 — NULL은 0이 아니다", () => {
    expect(formatMillion("3299986680")).toBe("3,299.99");
    expect(formatMillion("-23364320")).toBe("−23.36");
    expect(formatMillion("177303320")).toBe("177.30");
    expect(formatMillion(null, "미설정")).toBe("미설정");
    expect(formatMillion("0")).toBe("0.00");
  });
});
