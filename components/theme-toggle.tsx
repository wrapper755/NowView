"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";

/**
 * 라이트/다크 토글. 초기값은 OS 설정(`system`)이고 버튼은 현재 적용된 테마를 뒤집는다.
 *
 * 아이콘 교체를 React 상태가 아니라 `dark:` 변형(CSS)으로 처리한다.
 * 적용 테마는 서버에서 알 수 없으므로 렌더 결과에 반영하면 hydration 불일치가 나는데,
 * CSS로 처리하면 마크업이 양쪽 테마에서 동일해 그 문제가 생기지 않는다.
 * `resolvedTheme`은 렌더가 아니라 클릭 시점에만 읽는다.
 */
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();

  return (
    <Button
      variant="ghost"
      size="icon"
      className="size-8 shrink-0"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
      aria-label="테마 전환"
      title="라이트/다크 전환"
    >
      <Moon aria-hidden className="size-4 dark:hidden" />
      <Sun aria-hidden className="hidden size-4 dark:block" />
    </Button>
  );
}
