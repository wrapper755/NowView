import type { Metadata } from "next";

import { Sc03TasksScreen } from "@/components/sc03/tasks-screen";

export const metadata: Metadata = { title: "NowView — 분석과제 배정·인수" };

/** U36 분석과제 배정과 인수. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc03TasksScreen />;
}
