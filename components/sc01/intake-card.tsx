"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Bot } from "lucide-react";

import { StatePill } from "@/components/sc01/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { sc01Api } from "@/lib/sc01/client";
import type { IntakeStatus } from "@/lib/sc01/types";
import { selectView, useSc01 } from "@/lib/store/sc01";

/**
 * 가상 직원 상태를 다시 읽는 주기(ms). 데모 실행의 변경은 SSE가 나르지만(4.9) 일괄 결재·기동은 Center에서
 * 일어나 SSE가 모른다 — 이 카드만 따로 읽는다. 숨겨진 패널에서도 돌도록 `setTimeout`이다(4.10).
 */
const REFRESH_MS = 10_000;

const DECISION_LABEL = { 승인: "승인 — SC01 기동", 반려: "반려 — 보완 요청" } as const;

/**
 * UI02 「접수 가상 직원」(docs/chaeksas-integration.md N5). Center 실행이면 원천 수신이 SC01을 바로
 * 기동하지 않고 가상 직원의 접수 Bot을 깨운다 — 감독자가 일괄로 승인한 건만 SC01이 된다.
 *
 * * 숫자(오늘 접수·승인 대기·기동된 SC01)는 Center의 가상 직원 기록 그대로다 — 이 데모 실행만의
 *   것이 아니다(가상 직원 하나가 모든 데모 실행의 접수를 맡는다).
 * * 승인 대기 일괄은 감독자가 여기서 답할 수 있다 — 대리 답이고, 감독자인지는 Center가 대조한다.
 *   결정의 업무 효과(반려면 원천 보완 요청)는 접수 Bot의 기록 작업이 낸다.
 */
export function IntakeCard() {
  const view = useSc01(selectView);
  const actor = useSc01((s) => s.actor);
  const historical = useSc01((s) => s.past !== null);
  const [status, setStatus] = useState<IntakeStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const job = view?.bpm?.center?.job ?? null;
  // 이 데모 실행의 접수가 바뀌면(수신·결정·기동) 곧바로 다시 읽는다.
  const trigger = `${job?.job_id ?? ""}|${job?.decision ?? ""}|${view?.bpm?.externalRunId ?? ""}`;

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = () => {
      void sc01Api.intake().then((r) => {
        if (!alive) return;
        setStatus(r.ok ? r.data : { workerId: null, configured: false, problem: r.error });
        timer = setTimeout(load, REFRESH_MS);
      });
    };
    load();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [trigger]);

  const answer = async (requestId: string, decision: "승인" | "반려", opinion: string) => {
    setError(null);
    const r = await sc01Api.answerIntake(requestId, { 결정: decision, 의견: opinion }, actor);
    if (r.ok) setStatus(r.data);
    else setError(`${r.status} — ${r.error}`);
  };

  const mine = job?.via === "intake" ? job : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bot aria-hidden className="size-4" />
          접수 가상 직원
        </CardTitle>
        <CardDescription>
          {status?.name ? (
            <>
              {status.name} · 감독자 {(status.supervisors ?? []).join("·") || "없음"}
            </>
          ) : (
            "Center의 고객계획 접수 가상 직원"
          )}
        </CardDescription>
        <Commentary block>
          <p className="text-[13px] text-muted-foreground">
            수집·검증은 가상 직원(접수 Bot)이, 기동 승인은 사람 감독자가 한다(기획안 1단계). 반려된 건은 SC01을
            시작하지 않고 보완 요청으로 돌아간다.
          </p>
        </Commentary>
      </CardHeader>
      <CardContent className="space-y-3">
        {status?.problem ? (
          <p className="flex items-center gap-1.5 text-xs font-medium">
            <AlertTriangle aria-hidden className="size-3.5 shrink-0" style={{ color: "var(--viz-status-serious)" }} />
            {status.problem}
          </p>
        ) : null}

        {status?.configured && !status.problem ? (
          <dl className="grid grid-cols-3 gap-2 text-center">
            <Stat label="오늘 접수" value={status.today ?? 0} unit="건" />
            <Stat label="승인 대기" value={status.pendingApprovals?.length ?? 0} unit="건" />
            <Stat label="기동된 SC01" value={status.started ?? 0} unit="건" />
          </dl>
        ) : null}

        {mine ? (
          <div className="flex flex-wrap gap-1.5">
            <StatePill label="이 데모 실행" value={`${mine.source_id} 접수`} />
            <StatePill
              label="감독자"
              value={mine.decision ? DECISION_LABEL[mine.decision] : "승인 대기"}
              tone={mine.decision === "승인" ? "good" : mine.decision === "반려" ? "warn" : "neutral"}
            />
            {view?.bpm?.center?.processedBy ? (
              <StatePill label="SC01 처리자" value={view.bpm.center.processedBy} tone="good" />
            ) : null}
          </div>
        ) : null}

        {(status?.pendingApprovals ?? []).map((p) => (
          <PendingBatch
            key={p.requestId}
            requestId={p.requestId}
            runId={p.runId}
            disabled={historical}
            onAnswer={answer}
          />
        ))}
        {error ? (
          <p role="alert" className="text-xs" style={{ color: "var(--viz-status-critical)" }}>
            거절됨: {error}
          </p>
        ) : null}

        {status?.batches?.length ? (
          <Disclosure summary={`최근 일괄 ${status.batches.length}건`}>
            <ul className="space-y-1 text-xs">
              {status.batches.map((b) => (
                <li key={b.runId} className="flex flex-wrap gap-x-2">
                  <span className="font-mono">{b.runId}</span>
                  <span>{b.status}</span>
                  <span className="text-muted-foreground">
                    SC01 {b.children}건{b.openApprovals ? ` · 승인 대기 ${b.openApprovals}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          </Disclosure>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Stat({ label, value, unit }: { label: string; value: number; unit: string }) {
  return (
    <div className="rounded-md border px-2 py-2">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums">
        {value}
        <span className="ml-0.5 text-xs font-normal text-muted-foreground">{unit}</span>
      </dd>
    </div>
  );
}

function PendingBatch({
  requestId,
  runId,
  disabled,
  onAnswer,
}: {
  requestId: string;
  runId: string;
  disabled: boolean;
  onAnswer: (requestId: string, decision: "승인" | "반려", opinion: string) => Promise<void>;
}) {
  const [opinion, setOpinion] = useState("");
  const [busy, setBusy] = useState(false);
  const send = async (decision: "승인" | "반려") => {
    setBusy(true);
    await onAnswer(requestId, decision, opinion);
    setBusy(false);
  };
  return (
    <div className="space-y-2 rounded-md border border-dashed p-2">
      <p className="text-xs">
        일괄 결재 <span className="font-mono">{requestId}</span>
        <span className="text-muted-foreground"> · 접수 Bot 실행 {runId}</span>
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={opinion}
          onChange={(e) => setOpinion(e.target.value)}
          placeholder="의견 (반려면 보완할 내용)"
          aria-label="일괄 결재 의견"
          className="min-w-[12rem] flex-1 rounded-md border bg-transparent px-2 py-1 text-xs"
        />
        <Button size="sm" disabled={disabled || busy || !opinion.trim()} onClick={() => void send("승인")}>
          승인 — SC01 기동
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={disabled || busy || !opinion.trim()}
          onClick={() => void send("반려")}
        >
          반려
        </Button>
      </div>
    </div>
  );
}
