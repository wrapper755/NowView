"use client";

import { useState } from "react";
import { AlertTriangle } from "lucide-react";

import { useUserName } from "@/components/sc01/bits";
import { AgentCard } from "@/components/sc04/agent-card";
import { Mn, Sc04Body, Sc04Header, WaitingForms } from "@/components/sc04/bits";
import { Disclosure } from "@/components/shared/disclosure";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { sc04Api } from "@/lib/sc04/client";
import { gapWord, OUTCOME_LABEL } from "@/lib/sc04/format";
import type { ApprovalItem, BudgetPolicy, Sc04View } from "@/lib/sc04/types";
import { useSc01 } from "@/lib/store/sc01";

/**
 * U406 결정과 승인서 확정 — 대표가 과제별로 정하고(REV41), 경영관리가 초안을 쓰고, 대표가 승인서·회의록을 **함께**
 * 확정한다. 회의 결정과 유효한 승인서는 다른 상태다. 필수 누락이면 확정되지 않는다(E404). 위임 조항은 승인서 본문에
 * 있고, 예산 전용·초과는 규칙 조회까지만 한다(E407 — 실제 거래 없음).
 */
export function Sc04ApprovalScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc04Header id="U406" title="대표 포괄 승인" question="책임·예산 한도·두 기한·조건을 명확히 해 실행 권한을 주었는가?" />
      <Sc04Body>{(view) => <Approval view={view} />}</Sc04Body>
    </main>
  );
}

function Approval({ view }: { view: Sc04View }) {
  const name = useUserName();
  const dec = view.decision;
  const apr = view.approvals.at(-1);
  const draft = view.approvalDraft;
  const items: Record<string, ApprovalItem> | undefined = apr?.items ?? draft?.items;
  return (
    <>
      <WaitingForms
        view={view}
        nodes={["Decide", "Draft_Approval", "Finalize_Approval"]}
        expect={(n) =>
          n === "Decide" && view.decisionId ? { report: view.decisionId } : n === "Finalize_Approval" && draft ? { approval: draft.version } : undefined
        }
        labels={{ Decide: "결정", Draft_Approval: "초안 저장", Finalize_Approval: "승인" }}
      />
      {dec ? (
        <Card>
          <CardHeader>
            <CardTitle>대표 결정 {dec.decision_id}</CardTitle>
            <CardDescription>
              {name(dec.decided_by)} {formatClock(dec.decided_at)} · 기준 {dec.report_ref} · 승인 범위 효과 <Mn value={dec.approved_effect} />백만원 · 연간{" "}
              {gapWord(dec.gap)} <Mn value={dec.gap} />
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <ul className="space-y-1 text-sm">
              {Object.values(dec.items).map((it) => (
                <li key={it.alt_id}>
                  <span className="font-mono text-xs">{it.alt_id}</span> <span className="font-medium">{OUTCOME_LABEL[it.outcome]}</span> — {it.reason}
                  {it.condition_refs?.length ? <span className="ml-1 text-xs text-muted-foreground">조건 {it.condition_refs.join(", ")}</span> : null}
                </li>
              ))}
            </ul>
            {dec.conditional.length ? (
              <p className="text-xs text-muted-foreground">
                조건부 효과를 뺀 비교 — 연간 {gapWord(dec.gap_excl_conditional)} <Mn value={dec.gap_excl_conditional} />백만원(승인된 다른 시나리오가 아니다)
              </p>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {draft && !apr ? (
        <Card>
          <CardHeader>
            <CardTitle>승인서 초안 v{draft.version}</CardTitle>
            <CardDescription>
              {name(draft.drafted_by)} {formatClock(draft.drafted_at)} · 기준 {draft.decision_ref}
              {draft.returned ? ` · 대표 보완 요청: ${draft.returned.opinion}` : ""}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {draft.missing.length ? (
              <ul className="space-y-0.5 text-xs">
                {draft.missing.map((m) => (
                  <li key={m} className="flex items-center gap-1.5">
                    <AlertTriangle aria-hidden className="size-3.5" style={{ color: "var(--viz-status-serious)" }} />
                    {m}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">필수 항목이 다 있다 — 대표 확정을 기다린다.</p>
            )}
          </CardContent>
        </Card>
      ) : null}

      {apr || draft ? (
        <Card>
          <CardHeader>
            <CardTitle>{apr ? `승인서 ${apr.approval_id} · ${apr.minutes_ref}` : "승인 항목(초안)"}</CardTitle>
            <CardDescription>
              {apr
                ? `대표 ${name(apr.approved_by)} ${formatClock(apr.approved_at)} · 판단본 ${apr.decision_ref}(해시 ${apr.decision_hash}) · 전체 책임 ${name(apr.overall_owner)}`
                : `전체 책임 ${name(draft!.overall_owner)}`}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 overflow-x-auto">
            <table className="w-full min-w-[680px] text-sm" aria-label="과제별 승인 항목">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-1.5 pr-3 font-medium">대안</th>
                  <th className="py-1.5 pr-3 font-medium">결정</th>
                  <th className="py-1.5 pr-3 font-medium">책임 임원</th>
                  <th className="py-1.5 pr-3 text-right font-medium">배분 한도</th>
                  <th className="py-1.5 pr-3 font-medium">계획 제출</th>
                  <th className="py-1.5 font-medium">과제 완료</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {Object.values(items ?? {}).map((it) => (
                  <tr key={it.alt_id}>
                    <th scope="row" className="py-1.5 pr-3 text-left font-mono text-xs font-normal">
                      {it.alt_id}
                    </th>
                    <td className="py-1.5 pr-3 text-xs">
                      {OUTCOME_LABEL[it.decision]}
                      {it.conditions.length ? ` · ${it.conditions.join(", ")}` : ""}
                    </td>
                    <td className="py-1.5 pr-3 text-xs">{name(it.owner)}</td>
                    <td className="py-1.5 pr-3 text-right">
                      <Mn value={it.budget} empty="미입력" />
                    </td>
                    <td className="py-1.5 pr-3 text-xs">{it.plan_due ? formatClock(it.plan_due) : "미입력"}</td>
                    <td className="py-1.5 text-xs">{it.completion_due ? formatClock(it.completion_due) : "미입력"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {apr ? (
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs">
                <span>
                  총괄 한도 <Mn value={apr.total_budget} />
                </span>
                <span>
                  미약정 예정 <Mn value={apr.budget_status.planned} />
                </span>
                <span>
                  기약정 미집행 <Mn value={apr.budget_status.committed} />
                </span>
                <span>
                  집행 완료 <Mn value={apr.budget_status.spent} />
                </span>
                <span className="font-medium">
                  한도 여력 <Mn value={apr.budget_status.headroom} />
                </span>
              </div>
            ) : null}
            <p className="text-xs text-muted-foreground">
              한도는 전환·검증·교육 등 일회성 준비비다. 반복 외주·물류·운영비는 기존 운영예산과 정상 품의로 통제한다.
            </p>
          </CardContent>
        </Card>
      ) : null}

      {apr ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>위임 조항 {apr.policy_id}</CardTitle>
              <CardDescription>무보고 전용 불허 · 총괄 한도 안 전용은 전체 책임 임원 승인 · 총괄 초과는 대표 별도 승인</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <p>{apr.delegation}</p>
              <PolicyLookup />
            </CardContent>
          </Card>
          <Disclosure summary={`회의록 ${apr.minutes_ref}`}>
            <p className="text-xs">{view.minutes.at(-1)?.body}</p>
            <p className="mt-1 text-xs text-muted-foreground">기록 {view.minutes.at(-1)?.records.join(", ")}</p>
          </Disclosure>
        </>
      ) : null}
      <AgentCard view={view} kind="AG43" />
    </>
  );
}

/** E407 — 전용·총괄 초과 사례를 규칙으로만 조회한다. 거래·이력을 만들지 않는다. */
function PolicyLookup() {
  const demoRunId = useSc01((s) => s.demoRunId);
  const [answers, setAnswers] = useState<Array<{ q: string; a: BudgetPolicy | string }>>([]);
  const ask = async (q: string, body: Parameters<typeof sc04Api.budgetPolicy>[1]) => {
    if (!demoRunId) return;
    const r = await sc04Api.budgetPolicy(demoRunId, body);
    setAnswers((s) => [...s.filter((x) => x.q !== q), { q, a: r.ok ? r.data : `${r.status} — ${r.error}` }]);
  };
  return (
    <div className="space-y-2 rounded-md border p-3">
      <p className="text-xs text-muted-foreground">예산 변경 경로 조회 — 규칙 설명용이다. 실제 변경 신청·집행 품의는 후속 실행 범위다.</p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={() => void ask("ACT41 → ACT42 1백만원 전용", { kind: "transfer", from: "ACT41", amount: "1000000" })}>
          ACT41 → ACT42 1백만원 전용
        </Button>
        <Button size="sm" variant="outline" onClick={() => void ask("총괄 필요액 19백만원", { kind: "total", amount: "19000000" })}>
          총괄 필요액 19백만원
        </Button>
      </div>
      {answers.map(({ q, a }) => (
        <p key={q} className="text-xs">
          <span className="font-medium">{q}</span> —{" "}
          {typeof a === "string" ? a : `${a.allowed ? "가능" : "제한"} · 승인 ${a.approver ?? "—"} · ${a.rule}`}
        </p>
      ))}
    </div>
  );
}
