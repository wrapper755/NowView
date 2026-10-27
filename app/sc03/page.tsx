import type { Metadata } from "next";

import { Sc03InboxScreen } from "@/components/sc03/inbox-screen";

export const metadata: Metadata = { title: "NowView — 장면 3 수익성 검토 업무함" };

/** U31 수익성 검토 업무함 — D30 장면 2 인수 결과와 착수. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc03InboxScreen />;
}
