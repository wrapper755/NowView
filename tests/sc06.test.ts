/**
 * 장면 6 화면이 엔진 응답을 **잘못 읽는** 종류 — 미확인·미산정을 0으로 보이는 것, 차이 부호, 장면(세 동작) 대응.
 * 숫자 계산은 엔진 시험(`engine/tests/test_sc06_*`)이 잠근다. 화면은 단위만 바꾼다.
 */

import { describe, expect, it } from "vitest";

import { estimationText, formatDuration, million, shortClock, signedMillion } from "@/lib/sc06/format";
import { SC06_SCENES, sceneFor } from "@/lib/sc06/scenes";

describe("SC06 표기", () => {
  it("null은 0이 아니다 — 미확인·산정 보류로 쓴다(AT61-07)", () => {
    expect(million(null)).toBe("미확인");
    expect(million(null, "산정 보류")).toBe("산정 보류");
    expect(million(0)).toBe("0.00");
    expect(million(87_000_000)).toBe("87.00");
  });

  it("차이는 실현 − 기대 부호를 늘 붙인다", () => {
    expect(signedMillion(-4_800_000)).toBe("−4.80");
    expect(signedMillion(1_200_000)).toBe("+1.20");
    expect(signedMillion(0)).toBe("0.00");
    expect(signedMillion(null)).toBe("산정 보류");
  });

  it("발의 효과·예산 미산정은 0원 승인으로 읽히지 않는다(X61-06)", () => {
    expect(estimationText({ krw: null, estimation_status: "NOT_ESTIMATED", note: "NOT_ESTIMATED" })).toBe("미산정");
    expect(estimationText({ krw: null, estimation_status: "NOT_APPLICABLE", note: "해당 없음" })).toBe("비해당");
    expect(estimationText({ krw: 0, estimation_status: "CONFIRMED", note: "기존 운영비 범위" })).toBe("0.00백만원");
  });

  it("소요 시간 — 미확인은 0분이 아니다", () => {
    expect(formatDuration(40)).toBe("40분");
    expect(formatDuration(2880)).toBe("2일");
    expect(formatDuration(180)).toBe("3시간");
    expect(formatDuration(null)).toBe("미확인");
    expect(shortClock("2027-11-12T09:20:00+09:00")).toBe("11/12 09:20");
  });
});

describe("SC06 시연 세 동작", () => {
  it("두 화면·세 동작 210초(AT61-01)", () => {
    expect(SC06_SCENES.map((s) => s.route)).toEqual(["/sc06", "/sc06", "/sc06/report"]);
    expect(SC06_SCENES.reduce((n, s) => n + s.seconds, 0)).toBe(210);
    expect(SC06_SCENES.map((s) => s.detail)).toEqual([false, true, true]);
  });

  it("화면·펼침이 곧 장면이다 — U602에서 돌아오면 펼침이 남는다", () => {
    expect(sceneFor("/sc06", false)).toBe(0);
    expect(sceneFor("/sc06", true)).toBe(1);
    expect(sceneFor("/sc06/report", true)).toBe(2);
    expect(sceneFor("/sc06/report", false)).toBe(2);
  });
});
