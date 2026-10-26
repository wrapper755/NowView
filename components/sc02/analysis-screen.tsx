"use client";

import { useState } from "react";
import { Bot, CheckCircle2 } from "lucide-react";

import { useUserName } from "@/components/sc01/bits";
import {
  AnalysisCards,
  Assumptions,
  BridgeTable,
  ComparisonNote,
  MonthlyTable,
  Problems,
  RunMeta,
} from "@/components/sc02/analysis-parts";
import { Sc02Body, Sc02Header, StatusPills, WaitingForms } from "@/components/sc02/bits";
import { Disclosure } from "@/components/shared/disclosure";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { sc02Api } from "@/lib/sc02/client";
import { AGENT_KIND_LABEL, KIND_LABEL } from "@/lib/sc02/format";
import type { AgentOutput, Sc02View } from "@/lib/sc02/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc02 } from "@/lib/store/sc02";

/**
 * U22 사전 검토 및 영향분석 — 보고 기록 → 요청안 분석 → (협상) → 협상안 재분석.
 *
 * **생성된 안만 고른다**(U22-B). 한 번에 한 안을 보이고 여러 안을 더하지 않는다. 낡은 run(입력이 바뀐 이전
 * 결과)은 「이전 결과」로 따로 보인다 — 최신 성공처럼 보이게 하지 않는다(U22-03).
 */
export function Sc02AnalysisScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc02Header id="U22" title="사전 검토 · 영향분석" question="이 인상이 구매액과 제품 손익, 목표 달성에 얼마나 영향을 주는가?" />
      <Sc02Body>{(view) => <Analysis view={view} />}</Sc02Body>
    </main>
  );
}

function Analysis({ view }: { view: Sc02View }) {
  const name = useUserName();
  const runs = view.runs;
  const [picked, setPicked] = useState<string | null>(null);
  const latest = [...runs].reverse().find((r) => !r.is_stale && (r.kind === "NEGOTIATION" || r.kind === "REQUEST"));
  const run = runs.find((r) => r.run_id === picked) ?? latest ?? runs.at(-1);
  const report = view.report;
  const outputs = view.agentOutputs.filter((o) => run && o.run_id === run.run_id);

  return (
    <>
      <StatusPills view={view} />

      <Card>
        <CardHeader>
          <CardTitle>팀장 보고 · 협의</CardTitle>
          <CardDescription>구매담당이 구두보고 결과를 적는다 — 별도 전자승인 단계가 아니다(CT22).</CardDescription>
        </CardHeader>
        <CardContent className="text-sm">
          {report ? (
            <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[8rem_1fr]">
              <dt className="text-xs text-muted-foreground">일시 · 기록</dt>
              <dd>
                {formatClock(report.reported_at)} · {name(report.reported_by)}
              </dd>
              <dt className="text-xs text-muted-foreground">참여자</dt>
              <dd>{report.participants}</dd>
              <dt className="text-xs text-muted-foreground">요청 요약</dt>
              <dd>{report.summary}</dd>
              <dt className="text-xs text-muted-foreground">검토 필요성 · 방향</dt>
              <dd>
                {report.need} · {report.negotiation_direction || "—"}
              </dd>
              <dt className="text-xs text-muted-foreground">결론</dt>
              <dd>{report.conclusion}</dd>
            </dl>
          ) : (
            <p className="text-muted-foreground">아직 보고 기록이 없다.</p>
          )}
        </CardContent>
      </Card>

      <WaitingForms
        view={view}
        nodes={["Report_Lead", "Confirm_Analysis", "Confirm_Reanalysis"]}
        initial={{ Confirm_Analysis: { 협상기한: "2027-06-21T18:00:00+09:00" } }}
        labels={{ Report_Lead: "보고 기록", Confirm_Analysis: "분석 실행", Confirm_Reanalysis: "재분석 실행" }}
      />

      {runs.length === 0 ? (
        <p className="text-sm text-muted-foreground">아직 분석이 없다 — 보고 뒤 요청안 영향분석을 실행한다.</p>
      ) : run ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>분석 안</CardTitle>
              <CardDescription>생성된 안만 고를 수 있다. 다른 안을 함께 합산하지 않는다.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap gap-1" role="tablist" aria-label="분석 안 선택">
                {runs.map((r) => (
                  <button
                    key={r.run_id}
                    type="button"
                    role="tab"
                    aria-selected={r.run_id === run.run_id}
                    onClick={() => setPicked(r.run_id)}
                    className={
                      r.run_id === run.run_id
                        ? "rounded-md border bg-muted px-2.5 py-1 text-xs font-medium"
                        : "rounded-md border px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
                    }
                  >
                    {KIND_LABEL[r.kind]} <span className="font-mono">{r.run_id}</span>
                    {r.is_stale ? " · 이전" : ""}
                    {r.status === "BLOCKED" ? " · 미산출" : ""}
                  </button>
                ))}
              </div>
              <RunMeta run={run} />
              <Problems analysis={run.result} />
              <ComparisonNote analysis={run.result} />
            </CardContent>
          </Card>

          <AnalysisCards run={run} />

          <Card>
            <CardHeader>
              <CardTitle>손익 연결 — 이 안 기준</CardTitle>
              <CardDescription>
                F01+C01 → F02+C01(장면 1 물량) → F02+이 안(장면 2 단가). 고정비는 공장 월 1회 차감, 모델 배부 없음.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <BridgeTable periods={run.result.periods} kinds={["remaining", "year", "next12"]} />
              <MonthlyTable analysis={run.result} />
              <Disclosure summary="근거 및 가정">
                <Assumptions analysis={run.result} />
              </Disclosure>
            </CardContent>
          </Card>

          <AgentCard outputs={outputs} />
        </>
      ) : null}
    </>
  );
}

/**
 * Agent 초안 — 담당자 의견과 **다른 카드**다(AG-23). 채택은 사실만 남기고 원본을 바꾸지 않는다. 실패해도
 * 규칙 계산과 수동 검토는 그대로 간다(X09-B).
 */
export function AgentCard({ outputs }: { outputs: AgentOutput[] }) {
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const name = useUserName();
  const historical = useSc02((s) => s.past !== null);
  const [error, setError] = useState<string | null>(null);
  if (outputs.length === 0) return null;
  const adopt = async (id: string) => {
    if (!demoRunId) return;
    const r = await sc02Api.adopt(demoRunId, id, actor);
    if (r.ok) useSc02.getState().setLive(r.data);
    else setError(`${r.status} — ${r.error}`);
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>AI 초안 — 검토 지원</CardTitle>
        <CardDescription>규칙 계산 결과를 인용한 초안이다. 판단·결재는 사람이 한다. 승인자에게는 담당자 확인 여부가 함께 보인다.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {outputs.map((o) => (
          <div key={o.output_id} className="space-y-2 rounded-md border px-3 py-2">
            <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Bot aria-hidden className="size-3.5" />
              <span className="font-medium text-foreground">{AGENT_KIND_LABEL[o.kind]}</span>
              <span className="font-mono">{o.output_id}</span>
              <span>{formatClock(o.created_at)}</span>
              {o.stale ? <span>이전 자료 기준</span> : null}
              {o.adopted_by ? (
                <span className="inline-flex items-center gap-1 text-foreground">
                  <CheckCircle2 aria-hidden className="size-3" style={{ color: "var(--viz-status-good)" }} />
                  {name(o.adopted_by)} 확인·채택
                </span>
              ) : (
                <span>담당자 미확인</span>
              )}
            </p>
            {o.status === "FAILED" ? (
              <p className="text-sm">
                초안 생성 실패 — 수동으로 검토한다. <span className="text-xs text-muted-foreground">{o.errors.at(-1)}</span>
              </p>
            ) : o.draft ? (
              <>
                <p className="text-sm">{o.draft.summary}</p>
                <Disclosure summary={`근거 ${o.draft.findings.length}건 · 확인 질문 ${o.draft.questions.length}건`}>
                  <ul className="space-y-1 text-xs">
                    {o.draft.findings.map((f) => (
                      <li key={f.text}>
                        {f.text} <span className="font-mono text-muted-foreground">[{f.evidence_refs.join(", ")}]</span>
                      </li>
                    ))}
                  </ul>
                  <ul className="mt-2 space-y-0.5 text-xs text-muted-foreground">
                    {o.draft.questions.map((q) => (
                      <li key={q}>? {q}</li>
                    ))}
                  </ul>
                  {o.draft.draft_text ? <p className="mt-2 rounded bg-muted/40 px-2 py-1 text-xs">{o.draft.draft_text}</p> : null}
                </Disclosure>
                {!o.adopted_by ? (
                  <Button size="sm" variant="outline" className="h-7 text-[11px]" disabled={historical} onClick={() => void adopt(o.output_id)}>
                    확인·채택 기록
                  </Button>
                ) : null}
              </>
            ) : null}
          </div>
        ))}
        {error ? (
          <p role="alert" className="text-xs" style={{ color: "var(--viz-status-critical)" }}>
            거절됨: {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
