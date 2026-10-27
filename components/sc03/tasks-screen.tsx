"use client";

import { useUserName } from "@/components/sc01/bits";
import { Sc03Body, Sc03Header, StatusPills, WaitingForms } from "@/components/sc03/bits";
import { Disclosure } from "@/components/shared/disclosure";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { TASK_STATE_LABEL } from "@/lib/sc03/format";
import type { Sc03View } from "@/lib/sc03/types";

const ACCEPT = ["AT31", "AT32", "AT33", "AT34"].flatMap((t) => [`Accept_${t}`, `Reassign_${t}`]);

/**
 * U36 분석과제 배정과 인수 — 회의록 확인 → 일괄 배정 → 책임자별 인수(반려면 재배정 → 새 배정버전). 인수는 그
 * 과제 책임자만 한다(임원도 대신 못 한다). 인수율은 확정 배정 중 현재 버전 인수 비율이다 — 0건이면 N/A.
 */
export function Sc03TasksScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc03Header id="U36" title="분석과제 배정 · 인수" question="대응안 분석의 책임과 기한을 담당자가 인수했는가?" />
      <Sc03Body>{(view) => <Tasks view={view} />}</Sc03Body>
    </main>
  );
}

function Tasks({ view }: { view: Sc03View }) {
  const name = useUserName();
  const m = view.minutes.at(-1);
  const rate = view.acceptance;
  return (
    <>
      <StatusPills view={view} />
      <WaitingForms view={view} nodes={["Confirm_Minutes", "Assign_Tasks"]} labels={{ Confirm_Minutes: "회의록 확인", Assign_Tasks: "배정 · 통보" }} />

      <Card>
        <CardHeader>
          <CardTitle>회의록 · 인수율</CardTitle>
          <CardDescription>
            {m ? `${m.minutes_id} 확인 — ${name(m.confirmed_by)} ${formatClock(m.confirmed_at)}` : "회의록 확인 전"} · 인수기한{" "}
            {formatClock(view.schedule.accept_due)} · 제출기한 {formatClock(view.schedule.submit_due)}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p className="text-2xl font-semibold tabular-nums">
            {rate.rate === null ? "N/A" : `${Math.round(Number(rate.rate) * 100)}%`}
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              {rate.accepted}/{rate.assigned} 인수
            </span>
          </p>
          {m ? (
            <p className="text-xs text-muted-foreground">
              상세 분석 {m.included.join("·")} · 이번 제외 {m.excluded.map((e) => e.candidate_id).join("·")} · 잔여 질문 {m.open_questions.join("·")} · 다음 {m.next_meeting}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <WaitingForms
        view={view}
        nodes={ACCEPT}
        expect={(n) => {
          const t = view.assignments.find((a) => n.endsWith(a.task_id));
          return n.startsWith("Accept") && t ? { assignment: t.assignment_version } : undefined;
        }}
        labels={Object.fromEntries(ACCEPT.map((n) => [n, n.startsWith("Accept") ? "인수 · 반려" : "재배정"]))}
      />

      {view.assignments.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>분석과제</CardTitle>
            <CardDescription>회의 결론에서 포함된 후보로 경영관리가 과제 초안을 만든다.</CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="grid gap-3 [&>*]:min-w-0 lg:grid-cols-2">
          {view.assignments.map((a) => (
            <Card key={a.task_id} size="sm">
              <CardHeader>
                <CardTitle>
                  {a.task_id} {a.title}
                </CardTitle>
                <CardDescription>
                  {TASK_STATE_LABEL[a.state]} · 배정버전 {a.assignment_version || "—"}
                  {a.accepted_at ? ` · 인수 ${formatClock(a.accepted_at)}` : ""}
                  {view.delayed.includes(a.task_id) ? " · 제출 지연" : ""}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-1.5 text-sm">
                <p>{a.question}</p>
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
                  <dt className="text-muted-foreground">책임</dt>
                  <dd>{a.owner ? name(a.owner) : <span style={{ color: "var(--viz-status-critical)" }}>미지정</span>}</dd>
                  <dt className="text-muted-foreground">협조</dt>
                  <dd>{a.collaborators.map((c) => name(c)).join(" · ") || "—"}</dd>
                  <dt className="text-muted-foreground">산출물</dt>
                  <dd>{a.deliverable}</dd>
                  <dt className="text-muted-foreground">의존</dt>
                  <dd>{a.dependency || "—"}</dd>
                  <dt className="text-muted-foreground">후보</dt>
                  <dd>{a.candidate_refs.join("·") || "없음(원인분석)"}</dd>
                  <dt className="text-muted-foreground">기준</dt>
                  <dd>{a.basis}</dd>
                  <dt className="text-muted-foreground">효과</dt>
                  <dd className="text-muted-foreground">2027 미산정 · 12개월 미산정</dd>
                </dl>
                {a.return_reason ? <p className="text-xs" style={{ color: "var(--viz-status-serious)" }}>반려 사유: {a.return_reason}</p> : null}
                <Disclosure summary={`이력 ${a.history.length}건`}>
                  <ul className="space-y-0.5 text-xs text-muted-foreground">
                    {a.history.map((h, i) => (
                      <li key={i}>
                        {formatClock(h.at)} · {TASK_STATE_LABEL[h.state] ?? h.state}
                        {h.version ? ` v${h.version}` : ""} · {name(h.by)}
                        {h.note ? ` — ${h.note}` : ""}
                      </li>
                    ))}
                  </ul>
                </Disclosure>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {view.alerts.length ? (
        <Card>
          <CardHeader>
            <CardTitle>알림 {view.alerts.length}건</CardTitle>
            <CardDescription>기한 초과 — 인수 지연·제출 지연. 지연은 업무 완료를 취소하지 않는다.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {view.alerts.map((a) => (
                <li key={a.alert_id}>
                  {a.message} <span className="text-xs text-muted-foreground">→ {a.to.map((u) => name(u)).join(", ")}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </>
  );
}
