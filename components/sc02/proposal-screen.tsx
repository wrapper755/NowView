"use client";

import { useUserName } from "@/components/sc01/bits";
import { BridgeTable, ComparisonNote, Problems } from "@/components/sc02/analysis-parts";
import { AgentCard } from "@/components/sc02/analysis-screen";
import { Sc02Body, Sc02Header, StatusPills, WaitingForms, Won } from "@/components/sc02/bits";
import { Disclosure } from "@/components/shared/disclosure";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock, formatRatio, modelLabel } from "@/lib/sc01/format";
import { APPROVAL_STATUS_LABEL } from "@/lib/sc02/format";
import type { Proposal, Run, Sc02View } from "@/lib/sc02/types";

/**
 * U24 가격인상 보고 기안 — 기존 기안 내용(품목별 단가·적용일·연 구매액 증가)에 협상 결과와 손익 근거를 잇는다.
 * 상신하면 그 버전은 고정이다. 기안가·적용일이 협상안과 다르면 차이 사유가 필요하다(엔진이 422로 막는다).
 */
export function Sc02ProposalScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc02Header id="U24" title="가격인상 보고 기안" question="기존 기안에 협상 결과와 손익 근거가 함께 실렸는가?" />
      <Sc02Body>{(view) => <ProposalView view={view} />}</Sc02Body>
    </main>
  );
}

function ProposalView({ view }: { view: Sc02View }) {
  const neg = view.priceVersions.find((p) => p.version_id === "PV-NEG01");
  const negRun = view.runs.find((r) => r.price_version_id === "PV-NEG01" && !r.is_stale);
  const current = view.proposals.at(-1);
  const run = current ? view.runs.find((r) => r.run_id === current.run_id) : undefined;
  return (
    <>
      <StatusPills view={view} />
      {negRun && negRun.status === "BLOCKED" ? <Problems analysis={negRun.result} /> : null}
      <WaitingForms
        view={view}
        nodes={["Draft_Proposal"]}
        initial={{
          Draft_Proposal: neg
            ? { 기안단가: neg.new_price ? Number(neg.new_price) : null, 기안적용일: neg.effective_date }
            : {},
        }}
        labels={{ Draft_Proposal: "상신" }}
      />
      {current && run ? (
        <ProposalBody proposal={current} run={run} />
      ) : (
        <p className="text-sm text-muted-foreground">아직 상신한 기안이 없다 — 협상안 재분석 뒤 기안한다.</p>
      )}
      {view.proposals.length > 1 ? (
        <Disclosure summary={`이전 기안 버전 ${view.proposals.length - 1}건`}>
          <ul className="space-y-1 text-xs">
            {view.proposals.slice(0, -1).map((p) => (
              <li key={p.proposal_key}>
                <span className="font-mono">{p.proposal_key}</span> {Number(p.price).toLocaleString("ko-KR")}원 · {p.effective_date} ·{" "}
                {APPROVAL_STATUS_LABEL[p.status] ?? p.status} — 이전 승인은 새 버전에 승계하지 않는다
              </li>
            ))}
          </ul>
        </Disclosure>
      ) : null}
      <AgentCard outputs={view.agentOutputs.filter((o) => o.kind === "AG22")} />
    </>
  );
}

export function ProposalBody({ proposal, run }: { proposal: Proposal; run: Run }) {
  const name = useUserName();
  const a = run.result;
  return (
    <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-[3fr_2fr]">
      <Card>
        <CardHeader>
          <CardTitle>
            기안 <span className="font-mono">{proposal.proposal_key}</span>
          </CardTitle>
          <CardDescription>
            {formatClock(proposal.submitted_at)} 상신 · {name(proposal.submitted_by)} · {APPROVAL_STATUS_LABEL[proposal.status] ?? proposal.status} ·
            분석 <span className="font-mono">{proposal.run_id}</span>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[30rem] text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th scope="col" className="py-2 pr-3 font-medium">품목</th>
                  <th scope="col" className="py-2 pr-3 text-right font-medium">기존가</th>
                  <th scope="col" className="py-2 pr-3 text-right font-medium">기안가</th>
                  <th scope="col" className="py-2 pr-3 text-right font-medium">인상률</th>
                  <th scope="col" className="py-2 font-medium">적용일</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b">
                  <th scope="row" className="py-2 pr-3 text-left font-mono font-normal">{a.part_id}</th>
                  <td className="py-2 pr-3 text-right tabular-nums">{Number(a.old_price).toLocaleString("ko-KR")}원</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{Number(proposal.price).toLocaleString("ko-KR")}원</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{formatRatio(a.rate)}</td>
                  <td className="py-2">{proposal.effective_date}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[9rem_1fr]">
            <dt className="text-xs text-muted-foreground">연 구매액 증가</dt>
            <dd>
              당해 잔여 <Won value={a.remaining.increase} /> · 향후 12개월 <Won value={a.next12.increase} />
            </dd>
            <dt className="text-xs text-muted-foreground">인상 필요성</dt>
            <dd>{proposal.reason}</dd>
            {proposal.diff_reason ? (
              <>
                <dt className="text-xs text-muted-foreground">협상안과 차이 사유</dt>
                <dd>{proposal.diff_reason}</dd>
              </>
            ) : null}
            <dt className="text-xs text-muted-foreground">근거</dt>
            <dd className="font-mono text-xs">{[...proposal.evidence_ids, proposal.run_id].join(" · ")}</dd>
          </dl>
          <ComparisonNote analysis={a} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>예상 승인선</CardTitle>
          <CardDescription>AUTH02-v1 — 최종 기안 12개월 구매 증가(VAT 제외·공급사 요청건 합계) ≥ 1천만원이면 대표 승인.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p className="text-base font-semibold">
            구매팀장 → 구매임원{a.ceo_required ? " → 대표이사" : a.ceo_required === false ? " (임원 최종)" : " → 판정 보류"}
          </p>
          <p className="text-xs text-muted-foreground">
            근거 금액 <Won value={a.next12.increase} /> · 실제 대표 단계는 임원 승인 뒤 확정한다
          </p>
          <Disclosure summary="참고 — 모델별 손익(2027 Q3)">
            <ul className="space-y-0.5 text-xs">
              {a.q3_models.map((m) => (
                <li key={m.model_id}>
                  {modelLabel(m.model_id)} 물량 <Won value={m.volume_effect ?? null} signed /> · 단가 <Won value={m.cost_effect ?? null} signed />
                </li>
              ))}
            </ul>
          </Disclosure>
          <Disclosure summary="참고 — 손익 연결(2027·12개월)">
            <BridgeTable periods={a.periods} kinds={["year", "next12"]} />
          </Disclosure>
        </CardContent>
      </Card>
    </div>
  );
}
