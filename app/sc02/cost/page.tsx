import type { Metadata } from "next";

import { Sc02CostScreen } from "@/components/sc02/cost-screen";

export const metadata: Metadata = { title: "NowView — U26 원가 적용 등록" };

/** U26 승인 조건 대조와 원가 버전 등록. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc02CostScreen />;
}
