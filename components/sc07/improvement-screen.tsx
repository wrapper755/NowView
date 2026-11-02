"use client";

import { ArrowLeft, ArrowRight } from "lucide-react";

import { EvidenceChip, LoadGate, Sc07Body, Sc07Header, StateTag, who } from "@/components/sc07/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CASE_STATUS_LABEL, EXECUTION_LABEL, PROCEDURE_LABEL, STATUS3_LABEL, causeText, minutes, shortClock } from "@/lib/sc07/format";
import type { AgentOutput, Application, Improvement, Verification } from "@/lib/sc07/types";
import { useSc07 } from "@/lib/store/sc07";

/**
 * U701 관리모델 개선 및 적용 — 한 화면 두 보기(구현명세 1장). A(개선 전후)로 들어오고 「검증·적용 결과 보기」 한 번으로 B(검증·
 * 적용)로 바꾼다. 보기 전환은 읽기다 — 승인·배포·기준 변경을 만들지 않는다(U701-06). 숫자·상태는 엔진의 조회 결과다 — 화면은
 * PASS 건수로 적용 상태를 다시 판정하지 않는다(구현명세 6장).
 */
export function Sc07ImprovementScreen() {
  const meta = useSc07((s) => s.meta);
  const view = useSc07((s) => s.view);
  const setView = useSc07((s) => s.setView);
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
      <Sc07Header id="U701" title="관리모델 개선 및 적용" question="사람이 보정한 근거를 다음 검토에서는 Agent가 처음부터 잇는가?" />
      <Sc07Body>
        {meta ? (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2" data-index-skip>
            <StateTag tone={meta.status.procedure === "APPLIED" ? "good" : meta.status.procedure === "NEEDS_WORK" ? "warn" : "open"}>
              절차 {PROCEDURE_LABEL[meta.status.procedure]}
            </StateTag>
            <StateTag tone={meta.status.verification === "PASSED" ? "good" : meta.status.verification === "FAILED" ? "warn" : "neutral"}>
              검증 {meta.status.verification === "PASSED" ? "통과" : meta.status.verification === "FAILED" ? "미충족" : "미실행"}
            </StateTag>
            <StateTag tone={meta.status.application === "ST707" ? "good" : "open"}>{meta.status.applicationLabel}</StateTag>
            <StateTag tone="neutral">{EXECUTION_LABEL[meta.status.execution] ?? meta.status.execution}</StateTag>
            <Button size="sm" variant={view === "A" ? "default" : "outline"} className="ml-auto" onClick={() => setView(view === "A" ? "B" : "A")}>
              {view === "A" ? (
                <>
                  검증·적용 결과 보기
                  <ArrowRight aria-hidden className="size-3.5" />
                </>
              ) : (
                <>
                  <ArrowLeft aria-hidden className="size-3.5" />
                  개선 내용으로 돌아가기
                </>
              )}
            </Button>
          </div>
        ) : null}
        {view === "A" ? <ViewA /> : <ViewB />}
      </Sc07Body>
    </main>
  );
}

// ─────────────────────────── 보기 A — 개선 전후 ───────────────────────────

function ViewA() {
  const load = useSc07((s) => s.improvement);
  return (
    <LoadGate load={load} what="개선 내용">
      {(d) => (
        <>
          <Reason d={d} />
          <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-2">
            <Before d={d} />
            <After d={d} />
          </div>
          <Card>
            <CardHeader>
              <CardTitle>기준·절차 보완</CardTitle>
              <CardDescription>새 KPI·KRI·Control·임계값·효과 산식은 없다 — 기존 기준의 측정·해석과 자료 준비를 보완했다</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {[d.improvement.framework, d.improvement.process].map((i) =>
                i ? (
                  <p key={i.item_id}>
                    <span className="font-medium">{i.target === "Framework" ? "Framework" : "Process"}</span> · {i.after}
                    <span className="text-muted-foreground"> — {i.scope}</span>
                  </p>
                ) : null,
              )}
              <Disclosure summary={`변경 기준 ${d.improvement.rules.length}건 (${d.improvement.rules[0]?.version ?? ""})`}>
                <ul className="space-y-1 text-xs">
                  {d.improvement.rules.map((r) => (
                    <li key={r.rule_id}>
                      <span className="font-mono">{r.rule_id}</span> {r.content} <span className="text-muted-foreground">— {r.guard}</span>
                    </li>
                  ))}
                </ul>
              </Disclosure>
            </CardContent>
          </Card>
        </>
      )}
    </LoadGate>
  );
}

function Reason({ d }: { d: Improvement }) {
  const a = d.before.agent;
  return (
    <Card>
      <CardHeader>
        <CardTitle>개선 사유</CardTitle>
        <CardDescription>
          완료·성과 검토 대표 사례 {d.source.order.order_id} · {d.source.report_version} 보고 뒤 {d.improvement.proposed_on ?? ""} 발의
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm leading-relaxed">
        <p>
          Agent({a.run_id})는 주담당 확인란과 주문 비용만 받아 「{a.draft}」라고 제시했다. 대행자의 확인 로그는 입력에 연결되지 않았다.
        </p>
        <p>
          구매 담당이 대행 확인 기록과 공급 가능일을 직접 찾아 「{a.human}」로 바로잡았다. 같은 보완을 다음 검토에서 사람이 반복하지 않도록
          Agent가 처음부터 그 근거를 잇게 한다.
        </p>
      </CardContent>
    </Card>
  );
}

function Before({ d }: { d: Improvement }) {
  const a = d.before.agent;
  return (
    <Card>
      <CardHeader>
        <CardTitle>기존 검토 이력</CardTitle>
        <CardDescription>
          {d.before.agent_version} · 입력 {d.before.projection_version} · 원본 그대로(읽기 전용)
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <Field label="입력">{a.input_scope}</Field>
        <Field label="초안">
          <span className="font-medium">{a.draft}</span>
        </Field>
        <Field label="원인 후보">
          <span>확인 지연 가능성(대행 기록·공급 일정 추가 확인 필요)</span>
        </Field>
        <Commentary block>
          <p className="text-xs text-muted-foreground">
            사람의 보정은 비교용이고 재검증 입력이 아니다(BR708). 이 초안·보정·보고본은 바뀌지 않는다 — 근거 <EvidenceChip id={d.before.evidence_id} />
          </p>
        </Commentary>
      </CardContent>
    </Card>
  );
}

function After({ d }: { d: Improvement }) {
  const o = d.after;
  return (
    <Card>
      <CardHeader>
        <CardTitle>개선한 검토 방식</CardTitle>
        <CardDescription>
          {o.agent_version} · 입력 {o.projection_version} · 규칙 재계산(실시간 Agent 호출이 아니다)
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <Outcome o={o} />
        <Commentary block>
          <p className="text-xs text-muted-foreground">설계 의도다 — 같은 사례의 검증 결과는 「검증·적용 결과 보기」에서 본다.</p>
        </Commentary>
      </CardContent>
    </Card>
  );
}

/** 개선 Agent 출력 — 후보·근거 사실·누락·다음 처리. 후보는 판단이 아니다. */
function Outcome({ o }: { o: AgentOutput }) {
  return (
    <>
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <span>
          <span className="text-xs text-muted-foreground">확인 소요 </span>
          <span className="text-lg font-semibold tabular-nums">{minutes(o.elapsed_minutes)}</span>
          <span className="text-xs text-muted-foreground"> · {o.threshold_min}분 {STATUS3_LABEL[o.deadline_status]}</span>
        </span>
        <span>
          <span className="text-xs text-muted-foreground">원인 후보 </span>
          <span className="text-lg font-semibold">{causeText(o.candidate_cause)}</span>
        </span>
      </div>
      <ul className="space-y-1.5">
        {o.facts.map((f) => (
          <li key={f.text} className="flex flex-wrap items-baseline gap-1.5">
            <span>{f.text}</span>
            {f.evidence_refs.map((r) => (
              <EvidenceChip key={r} id={r} />
            ))}
          </li>
        ))}
      </ul>
      {o.missing_fields.length ? (
        <ul className="list-disc pl-4 text-xs">
          {o.missing_fields.map((m) => (
            <li key={m.field}>
              {m.label} — {m.reason_label}(보완 {m.owner})
            </li>
          ))}
        </ul>
      ) : null}
      <p className="text-xs text-muted-foreground">다음 처리 · {o.next_action}</p>
    </>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="min-w-0">{children}</span>
    </div>
  );
}

// ─────────────────────────── 보기 B — 검증·적용 ───────────────────────────

function ViewB() {
  const verification = useSc07((s) => s.verification);
  const application = useSc07((s) => s.application);
  return (
    <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-[1.15fr_1fr]">
      <div className="space-y-4">
        <LoadGate load={verification} what="검증 결과">
          {(v) => <VerificationCards v={v} />}
        </LoadGate>
      </div>
      <div className="space-y-4">
        <LoadGate load={application} what="적용 확인">
          {(a) => <ApplicationCards a={a} />}
        </LoadGate>
      </div>
    </div>
  );
}

function VerificationCards({ v }: { v: Verification }) {
  const rep = v.representative;
  const tc = v.cases.find((c) => c.check === rep.check);
  const rest = v.cases.filter((c) => c.check !== rep.check);
  const input = rep.input as Record<string, unknown>;
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>대표 검증</CardTitle>
          <CardDescription>
            {rep.check} · {String(input.input_id)} ({String(input.change_id ?? "")}) ·{" "}
            {v.run ? `검증 결과 조회 — ${v.run.run_id} ${shortClock(v.run.executed_at)} · ${v.run.agent_version}` : "미실행"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
            <Fact label="공유">{shortClock(input.shared_at as string | null)}</Fact>
            <Fact label="주담당 확인">{shortClock(input.primary_confirmed_at as string | null)}</Fact>
            <Fact label="대행 확인">
              {shortClock(input.deputy_confirmed_at as string | null)} {input.deputy_valid ? "(유효)" : "(무효)"}
            </Fact>
            <Fact label="발주 마감">{shortClock(input.order_cutoff_at as string | null)}</Fact>
            <Fact label="요구 납기">{shortClock(input.required_at as string | null)}</Fact>
            <Fact label="정상 공급">{shortClock(input.timely_supply_at as string | null)}</Fact>
          </dl>
          {rep.output ? (
            <div className="space-y-2 rounded-md border px-3 py-2">
              <p className="text-xs font-medium">검증 출력 — 개선 버전</p>
              <Outcome o={rep.output} />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">검증을 아직 실행하지 않았다 — 결과를 통과로 보이지 않는다.</p>
          )}
          {tc ? (
            <p className="text-xs">
              기대값 {causeText(tc.expected)} · 결과 {causeText(tc.observed)} ·{" "}
              <StateTag tone={tc.status === "PASS" ? "good" : tc.status === "FAIL" ? "warn" : "neutral"}>{CASE_STATUS_LABEL[tc.status]}</StateTag>
            </p>
          ) : null}
          <p className="rounded-md bg-muted/40 px-3 py-2 text-xs">
            <span className="font-medium">완료·성과 검토의 사람 판단</span>(별도 기록) · {rep.human} — {who(rep.human_by)}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>나머지 검증 {rest.length}건</CardTitle>
          <CardDescription>
            {v.summary.passed}/{v.summary.total} 충족 · 8건 충족은 Agent 정확도 100%가 아니다 · 합성 사례는 성과 집계에 넣지 않는다
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="divide-y text-sm">
            {rest.map((c) => (
              <li key={c.check} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 py-1.5">
                <span className="min-w-0">
                  <span className="font-mono text-xs">{c.check}</span> {c.title}
                  {c.fixture ? <span className="ml-1 rounded border px-1 text-[10px] text-muted-foreground">합성</span> : null}
                </span>
                <span className="flex items-center gap-2 text-xs">
                  <span className="text-muted-foreground">{causeText(c.observed)}</span>
                  <StateTag tone={c.status === "PASS" ? "good" : c.status === "FAIL" ? "warn" : "neutral"}>{CASE_STATUS_LABEL[c.status]}</StateTag>
                </span>
              </li>
            ))}
          </ul>
          <Disclosure className="mt-2" summary="가상 검증 이력(데이터)과의 대조">
            <p className="text-xs text-muted-foreground">
              데이터의 가상 결과·일치 여부(SIMULATED_HISTORY)는 판정에 쓰지 않는다 — 관측값은 엔진이 규칙으로 다시 계산했다. 데이터에 실행 일시·실행
              ID는 없다.
            </p>
            <ul className="mt-1 space-y-0.5 text-xs">
              {v.cases.map((c) => (
                <li key={c.check}>
                  <span className="font-mono">{c.check}</span> 가상 {causeText(c.simulated)} {c.simulated_status} · 재계산 {causeText(c.observed)}
                </li>
              ))}
            </ul>
          </Disclosure>
        </CardContent>
      </Card>
    </>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="tabular-nums">{children}</dd>
    </div>
  );
}

function ApplicationCards({ a }: { a: Application }) {
  const s = a.snapshot;
  const st = a.state;
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>적용 확인</CardTitle>
          <CardDescription>
            {a.application_id} · {a.scope} — {a.scope_detail}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <ul className="grid gap-1.5 sm:grid-cols-2">
            <li>
              <StateTag tone={st.verification_passed ? "good" : "neutral"}>검증 {st.verification_passed ? "통과" : "미완료"}</StateTag>
            </li>
            <li>
              <StateTag tone={st.confirmed ? "good" : "neutral"}>업무 확인 {st.confirmed ? "완료" : "대기"}</StateTag>
            </li>
            <li>
              <StateTag tone={st.setting_reflected ? "good" : st.reserved_only ? "open" : "neutral"}>
                {st.setting_reflected ? "운영 설정 반영 확인" : st.reserved_only ? "적용 예정(예약)" : st.label}
              </StateTag>
            </li>
            <li>
              <StateTag tone="neutral">{EXECUTION_LABEL[a.execution.status] ?? a.execution.status}</StateTag>
            </li>
          </ul>
          {st.attention.length ? <p className="text-xs font-medium">확인 필요 — {st.attention.join(" · ")}</p> : null}
          <dl className="grid grid-cols-[6rem_minmax(0,1fr)] gap-x-2 gap-y-1 text-xs">
            <dt className="text-muted-foreground">개선 버전</dt>
            <dd>
              {a.target_version} <span className="text-muted-foreground">(이전 {a.previous_version})</span>
            </dd>
            <dt className="text-muted-foreground">설정 반영</dt>
            <dd>{s ? `${s.snapshot_id} · ${shortClock(s.applied_at)} · ${who(s.applied_by)}` : "기록 없음"}</dd>
            <dt className="text-muted-foreground">증적</dt>
            <dd>{s ? `${s.evidence_type} · ${s.content}` : "—"}</dd>
            <dt className="text-muted-foreground">읽기 확인</dt>
            <dd>{s?.checked_at ? `${shortClock(s.checked_at)} · ${who(s.checked_by)} · ${s.check_result === "MATCH" ? "일치" : "불일치"}` : "대기"}</dd>
            <dt className="text-muted-foreground">운영 실행</dt>
            <dd>
              실행 ID 없음 · 다음 운영 예정 {shortClock(a.execution.next_run_at)}
              <span className="text-muted-foreground"> (예정은 실행 사실이 아니다)</span>
            </dd>
          </dl>
          <Disclosure summary="설정 반영 확인의 다섯 조건">
            <ul className="space-y-0.5 text-xs">
              {st.checks.map((c) => (
                <li key={c.key}>
                  <StateTag tone={c.ok ? "good" : "neutral"}>{c.label}</StateTag>
                  {c.detail ? <span className="ml-1 text-muted-foreground">{c.detail}</span> : null}
                </li>
              ))}
            </ul>
            <p className="mt-1 text-xs text-muted-foreground">이전 버전 복귀 — {a.rollback.previous_version} · {a.rollback.note}</p>
          </Disclosure>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>확인 이력</CardTitle>
          <CardDescription>대상 버전 {a.target_version} · 승인 버튼 없음(배경 이력)</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="divide-y text-sm">
            {a.confirmations.map((c) => (
              <li key={c.record_id} className="py-1.5">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span>
                    <span className="font-mono text-xs">{c.record_id}</span> {who(c.actor)}
                  </span>
                  <StateTag tone={c.state === "CONFIRMED" ? "good" : c.state === "PENDING" ? "neutral" : "warn"}>
                    {c.state === "CONFIRMED" ? "확인" : c.state === "PENDING" ? "대기" : "보완 요청"} {c.at ? shortClock(c.at) : ""}
                  </StateTag>
                </div>
                {c.content ? <p className="text-xs text-muted-foreground">{c.content} · {c.version}</p> : null}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>다음 점검</CardTitle>
          <CardDescription>장기 개선 효과는 미측정 — 시간 절감·정확도·재무 효과 수치를 만들지 않는다</CardDescription>
        </CardHeader>
        <CardContent className="text-sm">
          {a.follow_up ? (
            <p>
              {shortClock(a.follow_up.planned_at)} · {who(a.follow_up.owner)} · {a.follow_up.items}
            </p>
          ) : (
            <p className="text-muted-foreground">설정 반영이 확인된 뒤 점검 담당·예정일이 연결된다.</p>
          )}
        </CardContent>
      </Card>
    </>
  );
}
