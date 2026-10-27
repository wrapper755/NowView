"use client";

import { useState } from "react";
import { Bot } from "lucide-react";

import { Disclosure } from "@/components/shared/disclosure";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { sc05Api } from "@/lib/sc05/client";
import { REVIEW_STATUS_LABEL } from "@/lib/sc05/format";
import type { Sc05View } from "@/lib/sc05/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc05 } from "@/lib/store/sc05";

export type AgentKind = "AG51" | "AG52" | "AG53" | "AG54" | "AG55" | "AG56" | "AG57" | "AG58";

const TITLE: Record<AgentKind, string> = {
  AG51: "Agent 계획 초안(AG51)",
  AG52: "Agent 변경 비교(AG52)",
  AG53: "Agent 조건 근거 점검(AG53)",
  AG54: "Agent 고객 변경 요약(AG54)",
  AG55: "Agent 초기 실적 집계 설명(AG55)",
  AG56: "Agent 잔여 운영계획 제안(AG56)",
  AG57: "Agent 전망 대사 설명(AG57)",
  AG58: "Agent 후속 책임 점검(AG58)",
};

/**
 * Agent 초안 — **사람의 확정·확인·승인과 다른 카드다**(P508 「Agent 업무가 명확히 구분되게」). 원 제안·근거·사람 수정
 * 상태를 나란히 보인다. 숫자는 계산 서비스 결과에서만 오고, 근거 id가 붙는다. 고정 초안 재생이면 REPLAY로 보인다.
 * 실패하면 사유를 보이고 수동 작성으로 간다(T530) — 자동 승인으로 우회하지 않는다.
 */
export function AgentCard({
  view,
  kind,
  canRequest,
  onUse,
  useLabel,
}: {
  view: Sc05View;
  kind: AgentKind;
  /** 지금 이 초안을 요청할 수 있는 단계인가 — 화면이 정한다. */
  canRequest: boolean;
  /** 초안을 폼으로 가져오기(사람이 고친 뒤 제출한다). */
  onUse?: (outputId: string) => void;
  useLabel?: string;
}) {
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const output = [...view.agentOutputs].reverse().find((o) => o.kind === kind);
  const run = async (fn: () => Promise<{ ok: boolean; data?: Sc05View; error?: string; status?: number }>) => {
    setBusy(true);
    setError(null);
    const r = await fn();
    setBusy(false);
    if (r.ok && r.data) useSc05.getState().setLive(r.data);
    else setError(`${r.status} — ${r.error}`);
  };
  if (!output && !canRequest) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <Bot aria-hidden className="size-4" />
          {TITLE[kind]}
        </CardTitle>
        <CardDescription>
          {output
            ? `${output.output_id} · ${formatClock(output.created_at)} · ${output.mode} · ${output.prompt_version} · ${REVIEW_STATUS_LABEL[output.review_status] ?? output.review_status}`
            : "제안만 한다 — 확정·확인·승인은 사람이 한다."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {output?.status === "FAILED" ? (
          <p className="text-xs" style={{ color: "var(--viz-status-serious)" }}>
            초안 생성 실패 — {output.errors[0]}. 수동으로 작성한다. 계산값·기록·권한은 그대로다.
          </p>
        ) : null}
        {output?.draft ? (
          <>
            <p>{output.draft.summary}</p>
            <Disclosure summary={`근거 있는 문장 ${output.draft.findings.length}건${output.draft.activities ? ` · 제안 활동 ${output.draft.activities.length}개` : ""}`}>
              <ul className="list-disc space-y-1 pl-4 text-xs">
                {output.draft.findings.map((f) => (
                  <li key={f.text}>
                    {f.text} <span className="font-mono text-muted-foreground">[{f.evidence_refs.join(", ")}]</span>
                  </li>
                ))}
              </ul>
              {output.draft.activities ? (
                <ol className="mt-2 list-decimal space-y-0.5 pl-4 text-xs text-muted-foreground">
                  {output.draft.activities.map((a) => (
                    <li key={a.activity_id}>
                      {a.name} · {a.start}~{a.end} · 협조·비용 미기입
                    </li>
                  ))}
                </ol>
              ) : null}
            </Disclosure>
            {output.draft.draft_text ? <p className="rounded-md bg-muted px-3 py-2 text-xs">{output.draft.draft_text}</p> : null}
          </>
        ) : null}
        {!view.historical ? (
          <div className="flex flex-wrap gap-2">
            {canRequest ? (
              <Button size="sm" variant="outline" disabled={busy || actor === "u-demo"} onClick={() => void run(() => sc05Api.agent(demoRunId!, kind, actor))}>
                {output ? "다시 만들기" : "초안 요청"}
              </Button>
            ) : null}
            {output?.status === "SUCCEEDED" && onUse ? (
              <Button size="sm" variant="outline" onClick={() => onUse(output.output_id)}>
                {useLabel ?? "폼으로 가져오기"}
              </Button>
            ) : null}
            {output?.status === "SUCCEEDED" && output.review_status === "UNREVIEWED" ? (
              <Button size="sm" variant="outline" disabled={busy || actor === "u-demo"} onClick={() => void run(() => sc05Api.review(demoRunId!, output.output_id, actor))}>
                검토 기록
              </Button>
            ) : null}
          </div>
        ) : null}
        {error ? (
          <p role="alert" className="text-xs" style={{ color: "var(--viz-status-critical)" }}>
            거절됨: {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
