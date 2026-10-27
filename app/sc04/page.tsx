import type { Metadata } from "next";

import { Sc04InboxScreen } from "@/components/sc04/inbox-screen";

export const metadata: Metadata = { title: "NowView — 장면 4 분석 결과 업무함" };

/** U401 분석 결과 업무함 — D400 장면 3 인계와 착수. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc04InboxScreen />;
}
