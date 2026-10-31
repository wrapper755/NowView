"use client";

import { useState } from "react";
import { CompanyLink as Link } from "@/components/shared/company-link";
import { AlertTriangle, BellRing, ExternalLink, History, Loader2, PlayCircle, WifiOff } from "lucide-react";

import { StatePill } from "@/components/sc01/bits";
import { Sc03ActionForm } from "@/components/sc03/action-form";
import { Commentary } from "@/components/shared/commentary";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock, formatWonExact } from "@/lib/sc01/format";
import { sc03Api } from "@/lib/sc03/client";
import { formatMillion, OUTCOME_LABEL, REVIEW_STATE_LABEL } from "@/lib/sc03/format";
import type { Sc03View, Sc03Waiting } from "@/lib/sc03/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc02 } from "@/lib/store/sc02";
import { selectView3, useSc03 } from "@/lib/store/sc03";
import { PreparationNote } from "@/components/shared/preparation-note";
import type { Preparation } from "@/lib/preparation";

/**
 * 장면 3 화면 머리 — 제목 한 줄 + 상태 한 줄(장면 1·2와 같다). 검토건·공장·제품·단위는 상태 줄에 늘 있다
 * (UI31 — 전사 1조원 매출과 혼동 금지). 화면 id·질문은 해설 모드에서만 보인다.
 */
export function Sc03Header({ id, title, question }: { id: string; title: string; question: string }) {
  const view = useSc03(selectView3);
  return (
    <header className="space-y-1.5">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
        <span>{view ? formatClock(view.clock) : "—"}</span>
        <span aria-hidden>·</span>
        <span>MR-2706-01 · 울산 A제품 · 백만원</span>
        <span aria-hidden>·</span>
        <span>{view ? (REVIEW_STATE_LABEL[view.status.review] ?? view.status.review) : "—"}</span>
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
      <InflightBanner />
    </header>
  );
}

function MyAlerts() {
  const view = useSc03(selectView3);
  const actor = useSc01((s) => s.actor);
  const count = (view?.alerts ?? []).filter((a) => a.to.includes(actor)).length;
  if (count === 0) return null;
  return (
    <Link href="/sc03/tasks" className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium text-foreground">
      <BellRing aria-hidden className="size-3" style={{ color: "var(--viz-status-critical)" }} />내 알림 {count}건
    </Link>
  );
}

const EXECUTOR_LABEL: Record<string, string> = {
  center: "Center 서버 실행",
  studio: "Studio 시험 실행",
  embedded: "내장 BPM(시험용)",
};

/** 어디서 BPM이 도는지·어디서 답하는지 — 표시하지 않으면 화면에서 답할 수 있다고 착각한다(장면 2와 같다). */
function ExecutorBanner() {
  const view = useSc03(selectView3);
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
            ? "결재는 Studio 시험 대화상자에서 답하세요. 회의 기록·과제 초안 수정은 이 화면에서 한다."
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

/**
 * Center 반영 중 — 대리 답은 결재를 닫을 뿐이고 그 뒤의 기록·다음 결재는 실행기가 따로 올린다(10~25초, 화면 직접
 * 진행 실측). 그동안 폼은 사라지고 다음 업무는 아직이라 화면이 비어 「안 된 것인가」로 보였다. 엔진이 센 「보냈는데
 * 기록이 아직 안 온 결재」(`inflight`)가 있을 때만 보인다 — SSE로 반영되면 저절로 걷힌다.
 */
function InflightBanner() {
  const view = useSc03(selectView3);
  const topology = useSc03((s) => s.topology);
  const inflight = view?.historical ? [] : (view?.bpm?.center?.inflight ?? []);
  if (inflight.length === 0) return null;
  const titles = inflight.map((n) => topology?.nodes.find((x) => x.id === n)?.name ?? n).join(" · ");
  return (
    <p role="status" className="flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-xs">
      <Loader2 aria-hidden className="size-3.5 animate-spin" />
      <span>
        <span className="font-medium">Center 반영 중</span> — {titles}의 답을 Center 결재함에 보냈다. 실행기가 기록하고
        다음 업무를 올리면(보통 10~25초) 이 화면에 저절로 보인다. 다시 누르지 않아도 된다.
      </span>
    </p>
  );
}

function Banner() {
  const past = useSc03((s) => s.past);
  const connection = useSc03((s) => s.connection);
  const error = useSc03((s) => s.error);
  const setPast = useSc03((s) => s.setPast);
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
 * 장면 3이 아직 없는 데모 실행 — 시작을 묻는다. 장면 2가 인수 전이면 엔진이 장면 2 각본을 인수까지 **실제로**
 * 실행한 뒤 시작한다(지름길로 「인수됨」을 만들지 않는다). 그래서 저절로 하지 않고 묻는다.
 */
export function Sc03StartCard() {
  const demoRunId = useSc01((s) => s.demoRunId);
  const [busy, setBusy] = useState(false);
  const [prep, setPrep] = useState<Preparation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const start = async () => {
    setBusy(true);
    setError(null);
    // 실행 위치는 Center다(2026-10-27 — 화면은 내장을 고르지 않는다). Studio는 플레이어에서 고른다.
    const r = await sc03Api.create(demoRunId, "BASE", "center", setPrep);
    setBusy(false);
    setPrep(null);
    if (r.ok) {
      useSc03.getState().setLive(r.data);
      // 장면 2(·1)가 각본으로 끝났을 수 있다 — 그 화면도 새 상태를 받게 한다.
      useSc02.getState().clearLive(false);
    } else setError(`${r.status} — ${r.error}`);
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>수익성 통합 분석 시작</CardTitle>
        <CardDescription>
          수익성 통합 분석은 외주 단가 인상 검토의 승인 원가 등록·경영관리 인수에서 시작한다. 같은 데모 실행
          {demoRunId ? <span className="font-mono"> {demoRunId}</span> : null}을 잇는다.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-xs text-muted-foreground">
          외주 단가 인상 검토가 아직 인수 전이면 외주 단가 인상 검토 각본의 남은 단계를 인수까지 실제로 실행한다(역할 검사·업무 규칙 그대로).
        </p>
        <Button size="sm" onClick={() => void start()} disabled={busy || !demoRunId}>
          <PlayCircle aria-hidden className="size-3.5" />
          {busy ? "준비하는 중…" : "수익성 통합 분석 시작"}
        </Button>
        {busy ? <PreparationNote p={prep} /> : null}
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
export function Sc03Body({ children }: { children: (view: Sc03View) => React.ReactNode }) {
  const view = useSc03(selectView3);
  const missing = useSc03((s) => s.missing);
  if (view) return <>{children(view)}</>;
  if (missing) return <Sc03StartCard />;
  return <p className="text-sm text-muted-foreground">수익성 통합 분석을 불러오는 중…</p>;
}

/**
 * 독립 배지(UI31·DEC36) — 업무 상태 · 검토 결론 · Risk · 공식 Forecast · Target. 장면 완료 ≠ 위험 해소 ≠ 전망 승인.
 */
export function StatusPills({ view }: { view: Sc03View }) {
  const s = view.status;
  return (
    <div className="flex flex-wrap gap-1.5">
      <StatePill label="업무" value={REVIEW_STATE_LABEL[s.review] ?? s.review} tone={s.review === "SC03_COMPLETED" ? "good" : "neutral"} />
      <StatePill label="검토 결론" value={s.outcome ? OUTCOME_LABEL[s.outcome] : "결론 전"} />
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
  view: Sc03View;
  nodes: string[];
  initial?: Record<string, Record<string, unknown>>;
  expect?: (nodeId: string) => Record<string, unknown> | undefined;
  labels?: Record<string, string>;
}) {
  const waiting = (view.bpm?.waiting ?? []).filter((w) => nodes.includes(w.nodeId));
  if (waiting.length === 0 || view.historical) return null;
  return (
    <>
      {waiting.map((w: Sc03Waiting) => (
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
            <Sc03ActionForm
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
