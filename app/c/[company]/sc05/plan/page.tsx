import type { Metadata } from "next";

import { Sc05PlanScreen } from "@/components/sc05/plan-screen";

export const metadata: Metadata = { title: "NowView — 상세 실행계획" };

/** U502 상세 실행계획·변경. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc05PlanScreen />;
}
