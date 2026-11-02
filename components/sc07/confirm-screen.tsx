"use client";

import { useRef, useState } from "react";
import { Lock, PlayCircle, Send } from "lucide-react";

import { useUserName } from "@/components/sc01/bits";
import { Problem, Sc07Body, Sc07Header, StateTag } from "@/components/sc07/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { FormField, initialValue, isMissing } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { sc07Api } from "@/lib/sc07/client";
import { shortClock } from "@/lib/sc07/format";
import type { ProcedureStep, Sc07Meta, Sc07Waiting } from "@/lib/sc07/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc07 } from "@/lib/store/sc07";

const EXECUTOR_LABEL: Record<string, string> = { center: "Center 서버 실행", studio: "Studio 시험 실행", embedded: "내장 BPM(시험용)" };
const PROCEDURE_LABEL: Record<string, string> = {
  PENDING: "착수 전",
  CONFIRMING: "확인 중",
  NEEDS_WORK: "보완 필요",
  APPLIED: "완료",
};
const STARTER = "u-fin";

/**
 * 확인·적용 절차 — 착수(검증 실행) → 구매 임원 확인 → 경영관리 임원 확인 → 운영 설정 반영 → 설정 반영 확인 → 후속 점검
 * (업무설계표 SC07-S05~S09). BPM(`engine/processes/sc07.bpmn`)이 Studio·Center에서 돌고 화면은 대기 중인 결재에 답한다 —
 * Center면 대리 답이다. 검증 관측값은 서비스 태스크의 규칙 계산이고, 설정 확인의 「일치」는 연결된 레코드와 대조된다.
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
          {p.startedAt === null ? <StartButton meta={meta} /> : null}
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
            <CardTitle>{w.title}</CardTitle>
            <CardDescription>
              담당 <Name id={w.assignee} /> · 칸은 데이터의 확인·적용 기록으로 미리 채웠다(고쳐서 낼 수 있다)
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <ActionForm key={`${w.nodeId}:${w.taskId}`} waiting={w} />
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

function StartButton({ meta }: { meta: Sc07Meta }) {
  const actor = useSc01((s) => s.actor);
  const users = useSc01((s) => s.users);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const starter = users.find((u) => u.userId === STARTER);
  const start = async () => {
    setBusy(true);
    setError(null);
    const r = await sc07Api.start(meta.demoRunId, actor);
    setBusy(false);
    if (r.ok) useSc07.getState().setMeta(r.data);
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
        <span className="text-xs text-muted-foreground">Center에 SC07 확인·적용 절차를 기동한다</span>
      ) : meta.executor === "studio" ? (
        <span className="text-xs text-muted-foreground">착수만 적는다 — Studio에서 실행을 시작한다</span>
      ) : null}
      {error ? <Problem text={error} /> : null}
    </div>
  );
}

/**
 * 결재 폼 — 칸은 BPMN에서 온다. 장면 1~6과 같은 규칙: 검사는 엔진이 하고(403·409·422), 거절되면 사유와 남은 항목을
 * 그대로 보이고 **입력은 지우지 않는다**.
 */
function ActionForm({ waiting }: { waiting: Sc07Waiting }) {
  const meta = useSc07((s) => s.meta);
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
    const r = await sc07Api.act(meta.demoRunId, waiting.nodeId, answer, actor, keyRef.current);
    setBusy(false);
    if (r.ok) {
      keyRef.current = null;
      useSc07.getState().setMeta(r.data);
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
