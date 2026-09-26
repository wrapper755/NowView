import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { WorkspaceShell } from "@/components/workspace/workspace-shell";
import { reviewCase } from "@/lib/mock-data/review-case";
import { formatEok } from "@/lib/format";

export const metadata = {
  title: "NowView — Human-Agent Collaboration Station",
};

export default function WorkspacePage() {
  return (
    <main className="mx-auto w-full max-w-7xl space-y-5 px-4 py-6 sm:px-6 lg:px-8">
      <header className="space-y-2">
        <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
          <h1 className="text-xl font-semibold">Human-Agent Collaboration Station</h1>
          <span className="text-sm text-muted-foreground">{reviewCase.subject}</span>
        </div>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted-foreground">
          <span className="tabular-nums">
            전사 영업이익 Gap{" "}
            <span className="font-medium text-foreground">
              {formatEok(reviewCase.profitGap)}
            </span>
          </span>
          <span className="font-mono text-[10px]">{reviewCase.processId}</span>
          <Link
            href="/bpm-tracker"
            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-medium text-foreground hover:bg-muted"
          >
            프로세스에서 이 단계 보기
            <ArrowUpRight aria-hidden className="size-3" />
          </Link>
          <Link
            href="/"
            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-medium text-foreground hover:bg-muted"
          >
            Cockpit
            <ArrowUpRight aria-hidden className="size-3" />
          </Link>
        </div>
      </header>

      <WorkspaceShell reviewCase={reviewCase} />

      <p className="pb-2 text-xs text-muted-foreground">
        본 화면의 보고서·대안·시뮬레이션 결과는 Mock 데이터다. 시뮬레이션 응답 모델은 선형
        근사이며 실제 추정 엔진이 아니다.
      </p>
    </main>
  );
}
