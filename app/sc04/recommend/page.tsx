import type { Metadata } from "next";

import { Sc04RecommendScreen } from "@/components/sc04/recommend-screen";

export const metadata: Metadata = { title: "NowView — 장면 4 우선 실행안" };

/** U403 우선 실행안 제안. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc04RecommendScreen />;
}
