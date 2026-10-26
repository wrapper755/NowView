import type { Metadata } from "next";

import { Sc02AnalysisScreen } from "@/components/sc02/analysis-screen";

export const metadata: Metadata = { title: "NowView — U22 사전 검토 · 영향분석" };

/** U22 보고 기록과 요청안·협상안 영향분석. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc02AnalysisScreen />;
}
