import type { Metadata } from "next";

import { Sc06ReportScreen } from "@/components/sc06/report-screen";

export const metadata: Metadata = { title: "NowView — 보고 요약" };

/** U602 보완조치·추가 과제와 보고 요약. 확인된 보고본을 조회만 한다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc06ReportScreen />;
}
