import type { Metadata } from "next";

import { Sc05StatusScreen } from "@/components/sc05/status-screen";

export const metadata: Metadata = { title: "NowView — 장면 5 실행과제 현황" };

/** U501 실행과제 현황. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc05StatusScreen />;
}
