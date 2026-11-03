"use client";

import { Bot, Clock, TriangleAlert } from "lucide-react";

import { useUserName } from "@/components/sc01/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { CompanySiteNote } from "@/components/shared/company-site-note";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock, TASK_TYPE_LABEL } from "@/lib/sc01/format";
import type { AgentDraft, AgentOutput } from "@/lib/sc01/types";

/**
 * Agent 검토 지원 — **AI 초안**이다. 담당자 검토 의견과 따로 둔다(AG-03).
 *
 * * 엔진이 숫자·근거 ID를 규칙 결과와 대조해 통과한 것만 초안으로 온다. 실패한 응답은 화면에
 *   오지 않고 실패 사유만 온다(AG-01).
 * * 30초를 넘기면 "지연"으로 보인다(AG-02, 실제 시간). 엔진이 한 번 자동 재시도하고, 그 뒤에는
 *   다시 생성하거나 직접 검토한다 — 검토는 초안 없이도 끝난다(UI04-02).
 * * 「의견에 가져오기」(채택)·「다시 생성」은 회사 사이트에서 한다 — 이 화면은 초안과 그 기록을 보인다(읽기 전용, role-split §5.5).
 *   원본 초안은 바뀌지 않는다.
 */
export function AgentPanel({ runId, outputs }: { runId: string; outputs: AgentOutput[] }) {
  const nameOf = useUserName();
  const mine = outputs.filter((o) => o.run_id === runId);
  const latest = mine.at(-1);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <Bot aria-hidden className="size-4" /> Agent 검토 지원 — AI 초안
        </CardTitle>
        <CardDescription>판단과 승인은 사람이 한다.</CardDescription>
        <Commentary block>
          <p className="text-[13px] text-muted-foreground">
            규칙 계산값을 인용한 초안이다. 숫자·근거가 계산 결과와 다르면 엔진이 거절한다.
          </p>
        </Commentary>
      </CardHeader>
      <CardContent className="space-y-3">
        {!latest ? (
          <p className="text-sm text-muted-foreground">이 계산에 대한 초안 요청이 없다.</p>
        ) : (
          <>
            <Status output={latest} />
            {latest.status === "SUCCEEDED" && latest.draft ? <DraftView draft={latest.draft} /> : null}
            {latest.status === "FAILED" ? (
              <div className="space-y-1 rounded-md border p-2 text-xs">
                <p className="flex items-center gap-1 font-medium">
                  <TriangleAlert aria-hidden className="size-3.5" style={{ color: "var(--viz-status-serious)" }} />
                  초안을 만들지 못했다 — 담당자가 직접 검토한다(규칙 계산과 업무는 그대로다)
                </p>
                <ul className="list-disc space-y-0.5 pl-4 text-muted-foreground">
                  {latest.errors.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {latest.adopted_by ? (
              <p className="text-xs text-muted-foreground">
                {formatClock(latest.adopted_at)} {nameOf(latest.adopted_by)}가 의견에 가져왔다
              </p>
            ) : null}
          </>
        )}

        <CompanySiteNote>초안 채택(의견에 가져오기)·다시 생성은 회사 사이트에서 한다.</CompanySiteNote>
        {mine.length > 1 ? (
          <Commentary block>
            <p className="text-[11px] text-muted-foreground">
              이전 초안 {mine.length - 1}건은 보존되어 있다 (
              {mine
                .slice(0, -1)
                .map((o) => o.output_id)
                .join(", ")}
              ).
            </p>
          </Commentary>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Status({ output }: { output: AgentOutput }) {
  const label =
    output.status === "RUNNING"
      ? output.delayed
        ? "지연 — 30초를 넘겼다"
        : "생성 중"
      : output.status === "SUCCEEDED"
        ? "검증 통과"
        : "실패";
  return (
    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      <span className="inline-flex items-center gap-1 font-medium">
        {output.status === "RUNNING" ? <Clock aria-hidden className="size-3.5" /> : null}
        {output.output_id} · {label}
      </span>
      <Commentary>
        <span className="text-muted-foreground">
          {output.provenance ?? output.mode}
          {output.latency_ms !== null ? ` · ${(output.latency_ms / 1000).toFixed(1)}초` : ""}
          {output.attempts > 1 ? ` · ${output.attempts}회 시도` : ""}
          {output.prompt_version ? ` · ${output.prompt_version}` : ""}
        </span>
      </Commentary>
    </p>
  );
}

function DraftView({ draft }: { draft: AgentDraft }) {
  // 요약 한 문단만 먼저 — 사실·질문·제안·한계·근거를 다 펼치면 담당자 의견 폼보다 길어진다.
  return (
    <div className="space-y-3 rounded-md border border-dashed p-3 text-sm">
      <p>{draft.summary}</p>
      <Disclosure summary="사실·질문·근거 보기">
        <div className="space-y-2">
          <Section title="확인된 사실" items={draft.findings} />
          <Section title="확인 질문" items={draft.questions} />
          {draft.suggested_tasks.length > 0 ? (
            <div>
              <p className="text-xs font-medium text-muted-foreground">검토 제안 (배정은 사람이 한다)</p>
              <ul className="list-disc pl-4 text-xs">
                {draft.suggested_tasks.map((t) => (
                  <li key={t.type + t.reason}>
                    {TASK_TYPE_LABEL[t.type] ?? t.type} — {t.reason}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <Section title="한계" items={draft.limitations} />
          <p className="text-[11px] text-muted-foreground">근거: {draft.evidence_refs.join(" · ")}</p>
        </div>
      </Disclosure>
    </div>
  );
}

function Section({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{title}</p>
      <ul className="list-disc pl-4 text-xs">
        {items.map((i) => (
          <li key={i}>{i}</li>
        ))}
      </ul>
    </div>
  );
}
