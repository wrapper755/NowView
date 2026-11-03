/**
 * 장면 7 화면이 엔진 응답을 **잘못 읽는** 종류 — 누락을 0분·정상으로 보이는 것, 원인 코드의 화면 말,
 * BPMN 배치(기록 태스크·오류 경계 접기·불일치 고리). 판정·상태 계산은 엔진 시험(`engine/tests/test_sc07_*`)이 잠근다.
 */

import { describe, expect, it } from "vitest";

import topology from "./fixtures/sc07-process.json";
import { canvasTopology, nodeStates } from "@/lib/sc01/process-layout";
import type { ProcessTopology } from "@/lib/sc01/types";
import { causeText, minutes, shortClock } from "@/lib/sc07/format";

const TOPO = topology as ProcessTopology;

describe("SC07 표기", () => {
  it("원인 후보는 화면 말로 — 근거 보완 필요는 판단이 아니다", () => {
    expect(causeText("SUPPLY")).toBe("조달 제약");
    expect(causeText("INTERNAL")).toBe("내부 지연");
    expect(causeText("MIXED")).toBe("복합 제약");
    expect(causeText("NEED_EVIDENCE")).toBe("근거 보완 필요");
    expect(causeText(null)).toBe("판단 유보");
    expect(causeText("AGT71-v2")).toBe("AGT71-v2");
  });

  it("누락은 0분이 아니다(AT704)", () => {
    expect(minutes(40)).toBe("40분");
    expect(minutes(0)).toBe("0분");
    expect(minutes(null)).toBe("미확인");
    expect(shortClock(null)).toBe("미확인");
  });
});

describe("SC07 BPMN 배치", () => {
  it("기록 태스크·오류 경계는 결재에 접힌다 — 결재 넷과 서비스 셋이 남는다", () => {
    const canvas = canvasTopology(TOPO);
    const ids = canvas.nodes.map((n) => n.id);
    for (const hidden of ["Record_Confirm_Buy", "Bnd_Record_Check_Setting", "Record_Apply_Setting"]) {
      expect(ids).not.toContain(hidden);
    }
    for (const kept of ["Confirm_Buy", "Confirm_Finance", "Apply_Setting", "Check_Setting", "Task_Verify", "Task_FollowUp"]) {
      expect(ids).toContain(kept);
    }
    // 불일치면 설정 반영으로 돌아간다 — 접은 뒤에도 고리가 남는다
    expect(canvas.flows.some((f) => f.source === "Gw_Check" && f.target === "Apply_Setting")).toBe(true);
  });

  it("실행 중에는 안 간 끝(보완 필요)을 미실행으로 칠하지 않는다", () => {
    const states = nodeStates(TOPO, {
      executor: "center",
      state: "running",
      waiting: [{ node_id: "Confirm_Finance" }],
      position: [],
      visited: ["Start", "Task_Open", "Task_Verify", "Gw_Verified", "Confirm_Buy", "Record_Confirm_Buy", "Gw_Confirm_Buy"],
    } as never);
    expect(states["Confirm_Buy"]).toBe("done");
    expect(states["End_Rework"]).not.toBe("skipped");
  });
});
