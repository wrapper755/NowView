import type { Metadata } from "next";

import { Sc03HandoffScreen } from "@/components/sc03/handoff-screen";

export const metadata: Metadata = { title: "NowView — 검토 완료·월간회의 연결" };

/** U37 검토 완료와 월간회의 연결. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc03HandoffScreen />;
}
