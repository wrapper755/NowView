import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { Activity } from "lucide-react";

import { ActorSwitcher } from "@/components/sc01/actor-switcher";
import { Sc01SessionSync } from "@/components/sc01/session-sync";
import { CommentaryToggle } from "@/components/shared/commentary-toggle";
import { DemoPlayerSwitch } from "@/components/shared/demo-player-switch";
import { ScreenNav, WorkHeading, WorkSidebar } from "@/components/shared/scenario-nav";
import { SectionNav } from "@/components/shared/section-nav";
import { ThemeProvider } from "@/components/theme-provider";
import { ThemeToggle } from "@/components/theme-toggle";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "NowView — A제품 경영 현황",
  description:
    "INNONOW Management Reference Model 파일럿. 시나리오 1 — 고객 생산계획 변경 대응부터 완료·성과 검토까지 여섯 업무. 사람·AI Agent·BPM이 협업하는 경영 운영 프로토타입.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // next-themes가 hydration 전에 <html>의 class를 바꾸므로 경고를 억제해야 한다.
    <html
      lang="ko"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      {/* 맨 위는 업무와 무관한 공통 줄(로고·역할·해설·테마) — 화면 폭 전체이고 높이 3rem 고정이다(`pt-12`). 그 아래가
          세 단이다 — 왼쪽 업무(사이드바, `lg:pl-56`), 가운데 머리·본문, 오른쪽 데모 플레이어(xl, 여백은 globals.css의
          `[data-demo-player]`). 좁으면 업무는 가운데 머리의 선택, 플레이어는 하단 바다. 사이드바·플레이어·가운데 머리가
          `top-12`에 맞물리므로 공통 줄 높이를 바꾸면 함께 본다. */}
      <body className="min-h-full flex flex-col pt-12 lg:pl-56">
        <ThemeProvider>
          {/* `<header>`로 두지 않는다 — 섹션 탭이 첫 `header`의 아래 끝으로 스크롤 여백을 잰다(가운데 머리여야 한다). */}
          <div role="banner" className="chrome-ink fixed inset-x-0 top-0 z-50 flex h-12 items-center gap-3 border-b px-4 sm:gap-4 sm:px-6 lg:px-5">
            <Link href="/" className="mr-auto flex items-center gap-2 md:mr-0">
              <span aria-hidden className="flex size-6 items-center justify-center rounded-md bg-brand text-brand-foreground">
                <Activity className="size-3.5" />
              </span>
              <span className="text-sm font-semibold tracking-tight">NowView</span>
              <span className="hidden text-xs text-muted-foreground sm:inline">Management Reference Model</span>
            </Link>
            {/* 시연 환경임을 늘 보인다 — 회사·인물·숫자가 전부 가상이다(2.1). */}
            <span className="mr-auto hidden rounded-full border border-brand/70 bg-brand/20 px-2 py-0.5 text-[10px] font-medium tracking-wide text-foreground md:inline">
              DEMO · 가상 데이터
            </span>
            <ActorSwitcher />
            <CommentaryToggle />
            <ThemeToggle />
          </div>

          <WorkSidebar />
          <header className="sticky top-12 z-30 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
            {/* 지금 업무 — 업무 목록은 왼쪽 사이드바에 있다(좁으면 여기서 고른다). */}
            <div className="mx-auto flex w-full max-w-7xl items-center gap-3 px-4 pt-3 pb-2.5 sm:px-6 lg:px-8">
              <WorkHeading />
            </div>

            {/* 업무에 따라 달라지는 화면 메뉴 — 업무 이름 아래 줄이다. */}
            <ScreenNav />

            {/* 화면 안 섹션 이동. 스크롤이 길어(Cockpit 기준 약 3,300px) 찾기 어렵다 — 화면 메뉴 아래 한 줄. */}
            <SectionNav />
          </header>

          {/* 하단 여백은 데모 플레이어 높이만큼 CSS가 준다(globals.css의
              `[data-demo-player]`). 플레이어가 접히면 여백도 함께 줄어든다. */}
          <div className="flex-1">{children}</div>

          {/* 데모 실행을 여기서만 받는다(SSE, 폴백은 폴링) — 화면마다 받으면 같은
              화면의 두 패널이 서로 다른 순간을 보고, 요청이 패널 수만큼 배로 늘어난다. */}
          <Sc01SessionSync />
          <DemoPlayerSwitch />
        </ThemeProvider>
      </body>
    </html>
  );
}
