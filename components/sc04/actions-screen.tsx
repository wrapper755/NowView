"use client";

import { BellRing } from "lucide-react";

import { useUserName } from "@/components/sc01/bits";
import { Mn, Sc04Body, Sc04Header, WaitingForms } from "@/components/sc04/bits";
import { Disclosure } from "@/components/shared/disclosure";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { ASSIGNMENT_STATE_LABEL, DIRECTIVE_KIND_LABEL, GATE_LABEL, OUTCOME_LABEL } from "@/lib/sc04/format";
import type { Sc04View } from "@/lib/sc04/types";
import { useSc01 } from "@/lib/store/sc01";

const ACCEPT_NODES: Record<string, string> = {
  ACT41: "Accept_ACT41",
  ACT42: "Accept_ACT42",
  ACT43: "Accept_ACT43",
  SUP41: "Accept_SUP41",
  TOTAL: "Accept_Overall",
};

/**
 * U407 실행과제 등록과 책임 인수 — 유효 승인서로 ACT41~43을 한 번씩 만들고, 전체 책임과 개별 책임·지원·추가 지시
 * 인수를 따로 보인다. 조건부 과제는 조건 미충족 표시를 유지한 채 인수할 수 있다(인수는 조건 이행 완료가 아니다).
 * 상세 활동계획 입력은 없다 — 장면 5다.
 */
export function Sc04ActionsScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc04Header id="U407" title="실행과제 등록·책임 인수" question="회의 결정이 실제 책임 인수로 이어졌는가?" />
      <Sc04Body>{(view) => <Actions view={view} />}</Sc04Body>
    </main>
  );
}

function Actions({ view }: { view: Sc04View }) {
  const name = useUserName();
  const actor = useSc01((s) => s.actor);
  const rate = view.completion.rate;
  const nodes = ["Register_Actions", ...Object.values(ACCEPT_NODES), "Revise_ACT41", "Revise_ACT42", "Revise_ACT43", "Revise_SUP41"];
  const target = Object.fromEntries(Object.entries(ACCEPT_NODES).map(([t, n]) => [n, t]));
  const mine = view.alerts.filter((a) => a.to.includes(actor));
  return (
    <>
      <WaitingForms
        view={view}
        nodes={nodes}
        expect={(n) => {
          const a = view.assignments.find((x) => x.target_id === target[n]);
          return a ? { assignment: a.assignment_version } : undefined;
        }}
        labels={{ Register_Actions: "등록", ...Object.fromEntries(Object.values(ACCEPT_NODES).map((n) => [n, "인수·반려"])) }}
      />
      <Card data-index-skip>
        <CardHeader>
          <CardTitle>
            인수 현황 — 실행과제 {rate.accepted}/{rate.assigned} · 전체 책임 {rate.overall_accepted ? "인수" : "미인수"}
          </CardTitle>
          <CardDescription>현재 배정버전을 본인이 인수한 수다. 대리 인수는 없다. 실무 담당 지정은 임원 책임을 대체하지 않는다.</CardDescription>
        </CardHeader>
      </Card>

      {mine.length ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <BellRing aria-hidden className="size-4" style={{ color: "var(--viz-status-critical)" }} />내 알림 {mine.length}건
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-0.5 text-xs">
              {mine.map((a) => (
                <li key={a.alert_id}>
                  {formatClock(a.at)} — {a.message}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>실행과제·책임 {view.assignments.length}건</CardTitle>
          <CardDescription>
            {view.assignments.length ? `승인 ${view.assignments[0].approval_ref} · 분석과제 4개와 실행과제 수는 같을 필요가 없다(AT32 → ACT42·ACT43)` : "승인서가 확정되면 경영관리가 등록한다."}
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {view.assignments.length ? (
            <table className="w-full min-w-[820px] text-sm" aria-label="실행과제와 책임">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-1.5 pr-3 font-medium">대상</th>
                  <th className="py-1.5 pr-3 font-medium">책임</th>
                  <th className="py-1.5 pr-3 text-right font-medium">예상효과</th>
                  <th className="py-1.5 pr-3 text-right font-medium">한도</th>
                  <th className="py-1.5 pr-3 font-medium">계획 제출 · 완료</th>
                  <th className="py-1.5 pr-3 font-medium">실행 착수</th>
                  <th className="py-1.5 font-medium">인수</th>
                </tr>
              </thead>
              <tbody className="divide-y align-top">
                {view.assignments.map((a) => (
                  <tr key={a.target_id}>
                    <th scope="row" className="py-1.5 pr-3 text-left font-normal">
                      <span className="font-mono text-xs">{a.target_id}</span>{" "}
                      {a.kind === "ACTION" ? (
                        <span className="text-xs">
                          {a.alt_id} · {a.analysis_task} · {OUTCOME_LABEL[a.decision ?? ""]}
                        </span>
                      ) : a.kind === "SUPPORT" ? (
                        <span className="text-xs">지원 지시</span>
                      ) : (
                        <span className="text-xs">전체 책임 + {a.directive}</span>
                      )}
                    </th>
                    <td className="py-1.5 pr-3 text-xs">
                      {name(a.owner)}
                      {a.worker ? <span className="block text-muted-foreground">실무 {name(a.worker)}</span> : null}
                    </td>
                    <td className="py-1.5 pr-3 text-right">{a.expected_effect ? <Mn value={a.expected_effect} /> : "—"}</td>
                    <td className="py-1.5 pr-3 text-right">{a.budget ? <Mn value={a.budget} /> : a.total_budget ? <Mn value={a.total_budget} /> : "—"}</td>
                    <td className="py-1.5 pr-3 text-xs">{a.plan_due ? `${formatClock(a.plan_due)} · ${formatClock(a.completion_due)}` : "—"}</td>
                    <td className="py-1.5 pr-3 text-xs">{a.execution_gate ? (GATE_LABEL[a.execution_gate] ?? a.execution_gate) : "—"}</td>
                    <td className="py-1.5 text-xs">
                      {ASSIGNMENT_STATE_LABEL[a.state]} · v{a.assignment_version}
                      {a.accepted_at ? <span className="block text-muted-foreground">{formatClock(a.accepted_at)}</span> : null}
                      {a.state === "RETURNED" && a.return_reason ? <span className="block">반려: {a.return_reason}</span> : null}
                      {a.clarification ? <span className="block text-muted-foreground">보완: {a.clarification}</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-muted-foreground">아직 등록 전이다.</p>
          )}
        </CardContent>
      </Card>

      {view.directives.length ? (
        <Card>
          <CardHeader>
            <CardTitle>조건·지원·추가 지시 — 책임과 이행은 따로</CardTitle>
            <CardDescription>실행과제 수에 넣지 않는다. 조건 책임 인수(ACCEPTED)는 이행 완료(OPEN 유지)가 아니다.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm" aria-label="조건과 지시">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-1.5 pr-3 font-medium">지시</th>
                  <th className="py-1.5 pr-3 font-medium">책임 · 확인</th>
                  <th className="py-1.5 pr-3 font-medium">기한</th>
                  <th className="py-1.5 pr-3 font-medium">책임 인수</th>
                  <th className="py-1.5 font-medium">이행</th>
                </tr>
              </thead>
              <tbody className="divide-y align-top">
                {view.directives.map((d) => (
                  <tr key={d.directive_id}>
                    <th scope="row" className="py-1.5 pr-3 text-left font-normal">
                      <span className="font-mono text-xs">{d.directive_id}</span> <span className="text-xs text-muted-foreground">{DIRECTIVE_KIND_LABEL[d.kind]}</span>
                      <span className="block text-xs">{d.content}</span>
                    </th>
                    <td className="py-1.5 pr-3 text-xs">
                      {name(d.owner)} · {name(d.verifier)}
                    </td>
                    <td className="py-1.5 pr-3 text-xs">{formatClock(d.due_at)}</td>
                    <td className="py-1.5 pr-3 text-xs">{d.responsibility === "ACCEPTED" ? `인수 ${formatClock(d.responsibility_at)}` : "미인수"}</td>
                    <td className="py-1.5 text-xs">
                      {d.kind === "CONDITION" ? (d.fulfillment === "OPEN" ? "미충족(OPEN)" : "충족 확인") : "—"}
                      {d.kind === "DISCOVERY" ? <span className="block text-muted-foreground">효과 미산정</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ) : null}

      {view.assignments.some((a) => a.history.length > 2) ? (
        <Disclosure summary="반려·보완 이력">
          <ul className="space-y-0.5 text-xs">
            {view.assignments.flatMap((a) =>
              a.history.map((h) => (
                <li key={`${a.target_id}-${h.at}-${h.state}-${h.version}`}>
                  {a.target_id} v{h.version} {h.state} · {name(h.by)} {formatClock(h.at)} {h.note ? `— ${h.note}` : ""}
                </li>
              )),
            )}
          </ul>
        </Disclosure>
      ) : null}
    </>
  );
}
