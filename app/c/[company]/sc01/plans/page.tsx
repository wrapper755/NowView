import type { Metadata } from "next";

import { PlansScreen } from "@/components/sc01/plans-screen";

export const metadata: Metadata = { title: "NowView — UI02·03 고객 생산계획" };

/** UI02·03 고객 생산계획. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <PlansScreen />;
}
