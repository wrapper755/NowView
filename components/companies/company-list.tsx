"use client";

import Link from "next/link";
import { ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { SCENES, useCompanies } from "@/lib/companies";
import { SupplyBoardView } from "@/components/companies/supply-board";
import {
  type Dashboard,
  type Work,
  STATE_LABEL,
  caseUrl,
  formatClock,
  formatMetric,
  formatWon,
  workUrl,
} from "@/lib/dashboard";

/** 사건 화면에서 돌아올 곳 — 이 대시보드의 같은 회차(공통 플랫폼 X02 — 맥락 유지). */
function backUrl(companyId: string, world: string | null): string {
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const q = world ? `?world=${encodeURIComponent(world)}` : "";
  return `${origin}/c/${encodeURIComponent(companyId)}${q}`;
}

/** 회사 목록 — 엔진 설정의 공개 목록(이름·설명·업무). 회사는 설정이라 빌드 때 모른다. */
export function CompanyList() {
  const { companies, error } = useCompanies();
  if (error) return <p className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">{error}</p>;
  if (!companies) return <p className="text-sm text-muted-foreground">회사 목록을 읽는 중…</p>;
  if (companies.length === 0) return <p className="text-sm text-muted-foreground">등록된 회사가 없다.</p>;
  return (
    <ul className="grid gap-4 md:grid-cols-2">
      {companies.map((c) => (
        <li key={c.id}>
          <Link href={`/c/${c.id}`} className="block h-full">
            <Card className="h-full transition-colors hover:border-brand/60">
              <CardHeader>
                <CardTitle>{c.name}</CardTitle>
                <CardDescription>{c.description}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <p className="text-muted-foreground">업무 {c.scenes.length}개</p>
                <ol className="flex flex-wrap gap-1.5">
                  {SCENES.filter((s) => c.scenes.includes(s.no)).map((s) => (
                    <li key={s.no}>
                      <Badge variant="outline">
                        {s.no}. {s.work}
                      </Badge>
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          </Link>
        </li>
      ))}
    </ul>
  );
}

type Loaded = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ok"; data: Dashboard };

/**
 * 대시보드를 읽는다 — 10초마다 다시 읽는다(일꾼이 세계를 2초마다 따라가므로 그보다 촘촘할 까닭이 없다). `world`가 없으면
 * 엔진이 마지막 세계를 고른다. 회사가 없으면 404를 그대로 말한다.
 */
function useDashboard(companyId: string, world: string | null): Loaded {
  const [state, setState] = useState<Loaded>({ kind: "loading" });
  useEffect(() => {
    let alive = true;
    const read = async () => {
      let next: Loaded;
      try {
        const q = world ? `?world=${encodeURIComponent(world)}` : "";
        const res = await fetch(`/api/engine/companies/${encodeURIComponent(companyId)}/dashboard${q}`, {
          cache: "no-store",
        });
        next = res.ok
          ? { kind: "ok", data: (await res.json()) as Dashboard }
          : { kind: "error", message: res.status === 404 ? "404" : `엔진이 ${res.status}를 돌려줬다` };
      } catch {
        next = { kind: "error", message: "엔진에 닿지 않는다" };
      }
      if (alive) setState(next);
    };
    void read();
    const timer = setInterval(read, 10_000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [companyId, world]);
  return state;
}

function SiteLink({ href, children }: { href: string | null; children: React.ReactNode }) {
  if (!href) return null;
  return (
    <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm text-brand hover:underline">
      {children}
      <ExternalLink aria-hidden className="size-3.5" />
    </a>
  );
}

/** 업무 하나 — BPM 진행·열린 결재·핵심 지표·일꾼 일감, 그리고 회사 사이트의 업무 화면 링크. */
function WorkCard({ work, href }: { work: Work; href: string | null }) {
  const started = work.state !== "none";
  const { progress } = work;
  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle>
          {work.scene}. {work.work}
        </CardTitle>
        <CardDescription className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <Badge variant={work.state === "running" ? "default" : work.state === "failed" ? "destructive" : "secondary"}>
            {STATE_LABEL[work.state] ?? work.state}
          </Badge>
          {work.clock && <span>가상시각 {formatClock(work.clock)}</span>}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {progress && progress.approvals === 0 && (
          // 시나리오 2 장면 1 — 사람 결재가 없다(조회만). 구매 개정 하나가 실행 하나다.
          <p className="text-xs text-muted-foreground">사람 결재 없음 · 구매 개정 실행 {progress.runs ?? 0}건</p>
        )}
        {progress && progress.approvals > 0 && (
          <div className="space-y-1.5">
            <p className="flex justify-between text-xs text-muted-foreground">
              <span>지나온 결재</span>
              {/* 갈래가 있는 그림은 끝나도 모든 결재를 지나지 않는다 — 비율을 완료율로 읽지 않게 수만 쓴다. */}
              <span className="tabular-nums">
                {progress.passed} / 그림의 결재 {progress.approvals}
              </span>
            </p>
            <Progress value={progress.approvals ? (progress.passed / progress.approvals) * 100 : 0} aria-label="지나온 결재" />
          </div>
        )}
        {work.waiting.length > 0 && (
          <div>
            <p className="text-xs text-muted-foreground">열린 결재</p>
            <ul className="mt-1 space-y-0.5">
              {work.waiting.map((w, i) => (
                <li key={`${w.nodeId}-${i}`}>{w.title ?? w.nodeId}</li>
              ))}
            </ul>
          </div>
        )}
        {work.metrics.length > 0 && (
          <dl className="grid grid-cols-2 gap-x-3 gap-y-2">
            {work.metrics.map((m) => (
              <div key={m.label} className={m.kind === "text" ? "col-span-2" : undefined}>
                <dt className="text-xs text-muted-foreground">{m.label}</dt>
                <dd className="font-semibold tabular-nums" title={m.kind === "krw" ? formatWon(m.value) : undefined}>
                  {formatMetric(m)}
                </dd>
              </div>
            ))}
          </dl>
        )}
        {started && (
          <div>
            <p className="text-xs text-muted-foreground">
              일꾼 일감 {work.worker.count}건
              {work.worker.failed > 0 && <span className="text-destructive"> · 실패 {work.worker.failed}건</span>}
            </p>
            {work.worker.recent.length > 0 && (
              <ul className="mt-1 space-y-0.5 font-mono text-xs">
                {work.worker.recent.map((r, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="shrink-0 text-muted-foreground">{formatClock(r.at)}</span>
                    <span className={r.ok ? "truncate" : "truncate text-destructive"} title={r.reason ?? undefined}>
                      {r.operation}
                      {!r.ok && " ✕"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        <SiteLink href={href}>회사 사이트에서 보기</SiteLink>
      </CardContent>
    </Card>
  );
}

/**
 * 회사 대시보드 — 고른 세계(시연 회차)에서 그 회사 업무마다 BPM 진행·일꾼 일감·핵심 지표. **업무 판단 화면이 아니다** —
 * 업무 화면·해설·업무 설명은 회사 사이트(`/work/{회차}/sc0N`)에 있고 카드가 그리로 잇는다(2026-11-03 4단계,
 * `docs/role-split.md`). 실행 상세는 Center 콘솔이다.
 */
export function CompanyDashboard({ companyId, initialWorld = null }: { companyId: string; initialWorld?: string | null }) {
  const [world, setWorld] = useState<string | null>(initialWorld);
  const loaded = useDashboard(companyId, world);
  if (loaded.kind === "loading") return <p className="text-sm text-muted-foreground">읽는 중…</p>;
  if (loaded.kind === "error") {
    if (loaded.message === "404") {
      return (
        <p className="text-sm">
          없는 회사다: <span className="font-mono">{companyId}</span> —{" "}
          <Link href="/" className="underline">
            회사 목록
          </Link>
        </p>
      );
    }
    return <p className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">{loaded.message}</p>;
  }
  const { company, worlds, works, problem } = loaded.data;
  const chosen = loaded.data.world;
  // 시나리오 2 회차 — 납기 상황판(UI-D01)이 머리에 온다(장면 1 기록 `dashboard`)
  const board = works.find((w) => w.board)?.board ?? null;
  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{company.name}</h1>
          <p className="text-sm text-muted-foreground">{company.description}</p>
        </div>
        <SiteLink href={company.siteUrl}>회사 사이트</SiteLink>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <label htmlFor="world" className="text-muted-foreground">
          시연 회차
        </label>
        {worlds.length > 0 ? (
          <select
            id="world"
            value={chosen ?? ""}
            onChange={(e) => setWorld(e.target.value)}
            className="h-8 w-full min-w-0 rounded-md border bg-card px-2 font-mono text-xs sm:w-auto"
          >
            {worlds.map((w) => (
              <option key={w.worldId} value={w.worldId}>
                {`시나리오 ${(w.scenarioId ?? "s1").slice(1)}`} · {w.worldId} · {w.caseId ?? "BASE"} · {w.generation ?? 1}회차 ·{" "}
                {formatClock(w.clock)}
              </option>
            ))}
          </select>
        ) : (
          <span className="text-muted-foreground">없음 — 회사 사이트의 시연 조작에서 만든다</span>
        )}
      </div>
      {problem && <p className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">{problem}</p>}
      {board && (
        <SupplyBoardView
          board={board}
          openCase={(commitment) => caseUrl(company.siteUrl, chosen, backUrl(companyId, chosen), commitment)}
        />
      )}

      <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {works.map((w) => (
          <li key={w.scene}>
            <WorkCard work={w} href={workUrl(company.siteUrl, chosen, w.scene)} />
          </li>
        ))}
      </ol>
      <p className="text-xs text-muted-foreground">
        숫자는 NowView 규칙 계산 그대로다(회사 시스템에 적은 경영 기록과 같다). 업무 화면·결재·시연 조작은 회사 사이트에서
        한다. 실행 상세는 Chaeksas Center 콘솔에 있다.
      </p>
    </>
  );
}
