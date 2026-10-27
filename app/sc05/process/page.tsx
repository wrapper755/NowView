import type { Metadata } from "next";

import { Sc05ProcessScreen } from "@/components/sc05/process-screen";

export const metadata: Metadata = { title: "NowView — 장면 5 BPM 흐름" };

/** BPM 흐름. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc05ProcessScreen />;
}
