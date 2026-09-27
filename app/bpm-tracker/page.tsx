import { BpmTrackerShell } from "@/components/bpm/tracker-shell";
import { Commentary } from "@/components/shared/commentary";

export const metadata = {
  title: "NowView — Live BPM & Agent Process Tracker",
};

export default function BpmTrackerPage() {
  return (
    <main className="mx-auto w-full max-w-7xl space-y-5 px-4 py-6 sm:px-6 lg:px-8">
      <BpmTrackerShell />

      <Commentary block>
        <p className="pb-2 text-xs text-muted-foreground">
          기본은 Mock 데이터이며, 데모 플레이어는 이 모드에서만 동작한다. &ldquo;엔진으로
          실행&rdquo;을 누르면 LangGraph StateGraph 인스턴스가 상태를 소유하고 진행 지점이
          실행의 결과로 정해진다 — 그때는 단계를 임의로 되감을 수 없다.
        </p>
      </Commentary>
    </main>
  );
}
