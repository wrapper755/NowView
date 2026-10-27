import type { Metadata } from "next";

import { Sc04MeetingScreen } from "@/components/sc04/meeting-screen";

export const metadata: Metadata = { title: "NowView — 장면 4 대표 질의" };

/** U405 대표 질의·애로 조정. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc04MeetingScreen />;
}
