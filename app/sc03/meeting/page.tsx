import type { Metadata } from "next";

import { Sc03MeetingScreen } from "@/components/sc03/meeting-screen";

export const metadata: Metadata = { title: "NowView — 장면 3 수시 경영검토회의" };

/** U34 회의 준비 · U35 경영검토와 대안 가능성 탐색. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc03MeetingScreen />;
}
