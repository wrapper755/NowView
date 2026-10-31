import type { Metadata } from "next";

import { AdminConsole } from "@/components/admin/admin-console";
import { TopBar } from "@/components/shared/top-bar";

export const metadata: Metadata = { title: "NowView — 관리자", robots: { index: false, follow: false } };

/** NowView 관리자 모드 — 로그인 뒤에만 열린다. 공개 화면에는 링크가 없다(`docs/worker-interfaces.md` §1). */
export default function AdminPage() {
  return (
    <>
      <TopBar />
      <main className="mx-auto w-full max-w-5xl space-y-4 px-4 py-6 sm:px-6">
        <h1 className="text-xl font-semibold">관리자 모드</h1>
        <AdminConsole />
      </main>
    </>
  );
}
