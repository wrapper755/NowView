import type { Metadata } from "next";

import { Sc06ConfirmScreen } from "@/components/sc06/confirm-screen";

export const metadata: Metadata = { title: "NowView — 확인 절차" };

/** 확인 절차(담당 임원 확인 → 종합 → 결론 → 확정 → 대표 보고). 데이터는 클라이언트에서 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc06ConfirmScreen />;
}
