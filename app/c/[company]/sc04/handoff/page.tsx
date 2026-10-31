import type { Metadata } from "next";

import { Sc04HandoffScreen } from "@/components/sc04/handoff-screen";

export const metadata: Metadata = { title: "NowView — 인계·종료" };

/** U408 장면 5 인계·종료. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc04HandoffScreen />;
}
