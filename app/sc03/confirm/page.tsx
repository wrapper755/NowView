import type { Metadata } from "next";

import { Sc03ConfirmScreen } from "@/components/sc03/confirm-screen";

export const metadata: Metadata = { title: "NowView — 장면 3 부서 확인·쟁점" };

/** U33 부서 확인과 쟁점 정리. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc03ConfirmScreen />;
}
