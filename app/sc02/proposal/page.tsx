import type { Metadata } from "next";

import { Sc02ProposalScreen } from "@/components/sc02/proposal-screen";

export const metadata: Metadata = { title: "NowView — U24 가격인상 보고 기안" };

/** U24 가격인상 보고 기안. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc02ProposalScreen />;
}
