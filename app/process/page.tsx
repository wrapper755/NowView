import type { Metadata } from "next";

import { ProcessScreen } from "@/components/sc01/process-screen";

export const metadata: Metadata = { title: "NowView — SC01 업무 흐름(BPMN)" };

/** SC01 업무 흐름(BPMN). 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <ProcessScreen />;
}
