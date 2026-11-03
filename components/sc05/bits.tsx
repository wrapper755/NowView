"use client";

import { CompanyLink as Link } from "@/components/shared/company-link";
import { AlertTriangle, BellRing, History, Loader2, WifiOff } from "lucide-react";

import { StatePill } from "@/components/sc01/bits";
import { ExecutorNote, SceneNotOpened, WaitingNotice } from "@/components/shared/company-site-note";
import { Commentary } from "@/components/shared/commentary";
import { Card, CardContent } from "@/components/ui/card";
import { formatClock, formatWonExact } from "@/lib/sc01/format";
import {
  CHECK_LABEL,
  CONDITION_STATE_LABEL,
  formatMillion,
  OPERATION_STATE_LABEL,
  SCENE_STATE_LABEL,
} from "@/lib/sc05/format";
import type { Sc05View, Sc05Waiting } from "@/lib/sc05/types";
import { useSc01 } from "@/lib/store/sc01";
import { selectView5, useSc05 } from "@/lib/store/sc05";

/**
 * 장면 5 화면 머리 — 제목 한 줄 + 상태 한 줄(장면 1~4와 같다). 검토건·공장·제품·대상기간·단위·기준시각·공식본/검토안
 * 구분은 상태 줄에 늘 있다(구현명세 2장 공통 표시). 화면 id·질문은 해설 모드에서만 보인다.
 */
export function Sc05Header({ id, title, question }: { id: string; title: string; question: string }) {
  const view = useSc05(selectView5);
  return (
    <header className="space-y-1.5">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
        <span>{view ? formatClock(view.clock) : "—"}</span>
        <span aria-hidden>·</span>
        <span>MR-2706-01 · 울산 A제품 · 2027 · 백만원</span>
        <span aria-hidden>·</span>
        <span>{view ? (SCENE_STATE_LABEL[view.status.scene] ?? view.status.scene) : "—"}</span>
        <span aria-hidden>·</span>
        <span>공식본 {view?.official ?? "미적재"}</span>
        {view && view.caseId !== "BASE" ? (
          <span className="rounded border px-1.5 py-0.5 text-[10px] font-medium text-foreground">{view.caseLabel}</span>
        ) : null}
        <span className="rounded border px-1.5 py-0.5 text-[10px]">시연 데이터</span>
        <MyAlerts />
      </div>
      <Commentary block>
        <p className="text-xs text-muted-foreground">
          <span className="font-mono">{id}</span> · {question} · 공장관리손익은 전사 영업이익이 아니다(본사비·금융비·세금 제외) ·
          금액은 원 단위로 계산하고 백만원으로 보인다 · 미확인은 0이 아니다
        </p>
      </Commentary>
      <Banner />
      <ExecutorBanner />
      <InflightBanner />
    </header>
  );
}

/**
 * Center 반영 중 — 대리 답은 결재를 닫을 뿐이고 그 뒤의 기록·다음 결재는 실행기가 따로 올린다(약 10초, 화면 직접 진행
 * 실측). 그동안 폼은 사라지고 다음 업무는 아직이라 화면이 비었다. 엔진이 센 「보냈는데 기록이 아직 안 온 결재」
 * (`inflight`)가 있을 때만 보인다 — SSE로 반영되면 저절로 걷힌다(장면 3과 같다).
 */
function InflightBanner() {
  const view = useSc05(selectView5);
  const topology = useSc05((s) => s.topology);
  const inflight = view?.historical ? [] : (view?.bpm?.center?.inflight ?? []);
  if (inflight.length === 0) return null;
  const titles = inflight.map((n) => topology?.nodes.find((x) => x.id === n)?.name ?? n).join(" · ");
  return (
    <p role="status" className="flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-xs">
      <Loader2 aria-hidden className="size-3.5 animate-spin" />
      <span>
        <span className="font-medium">Center 반영 중</span> — {titles}의 답이 Center에 들어갔다. 실행기가 기록하고 다음 업무를 올리면 이 화면에 저절로 보인다.
      </span>
    </p>
  );
}

function MyAlerts() {
  const view = useSc05(selectView5);
  const actor = useSc01((s) => s.actor);
  const count = (view?.alerts ?? []).filter((a) => a.to.includes(actor)).length;
  if (count === 0) return null;
  return (
    <Link href="/sc05/changes" className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium text-foreground">
      <BellRing aria-hidden className="size-3" style={{ color: "var(--viz-status-critical)" }} />내 알림 {count}건
    </Link>
  );
}

/** 어디서 BPM이 도는지 — 그리고 결재 답·시연 조작은 회사 사이트에서 한다는 것(읽기 전용, role-split §5.5). */
function ExecutorBanner() {
  const view = useSc05(selectView5);
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
  const past = useSc05((s) => s.past);
  const connection = useSc05((s) => s.connection);
  const error = useSc05((s) => s.error);
  const setPast = useSc05((s) => s.setPast);
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

/** 장면 5 문서가 아직 없다 — 여는 것은 회사 사이트의 시연 조작이다(예전의 시작 카드 자리). */
function Sc05NotOpened() {
  const demoRunId = useSc01((s) => s.demoRunId);
  return <SceneNotOpened work="결정 실행과 계획 갱신" demoRunId={demoRunId} from="수익성 개선 대응안 검토의 실행 승인·책임 인수(HANDOFF41)" />;
}

/** 화면 몸통 — 문서가 없으면 「아직 열리지 않았다」(여는 것은 회사 사이트), 아직 오지 않았으면 불러오는 중. */
export function Sc05Body({ children }: { children: (view: Sc05View) => React.ReactNode }) {
  const view = useSc05(selectView5);
  const missing = useSc05((s) => s.missing);
  if (view) return <>{children(view)}</>;
  if (missing) return <Sc05NotOpened />;
  return <p className="text-sm text-muted-foreground">결정 실행·계획 갱신을 불러오는 중…</p>;
}

/**
 * 독립 배지(구현명세 10장) — 장면 · 계획(확정) · 경영관리 확인 · CON41 · SUP41 · ACT42 운영 · 공식 전망 · Risk · Target.
 * 계획 확정 ≠ 조건 충족 ≠ 착수 ≠ 성과 달성이고, 장면 완료 ≠ 과제 완료 ≠ 위험 해소다.
 */
export function StatusPills({ view }: { view: Sc05View }) {
  const s = view.status;
  return (
    <div className="flex flex-wrap gap-1.5">
      <StatePill label="업무" value={SCENE_STATE_LABEL[s.scene] ?? s.scene} tone={s.scene === "SC05_COMPLETED" ? "good" : "neutral"} />
      <StatePill label="ACT42 계획" value={s.planVersion ? `${s.planVersion} ${s.plan === "CONFIRMED" ? "확정" : (s.plan ?? "")}` : "초안 없음"} />
      <StatePill
        label="경영관리 확인"
        value={s.managementCheck ? (CHECK_LABEL[s.managementCheck] ?? s.managementCheck) : "—"}
        tone={s.managementCheck === "VERIFIED" ? "good" : "neutral"}
      />
      <StatePill label="CON41" value={CONDITION_STATE_LABEL[s.con41] ?? s.con41} tone={s.con41 === "SATISFIED" ? "good" : "warn"} />
      <StatePill label="SUP41" value={CONDITION_STATE_LABEL[s.sup41] ?? s.sup41} tone={s.sup41 === "VERIFIED" ? "good" : "warn"} />
      <StatePill label="ACT42 운영" value={OPERATION_STATE_LABEL[s.operation] ?? s.operation} />
      <StatePill label="공식 전망" value={s.official ?? "해당 시점 공식본 미적재"} />
      <StatePill label="Risk" value="OPEN — 미해결" tone="warn" />
      <StatePill label="Target" value="유지(UNCHANGED)" />
    </div>
  );
}

/**
 * 지금 기다리는 사람 업무 중 이 화면 것 — 읽기 전용이다. 답은 회사 사이트의 결재 화면에서 한다. 없으면 아무것도 그리지 않는다.
 */
export function WaitingList({ view, nodes }: { view: Sc05View; nodes: string[] }) {
  if (view.historical) return null;
  const waiting = (view.bpm?.waiting ?? []).filter((w) => nodes.includes(w.nodeId));
  return (
    <WaitingNotice
      items={waiting.map((w: Sc05Waiting) => ({
        nodeId: w.nodeId,
        title: w.title,
        who: w.assignee ?? w.role,
        taskId: w.taskId,
        due: w.taskId ? formatClock(view.tasks.find((t) => t.task_id === w.taskId)?.due_at) : null,
        
      }))}
    />
  );
}

/** 금액 한 칸 — 백만원 소수 둘째 자리, 원 단위는 title로. NULL은 미확인이다(0이 아니다). */
export function Mn({ value, empty = "미확인", signed = false }: { value: string | null | undefined; empty?: string; signed?: boolean }) {
  if (value === null || value === undefined) return <span className="text-muted-foreground">{empty}</span>;
  const text = signed && Number(value) > 0 ? `+${formatMillion(value)}` : formatMillion(value);
  return (
    <span title={formatWonExact(value)} className="tabular-nums">
      {text}
    </span>
  );
}

/** 숫자 타일 — 섹션 탭에 잡히지 않게 카드에 `data-index-skip`(4.10). */
export function Tile({ label, children, note }: { label: string; children: React.ReactNode; note?: string }) {
  return (
    <Card data-index-skip>
      <CardContent className="space-y-0.5 py-3">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-xl font-semibold tabular-nums">{children}</p>
        {note ? <p className="text-[11px] text-muted-foreground">{note}</p> : null}
      </CardContent>
    </Card>
  );
}

/** 요건 목록 — 충족·미충족을 따로 보인다(개수 합으로 판단하지 않는다, M502). */
export function Requirements({ items }: { items: Array<{ id: string; label: string; ok: boolean }> }) {
  return (
    <ul className="space-y-1 text-sm">
      {items.map((i) => (
        <li key={i.id} className="flex items-center gap-2">
          <span
            aria-hidden
            className="inline-block size-2 rounded-full"
            style={{ background: i.ok ? "var(--viz-status-good)" : "var(--viz-status-warning)" }}
          />
          <span>{i.label}</span>
          <span className="text-xs text-muted-foreground">{i.ok ? "충족" : "미충족"}</span>
        </li>
      ))}
    </ul>
  );
}
