import type { Metadata } from "next";

import { Sc04ApprovalScreen } from "@/components/sc04/approval-screen";

export const metadata: Metadata = { title: "NowView — 포괄 승인" };

/** U406 대표 포괄 승인. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc04ApprovalScreen />;
}
