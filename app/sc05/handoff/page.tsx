import type { Metadata } from "next";

import { Sc05HandoffScreen } from "@/components/sc05/handoff-screen";

export const metadata: Metadata = { title: "NowView — 후속 관리·인계" };

/** U508 실행·위험 후속 관리. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc05HandoffScreen />;
}
