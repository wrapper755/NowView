"use client";

import { useUiPrefs } from "@/lib/store/ui-prefs";

/**
 * 해설 — 방법론을 설명하는 문장. 기본으로 감춘다.
 *
 * **무엇을 감싸고 무엇을 남길지의 기준**: "이 수치가 무엇인가 · 몇 건인가 · 무엇을
 * 누르면 되는가"는 화면을 쓰는 데 필요하므로 남긴다. "왜 이렇게 보는가 · 이 구분이
 * 왜 중요한가"는 방법론 설명이므로 이 안에 넣는다.
 *
 * 지우지 않는 이유는 그 문장들이 이 파일럿의 내용 자체이기 때문이다 — 시연에서는
 * 켜고 본다. 다만 기본값으로 늘 떠 있으면 정작 봐야 할 수치가 문장에 묻힌다.
 *
 * 문장 일부만 감쌀 때는 `<span>`(기본), 문단·블록째 감쌀 때는 `block`을 준다.
 */
export function Commentary({
  children,
  block = false,
}: {
  children: React.ReactNode;
  block?: boolean;
}) {
  const show = useUiPrefs((s) => s.showCommentary);
  if (!show) return null;
  return block ? <div>{children}</div> : <span>{children}</span>;
}
