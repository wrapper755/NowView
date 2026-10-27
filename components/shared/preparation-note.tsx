"use client";

/**
 * 장면 시작의 준비 중 표시 — 앞 업무를 각본으로 끝까지 돌리는 동안 「어디까지 왔는가」를 보인다(엔진
 * `app/preparation.py`, `lib/preparation.ts`). Center 실행이면 몇 분이 걸린다 — 단추가 「준비하는 중…」으로만
 * 멈춰 있으면 멈춘 것인지 도는 것인지 알 수 없다.
 *
 * 화면 글에 「장면 N」을 쓰지 않는다(CLAUDE.md 4.12) — 업무 이름(`WORKS`)으로 쓴다.
 */

import { WORKS } from "@/components/shared/scenario-nav";
import type { Preparation } from "@/lib/preparation";

function workLabel(scene: string): string {
  const n = Number(scene.replace(/^sc0?/, ""));
  return WORKS.find((w) => w.scene === n)?.label ?? scene;
}

/** 「고객 생산계획 변경 대응 EV07 · 외주 단가 인상 검토 D08 진행 중 (2분 10초)」 */
export function preparationText(p: Preparation): string {
  const steps = (p.progress ?? []).map((s) => `${workLabel(s.scene)} ${s.step ?? "시작 전"}`);
  const started = p.startedAt ? Date.parse(p.startedAt) : NaN;
  const seconds = Number.isNaN(started) ? null : Math.max(0, Math.round((Date.now() - started) / 1000));
  const elapsed = seconds === null ? "" : ` (${seconds >= 60 ? `${Math.floor(seconds / 60)}분 ` : ""}${seconds % 60}초)`;
  return `앞 업무를 끝까지 진행하는 중 — ${steps.length ? steps.join(" · ") : "준비"}${elapsed}`;
}

export function PreparationNote({ p }: { p: Preparation | null }) {
  if (!p) return null;
  return (
    <p role="status" className="text-xs text-muted-foreground">
      {preparationText(p)}
    </p>
  );
}
