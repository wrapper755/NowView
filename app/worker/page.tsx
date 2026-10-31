import type { Metadata } from "next";

import { TopBar } from "@/components/shared/top-bar";
import { WorkerStatusPanel } from "@/components/shared/worker-status";

export const metadata: Metadata = { title: "NowView — 일꾼" };

/** NowView의 일꾼 역할 — Center 들이기·맡은 토픽·최근 일감. 데이터는 클라이언트가 엔진(BFF)에서 받는다(4.3). */
export default function WorkerPage() {
  return (
    <>
      <TopBar />
      <main className="mx-auto w-full max-w-5xl space-y-4 px-4 py-6 sm:px-6">
        <h1 className="text-xl font-semibold">일꾼</h1>
        <WorkerStatusPanel />
      </main>
    </>
  );
}
