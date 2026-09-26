import { BpmTrackerShell } from "@/components/bpm/tracker-shell";

export const metadata = {
  title: "NowView — Live BPM & Agent Process Tracker",
};

export default function BpmTrackerPage() {
  return (
    <main className="mx-auto w-full max-w-7xl space-y-5 px-4 py-6 sm:px-6 lg:px-8">
      <BpmTrackerShell />

      <p className="pb-2 text-xs text-muted-foreground">
        본 화면의 프로세스와 Agent 산출물은 Mock 데이터다. BPM 엔진(LangGraph StateGraph) 및
        실제 Agent 호출은 아직 연결되지 않았다.
      </p>
    </main>
  );
}
