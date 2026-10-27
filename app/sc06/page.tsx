import type { Metadata } from "next";

import { Sc06ReviewScreen } from "@/components/sc06/review-screen";

export const metadata: Metadata = { title: "NowView — 장면 6 완료·성과 검토" };

/** U601 완료·성과 검토. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc06ReviewScreen />;
}
