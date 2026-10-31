import type { Metadata } from "next";

import { Sc02HandoffScreen } from "@/components/sc02/handoff-screen";

export const metadata: Metadata = { title: "NowView — U27 통합 영향 · 수익성 통합 분석 인계" };

/** U27 장면 1·2 통합 영향과 경영관리 인계. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc02HandoffScreen />;
}
