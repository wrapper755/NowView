import type { Metadata } from "next";

import { Sc02ProcessScreen } from "@/components/sc02/process-screen";

export const metadata: Metadata = { title: "NowView — SC02 BPM 흐름" };

/** SC02 BPM 흐름(BPMN 캔버스). 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc02ProcessScreen />;
}
