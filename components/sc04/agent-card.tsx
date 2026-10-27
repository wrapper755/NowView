"use client";

import { useState } from "react";
import { Bot } from "lucide-react";

import { Disclosure } from "@/components/shared/disclosure";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { sc04Api } from "@/lib/sc04/client";
import type { Sc04View } from "@/lib/sc04/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc04 } from "@/lib/store/sc04";

type Kind = "AG41" | "AG42" | "AG43";
const TITLE: Record<Kind, string> = {
  AG41: "Agent 효과 검증·비교 요약",
  AG42: "Agent 대표 질의 후보",
  AG43: "Agent 회의록·승인서 초안",
};
const HINT: Record<Kind, string> = {
  AG41: "검증이 통과하면 서비스 태스크가 만든다 — 계산 결과와 근거 ID만 인용한다.",
  AG42: "회의 중 질의 후보를 정리한다 — 후보는 Agent 초안이며 현업 답변이 아니다.",
  AG43: "대표 결정 뒤 회의록·승인서 초안을 정리한다 — 확정·인수는 사람이 한다.",
};

/**
 * Agent 초안(AC417) — **사람이 확인한 발언·결정과 다른 카드다**. 근거 id가 붙고 숫자는 계산 결과에서만 온다. 채택은
 * 기록일 뿐 추천·승인·인수를 대신하지 않는다. 실패하면 사유를 보이고 수동 작성으로 간다(E408).
 */
export function AgentCard({ view, kind }: { view: Sc04View; kind: Kind }) {
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const output = [...view.agentOutputs].reverse().find((o) => o.kind === kind);
  const canRequest =
    (kind === "AG42" && view.meeting?.state === "IN_PROGRESS") || (kind === "AG43" && view.decision !== null && view.approvals.length === 0);
  const manager = actor === "u-fin" || actor === "u-fin-exec";
  const run = async (fn: () => Promise<{ ok: boolean; data?: Sc04View; error?: string; status?: number }>) => {
    setBusy(true);
    setError(null);
    const r = await fn();
    setBusy(false);
    if (r.ok && r.data) useSc04.getState().setLive(r.data);
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
            ? `${output.output_id} · ${formatClock(output.created_at)} · ${output.prompt_version} · 근거 ${output.source_version ?? "—"} · ${output.adopted_by ? "채택됨(검토 기록)" : "미검토"}`
            : HINT[kind]}
          {view.agentMode === "fail" ? " · 시연 모드: 실패 재현(E408)" : ""}
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
            <Disclosure summary={`근거 있는 문장 ${output.draft.findings.length}건 · 질문 ${output.draft.questions.length}건`}>
              <ul className="list-disc space-y-1 pl-4 text-xs">
                {output.draft.findings.map((f) => (
                  <li key={f.text}>
                    {f.text} <span className="font-mono text-muted-foreground">[{f.evidence_refs.join(", ")}]</span>
                  </li>
                ))}
              </ul>
              {output.draft.questions.length ? (
                <ul className="mt-2 list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
                  {output.draft.questions.map((q) => (
                    <li key={q}>{q}</li>
                  ))}
                </ul>
              ) : null}
            </Disclosure>
            {output.draft.draft_text ? <p className="rounded-md bg-muted px-3 py-2 text-xs">{output.draft.draft_text}</p> : null}
          </>
        ) : null}
        {!view.historical ? (
          <div className="flex flex-wrap gap-2">
            {canRequest ? (
              <Button size="sm" variant="outline" disabled={busy || !manager} onClick={() => void run(() => sc04Api.agent(demoRunId!, kind, actor))}>
                {output ? "다시 만들기" : "초안 요청"}
              </Button>
            ) : null}
            {output?.status === "SUCCEEDED" && !output.adopted_by ? (
              <Button size="sm" variant="outline" disabled={busy || !manager} onClick={() => void run(() => sc04Api.adopt(demoRunId!, output.output_id, actor))}>
                검토 후 채택 기록
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
