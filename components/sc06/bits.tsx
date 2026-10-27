"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, CircleDashed, CircleAlert, FileSearch, Lock, PlayCircle, RefreshCw, type LucideIcon } from "lucide-react";

import { Commentary } from "@/components/shared/commentary";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock, formatWonExact } from "@/lib/sc01/format";
import { cn } from "@/lib/utils";
import { sc06Api } from "@/lib/sc06/client";
import { million, shortClock } from "@/lib/sc06/format";
import type { Evidence, Person } from "@/lib/sc06/types";
import { useSc01 } from "@/lib/store/sc01";
import { type Load, useSc06 } from "@/lib/store/sc06";

/**
 * 장면 6 화면 머리 — 제목 한 줄 + 문맥 한 줄(장면 1~5와 같다). 문맥 줄은 구현명세 2장 「상단 문맥」이다: RV61 · 울산 A제품
 * · 2027 Q4 · FC51 · RPT61-v1 · 기준일·마감일·조회시각. 화면 id·질문은 해설 모드에서만 보인다.
 */
export function Sc06Header({ id, title, question }: { id: string; title: string; question: string }) {
  const meta = useSc06((s) => s.meta);
  return (
    <header className="space-y-1.5">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
        <span>조회 {meta ? formatClock(meta.clock) : "—"}</span>
        <span aria-hidden>·</span>
        <span>RV61 · 울산 A제품 · 2027 Q4(기준일 12/31 · 자료 마감 1/7 18:00)</span>
        <span aria-hidden>·</span>
        <span>비교 기준 {meta?.sc05.official ?? "FC51"} · 보고본 {meta?.reportVersion ?? "RPT61-v1"}</span>
        <span className="rounded border px-1.5 py-0.5 text-[10px]">백만원</span>
        <span className="rounded border px-1.5 py-0.5 text-[10px]">시연 데이터</span>
      </div>
      <Commentary block>
        <p className="text-xs text-muted-foreground">
          <span className="font-mono">{id}</span> · {question} · 확인된 보고본을 조회하는 화면이다 — 조회는 승인·확인·과제 등록을
          만들지 않는다 · 금액은 원 단위로 계산하고 백만원으로 보인다(VAT 제외) · 미확인·미산정은 0이 아니다 · 공장관리손익은 전사
          영업이익이 아니다
        </p>
      </Commentary>
    </header>
  );
}

/** 장면 6 본문 — 열리지 않았으면 「장면 6 열기」, 머리 조회 실패면 사유. */
export function Sc06Body({ children }: { children: React.ReactNode }) {
  const meta = useSc06((s) => s.meta);
  const missing = useSc06((s) => s.missing);
  const error = useSc06((s) => s.metaError);
  const demoRunId = useSc01((s) => s.demoRunId);
  if (error) return <Problem text={`장면 6 문서를 받지 못했다 — ${error}`} />;
  if (missing || (!meta && !demoRunId)) return <OpenCard />;
  if (!meta) return <p className="text-sm text-muted-foreground">장면 6 문서를 불러오는 중…</p>;
  return <>{children}</>;
}

function OpenCard() {
  const demoRunId = useSc01((s) => s.demoRunId);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const open = async () => {
    setPending(true);
    setError(null);
    const r = await sc06Api.open(demoRunId);
    setPending(false);
    if (!r.ok) {
      setError(r.error);
      return;
    }
    if (r.data.demoRunId !== demoRunId) useSc01.getState().setDemoRunId(r.data.demoRunId);
    useSc06.getState().setMeta(r.data);
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>장면 6이 아직 열리지 않았다</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p>
          장면 6은 장면 5 인계(HANDOFF51)와 공식 전망 FC51에서 이어진다. 열면 장면 5가 완료 전일 때 장면 5 각본을 끝까지 실제로
          실행하고, 2027 Q4 검토 자료(RV61)와 확인된 보고본 RPT61-v1을 적재한다.
        </p>
        <Button size="sm" onClick={() => void open()} disabled={pending}>
          <PlayCircle aria-hidden className="size-3.5" />
          {pending ? "여는 중…" : "장면 6 열기"}
        </Button>
        {error ? <Problem text={error} /> : null}
      </CardContent>
    </Card>
  );
}

export function Problem({ text }: { text: string }) {
  return (
    <p role="alert" className="flex items-start gap-2 rounded-md border px-3 py-2 text-xs">
      <AlertTriangle aria-hidden className="mt-0.5 size-3.5 shrink-0" style={{ color: "var(--viz-status-serious)" }} />
      {text}
    </p>
  );
}

/**
 * 조회 하나의 상태 — 로딩·권한 없음·버전 불일치·없음·통신 실패를 갈라 보인다. 실패를 0이나 이전 합계로 보이지 않는다
 * (구현명세 10장 오류 처리).
 */
export function LoadGate<T>({ load, what, children }: { load: Load<T>; what: string; children: (data: T) => React.ReactNode }) {
  if (load.state === "idle" || load.state === "loading") return <p className="text-sm text-muted-foreground">{what}을(를) 불러오는 중…</p>;
  if (load.state === "ok") return <>{children(load.data)}</>;
  if (load.code === "ACCESS_DENIED") return <AccessDenied />;
  if (load.code === "VERSION_MISMATCH") {
    return (
      <div className="space-y-2">
        <Problem text={`${load.error} 화면의 숫자와 문구를 섞지 않도록 표시를 멈췄다.`} />
        <Button variant="outline" size="sm" onClick={() => window.location.reload()}>
          <RefreshCw aria-hidden className="size-3.5" />
          다시 조회
        </Button>
      </div>
    );
  }
  return <Problem text={`${what} 조회 실패(${load.status}) — ${load.error}. 금액을 0이나 이전 값으로 보이지 않는다.`} />;
}

function AccessDenied() {
  const setActor = useSc01((s) => s.setActor);
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border px-3 py-2 text-sm">
      <Lock aria-hidden className="size-4 text-muted-foreground" />
      <span>
        지금 역할은 이 검토건(RV61)을 볼 수 없다. 검토·확인·보고에 참여한 경영관리·구매·생산·대표만 본다.
      </span>
      <Button size="sm" variant="outline" onClick={() => setActor("u-fin")}>
        경영관리 담당으로 보기
      </Button>
    </div>
  );
}

/** 금액 칸 — 백만원, 원값은 title. null은 이유 글자(0 아님). */
export function Mn({ won, empty, className }: { won: number | null | undefined; empty?: string; className?: string }) {
  return (
    <span className={cn("tabular-nums", className)} title={won === null || won === undefined ? undefined : formatWonExact(won)}>
      {million(won, empty)}
    </span>
  );
}

export function personName(p: Person | null | undefined): string {
  if (!p) return "—";
  return p.role ? `${p.role} ${p.name}` : p.name;
}

/** 상태 — 색만으로 말하지 않는다(4.4). 아이콘 + 글자. */
export function StateTag({ tone, children }: { tone: "good" | "warn" | "open" | "neutral"; children: React.ReactNode }) {
  const icon: Record<string, LucideIcon> = { good: CheckCircle2, warn: CircleAlert, open: CircleDashed, neutral: CircleDashed };
  const color: Record<string, string> = {
    good: "var(--viz-status-good)",
    warn: "var(--viz-status-serious)",
    open: "var(--viz-status-warning)",
    neutral: "var(--color-muted-foreground)",
  };
  const Icon = icon[tone];
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium">
      <Icon aria-hidden className="size-3.5 shrink-0" style={{ color: color[tone] }} />
      {children}
    </span>
  );
}

/**
 * 근거 ID — 누르면 같은 자리에서 본문·작성·확인 이력을 편다(외부 창·다운로드 없음). 가상 증빙이라고 밝힌다. 권한이 없거나
 * 못 찾으면 그 상태를 보이고 근거 확보로 처리하지 않는다(구현명세 4장 근거 조회 계약).
 */
export function EvidenceChip({ id }: { id: string }) {
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const version = useSc06((s) => s.meta?.reportVersion);
  const [open, setOpen] = useState(false);
  const [load, setLoad] = useState<Load<Evidence>>({ state: "idle" });
  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (!next || !demoRunId || !version || load.state === "ok") return;
    setLoad({ state: "loading" });
    const r = await sc06Api.evidence(demoRunId, id, version, actor);
    setLoad(r.ok ? { state: "ok", data: r.data } : { state: "error", status: r.status, error: r.error, code: r.code });
  };
  return (
    <span className="inline-block align-top">
      <button
        type="button"
        onClick={() => void toggle()}
        aria-expanded={open}
        className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[11px] hover:bg-muted"
      >
        <FileSearch aria-hidden className="size-3" />
        {id}
      </button>
      {open ? (
        <span className="mt-1.5 block max-w-prose rounded-md border bg-muted/40 px-3 py-2 text-xs leading-relaxed">
          {load.state === "ok" ? (
            <>
              <span className="block font-medium">
                {load.data.kind} · {load.data.target} <span className="font-normal text-muted-foreground">(가상 증빙 본문)</span>
              </span>
              <span className="block">{load.data.body}</span>
              <span className="block text-muted-foreground">
                작성 {personName(load.data.written_by)} {shortClock(load.data.written_at)} · 확인 {personName(load.data.checked_by)}{" "}
                {shortClock(load.data.checked_at)}
              </span>
            </>
          ) : load.state === "error" ? (
            <span className="block">
              {load.code === "ACCESS_DENIED" ? "이 근거를 볼 권한이 없다" : load.code === "NOT_FOUND" ? "근거를 찾지 못했다" : load.error} — 근거
              확보로 보지 않는다.
            </span>
          ) : (
            <span className="block text-muted-foreground">근거를 불러오는 중…</span>
          )}
        </span>
      ) : null}
    </span>
  );
}
