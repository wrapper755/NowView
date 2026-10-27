"use client";

import { CheckCircle2, CircleDashed, OctagonAlert, Undo2 } from "lucide-react";

import { useUserName } from "@/components/sc01/bits";
import { Sc02Body, Sc02Header, StatusPills, WaitingForms, Won } from "@/components/sc02/bits";
import { ProposalBody } from "@/components/sc02/proposal-screen";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { APPROVAL_STATUS_LABEL, STEP_LABEL } from "@/lib/sc02/format";
import type { Decision, Sc02View } from "@/lib/sc02/types";

/**
 * U25 승인 검토 · 추가 협상지시 — 현재 승인 차례의 사람만 결정한다(엔진이 같은 권한·상태·버전을 검사한다).
 * 결정 폼은 화면이 본 기안 버전을 함께 보낸다 — 그 사이 새 버전이 나왔으면 409다(U25-03).
 */
export function Sc02ApprovalScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc02Header id="U25" title="승인 검토" question="구매 필요성과 경영 영향을 함께 보고 승인하는가?" />
      <Sc02Body>{(view) => <Approval view={view} />}</Sc02Body>
    </main>
  );
}

const ICON = { 승인: CheckCircle2, 보완: Undo2, 반려: OctagonAlert, 추가협상지시: Undo2 } as const;

function Approval({ view }: { view: Sc02View }) {
  const name = useUserName();
  const current = view.proposals.at(-1);
  const run = current ? view.runs.find((r) => r.run_id === current.run_id) : undefined;
  if (!current || !run) {
    return <p className="text-sm text-muted-foreground">결재할 기안이 없다 — 기안 상신 뒤 결재가 열린다.</p>;
  }
  const steps: Decision["step"][] = ["TEAM", "EXEC", ...(run.result.ceo_required !== false ? (["CEO"] as const) : [])];
  const mine = view.decisions.filter((d) => d.proposal_key === current.proposal_key);
  return (
    <>
      <StatusPills view={view} />
      <WaitingForms
        view={view}
        nodes={["Approve_Lead", "Approve_Exec", "Approve_CEO"]}
        expect={{ proposal: current.proposal_key }}
        labels={{ Approve_Lead: "결정 기록", Approve_Exec: "결정 기록", Approve_CEO: "결정 기록" }}
      />

      <Card>
        <CardHeader>
          <CardTitle>승인선 — {current.proposal_key}</CardTitle>
          <CardDescription>{APPROVAL_STATUS_LABEL[current.status] ?? current.status} · 같은 기안 버전을 순서대로 승인한다</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <ol className="grid gap-2 sm:grid-cols-3">
            {steps.map((step, i) => {
              const d = mine.find((x) => x.step === step);
              // 앞 단계가 승인이 아니면(보완·반려·추가 협상지시) 이 단계는 열리지 않는다 — 「대기」가 아니다.
              const stopped = !d && steps.slice(0, i).some((s) => {
                const prev = mine.find((x) => x.step === s);
                return prev !== undefined && prev.decision !== "승인";
              });
              const Icon = d ? ICON[d.decision] : CircleDashed;
              return (
                <li key={step} className="rounded-md border px-3 py-2 text-sm">
                  <p className="flex items-center gap-1.5 font-medium">
                    <Icon
                      aria-hidden
                      className="size-3.5"
                      style={{ color: d?.decision === "승인" ? "var(--viz-status-good)" : d ? "var(--viz-status-serious)" : "var(--color-muted-foreground)" }}
                    />
                    {STEP_LABEL[step]} {d ? d.decision : stopped ? "진행 안 함" : "대기"}
                  </p>
                  {d ? (
                    <p className="text-xs text-muted-foreground">
                      {name(d.actor)} · {formatClock(d.decided_at)} — {d.comment}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ol>
          {current.authority ? (
            <p className="text-xs text-muted-foreground">
              대표 대상 판정({current.authority.authority_version}) — 12개월 구매 증가 <Won value={current.authority.amount} /> ·
              기준 <Won value={current.authority.threshold} /> → {current.authority.required ? "대표 대상" : "대표 비대상 · 임원 최종 승인"}
            </p>
          ) : null}
        </CardContent>
      </Card>

      {view.instruction ? (
        <Card>
          <CardHeader>
            <CardTitle>추가 협상지시 {view.instruction.instruction_id}</CardTitle>
            <CardDescription>
              {name(view.instruction.by)} · {formatClock(view.instruction.at)} — 미승인 · 재협상 대기
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p>사유: {view.instruction.reason}</p>
            <p>요구조건: {view.instruction.condition}</p>
            <p>
              담당 {name(view.instruction.assignee)} · 기한 {formatClock(view.instruction.due_at)}
            </p>
            <p className="text-xs text-muted-foreground">
              원가 등록과 외주 단가 인상 검토 완료는 막혀 있다. 2차 협상·재기안·재승인은 후속 범위다 — 수익성 통합 분석에는 미확정 자료로만 보인다.
            </p>
          </CardContent>
        </Card>
      ) : null}

      {view.decisions.some((d) => d.proposal_key !== current.proposal_key) ? (
        <Card>
          <CardHeader>
            <CardTitle>이전 버전의 결정</CardTitle>
            <CardDescription>보존하되 새 버전에 승계하지 않는다 — 새 버전은 팀장부터 다시 받는다.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-xs">
              {view.decisions
                .filter((d) => d.proposal_key !== current.proposal_key)
                .map((d) => (
                  <li key={d.decision_id}>
                    <span className="font-mono">{d.proposal_key}</span> {STEP_LABEL[d.step]} {d.decision} · {name(d.actor)} ·{" "}
                    {formatClock(d.decided_at)} — {d.comment}
                  </li>
                ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <ProposalBody proposal={current} run={run} />
    </>
  );
}
