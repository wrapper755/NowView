"use client";

import { useState } from "react";
import Link from "next/link";
import { CheckCircle2, CircleDashed, PlayCircle } from "lucide-react";

import { RiskTag, useUserName } from "@/components/sc01/bits";
import { Mn, Sc03Body, Sc03Header, StatusPills } from "@/components/sc03/bits";
import { Commentary } from "@/components/shared/commentary";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { sc03Api } from "@/lib/sc03/client";
import type { Risk } from "@/lib/sc01/types";
import type { Sc03View } from "@/lib/sc03/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc03 } from "@/lib/store/sc03";

/** 진행 단계(업무설계표 S31~S44) — 검토건 상태에서 파생한다. */
const STAGES: { id: string; label: string; done: (v: Sc03View) => boolean; href: string }[] = [
  { id: "S31", label: "착수 · 사건 연결", done: (v) => v.review.started_at !== null, href: "/sc03" },
  { id: "S32·33", label: "통합 분석", done: (v) => v.currentDraftId !== null, href: "/sc03/analysis" },
  { id: "S34~37", label: "부서 확인 · 쟁점", done: (v) => v.departments.every((d) => d.state === "RESPONDED") && v.questions.every((q) => q.state !== "OPEN"), href: "/sc03/confirm" },
  { id: "S38", label: "자료 확정 · 배포", done: (v) => v.meetings.some((m) => m.meeting_id === "MT31"), href: "/sc03/meeting" },
  { id: "S39~41", label: "수시회의 · 결론", done: (v) => v.decision !== null && v.decision.outcome !== "REWORK_REQUIRED", href: "/sc03/meeting" },
  { id: "S42·43", label: "회의록 · 과제 인수", done: (v) => v.acceptance.assigned > 0 && v.acceptance.accepted === v.acceptance.assigned, href: "/sc03/tasks" },
  { id: "S44", label: "업무 종료 · MT41 연결", done: (v) => v.handoff !== null, href: "/sc03/handoff" },
];

/**
 * U31 수익성 검토 업무함 — MR-2706-01의 두 사건 카드, 승인·원가 등록·인수 근거, 진행 단계·일정. 분석 시작은
 * 경영관리 담당이 한다(S31). 같은 검토건의 재착수는 기존 결과를 돌려준다(T31).
 */
export function Sc03InboxScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc03Header id="U31" title="수익성 검토 업무함" question="두 사건을 같은 경영 기준으로 이어 검토를 시작할 수 있는가?" />
      <Sc03Body>{(view) => <Inbox view={view} />}</Sc03Body>
    </main>
  );
}

function StartButton({ view }: { view: Sc03View }) {
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (view.review.started_at !== null || view.historical) return null;
  const start = async () => {
    if (!demoRunId) return;
    setBusy(true);
    setError(null);
    const r = await sc03Api.start(demoRunId, actor, crypto.randomUUID());
    setBusy(false);
    if (r.ok) useSc03.getState().setLive(r.data);
    else setError(`${r.status} — ${r.error}`);
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>지금 할 일 — 분석 시작</CardTitle>
        <CardDescription>담당 경영관리 담당 · 외주 단가 인상 검토 인수 근거를 확인하고 기존 검토건에 두 사건을 잇는다.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <Button size="sm" onClick={() => void start()} disabled={busy || actor !== "u-fin"}>
          <PlayCircle aria-hidden className="size-3.5" />
          {busy ? "착수하는 중…" : "분석 시작"}
        </Button>
        {actor !== "u-fin" ? <p className="text-xs text-muted-foreground">경영관리 담당(정하윤) 역할만 착수한다 — 상단에서 역할을 바꾼다.</p> : null}
        {error ? (
          <p role="alert" className="text-xs" style={{ color: "var(--viz-status-critical)" }}>
            거절됨: {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Inbox({ view }: { view: Sc03View }) {
  const name = useUserName();
  const b = view.sc02;
  const run = view.runs.find((r) => r.run_id === view.latestRunId && r.result.passed);
  const year = run?.result.periods.year;
  return (
    <>
      <StatusPills view={view} />
      <StartButton view={view} />

      <Card>
        <CardHeader>
          <CardTitle>수익성 검토건 {view.review.review_id}</CardTitle>
          <CardDescription>
            {view.review.started_at
              ? `${formatClock(view.review.started_at)} ${name(view.review.started_by)} 착수`
              : "미착수 — 외주 단가 인상 검토 인수 완료"}
            {year ? (
              <>
                {" "}
                · 전체 부족 <Mn value={year.total_gap} /> 백만원
              </>
            ) : null}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="grid gap-2 sm:grid-cols-2">
            {b.issues.map((i) => (
              <li key={i.issue_id} className="space-y-1 rounded-md border px-3 py-2 text-sm">
                <p className="flex flex-wrap items-center gap-2">
                  <span className="font-mono">{i.issue_id}</span>
                  <span className="text-xs text-muted-foreground">{i.type === "VOLUME" ? "고객 생산계획 변경 대응 물량" : "외주 단가 인상 검토 원가"}</span>
                  <RiskTag risk={i.risk as Risk} />
                </p>
                <p>{i.summary}</p>
                <p className="text-xs text-muted-foreground">
                  근거 <span className="font-mono">{i.run_id}</span> · 위험 열림 — 이력은 각 사건에 그대로 둔다
                </p>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>외주 단가 인상 검토 인수 근거</CardTitle>
            <CardDescription>승인 단가만 반영한다 — 요청가·협상가는 이력 조회용이다(CT31).</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
              <dt className="text-muted-foreground">승인 단가</dt>
              <dd>
                <span className="font-mono">{b.price.version_id}</span> {Number(b.price.old_price).toLocaleString("ko-KR")} →{" "}
                {Number(b.price.new_price).toLocaleString("ko-KR")}원 · {b.price.effective_date.slice(5).replace("-", "/")} 적용
              </dd>
              <dt className="text-muted-foreground">원가 버전</dt>
              <dd>
                <span className="font-mono">{b.cost.cost_version_id}</span> ({b.cost.parent_cost_version} 보존) · {formatClock(b.cost.registered_at)} 등록
              </dd>
              <dt className="text-muted-foreground">인수</dt>
              <dd>
                <span className="font-mono">{b.handoff.handoff_id}</span> · {name(b.handoff.accepted_by)} {formatClock(b.handoff.accepted_at)}
              </dd>
              <dt className="text-muted-foreground">물량 근거</dt>
              <dd>
                <span className="font-mono">{b.sc01_run}</span> · F02 {b.forecast_approval === "UNDER_REVIEW" ? "검토 중(승인 아님)" : b.forecast_approval}
              </dd>
              {b.request_price ? (
                <>
                  <dt className="text-muted-foreground">요청가(이력)</dt>
                  <dd className="text-muted-foreground">{Number(b.request_price).toLocaleString("ko-KR")}원 — 합산하지 않는다</dd>
                </>
              ) : null}
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>진행 단계</CardTitle>
            <CardDescription>회의 6/29 10시 · 인수 6/30 12시 · 제출 7/6 18시 · 월간회의 7/12 10시</CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="space-y-1.5 text-sm">
              {STAGES.map((s) => {
                const done = s.done(view);
                return (
                  <li key={s.id} className="flex items-center gap-2">
                    {done ? (
                      <CheckCircle2 aria-label="완료" className="size-4 shrink-0" style={{ color: "var(--viz-status-good)" }} />
                    ) : (
                      <CircleDashed aria-label="미완료" className="size-4 shrink-0 text-muted-foreground" />
                    )}
                    <span className="w-14 shrink-0 font-mono text-xs text-muted-foreground">{s.id}</span>
                    <Link href={s.href} className="hover:underline">
                      {s.label}
                    </Link>
                  </li>
                );
              })}
            </ol>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>업무 {view.tasks.filter((t) => t.status !== "COMPLETED").length}건 진행 중</CardTitle>
          <CardDescription>BPM의 사람 대기가 업무가 된다. 기한 초과는 상태와 따로 표시한다.</CardDescription>
        </CardHeader>
        <CardContent>
          {view.tasks.length === 0 ? (
            <p className="text-sm text-muted-foreground">아직 업무가 없다.</p>
          ) : (
            <ul className="divide-y text-sm">
              {view.tasks
                .slice()
                .reverse()
                .slice(0, 8)
                .map((t) => (
                  <li key={t.task_id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-0.5 py-1.5">
                    <span>
                      <span className="font-mono text-xs">{t.task_id}</span> {t.assignedName}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {t.status === "COMPLETED" ? "완료" : "진행"} · 기한 {formatClock(t.due_at)}
                      {t.overdue ? <span style={{ color: "var(--viz-status-critical)" }}> · 기한 초과</span> : null}
                      {t.opened_late ? " · 늦게 열림(바깥 실행)" : null}
                    </span>
                  </li>
                ))}
            </ul>
          )}
          <Commentary>
            <p className="mt-2 text-xs text-muted-foreground">
              수익성 통합 분석은 분석 결과를 검토하고 대응안 분석의 책임·기한을 정한다. 대안 선택·실행 승인은 다음 업무인 개선안 검토·실행 승인(대표 주재 월간회의)에서 한다.
            </p>
          </Commentary>
        </CardContent>
      </Card>
    </>
  );
}
