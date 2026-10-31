import type { Metadata } from "next";

import { HandoffScreen } from "@/components/sc01/handoff-screen";

export const metadata: Metadata = { title: "NowView — UI06 경영이슈·인계 현황" };

/** UI06 경영이슈·인계 현황. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <HandoffScreen />;
}
