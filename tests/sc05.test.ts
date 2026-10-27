/**
 * SC05 화면 쪽 순수 로직 — 배치·장면·표기. 업무 규칙과 숫자는 엔진 테스트(`engine/tests/test_sc05_*.py`)가 잠근다.
 * 여기서는 화면이 엔진 응답을 **잘못 읽는** 종류만 본다(장면 1~4 테스트와 같은 기준).
 */

import { describe, expect, it } from "vitest";

import topology from "./fixtures/sc05-process.json";
import { canvasTopology, layoutProcess, nodeStates } from "@/lib/sc01/process-layout";
import type { DemoRunView, ProcessTopology } from "@/lib/sc01/types";
import { activityLines, formatCount, formatMillion, formatMinutes, formatRate, gapWord } from "@/lib/sc05/format";
import { ROUTE_OF_NODE, scenesFor } from "@/lib/sc05/scenes";
import type { Activity, Sc05ScriptStep } from "@/lib/sc05/types";

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

describe("SC05 장면", () => {
  const step = (index: number, code: string, kind: Sc05ScriptStep["kind"], nodeId: string | null, label = ""): Sc05ScriptStep => ({
    index,
    code,
    at: "2027-07-13T10:05:00+09:00",
    actor: "u-fin",
    kind,
    nodeId,
    label,
    event: null,
  });

  it("엔진 각본 → 장면. D500이 맨 앞이고 노드·단계 코드가 화면을 정한다", () => {
    const scenes = scenesFor([
      step(0, "D501", "start", null, "착수"),
      step(1, "D502", "agent", null, "AG51"),
      step(2, "D504", "view", null, "착수 요건"),
      step(3, "D507", "review", null, "AG53 검토"),
      step(4, "D512", "act", "Approve_Urgent"),
      step(5, "D513", "act", "Confirm_Observation"),
      step(6, "D517", "act", "Publish_Forecast"),
      step(7, "X507", "act", "Approve_Forecast", "대표 반려"),
    ]);
    expect(scenes.map((s) => s.route)).toEqual([
      "/sc05",
      "/sc05",
      "/sc05/plan",
      "/sc05/ready",
      "/sc05/ready",
      "/sc05/changes",
      "/sc05/results",
      "/sc05/forecast",
      "/sc05/forecast",
    ]);
    expect(scenes[0].script).toBe(-1);
    expect(scenes[8].narration).toContain("기본 시연과 다른 갈래");
  });

  it("모든 사람 노드에 화면이 있다", () => {
    const users = process.nodes.filter((n) => n.kind === "userTask").map((n) => n.id);
    expect(users.length).toBe(41);
    expect(users.filter((id) => !ROUTE_OF_NODE[id])).toEqual([]);
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

  it("Agent 초안 활동을 폼 글로 — 협조·비용 빈칸을 0으로 메우지 않는다", () => {
    const a: Activity = {
      activity_id: "01",
      name: "공동 기준 작성",
      owner: "u-buy-lead",
      start: "2027-07-19",
      end: "2027-08-17",
      predecessors: [],
      cooperation: null,
      cost: null,
      completion: "정례 공유와 수시 공유의 기본 역할",
      evidence: "DOC51",
    };
    expect(activityLines([a, { ...a, activity_id: "02", predecessors: ["01"], cost: "0" }], () => "서도현")).toBe(
      "01 | 공동 기준 작성 | 서도현 | 2027-07-19 | 2027-08-17 | - |  |  | 정례 공유와 수시 공유의 기본 역할 | DOC51\n" +
        "02 | 공동 기준 작성 | 서도현 | 2027-07-19 | 2027-08-17 | 01 |  | 0 | 정례 공유와 수시 공유의 기본 역할 | DOC51",
    );
  });
});
