import type { Metadata } from "next";

import { Sc02NegotiationScreen } from "@/components/sc02/negotiation-screen";

export const metadata: Metadata = { title: "NowView — U23 1차 협상 결과" };

/** U23 1차 협상 결과. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc02NegotiationScreen />;
}
