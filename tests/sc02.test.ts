/**
 * SC02 화면 쪽 순수 로직 — 배치·장면·표기. 업무 규칙과 숫자는 엔진 테스트(`engine/tests/test_sc02_*.py`)가
 * 잠근다. 여기서는 화면이 엔진 응답을 **잘못 읽는** 종류만 본다(SC01 테스트와 같은 기준).
 */

import { describe, expect, it } from "vitest";

import topology from "./fixtures/sc02-process.json";
import { canvasTopology, layoutProcess, nodeStates } from "@/lib/sc01/process-layout";
import type { DemoRunView, ProcessTopology, ScriptStep } from "@/lib/sc01/types";
import { formatPeriod } from "@/lib/sc02/format";
import { ROUTE_OF_NODE, scenesFor } from "@/lib/sc02/scenes";

const process = topology as ProcessTopology;

describe("SC02 BPMN 배치", () => {
  it("결정 기록 태스크를 결재에 접고 흐름이 끊기지 않는다", () => {
    const { nodes, flows } = canvasTopology(process);
    const ids = new Set(nodes.map((n) => n.id));
    expect(nodes.some((n) => n.id === "Record_Lead")).toBe(false);
    expect(flows.every((f) => ids.has(f.source) && ids.has(f.target))).toBe(true);
    // 결재 → 게이트웨이로 바로 잇는다(기록 태스크를 건너뛴다)
    expect(flows.some((f) => f.source === "Approve_Lead" && f.target === "Gw_Lead")).toBe(true);
  });

  it("보완 → 기안으로 돌아가는 흐름은 층 계산에서 빠진다 — 기안이 결재보다 앞 층이다", () => {
    const placed = layoutProcess(process, 8);
    const rank = (id: string) => placed.find((p) => p.id === id)!.rank;
    expect(rank("Draft_Proposal")).toBeLessThan(rank("Approve_Lead"));
    expect(rank("Approve_Lead")).toBeLessThan(rank("Approve_Exec"));
    expect(rank("Approve_Exec")).toBeLessThan(rank("Approve_CEO"));
  });

  it("넓게 펴면 줄 수가 준다 — 장면 2는 층이 많다", () => {
    const rows = (cols: number) => new Set(layoutProcess(process, cols).map((p) => Math.round(p.y / 50))).size;
    expect(rows(8)).toBeLessThanOrEqual(rows(5));
  });

  it("끝나면 도달한 종료만 완료 — 가지 않은 반려·재협상·미합의 종료는 미실행이다", () => {
    const bpm = {
      executor: "embedded",
      state: "done",
      waiting: [],
      position: [],
      visited: ["Start", "Approve_Lead", "Gw_Lead", "End_Rejected"],
    } as unknown as DemoRunView["bpm"];
    const states = nodeStates(process, bpm);
    expect(states.End_Rejected).toBe("done");
    expect(states.End_Reneg).toBe("skipped");
    expect(states.End).toBe("skipped");
    expect(states.Approve_CEO).toBe("skipped");
  });
});

describe("SC02 장면", () => {
  const step = (index: number, code: string, nodeId: string | null, label = ""): ScriptStep => ({
    index,
    code,
    at: "2027-06-17T09:00:00+09:00",
    actor: "u-buy",
    nodeId,
    label,
  });

  it("첫 장면은 D00 — 엔진 각본보다 앞이다", () => {
    const scenes = scenesFor([step(0, "D01", null, "접수")]);
    expect(scenes[0].script).toBe(-1);
    expect(scenes[1]).toMatchObject({ script: 0, route: "/sc02/request" });
  });

  it("사례마다 각본이 다르다 — X01은 그 단계의 라벨로 보인다", () => {
    const scenes = scenesFor([step(0, "D01", null), step(1, "X01", "Approve_Exec", "추가 협상지시")]);
    expect(scenes.at(-1)!.title).toBe("X01 추가 협상지시");
    expect(scenes.at(-1)!.route).toBe("/sc02/approval");
  });

  it("모든 사람 노드에 화면이 있다", () => {
    for (const n of process.nodes.filter((n) => n.kind === "userTask")) {
      expect(ROUTE_OF_NODE[n.id], n.id).toBeDefined();
    }
  });
});

describe("SC02 표기", () => {
  it("기간은 종료 제외 경계를 한 달 앞으로 보인다 — [2027-07, 2028-07) = 2027-07~2028-06", () => {
    expect(formatPeriod("2027-07-01", "2028-07-01")).toBe("2027-07~2028-06");
    expect(formatPeriod("2027-07-01", "2028-01-01")).toBe("2027-07~2027-12");
  });
});
