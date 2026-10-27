import type { Metadata } from "next";

import { Sc04ActionsScreen } from "@/components/sc04/actions-screen";

export const metadata: Metadata = { title: "NowView — 책임 인수" };

/** U407 실행과제 등록·책임 인수. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc04ActionsScreen />;
}
