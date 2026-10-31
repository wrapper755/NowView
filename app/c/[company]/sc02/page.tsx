import type { Metadata } from "next";

import { Sc02OverviewScreen } from "@/components/sc02/overview-screen";

export const metadata: Metadata = { title: "NowView — 단가 인상 검토 현황" };

/** 장면 2 현황 — D00 장면 1 결과 확인과 공통 업무함. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc02OverviewScreen />;
}
