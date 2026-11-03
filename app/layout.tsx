import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { ThemeProvider } from "@/components/theme-provider";

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
  title: "NowView — 회사별 운영 현황",
  description:
    "Chaeksas BPM 프로세스와 연계해 서비스 태스크를 수행하는 일꾼이자, 회사별 운영 현황을 보여 주는 대시보드. INNONOW Management Reference Model 파일럿.",
};

/**
 * 뼈대만 둔다 — 공통 줄(`TopBar`)은 화면이 둔다: 회사 목록·관리자는 로고·테마뿐이고, 회사 대시보드(`/c/{회사}`)는 회사 이름을
 * 더한다.
 */
export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // next-themes가 hydration 전에 <html>의 class를 바꾸므로 경고를 억제해야 한다.
    <html
      lang="ko"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col pt-12">
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
