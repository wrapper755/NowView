"use client";

import { useUserName } from "@/components/sc01/bits";
import { AgentCard } from "@/components/sc05/agent-card";
import { Mn, Requirements, Sc05Body, Sc05Header, WaitingForms } from "@/components/sc05/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { CONDITION_STATE_LABEL, OPERATION_STATE_LABEL, REQUEST_STATE_LABEL } from "@/lib/sc05/format";
import type { Sc05View } from "@/lib/sc05/types";

const NODES = [
  "Evidence_CON41",
  "Register_SUP41",
  "Ready_CON41",
  "Confirm_CON41",
  "Verify_SUP41",
  "Submit_REQ51",
  "Submit_OP51",
  "Func_REQ51",
  "Func_OP51",
  "Budget_REQ51",
  "Budget_OP51",
  "Start_Operation",
];

/**
 * U503 조건·품의·착수 — 한 화면에서 처리한다(검토 의견: 화면을 너무 나누지 않는다). 상단에 착수 대기 사유를 모으고,
 * CON41·SUP41(근거와 확인을 분리), 품의(현업 임원 → 예산 임원, 약정·집행), 하단에 실제 착수를 둔다. 요건 하나라도
 * 미충족이면 착수하지 않는다 — 개수 합이나 ready 값으로 허용하지 않는다(M502·CT507).
 */
export function Sc05ReadyScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc05Header id="U503" title="조건·품의·착수" question="실제로 시작해도 되는가 — 무엇이 남았는가?" />
      <Sc05Body>{(view) => <Body view={view} />}</Sc05Body>
    </main>
  );
}

function Body({ view }: { view: Sc05View }) {
  const nameOf = useUserName();
  const check = view.startCheck;
  const op = view.operation.find((o) => o.task_id === "ACT42");
  const waiting = new Set((view.bpm?.waiting ?? []).map((w) => w.nodeId));
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>착수 요건</CardTitle>
          <CardDescription>
            ACT42 {op ? OPERATION_STATE_LABEL[op.state] : "—"}
            {check ? ` · 준비 ${check.ready === "READY" ? "완료" : "대기"} · 적용일 ${formatClock(check.apply_at)}` : " · 장면 착수 전"}
            {view.start ? ` · ${view.start.start_id} ${formatClock(view.start.started_at)} 착수(${view.start.plan_version})` : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 [&>*]:min-w-0 md:grid-cols-2">
          {check ? <Requirements items={check.items} /> : <p className="text-sm text-muted-foreground">착수 전이다.</p>}
          {check && check.blocking.length && !view.start ? (
            <div className="text-sm">
              <p className="text-xs font-medium">지금 착수할 수 없는 이유</p>
              <ul className="list-disc pl-4 text-xs">
                {check.blocking.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <WaitingForms
        view={view}
        nodes={NODES}
        labels={{ Start_Operation: "운영 적용 착수", Confirm_CON41: "충족 확인", Verify_SUP41: "이행 확인" }}
        initial={view.planPointer ? { Start_Operation: { 착수계획버전: view.planPointer } } : undefined}
      />

      <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-2">
        {view.conditions.map((c) => (
          <Card key={c.condition_id}>
            <CardHeader>
              <CardTitle>{c.condition_id === "CON41" ? "CON41 생산·구매 공동 기준" : "SUP41 생산 지원 지시"}</CardTitle>
              <CardDescription>
                {CONDITION_STATE_LABEL[c.state] ?? c.state} · 책임 {nameOf(c.owner)} · 확인 {nameOf(c.verifier)} · 기한 {formatClock(c.due_at)}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>{c.content}</p>
              {c.evidence.length ? (
                <ul className="space-y-1 text-xs">
                  {c.evidence.map((e) => (
                    <li key={e.version}>
                      근거 v{e.version} <span className="font-mono">{e.refs.join(", ")}</span> · {nameOf(e.by)} {formatClock(e.at)}
                      <span className="block text-muted-foreground">{e.details}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-muted-foreground">근거 등록 전</p>
              )}
              {c.confirmed_at ? (
                <p className="text-xs">
                  {c.condition_id === "CON41" ? "충족 확인" : "이행 확인"} — {nameOf(c.confirmed_by)} {formatClock(c.confirmed_at)}
                </p>
              ) : null}
            </CardContent>
          </Card>
        ))}
      </div>

      <AgentCard view={view} kind="AG53" canRequest={waiting.has("Confirm_CON41") || waiting.has("Verify_SUP41")} />

      <Card>
        <CardHeader>
          <CardTitle>실행 품의와 예산</CardTitle>
          <CardDescription>
            대표 승인서({view.sc04.approval.approval_id})를 근거로 현업 임원·예산 임원이 승인한다. 한도 안이라 대표 재승인은 없다.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-1.5 pr-3 font-medium">품의</th>
                  <th className="pr-3 font-medium">과제·범위</th>
                  <th className="pr-3 text-right font-medium">요청액(백만원)</th>
                  <th className="pr-3 font-medium">상태</th>
                  <th className="pr-3 font-medium">승인 이력</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {view.requests.map((r) => (
                  <tr key={r.request_id}>
                    <th scope="row" className="py-1.5 pr-3 text-left font-medium">
                      {r.request_id}
                      {r.background ? <span className="block text-[11px] font-normal text-muted-foreground">배경</span> : null}
                    </th>
                    <td className="pr-3">
                      {r.task_id} · {r.scope === "ONEOFF" ? "일회성" : "운영지원(별도 원장)"}
                    </td>
                    <td className="pr-3 text-right">
                      <Mn value={r.amount} />
                    </td>
                    <td className="pr-3">{REQUEST_STATE_LABEL[r.state] ?? r.state}</td>
                    <td className="pr-3 text-xs">{r.history.map((h) => `${h.at.slice(5, 16).replace("T", " ")} ${nameOf(h.by)}`).join(" → ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {view.requests.length === 0 ? <p className="text-sm text-muted-foreground">아직 품의가 없다.</p> : null}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[36rem] text-sm">
              <caption className="pb-1 text-left text-xs text-muted-foreground">예산 사용가능액 = 한도 − 집행 − 미집행 약정 (백만원)</caption>
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-1.5 pr-3 font-medium">범위</th>
                  <th className="pr-3 text-right font-medium">한도</th>
                  <th className="pr-3 text-right font-medium">미집행 약정</th>
                  <th className="pr-3 text-right font-medium">집행</th>
                  <th className="pr-3 text-right font-medium">사용가능</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {[...view.budget.tasks.map((t) => ({ k: `${t.task_id} 일회성`, ...t })), { k: "총괄 일회성", ...view.budget.total }, { k: "운영지원(OP51)", ...view.budget.operating }].map((b) => (
                  <tr key={b.k}>
                    <th scope="row" className="py-1.5 pr-3 text-left font-medium">
                      {b.k}
                    </th>
                    <td className="pr-3 text-right">
                      <Mn value={b.limit} />
                    </td>
                    <td className="pr-3 text-right">
                      <Mn value={b.commitment} />
                    </td>
                    <td className="pr-3 text-right">
                      <Mn value={b.paid} />
                    </td>
                    <td className="pr-3 text-right">
                      <Mn value={b.available} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Disclosure summary={`예산 원장 ${view.ledger.length}건`}>
            <ul className="space-y-0.5 text-xs">
              {view.ledger.map((t) => (
                <li key={t.txn_id}>
                  <span className="font-mono">{t.txn_id}</span> {formatClock(t.at)} {t.request_ref} {t.type === "COMMIT" ? "약정" : "정산"} · 약정{" "}
                  <Mn value={t.commitment_delta} signed /> · 집행 <Mn value={t.paid_delta} /> · 근거 {t.evidence}
                </li>
              ))}
            </ul>
          </Disclosure>
          <Commentary>
            <p className="text-xs text-muted-foreground">
              정산(SETTLE)은 같은 약정을 줄이며 집행을 늘리는 한 거래다 — 사용가능액을 두 번 줄이지 않는다. 과제 간 전용은 경영관리 임원 승인, 총괄 초과는 대표
              별도 승인 전 시행 보류다(본 시연에서는 실행하지 않는다).
            </p>
          </Commentary>
        </CardContent>
      </Card>
    </>
  );
}
