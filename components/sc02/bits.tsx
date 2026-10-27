"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, BellRing, ExternalLink, History, PlayCircle, WifiOff } from "lucide-react";

import { StatePill } from "@/components/sc01/bits";
import { Sc02ActionForm } from "@/components/sc02/action-form";
import { Commentary } from "@/components/shared/commentary";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock, formatKrw, formatWonExact } from "@/lib/sc01/format";
import { sc02Api } from "@/lib/sc02/client";
import {
  APPROVAL_STATUS_LABEL,
  COST_STATUS_LABEL,
  HANDOFF_STATUS_LABEL,
  REQUEST_STATUS_LABEL,
  SCENE2_LABEL,
} from "@/lib/sc02/format";
import type { Sc02View, Waiting } from "@/lib/sc02/types";
import { useSc01 } from "@/lib/store/sc01";
import { selectView2, useSc02 } from "@/lib/store/sc02";

/**
 * 장면 2 화면 머리 — SC01과 같은 모양(제목 한 줄 + 상태 한 줄). 화면 id·질문은 해설 모드에서만 보인다.
 * 지난 시점·연결 끊김·장면 2 없음은 배너로 말한다 — 조용히 낡은 화면을 보이지 않는다.
 */
export function Sc02Header({ id, title, question }: { id: string; title: string; question: string }) {
  const view = useSc02(selectView2);
  return (
    <header className="space-y-1.5">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
        <span>{view ? formatClock(view.clock) : "—"}</span>
        <span aria-hidden>·</span>
        <span>외주 단가 인상 검토 {view ? SCENE2_LABEL[view.status.scene] ?? view.status.scene : "—"}</span>
        {view && view.caseId !== "BASE" ? (
          <span className="rounded border px-1.5 py-0.5 text-[10px] font-medium text-foreground">{view.caseLabel}</span>
        ) : null}
        <span className="rounded border px-1.5 py-0.5 text-[10px]">시연 데이터</span>
        <MyAlerts />
      </div>
      <Commentary block>
        <p className="text-xs text-muted-foreground">
          <span className="font-mono">{id}</span> · {question} · A제품 · 울산공장(ULS) · 공통부품 P-COM01 · 공급사
          SUP-01 · 금액은 VAT 제외 원 단위
        </p>
      </Commentary>
      <Banner />
      <ExecutorBanner />
    </header>
  );
}

function MyAlerts() {
  const view = useSc02(selectView2);
  const actor = useSc01((s) => s.actor);
  const count = (view?.alerts ?? []).filter((a) => a.to.includes(actor)).length;
  if (count === 0) return null;
  return (
    <Link
      href="/sc02"
      className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium text-foreground"
    >
      <BellRing aria-hidden className="size-3" style={{ color: "var(--viz-status-critical)" }} />내 알림 {count}건
    </Link>
  );
}

const EXECUTOR_LABEL: Record<string, string> = {
  center: "Center 서버 실행",
  studio: "Studio 시험 실행",
  embedded: "내장 BPM(시험용)",
};

/**
 * 어디서 BPM이 도는지·어디서 답하는지 — 표시하지 않으면 화면에서 답할 수 있다고 착각한다(SC01 N2와 같다).
 * Studio면 Studio에 넣을 입력(데모실행ID·요청ID)을 보이고, Center면 기동한 작업과 막힌 사유를 그대로 보인다.
 */
function ExecutorBanner() {
  const view = useSc02(selectView2);
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
            ? "결재는 Studio 시험 대화상자에서 답하세요. 이 화면은 결재를 받지 않는다."
            : "결재는 Center 결재함에서 답하세요."}
      </span>
      {problem ? (
        <span className="inline-flex basis-full items-center gap-1 font-medium">
          <AlertTriangle aria-hidden className="size-3.5 shrink-0" style={{ color: "var(--viz-status-serious)" }} />
          {problem}
        </span>
      ) : null}
      <span className="text-muted-foreground">
        입력 데모실행ID <span className="font-mono">{view.demoRunId}</span>
        {view.request ? (
          <>
            {" "}· 요청ID <span className="font-mono">{view.request.request_id}</span>
          </>
        ) : null}{" "}
        · 바깥 실행 {view.bpm?.externalRunId ? <span className="font-mono">{view.bpm.externalRunId}</span> : "첫 작업 호출 전"}
        {view.bpm?.center?.job ? (
          <>
            {" "}· 작업 <span className="font-mono">{view.bpm.center.job.job_id}</span>
          </>
        ) : null}
      </span>
    </p>
  );
}

function Banner() {
  const past = useSc02((s) => s.past);
  const connection = useSc02((s) => s.connection);
  const error = useSc02((s) => s.error);
  const setPast = useSc02((s) => s.setPast);
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
 * 장면 2가 아직 없는 데모 실행 — 시작을 묻는다. 장면 1이 인계 전이면 엔진이 장면 1 각본을 인계까지
 * **실제로** 실행한 뒤 시작한다(지름길로 「인계됨」을 만들지 않는다). 그래서 저절로 하지 않고 묻는다.
 */
export function Sc02StartCard() {
  const demoRunId = useSc01((s) => s.demoRunId);
  const sc01Scene = useSc01((s) => s.live?.scene);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const start = async () => {
    setBusy(true);
    setError(null);
    // 실행 위치는 Center다(2026-10-27 — 화면은 내장을 고르지 않는다). Studio는 플레이어에서 고른다.
    const r = await sc02Api.create(demoRunId, "BASE", "center");
    setBusy(false);
    if (r.ok) {
      useSc02.getState().setLive(r.data);
      // 장면 1이 각본으로 끝났을 수 있다 — 장면 1 화면도 새 상태를 받게 한다.
      const sc01 = await fetch(`/api/engine/sc01/demo-runs/${r.data.demoRunId}`, { cache: "no-store" });
      if (sc01.ok) useSc01.getState().setLive(await sc01.json());
    } else {
      setError(`${r.status} — ${r.error}`);
    }
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>외주 단가 인상 검토 시작</CardTitle>
        <CardDescription>
          외주 단가 인상 검토는 고객 생산계획 변경 대응의 인계 결과(ISSUE-B07 · 검토 전망 F02)에서 시작한다. 같은 데모 실행
          {demoRunId ? <span className="font-mono"> {demoRunId}</span> : null}을 잇는다.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {sc01Scene !== "HANDED_OFF" ? (
          <p className="text-xs text-muted-foreground">
            고객 생산계획 변경 대응이 아직 인계 전이다 — 시작하면 고객 생산계획 변경 대응 각본의 남은 단계를 인계까지 실제로 실행한다(역할 검사·업무 규칙
            그대로).
          </p>
        ) : null}
        <Button size="sm" onClick={() => void start()} disabled={busy || !demoRunId}>
          <PlayCircle aria-hidden className="size-3.5" />
          {busy ? "준비하는 중…" : "외주 단가 인상 검토 시작"}
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
export function Sc02Body({ children }: { children: (view: Sc02View) => React.ReactNode }) {
  const view = useSc02(selectView2);
  const missing = useSc02((s) => s.missing);
  if (view) return <>{children(view)}</>;
  if (missing) return <Sc02StartCard />;
  return <p className="text-sm text-muted-foreground">외주 단가 인상 검토를 불러오는 중…</p>;
}

/** 상태 칩 — 축마다 따로(구현명세 10장). 단가안 승인 완료 ≠ 위험 해소 ≠ 전망 승인. */
export function StatusPills({ view }: { view: Sc02View }) {
  const s = view.status;
  return (
    <div className="flex flex-wrap gap-1.5">
      <StatePill label="요청" value={s.request ? REQUEST_STATUS_LABEL[s.request] ?? s.request : "접수 전"} />
      <StatePill
        label="기안 승인"
        value={s.approval ? APPROVAL_STATUS_LABEL[s.approval] ?? s.approval : "상신 전"}
        tone={s.approval === "APPROVED" ? "good" : s.approval && /REJECT|RENEG|RETURN/.test(s.approval) ? "warn" : "neutral"}
      />
      <StatePill label="원가" value={s.cost ? COST_STATUS_LABEL[s.cost] : "미등록"} />
      <StatePill label="인계" value={s.handoff ? HANDOFF_STATUS_LABEL[s.handoff] : "인계 전"} tone={s.handoff === "HANDED_OFF" ? "good" : "neutral"} />
      <StatePill label="수익성 위험" value="열림 — 미해결" tone="warn" />
      <StatePill label="전망" value="F02 검토 중 — 승인 아님" />
    </div>
  );
}

/**
 * 지금 기다리는 사람 업무 중 이 화면 것 — 폼은 BPMN에서 온다. 없으면 아무것도 그리지 않는다.
 * `expect`는 결재·인수에 화면이 본 버전을 싣는다.
 */
export function WaitingForms({
  view,
  nodes,
  initial,
  expect,
  labels,
}: {
  view: Sc02View;
  nodes: string[];
  initial?: Record<string, Record<string, unknown>>;
  expect?: Record<string, string>;
  labels?: Record<string, string>;
}) {
  const waiting = (view.bpm?.waiting ?? []).filter((w) => nodes.includes(w.nodeId));
  if (waiting.length === 0 || view.historical) return null;
  return (
    <>
      {waiting.map((w: Waiting) => (
        <Card key={w.nodeId}>
          <CardHeader>
            <CardTitle>지금 할 일 — {w.title}</CardTitle>
            <CardDescription>
              담당 {w.role}
              {w.taskId ? (
                <>
                  {" "}
                  · <span className="font-mono">{w.taskId}</span> 기한{" "}
                  {formatClock(view.tasks.find((t) => t.task_id === w.taskId)?.due_at)}
                </>
              ) : null}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Sc02ActionForm
              key={`${w.nodeId}-${view.audit.length}`}
              waiting={w}
              initial={initial?.[w.nodeId]}
              expect={expect}
              submitLabel={labels?.[w.nodeId] ?? "제출"}
            />
          </CardContent>
        </Card>
      ))}
    </>
  );
}

/** 금액 한 칸 — 억·만 단위 표시, 원 단위는 title로(UI01-05와 같다). 미산출은 미산출이다(0이 아니다). */
export function Won({ value, signed = false }: { value: string | null | undefined; signed?: boolean }) {
  if (value === null || value === undefined) return <span className="text-muted-foreground">미산출</span>;
  const v = Number(value);
  const text = signed && v > 0 ? `+${formatKrw(value)}` : formatKrw(value);
  return (
    <span title={formatWonExact(value)} className="tabular-nums">
      {text}원
    </span>
  );
}

/** 정밀 원값 그대로 — 상세 확인용. */
export function WonExact({ value }: { value: string | null | undefined }) {
  if (value === null || value === undefined) return <span className="text-muted-foreground">미산출</span>;
  return <span className="tabular-nums">{formatWonExact(value)}</span>;
}
