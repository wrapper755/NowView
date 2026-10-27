import type { Metadata } from "next";

import { Sc05ResultsScreen } from "@/components/sc05/results-screen";

export const metadata: Metadata = { title: "NowView — 장면 5 초기 실행 결과" };

/** U505 초기 실행 결과. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc05ResultsScreen />;
}
