import type { Metadata } from "next";

import { RiskScreen } from "@/components/sc01/risk-screen";

export const metadata: Metadata = { title: "NowView — UI04 공급전망 변동·위험 검토" };

/** UI04 공급전망 변동·위험 검토. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <RiskScreen />;
}
