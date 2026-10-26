import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";

import { ActorSwitcher } from "@/components/sc01/actor-switcher";
import { Sc01SessionSync } from "@/components/sc01/session-sync";
import { CommentaryToggle } from "@/components/shared/commentary-toggle";
import { DemoPlayerSwitch } from "@/components/shared/demo-player-switch";
import { ScenarioNav } from "@/components/shared/scenario-nav";
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
    "INNONOW Management Reference Model 파일럿. 시나리오 1 — 장면 1 고객 생산계획 변경 대응, 장면 2 구매·외주 단가 인상 검토. 사람·AI Agent·BPM이 협업하는 경영 운영 프로토타입.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // next-themes가 hydration 전에 <html>의 class를 바꾸므로 경고를 억제해야 한다.
    <html
      lang="ko"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <ThemeProvider>
          <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
            {/* 좁은 화면에서는 간격을 줄인다 — 24px씩 두 번이면 360px 화면에서 GNB가
                쓸 폭이 그만큼 사라진다. 화면 이동이 해설·테마보다 자주 쓰인다. */}
            <div className="mx-auto flex w-full max-w-7xl items-center gap-3 px-4 py-2.5 sm:gap-6 sm:px-6 lg:px-8">
              <Link href="/" className="flex items-baseline gap-2">
                <span className="text-sm font-semibold tracking-tight">NowView</span>
                <span className="hidden text-xs text-muted-foreground sm:inline">
                  Management Reference Model
                </span>
              </Link>

              {/* 장면 선택 + 그 장면의 화면. 장면은 경로로 가른다(`/sc02/*` = 장면 2). */}
              <ScenarioNav />

              <ActorSwitcher />
              <CommentaryToggle />
              <ThemeToggle />
            </div>

            {/* 화면 안 섹션 이동. 스크롤이 길어(Cockpit 기준 약 3,300px) 찾기 어려운데,
                왼쪽 레일로 두면 GNB와 시선 축이 갈리고 본문까지 밀어낸다 — 같은 줄에 둔다. */}
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
