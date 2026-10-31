import type { Metadata } from "next";

import { Sc02RequestScreen } from "@/components/sc02/request-screen";

export const metadata: Metadata = { title: "NowView — U21 단가 인상 요청 접수" };

/** U21 단가 인상 요청 접수. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc02RequestScreen />;
}
