"use client";

import { useRef, useState } from "react";
import { Lock, PlayCircle, Send } from "lucide-react";

import { useUserName } from "@/components/sc01/bits";
import { Problem, Sc06Body, Sc06Header, StateTag, personName } from "@/components/sc06/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { FormField, initialValue, isMissing } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { sc06Api } from "@/lib/sc06/client";
import { shortClock } from "@/lib/sc06/format";
import type { ProcedureStep, Sc06Meta, Sc06Waiting } from "@/lib/sc06/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc06 } from "@/lib/store/sc06";

const EXECUTOR_LABEL: Record<string, string> = { center: "Center 서버 실행", studio: "Studio 시험 실행", embedded: "내장 BPM(시험용)" };
const PROCEDURE_LABEL: Record<string, string> = {
  PENDING: "착수 전",
  CONFIRMING: "확인 중",
  REPORTED: "대표 보고 완료",
  LOADED: "끝난 기록으로 적재",
};
const STARTER = "u-fin";

/**
 * 확인 절차 — 담당 임원 성과 근거 확인(생산 ∥ 구매) → 경영관리 종합 확인 → 보고 결론 → 보고본 확정 → 대표 보고
 * (업무설계표 S11~S13). BPM(`engine/processes/sc06.bpmn`)이 Studio·Center에서 돌고 화면은 대기 중인 결재에 답한다 —
 * Center면 대리 답이다. 숫자는 적재 때 규칙 계산이 만들었고, 확정이 그 산정을 보고본에 묶는다(결론 숫자가 다르면 막힌다).
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
          확인 절차를 BPM으로 돌기 전에 만든 데모 실행이다 — 확인 이력은 데이터 그대로 끝나 있다. 플레이어의 「초기화」를 누르면 적재(숫자·근거)는 그대로
          두고 확인 전으로 돌아가 절차를 다시 돈다.
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
          {p.startedAt === null ? <StartButton meta={meta} /> : null}
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
            <CardTitle>{w.title}</CardTitle>
            <CardDescription>
              담당 <Name id={w.assignee} /> · 칸은 데이터의 확인 기록으로 미리 채웠다(고쳐서 낼 수 있다)
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
            <ActionForm key={`${w.nodeId}:${w.taskId}`} waiting={w} />
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

function StartButton({ meta }: { meta: Sc06Meta }) {
  const actor = useSc01((s) => s.actor);
  const users = useSc01((s) => s.users);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const starter = users.find((u) => u.userId === STARTER);
  const start = async () => {
    setBusy(true);
    setError(null);
    const r = await sc06Api.start(meta.demoRunId, actor);
    setBusy(false);
    if (r.ok) useSc06.getState().setMeta(r.data);
    else setError(`${r.status} — ${r.error}`);
  };
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button size="sm" onClick={() => void start()} disabled={busy || actor !== STARTER}>
        <PlayCircle aria-hidden className="size-3.5" />
        {busy ? "착수하는 중…" : "확인 착수"}
      </Button>
      {actor !== STARTER ? (
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
          <Lock aria-hidden className="size-3" />
          {starter ? `${starter.role} ${starter.name}` : "경영관리 담당"}이 착수한다 — 상단에서 역할을 바꾼다
        </span>
      ) : meta.executor === "center" ? (
        <span className="text-xs text-muted-foreground">Center에 SC06 확인 절차를 기동한다</span>
      ) : meta.executor === "studio" ? (
        <span className="text-xs text-muted-foreground">착수만 적는다 — Studio에서 실행을 시작한다</span>
      ) : null}
      {error ? <Problem text={error} /> : null}
    </div>
  );
}

/**
 * 결재 폼 — 칸은 BPMN에서 온다. 장면 1~5와 같은 규칙: 검사는 엔진이 하고(403·409·422), 거절되면 사유와 남은 항목을
 * 그대로 보이고 **입력은 지우지 않는다**.
 */
function ActionForm({ waiting }: { waiting: Sc06Waiting }) {
  const meta = useSc06((s) => s.meta);
  const actor = useSc01((s) => s.actor);
  const users = useSc01((s) => s.users);
  const [values, setValues] = useState<Record<string, unknown>>(() =>
    Object.fromEntries(waiting.fields.map((f) => [f.key, initialValue(f)])),
  );
  const [error, setError] = useState<{ text: string; items?: string[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const keyRef = useRef<string | null>(null);
  const elsewhere = meta !== null && !meta.answerHere;
  const relay = meta?.executor === "center";
  const wrongActor = waiting.assignee !== null && waiting.assignee !== actor;
  const missing = waiting.fields.some((f) => isMissing(f, values[f.key]));
  const assigneeName = users.find((u) => u.userId === waiting.assignee)?.name;

  const submit = async () => {
    if (!meta) return;
    setBusy(true);
    setError(null);
    keyRef.current ??= crypto.randomUUID();
    const answer = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== null && v !== undefined && v !== ""));
    const r = await sc06Api.act(meta.demoRunId, waiting.nodeId, answer, actor, keyRef.current);
    setBusy(false);
    if (r.ok) {
      keyRef.current = null;
      useSc06.getState().setMeta(r.data);
    } else {
      setError({ text: `${r.status} — ${r.error}`, items: r.blockingItems });
    }
  };

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      {waiting.fields.map((f) => (
        <FormField
          key={f.key}
          field={f}
          value={values[f.key]}
          users={users}
          onChange={(v) => {
            keyRef.current = null;
            setValues((s) => ({ ...s, [f.key]: v }));
          }}
        />
      ))}
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" size="sm" disabled={busy || elsewhere || wrongActor || missing}>
          <Send aria-hidden className="size-3.5" />
          {busy ? "보내는 중…" : "제출"}
        </Button>
        {elsewhere ? (
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Lock aria-hidden className="size-3" />
            바깥 실행이 도는 데모 실행이다 — 결재는 {relay ? "Center 결재함" : "Studio"}에서 답한다
          </span>
        ) : wrongActor ? (
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Lock aria-hidden className="size-3" />
            {assigneeName ?? waiting.role}만 할 수 있다 — 상단에서 역할을 바꾼다
          </span>
        ) : relay ? (
          <span className="text-xs text-muted-foreground">Center 결재함에 대리 답으로 간다</span>
        ) : null}
      </div>
      {error ? (
        <div role="alert" className="space-y-1 text-xs" style={{ color: "var(--viz-status-critical)" }}>
          <p>거절됨(저장되지 않음): {error.text}</p>
          {error.items?.length ? (
            <ul className="list-disc pl-4">
              {error.items.map((i) => (
                <li key={i}>{i}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </form>
  );
}
