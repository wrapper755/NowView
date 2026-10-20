import { ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * 접어 두는 상세 — "자세히 보기".
 *
 * 화면이 글자로 꽉 차 답답하다는 지적에 대한 원칙: **지우지 않고 접는다.** 15행 표·이력·근거처럼
 * 확인할 때만 필요한 것은 닫아 두고, 화면에는 판단에 필요한 숫자와 상태만 먼저 보인다.
 *
 * 네이티브 `<details>`다 — 상태 없이 접근성(키보드·스크린 리더)이 따라오고, 서버 렌더와 클라이언트
 * 렌더가 같아 하이드레이션 걱정이 없다.
 */
export function Disclosure({
  summary,
  children,
  defaultOpen = false,
  className,
}: {
  summary: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
  className?: string;
}) {
  return (
    <details open={defaultOpen} className={cn("group", className)}>
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-xs font-medium text-muted-foreground select-none hover:text-foreground [&::-webkit-details-marker]:hidden">
        <ChevronRight aria-hidden className="size-3.5 transition-transform group-open:rotate-90" />
        {summary}
      </summary>
      <div className="mt-3">{children}</div>
    </details>
  );
}
