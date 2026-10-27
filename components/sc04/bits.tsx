"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, BellRing, ExternalLink, History, PlayCircle, WifiOff } from "lucide-react";

import { StatePill } from "@/components/sc01/bits";
import { Sc04ActionForm } from "@/components/sc04/action-form";
import { Commentary } from "@/components/shared/commentary";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock, formatWonExact } from "@/lib/sc01/format";
import { sc04Api } from "@/lib/sc04/client";
import { formatMillion, SCENE_STATE_LABEL } from "@/lib/sc04/format";
import type { Sc04View, Sc04Waiting } from "@/lib/sc04/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc03 } from "@/lib/store/sc03";
import { selectView4, useSc04 } from "@/lib/store/sc04";

/**
 * 장면 4 화면 머리 — 제목 한 줄 + 상태 한 줄(장면 1~3과 같다). 검토건·공장·제품·기준 버전·단위는 상태 줄에 늘
 * 있다(COMMON — 전사 1조원 매출과 혼동 금지). 화면 id·질문은 해설 모드에서만 보인다.
 */
export function Sc04Header({ id, title, question }: { id: string; title: string; question: string }) {
  const view = useSc04(selectView4);
  return (
    <header className="space-y-1.5">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
        <span>{view ? formatClock(view.clock) : "—"}</span>
        <span aria-hidden>·</span>
        <span>MR-2706-01 · 울산 A제품 · 2027 · 기준 수익성 통합 분석 통합손익 · 백만원</span>
        <span aria-hidden>·</span>
        <span>{view ? (SCENE_STATE_LABEL[view.status.review] ?? view.status.review) : "—"}</span>
        {view && view.caseId !== "BASE" ? (
          <span className="rounded border px-1.5 py-0.5 text-[10px] font-medium text-foreground">{view.caseLabel}</span>
        ) : null}
        <span className="rounded border px-1.5 py-0.5 text-[10px]">시연 데이터</span>
        <MyAlerts />
      </div>
      <Commentary block>
        <p className="text-xs text-muted-foreground">
          <span className="font-mono">{id}</span> · {question} · 공장관리손익은 전사 영업이익이 아니다(본사비·금융비·세금 제외) ·
          금액은 원 단위로 계산하고 백만원으로 보인다
        </p>
      </Commentary>
      <Banner />
      <ExecutorBanner />
    </header>
  );
}

function MyAlerts() {
  const view = useSc04(selectView4);
  const actor = useSc01((s) => s.actor);
  const count = (view?.alerts ?? []).filter((a) => a.to.includes(actor)).length;
  if (count === 0) return null;
  return (
    <Link href="/sc04/actions" className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium text-foreground">
      <BellRing aria-hidden className="size-3" style={{ color: "var(--viz-status-critical)" }} />내 알림 {count}건
    </Link>
  );
}

const EXECUTOR_LABEL: Record<string, string> = {
  center: "Center 서버 실행",
  studio: "Studio 시험 실행",
  embedded: "내장 BPM(시험용)",
};

/** 어디서 BPM이 도는지·어디서 답하는지 — 표시하지 않으면 화면에서 답할 수 있다고 착각한다(장면 2·3과 같다). */
function ExecutorBanner() {
  const view = useSc04(selectView4);
  if (!view || view.executor === "embedded") return null;
  const problem = view.bpm?.center?.problem;
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border px-3 py-2 text-xs">
      <ExternalLink aria-hidden className="size-3.5" />
      <span>
        <span className="font-medium">{EXECUTOR_LABEL[view.executor]}</span>이 BPM을 돈다 —{" "}
        {view.answerHere
          ? "이 화면의 답은 Center 결재함에 대리 답으로 간다."
          : view.executor === "studio"
            ? "결재는 Studio 시험 대화상자에서 답하세요. 회의 기록·Agent 초안·예산 위임 조회는 이 화면에서 한다."
            : "결재는 Center 결재함에서 답하세요."}
      </span>
      {problem ? (
        <span className="inline-flex basis-full items-center gap-1 font-medium">
          <AlertTriangle aria-hidden className="size-3.5 shrink-0" style={{ color: "var(--viz-status-serious)" }} />
          {problem}
        </span>
      ) : null}
      <span className="text-muted-foreground">
        입력 데모실행ID <span className="font-mono">{view.demoRunId}</span> · 바깥 실행{" "}
        {view.bpm?.externalRunId ? <span className="font-mono">{view.bpm.externalRunId}</span> : "첫 작업 호출 전"}
        {view.bpm?.center?.job ? (
          <>
            {" "}
            · 작업 <span className="font-mono">{view.bpm.center.job.job_id}</span>
          </>
        ) : null}
      </span>
    </p>
  );
}

function Banner() {
  const past = useSc04((s) => s.past);
  const connection = useSc04((s) => s.connection);
  const error = useSc04((s) => s.error);
  const setPast = useSc04((s) => s.setPast);
  if (past) {
    return (
      <p className="flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-xs">
        <History aria-hidden className="size-3.5" />
        지난 시점({formatClock(past.view.clock)})을 보고 있다 — 이 화면에서는 조작할 수 없다.
        <button type="button" className="font-medium underline" onClick={() => setPast(null)}>
          현재로
        </button>
      </p>
    );
  }
  if (connection === "offline") {
    return (
      <p role="alert" className="flex items-center gap-2 rounded-md border px-3 py-2 text-xs">
        <WifiOff aria-hidden className="size-3.5" style={{ color: "var(--viz-status-serious)" }} />
        BPM 엔진에 닿지 않는다 — {error ?? "연결 실패"}. `npm run stack:start`로 엔진을 띄운다.
      </p>
    );
  }
  if (error) {
    return (
      <p role="alert" className="flex items-center gap-2 rounded-md border px-3 py-2 text-xs">
        <AlertTriangle aria-hidden className="size-3.5" style={{ color: "var(--viz-status-serious)" }} />
        {error}
      </p>
    );
  }
  return null;
}

/**
 * 장면 4가 아직 없는 데모 실행 — 시작을 묻는다. 장면 3이 완료 전이면 엔진이 장면 3 각본을 완료까지 **실제로**
 * 실행한 뒤 시작한다(지름길로 「완료됨」을 만들지 않는다). 그래서 저절로 하지 않고 묻는다.
 */
export function Sc04StartCard() {
  const demoRunId = useSc01((s) => s.demoRunId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const start = async () => {
    setBusy(true);
    setError(null);
    // 실행 위치는 Center다(2026-10-27 — 화면은 내장을 고르지 않는다). Studio는 플레이어에서 고른다.
    const r = await sc04Api.create(demoRunId, "BASE", "center");
    setBusy(false);
    if (r.ok) {
      useSc04.getState().setLive(r.data);
      // 장면 3(·1·2)이 각본으로 끝났을 수 있다 — 그 화면도 새 상태를 받게 한다.
      useSc03.getState().clearLive(false);
    } else setError(`${r.status} — ${r.error}`);
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>개선안 검토·실행 승인 시작</CardTitle>
        <CardDescription>
          개선안 검토·실행 승인은 수익성 통합 분석 완료(HANDOFF31 — 분석과제 AT31~AT34 인수)에서 시작한다. 같은 데모 실행
          {demoRunId ? <span className="font-mono"> {demoRunId}</span> : null}을 잇는다.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-xs text-muted-foreground">
          수익성 통합 분석이 아직 완료 전이면 수익성 통합 분석 각본의 남은 단계를 완료까지 실제로 실행한다(역할 검사·업무 규칙 그대로).
        </p>
        <Button size="sm" onClick={() => void start()} disabled={busy || !demoRunId}>
          <PlayCircle aria-hidden className="size-3.5" />
          {busy ? "준비하는 중…" : "개선안 검토·실행 승인 시작"}
        </Button>
        {error ? (
          <p role="alert" className="text-xs" style={{ color: "var(--viz-status-critical)" }}>
            시작 실패: {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** 화면 몸통 — 문서가 없으면 시작 카드, 아직 오지 않았으면 불러오는 중. */
export function Sc04Body({ children }: { children: (view: Sc04View) => React.ReactNode }) {
  const view = useSc04(selectView4);
  const missing = useSc04((s) => s.missing);
  if (view) return <>{children(view)}</>;
  if (missing) return <Sc04StartCard />;
  return <p className="text-sm text-muted-foreground">개선안 검토·실행 승인을 불러오는 중…</p>;
}

/**
 * 독립 배지(DEC409) — 장면 · 승인서 · 조건 · Risk · 공식 Forecast · Target. 장면 완료 ≠ 실행 완료 ≠ 위험 해소 ≠ 전망
 * 승인이다. 승인 효과는 예상치다.
 */
export function StatusPills({ view }: { view: Sc04View }) {
  const s = view.status;
  return (
    <div className="flex flex-wrap gap-1.5">
      <StatePill label="업무" value={SCENE_STATE_LABEL[s.review] ?? s.review} tone={s.review === "SC04_COMPLETED" ? "good" : "neutral"} />
      <StatePill label="승인서" value={s.approval === "VALID" ? "유효(APR41-v1)" : "확정 전"} tone={s.approval === "VALID" ? "good" : "neutral"} />
      <StatePill label="조건" value={s.conditions === "OPEN" ? "CON41 미충족 — 실행 착수 제한" : s.conditions ? "충족" : "없음"} tone={s.conditions === "OPEN" ? "warn" : "neutral"} />
      <StatePill label="Risk" value="OPEN — 미해결" tone="warn" />
      <StatePill label="공식 Forecast" value="REVIEW_PENDING — 승인 아님" />
      <StatePill label="Target" value="유지(UNCHANGED)" />
    </div>
  );
}

/** 지금 기다리는 사람 업무 중 이 화면 것 — 폼은 BPMN에서 온다. 없으면 아무것도 그리지 않는다. */
export function WaitingForms({
  view,
  nodes,
  initial,
  expect,
  labels,
}: {
  view: Sc04View;
  nodes: string[];
  initial?: Record<string, Record<string, unknown>>;
  expect?: (nodeId: string) => Record<string, unknown> | undefined;
  labels?: Record<string, string>;
}) {
  const waiting = (view.bpm?.waiting ?? []).filter((w) => nodes.includes(w.nodeId));
  if (waiting.length === 0 || view.historical) return null;
  return (
    <>
      {waiting.map((w: Sc04Waiting) => (
        <Card key={w.nodeId}>
          <CardHeader>
            <CardTitle>지금 할 일 — {w.title}</CardTitle>
            <CardDescription>
              담당 {w.role}
              {w.taskId ? (
                <>
                  {" "}
                  · <span className="font-mono">{w.taskId}</span> 기한 {formatClock(view.tasks.find((t) => t.task_id === w.taskId)?.due_at)}
                </>
              ) : null}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Sc04ActionForm
              key={`${w.nodeId}-${view.audit.length}`}
              waiting={w}
              initial={initial?.[w.nodeId]}
              expect={expect?.(w.nodeId)}
              submitLabel={labels?.[w.nodeId] ?? "제출"}
            />
          </CardContent>
        </Card>
      ))}
    </>
  );
}

/** 금액 한 칸 — 백만원 소수 둘째 자리, 원 단위는 title로. NULL은 미산정·미설정이다(0이 아니다). */
export function Mn({ value, empty = "미산정", signed = false }: { value: string | null | undefined; empty?: string; signed?: boolean }) {
  if (value === null || value === undefined) return <span className="text-muted-foreground">{empty}</span>;
  const text = signed && Number(value) > 0 ? `+${formatMillion(value)}` : formatMillion(value);
  return (
    <span title={formatWonExact(value)} className="tabular-nums">
      {text}
    </span>
  );
}
