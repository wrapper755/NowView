import type { Metadata } from "next";

import { Sc05ReadyScreen } from "@/components/sc05/ready-screen";

export const metadata: Metadata = { title: "NowView — 조건·품의·착수" };

/** U503 조건·품의·착수. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc05ReadyScreen />;
}
