"use client";

import { useUserName } from "@/components/sc01/bits";
import { Problem, Sc07Body, Sc07Header, StateTag } from "@/components/sc07/bits";
import { CompanySiteNote } from "@/components/shared/company-site-note";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { shortClock } from "@/lib/sc07/format";
import type { ProcedureStep, Sc07Meta } from "@/lib/sc07/types";
import { useSc07 } from "@/lib/store/sc07";

const EXECUTOR_LABEL: Record<string, string> = { center: "Center 서버 실행", studio: "Studio 시험 실행", embedded: "내장 BPM(시험용)" };
const PROCEDURE_LABEL: Record<string, string> = {
  PENDING: "착수 전",
  CONFIRMING: "확인 중",
  NEEDS_WORK: "보완 필요",
  APPLIED: "완료",
};

/**
 * 확인·적용 절차 — 착수(검증 실행) → 구매 임원 확인 → 경영관리 임원 확인 → 운영 설정 반영 → 설정 반영 확인 → 후속 점검
 * (업무설계표 SC07-S05~S09). BPM(`engine/processes/sc07.bpmn`)이 Studio·Center에서 돈다 — 착수·결재 답은 회사 사이트가 하고(role-split §5.5),
 * 이 화면은 절차 상태·기다리는 결재·이력을 보인다. 검증 관측값은 서비스 태스크의 규칙 계산이고, 설정 확인의 「일치」는 연결된 레코드와 대조된다.
 */
export function Sc07ConfirmScreen() {
  const meta = useSc07((s) => s.meta);
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc07Header id="U700" title="확인·적용 절차" question="개선 버전을 누가 검증·확인했고 다음 운영 설정에 반영됐는가?" />
      <Sc07Body>{meta ? <Procedure meta={meta} /> : null}</Sc07Body>
    </main>
  );
}

function Procedure({ meta }: { meta: Sc07Meta }) {
  const p = meta.procedure;
  const waiting = meta.bpm?.waiting ?? [];
  const center = meta.bpm?.center;
  const v = p.verification;
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>절차 상태</CardTitle>
          <CardDescription>
            {EXECUTOR_LABEL[meta.executor ?? ""] ?? "—"} · {meta.bpm?.runId ?? "실행 전"} · 대상 버전 {p.plan.target_version} · 범위 {p.plan.scope}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <StateTag tone={meta.status.procedure === "APPLIED" ? "good" : meta.status.procedure === "NEEDS_WORK" ? "warn" : meta.status.procedure === "CONFIRMING" ? "open" : "neutral"}>
              {PROCEDURE_LABEL[meta.status.procedure]}
            </StateTag>
            <StateTag tone={meta.status.application === "ST707" ? "good" : "open"}>
              {meta.status.application} {meta.status.applicationLabel}
            </StateTag>
            <span className="text-xs text-muted-foreground">운영 실행 미확인</span>
          </div>
          {v ? (
            <p className="text-xs">
              검증 {v.run_id} · {v.set} · {v.agent_version} · {shortClock(v.executed_at)} —{" "}
              {v.passed ? `${v.total}건 모두 충족` : `미충족 ${v.failed.join(", ")}`}
              <span className="text-muted-foreground"> (규칙 재계산 — Agent 실행 ID가 아니다)</span>
            </p>
          ) : null}
          {p.startedAt === null ? <CompanySiteNote>착수 전이다 — 확인 착수(경영관리 담당)는 회사 사이트의 시연 조작에서 한다.</CompanySiteNote> : null}
          {center?.problem ? <Problem text={center.problem} /> : null}
          {p.lastRejection && meta.status.procedure !== "APPLIED" ? (
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
              확인은 검증을 통과한 대상 버전에만 한다 — 다른 버전의 확인은 적용 근거가 아니다. 설정 반영은 두 임원 확인 뒤이고, 예약(RESERVED)만으로는
              반영을 확인하지 않는다. 기록 시각은 데이터의 일정이다(시각 이동은 확인을 만들지 않는다).
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
            <CompanySiteNote>답은 회사 사이트의 결재 화면에서 한다 — 기록이 들어오면 아래 이력에 보인다.</CompanySiteNote>
          </CardContent>
        </Card>
      ))}

      <Card>
        <CardHeader>
          <CardTitle>확인·적용 이력</CardTitle>
          <CardDescription>결재마다 남긴 기록 — 대상 버전 {p.plan.target_version}</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="divide-y text-sm">
            {p.steps.map((s) => (
              <StepRow key={s.nodeId} step={s} waiting={waiting.some((w) => w.nodeId === s.nodeId)} />
            ))}
          </ol>
          {p.followUp ? (
            <p className="mt-3 rounded-md border bg-muted/40 px-3 py-2 text-xs">
              <span className="font-medium">후속 점검</span> · {shortClock(p.followUp.planned_at)} · {p.followUp.items}
            </p>
          ) : null}
          {p.history.length ? (
            <Disclosure className="mt-3" summary={`다시 받은 기록 ${p.history.length}건`}>
              <ul className="space-y-1 text-xs">
                {p.history.map((h, i) => (
                  <li key={i}>
                    <span className="font-mono">{String(h.record_id ?? h.run_id ?? "")}</span> {String(h.state ?? h.evidence_type ?? "")}{" "}
                    {h.retired ? <span className="text-muted-foreground">(다시 받음: {h.retired})</span> : null}
                  </li>
                ))}
              </ul>
            </Disclosure>
          ) : null}
        </CardContent>
      </Card>
      {/* 회사 시스템에 적는 것이 없다 — Agent 설정은 에이전트 기록이다. 빈 「오간 것」 카드는 「옛 데모 실행」으로 읽혔다. */}
      <p className="text-xs text-muted-foreground">
        회사 시스템에 적는 것은 없다 — 개선 버전·검증 결과·운영 설정(CFG71)은 에이전트 기록이고, 확인 기록이 시계를 옮기면 회사 세계 시각만 함께
        옮긴다.
      </p>
    </>
  );
}

function StepRow({ step, waiting }: { step: ProcedureStep; waiting: boolean }) {
  const r = step.record;
  return (
    <li className="grid gap-1 py-2.5 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)] sm:gap-4">
      <div className="space-y-0.5">
        <div className="font-medium">{STEP_LABEL[step.recordId] ?? step.recordId}</div>
        <div className="text-xs text-muted-foreground">
          <span className="font-mono">{step.recordId}</span> · {step.role === step.assigneeName ? step.role : `${step.role} ${step.assigneeName}`}
        </div>
      </div>
      <div className="min-w-0 space-y-0.5">
        {r ? (
          <>
            <StateTag tone={r.state === "REWORK_REQUESTED" || r.result === "MISMATCH" ? "warn" : "good"}>
              {r.state ?? (r.result ? (r.result === "MATCH" ? "일치" : "불일치") : r.evidence_type === "SETTINGS_SNAPSHOT" ? "반영" : `예약(${r.evidence_type})`)} ·{" "}
              {shortClock(r.at)}
            </StateTag>
            {waiting ? <StateTag tone="open">다시 결재 대기</StateTag> : null}
            {r.content ? (
              <p className="text-xs">
                {r.content}
                {r.version ? <span className="text-muted-foreground"> · {r.version}</span> : null}
              </p>
            ) : null}
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

const STEP_LABEL: Record<string, string> = {
  CF71: "구매 임원 업무 확인",
  CF72: "경영관리 임원 정합성 확인",
  CFG71: "운영 설정 반영",
  "CFG71-R": "운영 설정 반영 확인",
};

function Name({ id }: { id: string | null }) {
  const name = useUserName();
  return <>{id ? name(id) : "—"}</>;
}

