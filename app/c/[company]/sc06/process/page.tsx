import type { Metadata } from "next";

import { Sc06ProcessScreen } from "@/components/sc06/process-screen";

export const metadata: Metadata = { title: "NowView — BPM 흐름" };

/** BPM 흐름(확인 절차). 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc06ProcessScreen />;
}
