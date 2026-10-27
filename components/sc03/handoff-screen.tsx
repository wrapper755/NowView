"use client";

import { CheckCircle2, CircleDashed } from "lucide-react";

import { useUserName } from "@/components/sc01/bits";
import { Sc03Body, Sc03Header, StatusPills, WaitingForms } from "@/components/sc03/bits";
import { Disclosure } from "@/components/shared/disclosure";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { OUTCOME_LABEL } from "@/lib/sc03/format";
import type { Sc03View } from "@/lib/sc03/types";

interface Handoff {
  handoff_id: string;
  report_version: string;
  analysis_run: string;
  minutes_version: string;
  decision: string;
  outcome: string;
  open_questions: string[];
  accepted_tasks: { task_id: string; version: number; accepted_at: string; owner: string }[];
  excluded_candidates: { candidate_id: string; reason: string; evidence_ref: string }[];
  next_meeting: { meeting_id: string; at: string };
  analysis_due: string;
  consolidation_due: string;
  basis: string;
  pending_revisions: string[];
  as_of: string;
  elapsed_minutes: number;
  business_minutes: number;
}

const hm = (m: number) => `${Math.floor(m / 60)}시간 ${m % 60}분`;

/**
 * U37 검토 완료와 월간회의 연결 — 종료 요건 체크·독립 상태·결론·인수 4/4·제출/취합/월간회의 일정·장면 4 인계.
 * **전건 인수만으로 자동 종료하지 않는다** — 경영관리 담당이 완료를 요청하면 서버가 전체 조건을 다시 본다.
 */
export function Sc03HandoffScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc03Header id="U37" title="검토 완료 · 월간회의 연결" question="수익성 통합 분석을 끝내고 개선안 검토·실행 승인으로 무엇을 넘기는가?" />
      <Sc03Body>{(view) => <HandoffView view={view} />}</Sc03Body>
    </main>
  );
}

function HandoffView({ view }: { view: Sc03View }) {
  const name = useUserName();
  const h = view.handoff as Handoff | null;
  return (
    <>
      <StatusPills view={view} />
      <WaitingForms view={view} nodes={["Complete_Scene"]} labels={{ Complete_Scene: "수익성 통합 분석 완료" }} />

      <Card>
        <CardHeader>
          <CardTitle>종료 요건</CardTitle>
          <CardDescription>{view.completion.met ? "모두 충족 — 경영관리 담당이 완료한다" : "미충족 항목이 있으면 완료가 거절된다(422)"}</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="space-y-1 text-sm">
            {view.completion.items.map((i) => (
              <li key={i.id} className="flex items-center gap-2">
                {i.ok ? (
                  <CheckCircle2 aria-label="충족" className="size-4 shrink-0" style={{ color: "var(--viz-status-good)" }} />
                ) : (
                  <CircleDashed aria-label="미충족" className="size-4 shrink-0 text-muted-foreground" />
                )}
                {i.label}
              </li>
            ))}
          </ul>
          {!view.completion.met && view.completion.blocking.length ? (
            <p className="mt-2 text-xs text-muted-foreground">남은 것: {view.completion.blocking.join(" · ")}</p>
          ) : null}
        </CardContent>
      </Card>

      {h ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>개선안 검토·실행 승인 인계 {h.handoff_id}</CardTitle>
              <CardDescription>
                {formatClock(h.as_of)} 기준 · 착수부터 경과 {hm(h.elapsed_minutes)} · 영업시간 {hm(h.business_minutes)} (투입시간이 아니다)
              </CardDescription>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
                <dt className="text-muted-foreground">보고 · 분석</dt>
                <dd className="font-mono text-xs">
                  {h.report_version} · {h.analysis_run}
                </dd>
                <dt className="text-muted-foreground">회의록 · 결론</dt>
                <dd>
                  <span className="font-mono text-xs">{h.minutes_version}</span> · {h.decision} {OUTCOME_LABEL[h.outcome]}
                </dd>
                <dt className="text-muted-foreground">잔여 질문</dt>
                <dd>{h.open_questions.join(" · ")} — 7/6 18시까지 후속 확인</dd>
                <dt className="text-muted-foreground">인수 과제</dt>
                <dd>{h.accepted_tasks.map((t) => `${t.task_id} v${t.version} ${name(t.owner)}`).join(" · ")}</dd>
                <dt className="text-muted-foreground">제외 후보</dt>
                <dd>
                  {h.excluded_candidates.map((c) => (
                    <span key={c.candidate_id} className="block">
                      {c.candidate_id} — {c.reason}
                    </span>
                  ))}
                </dd>
                <dt className="text-muted-foreground">기준</dt>
                <dd className="text-xs">{h.basis} · 잔여 2027과 향후 12개월 효과를 따로 비교한다</dd>
                {h.pending_revisions.length ? (
                  <>
                    <dt className="text-muted-foreground">재확인 대기</dt>
                    <dd className="font-mono text-xs">{h.pending_revisions.join(" · ")}</dd>
                  </>
                ) : null}
              </dl>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>다음 일정</CardTitle>
              <CardDescription>제출·취합·월간회의는 수익성 통합 분석 이후다 — 상세 분석 자료 제출·성과 개선은 아직 없다.</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1 text-sm">
                <li>분석 제출 {formatClock(h.analysis_due)} — 과제 책임자</li>
                <li>경영관리 취합 {formatClock(h.consolidation_due)}</li>
                <li>
                  {h.next_meeting.meeting_id} 월간 경영회의 {formatClock(h.next_meeting.at)} — 대표 주재, 상세 대안 비교·결정
                </li>
              </ul>
              {view.delayed.length ? (
                <p className="mt-2 text-xs" style={{ color: "var(--viz-status-serious)" }}>
                  제출 지연: {view.delayed.join(" · ")} — 과거 수익성 통합 분석 완료는 그대로다
                </p>
              ) : null}
            </CardContent>
          </Card>
        </>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>감사 이력</CardTitle>
          <CardDescription>행위자·시각·근거 — 최근 5건만 보인다.</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="space-y-0.5 text-xs">
            {view.audit.slice(-5).map((a) => (
              <li key={a.seq}>
                {formatClock(a.at)} · {a.actor_name} · {a.action}
                {a.event_code ? ` · ${a.event_code}` : ""}
              </li>
            ))}
          </ul>
          <Disclosure summary={`전체 ${view.audit.length}건`}>
            <ul className="max-h-80 space-y-0.5 overflow-y-auto text-xs text-muted-foreground">
              {view.audit.map((a) => (
                <li key={a.seq}>
                  {formatClock(a.at)} · {a.actor_name} · {a.action}
                  {a.event_code ? ` · ${a.event_code}` : ""}
                </li>
              ))}
            </ul>
          </Disclosure>
        </CardContent>
      </Card>
    </>
  );
}
