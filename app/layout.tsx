import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import {
  Activity,
  FlaskConical,
  GaugeCircle,
  ListChecks,
  Users,
  type LucideIcon,
} from "lucide-react";

import { DemoPlayer } from "@/components/demo/demo-player";
import { StoreHydrator } from "@/components/demo/store-hydrator";
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
  title: "NowView — Executive Cockpit",
  description:
    "INNONOW Management Reference Model 파일럿. 사람과 멀티 AI Agent가 협업하는 경영 운영 플랫폼 프로토타입.",
};

/**
 * GNB — CLAUDE.md 4장의 5개 화면.
 *
 * `href`가 없는 항목은 아직 라우트가 없다. 링크로 걸면 404가 되므로 비활성 표시만 한다.
 * 해당 화면을 만들 때 `href`를 채운다.
 */
const NAV_ITEMS: Array<{ label: string; icon: LucideIcon; href?: string }> = [
  { label: "Executive Cockpit", icon: GaugeCircle, href: "/" },
  { label: "BPM & Agent Tracker", icon: Activity, href: "/bpm-tracker" },
  { label: "Collaboration Station", icon: Users, href: "/workspace" },
  { label: "Rolling Plan", icon: ListChecks, href: "/rolling-plan" },
  { label: "Evolution Lab", icon: FlaskConical, href: "/evolution" },
];

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
            <div className="mx-auto flex w-full max-w-7xl items-center gap-6 px-4 py-2.5 sm:px-6 lg:px-8">
              <Link href="/" className="flex items-baseline gap-2">
                <span className="text-sm font-semibold tracking-tight">NowView</span>
                <span className="hidden text-xs text-muted-foreground sm:inline">
                  Management Reference Model
                </span>
              </Link>

              <nav aria-label="주요 화면" className="min-w-0 flex-1">
                <ul className="flex items-center gap-1 overflow-x-auto">
                  {NAV_ITEMS.map(({ label, icon: Icon, href }) => (
                    <li key={label} className="shrink-0">
                      {href ? (
                        <Link
                          href={href}
                          className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-muted"
                        >
                          <Icon aria-hidden className="size-3.5" />
                          {label}
                        </Link>
                      ) : (
                        <span
                          aria-disabled="true"
                          title="아직 구현되지 않은 화면"
                          className="inline-flex cursor-not-allowed items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-muted-foreground/60"
                        >
                          <Icon aria-hidden className="size-3.5" />
                          {label}
                          <span className="rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">
                            준비중
                          </span>
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </nav>

              <ThemeToggle />
            </div>
          </header>

          {/* 플로팅 플레이어가 화면 하단을 가리므로 그만큼 여백을 둔다.
              플레이어 최대 높이 170px + 하단 오프셋 16px = 186px이 필요하다(측정값).
              내레이션이 길어지면 플레이어가 커지므로 `lib/demo-scenario.ts`의 길이 제약과 함께 본다. */}
          <div className="flex-1 pb-48">{children}</div>

          <StoreHydrator />
          <DemoPlayer />
        </ThemeProvider>
      </body>
    </html>
  );
}
