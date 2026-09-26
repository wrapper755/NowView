import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { EvolutionShell } from "@/components/evolution/evolution-shell";
import { evolutionLab } from "@/lib/mock-data/evolution-lab";

export const metadata = {
  title: "NowView — Management Evolution Lab",
};

export default function EvolutionPage() {
  return (
    <main className="mx-auto w-full max-w-7xl space-y-5 px-4 py-6 sm:px-6 lg:px-8">
      <header className="space-y-2">
        <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
          <h1 className="text-xl font-semibold">Management Evolution Lab</h1>
          <span className="text-sm text-muted-foreground">
            루프 6단계 — 경영 시스템 자체의 개선
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted-foreground">
          <span>촉발 안건 {evolutionLab.subject}</span>
          <Link
            href="/bpm-tracker"
            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-medium text-foreground hover:bg-muted"
          >
            프로세스 보기
            <ArrowUpRight aria-hidden className="size-3" />
          </Link>
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          앞 단계들이 &ldquo;이번 건을 어떻게 할 것인가&rdquo;를 다뤘다면, 이 단계는
          &ldquo;다음에 같은 일이 생기면 더 빨리 잡히는가&rdquo;를 다룬다. 여기서의 결정은
          다음 루프부터 효력이 생긴다.
        </p>
      </header>

      <EvolutionShell lab={evolutionLab} />

      <p className="pb-2 text-xs text-muted-foreground">
        백테스트 수치는 Mock이다. 채택·보류 결정은 이 화면에만 남으며 실제 프레임워크 배포로
        이어지지 않는다.
      </p>
    </main>
  );
}
