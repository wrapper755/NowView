import type { Metadata } from "next";

import { TasksScreen } from "@/components/sc01/tasks-screen";

export const metadata: Metadata = { title: "NowView — UI05 검토·승인 업무" };

/** UI05 검토·승인 업무. 데이터는 클라이언트에서 엔진(BFF)으로 받는다 — 페이지는 정적이다(4.3). */
export default function Page() {
  return <TasksScreen />;
}
