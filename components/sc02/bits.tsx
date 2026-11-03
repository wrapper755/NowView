"use client";

import { CompanyLink as Link } from "@/components/shared/company-link";
import { AlertTriangle, BellRing, History, WifiOff } from "lucide-react";

import { StatePill } from "@/components/sc01/bits";
import { ExecutorNote, SceneNotOpened, WaitingNotice } from "@/components/shared/company-site-note";
import { Commentary } from "@/components/shared/commentary";
import { formatClock, formatKrw, formatWonExact } from "@/lib/sc01/format";
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

/** 어디서 BPM이 도는지 — 그리고 결재 답·시연 조작은 회사 사이트에서 한다는 것(읽기 전용, role-split §5.5). */
function ExecutorBanner() {
  const view = useSc02(selectView2);
  if (!view) return null;
  return (
    <ExecutorNote
      executor={view.executor}
      problem={view.bpm?.center?.problem}
      demoRunId={view.demoRunId}
      externalRunId={view.bpm?.externalRunId ?? null}
    />
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
        지난 시점({formatClock(past.view.clock)})을 보고 있다.
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

/** 화면 몸통 — 문서가 없으면 「아직 열리지 않았다」(여는 것은 회사 사이트), 아직 오지 않았으면 불러오는 중. */
export function Sc02Body({ children }: { children: (view: Sc02View) => React.ReactNode }) {
  const view = useSc02(selectView2);
  const missing = useSc02((s) => s.missing);
  if (view) return <>{children(view)}</>;
  if (missing) return <Sc02NotOpened />;
  return <p className="text-sm text-muted-foreground">외주 단가 인상 검토를 불러오는 중…</p>;
}

function Sc02NotOpened() {
  const demoRunId = useSc01((s) => s.demoRunId);
  return (
    <SceneNotOpened
      work="외주 단가 인상 검토"
      demoRunId={demoRunId}
      from="고객 생산계획 변경 대응의 인계 결과(ISSUE-B07 · 검토 전망 F02)"
    />
  );
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
 * 지금 기다리는 사람 업무 중 이 화면 것 — 읽기 전용이다. 답은 회사 사이트의 결재 화면에서 한다. 없으면 아무것도 그리지 않는다.
 */
export function WaitingList({ view, nodes }: { view: Sc02View; nodes: string[] }) {
  if (view.historical) return null;
  const waiting = (view.bpm?.waiting ?? []).filter((w) => nodes.includes(w.nodeId));
  return (
    <WaitingNotice
      items={waiting.map((w: Waiting) => ({
        nodeId: w.nodeId,
        title: w.title,
        who: w.role,
        taskId: w.taskId,
        due: w.taskId ? formatClock(view.tasks.find((t) => t.task_id === w.taskId)?.due_at) : null,
      }))}
    />
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
