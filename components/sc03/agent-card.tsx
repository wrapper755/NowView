"use client";

import { useState } from "react";
import { Bot } from "lucide-react";

import { Disclosure } from "@/components/shared/disclosure";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { sc03Api } from "@/lib/sc03/client";
import type { Sc03View } from "@/lib/sc03/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc03 } from "@/lib/store/sc03";

const TITLE = { AG30: "Agent 손익 설명 초안", AG31: "Agent 회의 요약 · 과제 초안" } as const;

/**
 * Agent 초안(UI45) — **사람의 검토·결론과 다른 카드다**. 근거 id가 붙고 숫자는 규칙 결과에서만 온다. 채택은 기록일
 * 뿐 결론·인수를 대신하지 않는다. 실패하면 사유를 보이고 수동 작성으로 간다(E36) — 원 계산·회신·기록은 그대로다.
 */
export function AgentCard({ view, kind }: { view: Sc03View; kind: "AG30" | "AG31" }) {
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const output = [...view.agentOutputs].reverse().find((o) => o.kind === kind);
  const meetingOpen = view.meetings.some((m) => m.meeting_id === "MT31" && m.state === "IN_PROGRESS");
  const run = async (fn: () => Promise<{ ok: boolean; data?: Sc03View; error?: string; status?: number }>) => {
    setBusy(true);
    setError(null);
    const r = await fn();
    setBusy(false);
    if (r.ok && r.data) useSc03.getState().setLive(r.data);
    else setError(`${r.status} — ${r.error}`);
  };
  if (!output && !(kind === "AG31" && meetingOpen)) return null;
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
            : "회의 질의와 후보 설명을 요약한다 — 포함·제외는 주재자 판단이다."}
          {view.agentMode === "fail" ? " · 시연 모드: 실패 재현(E36)" : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {output?.status === "FAILED" ? (
          <p className="text-xs" style={{ color: "var(--viz-status-serious)" }}>
            초안 생성 실패 — {output.errors[0]}. 수동으로 작성한다. 계산값·회신·회의 기록은 그대로다(0원으로 채우지 않는다).
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
            {kind === "AG31" && meetingOpen ? (
              <Button size="sm" variant="outline" disabled={busy || actor !== "u-fin"} onClick={() => void run(() => sc03Api.agent(demoRunId!, "AG31", actor))}>
                {output ? "다시 요약" : "회의 요약 요청"}
              </Button>
            ) : null}
            {output?.status === "SUCCEEDED" && !output.adopted_by ? (
              <Button size="sm" variant="outline" disabled={busy || actor !== "u-fin"} onClick={() => void run(() => sc03Api.adopt(demoRunId!, output.output_id, actor))}>
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
