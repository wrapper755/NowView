import type { Metadata } from "next";

import { Sc03AnalysisScreen } from "@/components/sc03/analysis-screen";

export const metadata: Metadata = { title: "NowView — 통합 손익영향 분석" };

/** U32 통합 손익영향 분석. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc03AnalysisScreen />;
}
