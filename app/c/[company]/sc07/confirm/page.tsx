import type { Metadata } from "next";

import { Sc07ConfirmScreen } from "@/components/sc07/confirm-screen";

export const metadata: Metadata = { title: "NowView — 확인·적용 절차" };

/** 확인·적용 절차(검증 → 두 임원 확인 → 운영 설정 반영 → 확인 → 후속 점검). 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc07ConfirmScreen />;
}
