import type { Metadata } from "next";

import { Sc07ImprovementScreen } from "@/components/sc07/improvement-screen";

export const metadata: Metadata = { title: "NowView — 관리모델 개선 및 적용" };

/** U701 관리모델 개선 및 적용. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc07ImprovementScreen />;
}
