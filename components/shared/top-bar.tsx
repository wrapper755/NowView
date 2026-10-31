import Link from "next/link";
import { Activity } from "lucide-react";
import type { ReactNode } from "react";

import { ThemeToggle } from "@/components/theme-toggle";

/**
 * 맨 위 공통 줄(로고 · 지금 회사 · 시연 표시 · 테마) — 화면 폭 전체, 높이 3rem 고정(`body pt-12`). 회사 화면은 역할 전환·해설을
 * `children`으로 더한다 — 회사 목록·일꾼 화면에는 역할이 없다.
 * `<header>`로 두지 않는다 — 섹션 탭이 첫 `header`의 아래 끝으로 스크롤 여백을 잰다(가운데 머리여야 한다).
 */
export function TopBar({ company, children }: { company?: { id: string; name: string }; children?: ReactNode }) {
  return (
    <div role="banner" className="chrome-ink fixed inset-x-0 top-0 z-50 flex h-12 items-center gap-3 border-b px-4 sm:gap-4 sm:px-6 lg:px-5">
      <div className="mr-auto flex min-w-0 items-center gap-2 md:mr-0">
        <Link href="/" className="flex shrink-0 items-center gap-2">
          <span aria-hidden className="flex size-6 items-center justify-center rounded-md bg-brand text-brand-foreground">
            <Activity className="size-3.5" />
          </span>
          <span className="text-sm font-semibold tracking-tight">NowView</span>
        </Link>
        {company ? (
          <>
            <span aria-hidden className="text-muted-foreground">/</span>
            <Link href={`/c/${company.id}`} className="truncate text-sm font-medium hover:underline">
              {company.name}
            </Link>
          </>
        ) : (
          <span className="hidden text-xs text-muted-foreground sm:inline">BPM 일꾼 · 회사별 운영 현황</span>
        )}
      </div>
      {/* 시연 환경임을 늘 보인다 — 회사·인물·숫자가 전부 가상이다(2.1). */}
      <span className="mr-auto hidden rounded-full border border-brand/70 bg-brand/20 px-2 py-0.5 text-[10px] font-medium tracking-wide text-foreground md:inline">
        DEMO · 가상 데이터
      </span>
      <Link href="/worker" className="hidden text-xs text-muted-foreground hover:text-foreground sm:inline">
        일꾼
      </Link>
      {children}
      <ThemeToggle />
    </div>
  );
}
