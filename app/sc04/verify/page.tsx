import type { Metadata } from "next";

import { Sc04VerifyScreen } from "@/components/sc04/verify-screen";

export const metadata: Metadata = { title: "NowView — 장면 4 비용·중복 검증" };

/** U402 비용·중복 효과 검증. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc04VerifyScreen />;
}
