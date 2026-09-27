"use client";

import { BookOpen } from "lucide-react";

import { useUiPrefs } from "@/lib/store/ui-prefs";

/**
 * 해설 표시 스위치 — GNB에 상주한다.
 *
 * 켜면 카드마다 "왜 이렇게 보는가"를 설명하는 문장과 화면 하단의 Mock 데이터 주석이
 * 함께 나타난다. 기본은 꺼짐이다(`lib/store/ui-prefs.ts`).
 */
export function CommentaryToggle() {
  const show = useUiPrefs((s) => s.showCommentary);
  const setCommentary = useUiPrefs((s) => s.setCommentary);

  return (
    <button
      type="button"
      onClick={() => setCommentary(!show)}
      aria-pressed={show}
      title={show ? "해설 끄기" : "해설 켜기 — 각 패널을 왜 이렇게 보는지 설명한다"}
      className={
        show
          ? "inline-flex shrink-0 items-center gap-1.5 rounded-md bg-muted px-2 py-1.5 text-xs font-medium text-foreground"
          : "inline-flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
      }
    >
      <BookOpen aria-hidden className="size-3.5" />
      해설
    </button>
  );
}
