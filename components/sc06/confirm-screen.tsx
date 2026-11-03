"use client";

import { useUserName } from "@/components/sc01/bits";
import { CompanyExchangeCard } from "@/components/sc01/company-exchange";
import { Problem, Sc06Body, Sc06Header, StateTag, personName } from "@/components/sc06/bits";
import { CompanySiteNote } from "@/components/shared/company-site-note";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { shortClock } from "@/lib/sc06/format";
import type { ProcedureStep, Sc06Meta } from "@/lib/sc06/types";
import { useSc06 } from "@/lib/store/sc06";

const EXECUTOR_LABEL: Record<string, string> = { center: "Center 서버 실행", studio: "Studio 시험 실행", embedded: "내장 BPM(시험용)" };
const PROCEDURE_LABEL: Record<string, string> = {
  PENDING: "착수 전",
  CONFIRMING: "확인 중",
  REPORTED: "대표 보고 완료",
  LOADED: "끝난 기록으로 적재",
};

/**
 * 확인 절차 — 담당 임원 성과 근거 확인(생산 ∥ 구매) → 경영관리 종합 확인 → 보고 결론 → 보고본 확정 → 대표 보고
 * (업무설계표 S11~S13). BPM(`engine/processes/sc06.bpmn`)이 Studio·Center에서 돈다 — 착수·결재 답은 회사 사이트가 하고(role-split §5.5),
 * 이 화면은 절차 상태·기다리는 결재·이력을 보인다. 숫자는 적재 때 규칙 계산이 만들었고, 확정이 그 산정을 보고본에 묶는다(결론 숫자가 다르면 막힌다).
 * 보고 확정은 과제 실행·예산 승인이 아니다.
 */
export function Sc06ConfirmScreen() {
  const meta = useSc06((s) => s.meta);
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc06Header id="U600" title="확인 절차" question="Q4 성과를 누가 어디까지 확인했고 보고본은 확정됐는가?" />
      <Sc06Body>{meta ? <Procedure meta={meta} /> : null}</Sc06Body>
    </main>
  );
}

function Procedure({ meta }: { meta: Sc06Meta }) {
  const p = meta.procedure;
  if (!p) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>확인 기록을 끝난 것으로 적재한 검토건이다</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          확인 절차를 BPM으로 돌기 전에 만든 데모 실행이다 — 확인 이력은 데이터 그대로 끝나 있다. 회사 사이트의 시연 조작에서 이 업무만 처음으로 돌리면
          적재(숫자·근거)는 그대로 두고 확인 전으로 돌아가 절차를 다시 돈다.
        </CardContent>
      </Card>
    );
  }
  const waiting = meta.bpm?.waiting ?? [];
  const center = meta.bpm?.center;
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>절차 상태</CardTitle>
          <CardDescription>
            {EXECUTOR_LABEL[meta.executor ?? ""] ?? "—"} · {meta.bpm?.runId ?? "실행 전"} · 보고본 {meta.reportVersion}{" "}
            {meta.reportState} · 산정 {meta.calculationVersion}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <StateTag tone={meta.status.procedure === "REPORTED" ? "good" : meta.status.procedure === "CONFIRMING" ? "open" : "neutral"}>
              {PROCEDURE_LABEL[meta.status.procedure]}
            </StateTag>
            <StateTag tone="warn">위험 {meta.status.risk}</StateTag>
            <span className="text-xs text-muted-foreground">확인 {meta.status.confirmed.length}/5 단계</span>
          </div>
          {p.startedAt === null ? <CompanySiteNote>착수 전이다 — 확인 착수(경영관리 담당)는 회사 사이트의 시연 조작에서 한다.</CompanySiteNote> : null}
          {center?.problem ? <Problem text={center.problem} /> : null}
          {p.lastRejection && meta.reportState !== "REPORTED" ? (
            <Disclosure summary={`최근 거절된 답 — ${p.lastRejection.node_id} (${p.lastRejection.status})`}>
              <p className="text-xs">{p.lastRejection.reason}</p>
              {p.lastRejection.blocking_items?.length ? (
                <ul className="mt-1 list-disc pl-4 text-xs">
                  {p.lastRejection.blocking_items.map((i) => (
                    <li key={i}>{i}</li>
                  ))}
                </ul>
              ) : null}
            </Disclosure>
          ) : null}
          <Commentary block>
            <p className="text-[13px] text-muted-foreground">
              확인은 숫자를 바꾸지 않는다 — 자료 마감(1/7) 뒤 적재 때 계산된 산정을 사람이 확인하고, 확정이 그 산정을 보고본에 묶는다. 결론 문장의
              「…백만원」이 산정과 다르면 확정이 막힌다. 기록 시각은 데이터의 일정이다(시각 이동은 확인을 만들지 않는다).
            </p>
          </Commentary>
        </CardContent>
      </Card>

      {waiting.map((w) => (
        <Card key={w.nodeId}>
          <CardHeader>
            <CardTitle>기다리는 결재 — {w.title}</CardTitle>
            <CardDescription>
              담당 <Name id={w.assignee} /> · 기다리는 결재
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {w.nodeId === "Finalize_Report" && p.finalizeBlocking.length ? (
              <div className="space-y-1 text-xs" role="status">
                <p className="font-medium">지금 확정하면 막힌다 — 남은 항목</p>
                <ul className="list-disc pl-4">
                  {p.finalizeBlocking.map((i) => (
                    <li key={i}>{i}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            <CompanySiteNote>답은 회사 사이트의 결재 화면에서 한다 — 기록이 들어오면 아래 이력에 보인다.</CompanySiteNote>
          </CardContent>
        </Card>
      ))}

      <Card>
        <CardHeader>
          <CardTitle>확인 이력</CardTitle>
          <CardDescription>결재마다 남긴 기록 — 모두 보고 버전 {meta.reportVersion}에 묶인다</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="divide-y text-sm">
            {p.steps.map((s) => (
              <StepRow key={s.nodeId} step={s} waiting={waiting.some((w) => w.nodeId === s.nodeId)} />
            ))}
          </ol>
          {p.note ? (
            <p className="mt-3 rounded-md border bg-muted/40 px-3 py-2 text-xs">
              <span className="font-medium">남는 사항(NOTE61)</span> · {p.note.content}
            </p>
          ) : null}
          {p.history.length ? (
            <Disclosure className="mt-3" summary={`다시 받은 기록 ${p.history.length}건`}>
              <ul className="space-y-1 text-xs">
                {p.history.map((h, i) => (
                  <li key={`${h.record_id}:${i}`}>
                    <span className="font-mono">{h.record_id}</span> {h.state} · {personName(h.actor)} {shortClock(h.at)} — {h.content}
                    {h.retired ? <span className="text-muted-foreground"> (다시 받음: {h.retired})</span> : null}
                  </li>
                ))}
              </ul>
            </Disclosure>
          ) : null}
        </CardContent>
      </Card>
      <CompanyExchangeCard log={meta.companyLog ?? []} />
    </>
  );
}

function StepRow({ step, waiting }: { step: ProcedureStep; waiting: boolean }) {
  const r = step.record;
  return (
    <li className="grid gap-1 py-2.5 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)] sm:gap-4">
      <div className="space-y-0.5">
        <div className="font-medium">{step.step ?? step.recordId}</div>
        <div className="text-xs text-muted-foreground">
          <span className="font-mono">{step.recordId}</span> · {step.role} {step.assigneeName}
        </div>
      </div>
      <div className="min-w-0 space-y-0.5">
        {r ? (
          <>
            <StateTag tone="good">
              {r.state} · {shortClock(r.at)}
            </StateTag>
            <p className="text-xs">{r.content}</p>
          </>
        ) : waiting ? (
          <StateTag tone="open">결재 대기 — 일정 {shortClock(step.plannedAt)}</StateTag>
        ) : (
          <StateTag tone="neutral">아직 — 일정 {shortClock(step.plannedAt)}</StateTag>
        )}
      </div>
    </li>
  );
}

function Name({ id }: { id: string | null }) {
  const name = useUserName();
  return <>{id ? name(id) : "—"}</>;
}

