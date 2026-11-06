import { describe, expect, it } from "vitest";

import { caseUrl, formatClock, formatKrw, formatMetric, formatPercent, workUrl } from "@/lib/dashboard";

describe("대시보드 표기", () => {
  it("금액은 억·만·원으로, 부호는 −를 쓴다", () => {
    expect(formatKrw("3309351000")).toBe("33.09억");
    expect(formatKrw("-167939000", true)).toBe("−1.68억");
    expect(formatKrw("-14000000", true)).toBe("−1,400만");
    expect(formatKrw("18817440")).toBe("1,882만");
    expect(formatKrw("4800000", true)).toBe("+480만");
    expect(formatKrw("0", true)).toBe("0원");
  });

  it("값이 없으면 0이 아니라 미산출이다", () => {
    expect(formatKrw(null)).toBe("미산출");
    expect(formatMetric({ label: "적용 상태", kind: "text", value: null })).toBe("미확인");
  });

  it("가상시각은 엔진이 준 KST 그대로 읽는다", () => {
    expect(formatClock("2027-06-16T11:45:00+09:00")).toBe("2027-06-16 11:45");
    expect(formatClock(null)).toBe("—");
  });

  it("회사 사이트 업무 화면 주소 — 사이트 주소나 세계가 없으면 링크하지 않는다", () => {
    expect(workUrl("http://localhost:3100", "demo-db9e1a3e", 3)).toBe("http://localhost:3100/work/demo-db9e1a3e/sc03");
    expect(workUrl(null, "demo-1", 1)).toBeNull();
    expect(workUrl("http://localhost:3100", null, 1)).toBeNull();
  });
});

describe("시나리오 2 — 공통 플랫폼", () => {
  it("업무 번호 21은 회사 사이트의 시나리오 2 장면 1 화면이다", () => {
    expect(workUrl("https://site", "demo-1", 21)).toBe("https://site/work/demo-1/s2/sc01");
    expect(workUrl("https://site", "demo-1", 24)).toBe("https://site/work/demo-1/s2/sc04");
    expect(workUrl("https://site", "demo-1", 31)).toBe("https://site/work/demo-1/s3/sc01");
    expect(workUrl("https://site", "demo-1", 32)).toBe("https://site/work/demo-1/s3/sc02");
    expect(workUrl("https://site", "demo-1", 33)).toBe("https://site/work/demo-1/s3/sc03");
    expect(workUrl("https://site", "demo-1", 1)).toBe("https://site/work/demo-1/sc01");
  });
  it("사건 열기는 돌아올 곳과 약정을 넘긴다(맥락 유지)", () => {
    const url = caseUrl("https://site", "demo-1", "https://nv/c/company1?world=demo-1", "COM-R");
    expect(url).toBe("https://site/work/demo-1/s2/sc01?back=https%3A%2F%2Fnv%2Fc%2Fcompany1%3Fworld%3Ddemo-1&commitment=COM-R");
    expect(caseUrl(null, "demo-1", "x")).toBeNull();
  });
  it("비율은 %로, 분모 0은 「대상 없음」(0%가 아니다)", () => {
    expect(formatPercent("0.9900")).toBe("99%");
    expect(formatPercent("0.9500")).toBe("95%");
    expect(formatPercent(null)).toBe("대상 없음");
  });
});
