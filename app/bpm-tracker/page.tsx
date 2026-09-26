import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { BpmTrackerShell } from "@/components/bpm/tracker-shell";
import { bpmProcess } from "@/lib/mock-data/bpm-process";

export const metadata = {
  title: "NowView — Live BPM & Agent Process Tracker",
};

export default function BpmTrackerPage() {
  const process = bpmProcess;

  return (
    <main className="mx-auto w-full max-w-7xl space-y-5 px-4 py-6 sm:px-6 lg:px-8">
      <header className="space-y-2">
        <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
          <h1 className="text-xl font-semibold">Live BPM &amp; Agent Process Tracker</h1>
          <span className="text-sm text-muted-foreground">{process.subject}</span>
        </div>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted-foreground">
          <span className="tabular-nums">
            {process.kri.label}{" "}
            <span className="font-medium text-foreground">{process.kri.value}</span>
            <span className="mx-1 text-muted-foreground/60">/</span>
            임계 {process.kri.threshold}
          </span>
          <span className="tabular-nums">착수 {process.startedAt}</span>
          <span className="font-mono text-[10px]">{process.id}</span>
          {/* 두 화면이 같은 사건을 다루므로 왕복할 수 있게 해 둔다. */}
          <Link
            href="/"
            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-medium text-foreground hover:bg-muted"
          >
            Cockpit의 해당 리스크 보기
            <ArrowUpRight aria-hidden className="size-3" />
          </Link>
        </div>
      </header>

      <BpmTrackerShell process={process} />

      <p className="pb-2 text-xs text-muted-foreground">
        본 화면의 프로세스와 Agent 산출물은 Mock 데이터다. BPM 엔진(LangGraph StateGraph) 및
        실제 Agent 호출은 아직 연결되지 않았다.
      </p>
    </main>
  );
}
