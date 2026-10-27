import type { Metadata } from "next";

import { Sc04ReportScreen } from "@/components/sc04/report-screen";

export const metadata: Metadata = { title: "NowView — 장면 4 월간회의 보고" };

/** U404 월간 경영회의 보고. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc04ReportScreen />;
}
