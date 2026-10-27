import type { Metadata } from "next";

import { Sc05ChangesScreen } from "@/components/sc05/changes-screen";

export const metadata: Metadata = { title: "NowView — 장면 5 변경정보·구매 대응" };

/** U504 생산 변경정보·구매 대응. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc05ChangesScreen />;
}
