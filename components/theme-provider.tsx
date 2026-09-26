"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ComponentProps } from "react";

/**
 * 테마 공급자.
 *
 * `.dark` 클래스를 `<html>`에 붙이는 방식을 쓴다 — Tailwind v4 쪽 설정
 * (`@custom-variant dark (&:is(.dark *))`)과 `globals.css`의 `.dark .viz-root`가
 * 모두 이 클래스를 기준으로 하므로, UI 토큰과 차트 색이 항상 같이 전환된다.
 */
export function ThemeProvider({
  children,
  ...props
}: ComponentProps<typeof NextThemesProvider>) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
      {...props}
    >
      {children}
    </NextThemesProvider>
  );
}
