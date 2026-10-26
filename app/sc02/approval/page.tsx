import type { Metadata } from "next";

import { Sc02ApprovalScreen } from "@/components/sc02/approval-screen";

export const metadata: Metadata = { title: "NowView — U25 승인 검토" };

/** U25 승인 검토와 추가 협상지시. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <Sc02ApprovalScreen />;
}
