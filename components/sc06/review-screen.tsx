"use client";

import Link from "next/link";
import { ArrowRight, Bot, ChevronDown, ChevronUp, UserCheck } from "lucide-react";

import { EvidenceChip, LoadGate, Mn, personName, Problem, Sc06Body, Sc06Header, StateTag } from "@/components/sc06/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock, formatWonExact } from "@/lib/sc01/format";
import { cn } from "@/lib/utils";
import {
  ACTIVITY_LABEL,
  AGENT_STATE_LABEL,
  CAUSE_LABEL,
  COLLECTION_LABEL,
  formatDuration,
  JUDGMENT_LABEL,
  million,
  monthLabel,
  shortClock,
  signedMillion,
} from "@/lib/sc06/format";
import type { AgentRun, Judgment, ReadContext, Summary, TaskRow, Variance } from "@/lib/sc06/types";
import { useSc06 } from "@/lib/store/sc06";

/**
 * U601 완료·성과 검토 — 동작 ①(요약 열기)·②(ACT42 주요 차이 한 건 펼치기). 활동 완료와 효과 달성을 다른 열로 둔다 —
 * 일부 기대 미달을 「과제 활동 미완료」로 바꾸지 않는다(구현명세 3장). 상세는 같은 화면 안에서 펼친다(외부 창·결재 없음).
 */
export function Sc06ReviewScreen() {
  const summary = useSc06((s) => s.summary);
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc06Header id="U601" title="완료·성과 검토" question="과제는 끝났다. 기대한 성과는 얼마나 나타났고, 차이의 원인은 무엇인가?" />
      <Sc06Body>
        <LoadGate load={summary} what="검토 요약">
          {(s) => <Body summary={s} />}
        </LoadGate>
      </Sc06Body>
    </main>
  );
}

function Body({ summary: s }: { summary: Summary }) {
  const detailOpen = useSc06((x) => x.detailOpen);
  const { openDetail, closeDetail } = useSc06.getState();
  const jdg = s.judgments.find((j) => j.task_id === "ACT42") ?? s.judgments[0];
  return (
    <>
      <NewerCalculation ctx={s} />
      {/* U601-01 · U601-02 — 기준과 검토 판단 */}
      <section aria-label="검토 기준과 판단" className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
        <Card data-index-skip>
          <CardContent className="space-y-1.5 text-sm">
            <p className="text-xs text-muted-foreground">검토 기준 · 고정</p>
            <p>
              <span className="font-medium">{s.period.label}</span> 10/1 ~ 12/31 측정 · 자료 마감 {shortClock(s.data_close)} · 보고{" "}
              {shortClock(s.report_date)}
            </p>
            <p>
              비교 기준 <span className="font-medium">{s.basis_version}</span>(결정 실행·계획 갱신 공식 전망의 Q4 기대, 소급 수정 없음) · 산정{" "}
              <span className="font-mono text-xs">{s.calculation_version}</span>
            </p>
            <p className="text-xs text-muted-foreground">
              울산 A제품 a~e 관리손익 범위 · 원 단위 계산, 백만원 표시 · VAT 제외 · 자료 {s.data_status === "COMPLETE" ? "대사 완료" : "대사 미완료"}
            </p>
          </CardContent>
        </Card>
        {jdg ? <JudgmentLine j={jdg} /> : null}
      </section>

      {/* U601-03 — 3과제 요약 */}
      <Card>
        <CardHeader>
          <CardTitle>과제별 완료와 성과</CardTitle>
          <CardDescription>활동 완료 판단과 효과 판단은 별개다 · 차이 = 확인 효과 − 기대 효과(음수는 미달)</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-3 font-medium">과제</th>
                  <th className="py-2 pr-3 font-medium">활동 완료 판단</th>
                  <th className="py-2 pr-3 text-right font-medium">Q4 기대</th>
                  <th className="py-2 pr-3 text-right font-medium">확인 효과</th>
                  <th className="py-2 pr-3 text-right font-medium">차이</th>
                  <th className="py-2 pr-3 font-medium">효과 판단</th>
                  <th className="py-2 font-medium">
                    <span className="sr-only">상세</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {s.tasks.map((t) => (
                  <TaskLine key={t.task_id} t={t} open={detailOpen && t.focus} onOpen={() => (detailOpen && t.focus ? closeDetail() : openDetail(t.task_id))} />
                ))}
                <tr className="border-t font-medium">
                  <th scope="row" className="py-2 pr-3 text-left">
                    3과제 합계
                  </th>
                  <td className="py-2 pr-3 text-xs text-muted-foreground">과제별 판단</td>
                  <td className="py-2 pr-3 text-right">
                    <Mn won={s.totals.expected_krw} />
                  </td>
                  <td className="py-2 pr-3 text-right">
                    <Mn won={s.totals.actual_krw} empty="산정 보류" />
                  </td>
                  <td className="py-2 pr-3 text-right">
                    <span className="tabular-nums" title={s.totals.variance_krw === null ? undefined : formatWonExact(s.totals.variance_krw)}>
                      {signedMillion(s.totals.variance_krw)}
                    </span>
                  </td>
                  <td className="py-2 pr-3">
                    {s.totals.variance_krw === null ? <StateTag tone="open">산정 보류</StateTag> : s.totals.variance_krw < 0 ? <StateTag tone="warn">일부 기대 미달</StateTag> : <StateTag tone="good">기대 달성</StateTag>}
                  </td>
                  <td />
                </tr>
              </tbody>
            </table>
          </div>
          {s.totals.actual_krw === null ? (
            <Problem
              text={`산정 보류 과제가 있어 3과제 합계를 내지 않는다. 확인된 과제(${s.totals.confirmed_subtotal.tasks.join("·")})만의 소계는 ${million(
                s.totals.confirmed_subtotal.actual_krw,
              )}백만원이다 — 전체 확정 합계가 아니다.`}
            />
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant={detailOpen ? "outline" : "default"} onClick={() => (detailOpen ? closeDetail() : openDetail("ACT42"))} aria-expanded={detailOpen} aria-controls="act42-detail">
              {detailOpen ? <ChevronUp aria-hidden className="size-3.5" /> : <ChevronDown aria-hidden className="size-3.5" />}
              {detailOpen ? "주요 차이 닫기" : "ACT42 주요 차이 보기"}
            </Button>
            <span className="text-xs text-muted-foreground">ACT41·43은 기대·실현·완료 요약과 근거만 본다</span>
          </div>
        </CardContent>
      </Card>

      {/* U601-04 — 업무 변화: Agent 준비와 사람 판단 */}
      <Card>
        <CardHeader>
          <CardTitle>검토 자료 준비 — Agent와 사람</CardTitle>
          <CardDescription>
            이전: 부서 자료 요청 → Excel 취합·대사 → 차이 설명 작성. 지금: 자료·근거 연결 → 주요 차이 검토 → 후속 조치.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {s.agent.map((a) => (
            <AgentPair key={a.run_id} a={a} />
          ))}
          <p className="text-xs text-muted-foreground">
            Agent 검토 이력 — 검토 완료된 기록을 그대로 재현한다(실시간 생성 아님). 숫자는 규칙 계산만 만든다 · 절감 시간·생산성 향상률은
            근거가 없어 보이지 않는다.
          </p>
        </CardContent>
      </Card>

      {/* U601-05~07 — 같은 화면 하단의 상세(동작 ②) */}
      {detailOpen ? <VarianceDetail /> : null}

      {/* U601-08 — 보고 요약으로 */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border px-4 py-3">
        <p className="text-sm">
          성과 판단과 후속 대응이 담긴 보고 요약 — {s.report_version} · {s.period.label}
        </p>
        <Button asChild size="sm">
          <Link href="/sc06/report">
            보고 요약 보기
            <ArrowRight aria-hidden className="size-3.5" />
          </Link>
        </Button>
      </div>

      <Disclosure summary="데이터 대사 17항목 · 적재 묶음">
        <div className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2 lg:grid-cols-3">
          {s.checks.map((c) => (
            <p key={c.check_id}>
              <span className="font-mono text-muted-foreground">{c.check_id}</span> {c.label}{" "}
              <span className="tabular-nums font-medium">{c.value === null ? "미산정" : c.value.toLocaleString("ko-KR")}</span>
            </p>
          ))}
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          {s.batch.batch_id} · {s.batch.seed_id} · <span className="font-mono">{s.batch.sha256.slice(0, 12)}</span> ·{" "}
          {s.batch.problems.length ? `적재 문제 ${s.batch.problems.length}건` : "적재 문제 없음"}
        </p>
      </Disclosure>
    </>
  );
}

function TaskLine({ t, open, onOpen }: { t: TaskRow; open: boolean; onOpen: () => void }) {
  return (
    <tr className={cn("border-b align-top", t.focus && "bg-muted/50")}>
      <th scope="row" className="py-2 pr-3 text-left font-normal">
        <span className="font-mono text-xs text-muted-foreground">{t.task_id}</span> <span className={cn(t.focus && "font-medium")}>{t.name}</span>
        <span className="block text-xs text-muted-foreground">
          완료 {shortClock(t.completed_at)} · {t.followup?.replaceAll(";", " · ")}
        </span>
        <span className="mt-1 flex flex-wrap gap-1">
          {/* 장면 6 근거(DOC61-*)만 연다 — DOC54 등 앞 장면 근거는 이 검토건의 근거 목록에 없다 */}
          {t.evidence_refs
            .filter((e) => e.startsWith("DOC61"))
            .map((e) => (
              <EvidenceChip key={e} id={e} />
            ))}
        </span>
      </th>
      <td className="py-2 pr-3">
        <StateTag tone={t.activity_judgment === "HOLD" ? "open" : "good"}>{ACTIVITY_LABEL[t.activity_judgment]}</StateTag>
      </td>
      <td className="py-2 pr-3 text-right">
        <Mn won={t.expected_krw} />
      </td>
      <td className="py-2 pr-3 text-right">
        <Mn won={t.actual_krw} empty="산정 보류" />
      </td>
      <td className="py-2 pr-3 text-right">
        <span className={cn("tabular-nums", (t.variance_krw ?? 0) < 0 && "font-semibold")} title={t.variance_krw === null ? undefined : formatWonExact(t.variance_krw)}>
          {signedMillion(t.variance_krw)}
        </span>
      </td>
      <td className="py-2 pr-3">
        <StateTag tone={t.variance_krw === null ? "open" : t.variance_krw < 0 ? "warn" : "good"}>{t.performance}</StateTag>
      </td>
      <td className="py-2 text-right">
        {t.focus ? (
          <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={onOpen} aria-expanded={open}>
            {open ? "닫기" : "상세"}
          </Button>
        ) : null}
      </td>
    </tr>
  );
}

/** U601-02 — 자료 수집 상태와 업무 판단을 따로. 미비·대체 근거·판단자·보완 담당·기한을 한 자리에. */
function JudgmentLine({ j }: { j: Judgment }) {
  return (
    <Card data-index-skip>
      <CardContent className="space-y-2 text-sm">
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="text-xs text-muted-foreground">{j.judgment_id} · {j.target}</span>
          <StateTag tone={j.collection_state === "COMPLETE" ? "good" : "open"}>자료 {COLLECTION_LABEL[j.collection_state]}</StateTag>
          <StateTag tone={j.judgment_state === "REVIEWABLE" ? "good" : "warn"}>업무 판단 {JUDGMENT_LABEL[j.judgment_state]}</StateTag>
        </p>
        {j.missing ? (
          <p>
            미비 <span className="font-medium">{j.missing}</span> — 대체 근거 {j.alternatives.join(" · ") || "없음"}
          </p>
        ) : null}
        {j.impact ? <p className="text-xs text-muted-foreground">영향 판단: {j.impact}</p> : null}
        {j.hold_reasons.length ? <Problem text={`판단 보류 — ${j.hold_reasons.join(" · ")}`} /> : null}
        <p className="text-xs text-muted-foreground">
          판단 {personName(j.judged_by)} {shortClock(j.judged_at)}
          {j.owner && j.due_at ? ` · 보완 ${personName(j.owner)} ${shortClock(j.due_at)}까지` : ""} · <EvidenceChip id={j.evidence_id} />
        </p>
      </CardContent>
    </Card>
  );
}

function AgentPair({ a }: { a: AgentRun }) {
  return (
    <div className="grid gap-2 rounded-md border p-3 text-sm md:grid-cols-2">
      <div className="space-y-1">
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Bot aria-hidden className="size-3.5" />
          {a.run_id} · {a.task} · {shortClock(a.at)} · 입력 {a.input_scope}
        </p>
        <p>
          <span className="text-xs text-muted-foreground">초안 </span>
          {a.draft}
        </p>
      </div>
      <div className="space-y-1 md:border-l md:pl-3">
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <UserCheck aria-hidden className="size-3.5" />
          {AGENT_STATE_LABEL[a.state]}
          {a.reviewed_by ? ` · ${personName(a.reviewed_by)} ${shortClock(a.reviewed_at)}` : ""}
        </p>
        <p>{a.human ?? <span className="text-muted-foreground">사람 판단 전 — 이 초안은 후보다</span>}</p>
      </div>
    </div>
  );
}

function NewerCalculation({ ctx }: { ctx: ReadContext }) {
  const n = ctx.newer_calculation;
  if (!n) return null;
  return (
    <Problem
      text={`이 보고본(${ctx.report_version})은 ${ctx.calculation_version} 산정에 묶여 있다. 그 뒤 ${n.calculation_version}(${n.reason ?? "재적재"})에서 ${n.changed_tasks.join("·")} 수치가 바뀌었다 — 3과제 확인 효과 ${million(
        n.totals.actual_krw,
        "산정 보류",
      )}백만원. 새 보고 버전에서 ${n.reconfirm.join(" → ")} 확인을 다시 해야 한다.`}
    />
  );
}

/** U601-05·06·07 — ACT42 차이 상세. 원인 집계(전체 14건)와 대표 주문 한 건, Agent 초안과 사람 보정을 함께. */
function VarianceDetail() {
  const variance = useSc06((s) => s.variance);
  return (
    <section id="act42-detail" aria-label="ACT42 주요 차이 상세" className="space-y-4">
      <LoadGate load={variance} what="ACT42 차이 상세">
        {(v) => <VarianceBody v={v} />}
      </LoadGate>
    </section>
  );
}

function VarianceBody({ v }: { v: Variance }) {
  const m = Object.fromEntries(v.metrics.map((x) => [x.metric_id, x]));
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>ACT42 긴급구매 원인</CardTitle>
          <CardDescription>
            Q4 주문 {m["M61-01"]?.value}건 중 긴급 {v.cause_total.count}건 — 원인별 비용은 긴급 전체의 실제 비용이다. 기대 대비 차이(
            {signedMillion(v.variance_krw)})를 나눈 것이 아니다.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-3">
            {v.cause_groups.map((g) => (
              <div key={g.cause} className={cn("rounded-md border p-3", g.cause === v.change?.cause && "bg-muted/50")}>
                <p className="text-xs text-muted-foreground">{g.label}</p>
                <p className="text-xl font-semibold tabular-nums">{g.count}건</p>
                <p className="text-xs">
                  실제 긴급비 <Mn won={g.actual_urgent_cost_krw} />
                  백만원
                </p>
                <p className="text-[11px] text-muted-foreground">
                  {g.cause === "INTERNAL" ? "→ FUP61 운영 보완" : g.cause === "SUPPLY" ? "→ PROP61 공급조건 검토" : g.cause === "MIXED" ? "→ FUP61·PROP61 함께" : ""}
                </p>
              </div>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            합계 {v.cause_total.count}건 · <Mn won={v.cause_total.actual_urgent_cost_krw} />
            백만원 · 기준 {m["M61-08"]?.value}건 대비 FC51 전망 {m["M61-09"]?.value}건, 실제 {v.cause_total.count}건(전망 대비 +{m["M61-10"]?.value}건) · 공유 지연{" "}
            {m["M61-06"]?.value}건 · 구매 확인 지연 {m["M61-07"]?.value}건(복합 포함, 기준 {v.limits.confirm_minutes}분) · 납기·품질 이상 {m["M61-11"]?.value}·
            {m["M61-12"]?.value}건
          </p>
          {v.cause_reconciliation.problems.map((p) => (
            <Problem key={p} text={p} />
          ))}
          <Disclosure summary="월별 ACT42 효과와 긴급 14건 전체">
            <div className="space-y-3">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[36rem] text-xs">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="py-1.5 pr-3 font-medium">월</th>
                      <th className="py-1.5 pr-3 text-right font-medium">기준 긴급비</th>
                      <th className="py-1.5 pr-3 text-right font-medium">실제 긴급비</th>
                      <th className="py-1.5 pr-3 text-right font-medium">운영지원비</th>
                      <th className="py-1.5 pr-3 text-right font-medium">확인 효과</th>
                      <th className="py-1.5 pr-3 text-right font-medium">기대</th>
                      <th className="py-1.5 text-right font-medium">차이</th>
                    </tr>
                  </thead>
                  <tbody>
                    {v.months.map((x) => (
                      <tr key={x.effect_id} className="border-b">
                        <th scope="row" className="py-1.5 pr-3 text-left font-normal">
                          {monthLabel(x.month)} · 긴급 {x.urgent_count ?? "—"}건
                        </th>
                        <td className="py-1.5 pr-3 text-right">
                          <Mn won={x.baseline_or_avoided} />
                        </td>
                        <td className="py-1.5 pr-3 text-right">
                          <Mn won={x.actual_cost} />
                        </td>
                        <td className="py-1.5 pr-3 text-right">
                          <Mn won={x.operating_cost} />
                        </td>
                        <td className="py-1.5 pr-3 text-right">
                          <Mn won={x.net} empty="산정 보류" />
                        </td>
                        <td className="py-1.5 pr-3 text-right">
                          <Mn won={x.expected} />
                        </td>
                        <td className="py-1.5 text-right tabular-nums">{signedMillion(x.variance)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-muted-foreground text-[11px]">
                기준 = 월 12건 × 120만원(FC51 물량 정규화 가정, 과거 실적 아님) · 8월 일회성 2백만원은 Q4에 다시 빼지 않는다
              </p>
              <ul className="grid gap-x-4 gap-y-0.5 text-[11px] sm:grid-cols-2">
                {v.urgent_orders.map((o) => (
                  <li key={o.order_id} className={cn("tabular-nums", o.order_id === v.order?.order_id && "font-semibold")}>
                    <span className="font-mono">{o.order_id}</span> {CAUSE_LABEL[o.cause ?? "UNKNOWN"]} · 공유 {formatDuration(o.share_minutes)} · 확인{" "}
                    {formatDuration(o.confirm_minutes)} · 공급 지연 {formatDuration(o.supply_gap_minutes)} · <Mn won={o.urgent_cost} />
                  </li>
                ))}
              </ul>
            </div>
          </Disclosure>
        </CardContent>
      </Card>

      {v.order && v.change ? <RepresentativeOrder v={v} /> : <Problem text="대표 주문 근거를 찾지 못했다 — 원인 판단 근거로 쓰지 않는다." />}
    </>
  );
}

/** U601-06·07 — PO61-1103: 시각 순서와 공급 일정, Agent 초안 ↔ 사람 보정을 같은 영역에. */
function RepresentativeOrder({ v }: { v: Variance }) {
  const o = v.order!;
  const c = v.change!;
  const steps: Array<[string, string | null, string]> = [
    ["변경 수신", c.received_at, ""],
    ["공유", c.shared_at, `수신 후 ${formatDuration(c.share_minutes)} (기준 ${v.limits.share_minutes}분)`],
    ["구매 확인", c.confirmed_at, `공유 후 ${formatDuration(c.confirm_minutes)} (기준 ${v.limits.confirm_minutes}분)`],
    ["긴급 승인", o.approved_at, personName(o.approver)],
    ["발주", o.ordered_at, `운송 ${formatWonExact(o.freight)} + 할증 ${formatWonExact(o.surcharge)}`],
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle>대표 주문 {o.order_id} — 확인은 제때, 공급이 늦었다</CardTitle>
        <CardDescription>
          {c.change_id} · {o.model_id} · {o.part_id} {o.qty.toLocaleString("ko-KR")}개 · 최종 원인 {CAUSE_LABEL[c.cause]} · 이 한 건으로 14건 전체 원인을 추정하지
          않는다
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 lg:grid-cols-2">
          <ol className="space-y-1.5 text-sm">
            {steps.map(([label, at, note]) => (
              <li key={label} className="grid grid-cols-[4.5rem_6.5rem_1fr] gap-2">
                <span className="text-muted-foreground">{label}</span>
                <span className="whitespace-nowrap tabular-nums font-medium">{shortClock(at)}</span>
                <span className="text-xs text-muted-foreground">{note}</span>
              </li>
            ))}
          </ol>
          <div className="space-y-1.5 rounded-md border p-3 text-sm">
            <p>
              요구 납기 <span className="font-medium tabular-nums">{shortClock(c.required_at)}</span> · 정상 공급 가능{" "}
              <span className="font-medium tabular-nums">{shortClock(c.supply_at)}</span>
            </p>
            <p className="text-xs text-muted-foreground">
              정상 조달이 요구 납기보다 {formatDuration(c.supply_gap_minutes)} 늦다 — 제때 공유·확인했어도 긴급 대응이 필요했다. 납기·품질 이상{" "}
              {o.delivery_issue}·{o.quality_issue}건.
            </p>
            <p className="text-xs">{c.reason}</p>
            <p className="flex flex-wrap gap-1">
              {v.evidence.map((e) => (
                <EvidenceChip key={e} id={e} />
              ))}
            </p>
          </div>
        </div>
        {v.agent ? <AgentCorrection a={v.agent} /> : null}
      </CardContent>
    </Card>
  );
}

function AgentCorrection({ a }: { a: AgentRun }) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <div className="space-y-1.5 rounded-md border p-3 text-sm">
        <p className="flex items-center gap-1.5 text-xs font-medium">
          <Bot aria-hidden className="size-3.5" />
          {a.run_id} 초안 · {shortClock(a.at)} · 후보 {a.candidate_cause ? CAUSE_LABEL[a.candidate_cause] : "—"}
        </p>
        <p className="text-xs text-muted-foreground">입력 범위: {a.input_scope}</p>
        <p>{a.draft}</p>
      </div>
      <div className="space-y-1.5 rounded-md border p-3 text-sm">
        <p className="flex items-center gap-1.5 text-xs font-medium">
          <UserCheck aria-hidden className="size-3.5" />
          {a.state === "HUMAN_REVIEWED" ? `사람 보정 · ${personName(a.reviewed_by)} ${a.reviewed_at ? formatClock(a.reviewed_at) : ""}` : AGENT_STATE_LABEL[a.state]}
        </p>
        <p className="text-xs text-muted-foreground">추가 확인 근거: {a.links.join(" · ")}</p>
        <p>{a.human ?? "사람이 확인하기 전이다 — 원인은 후보로만 본다."}</p>
        <Commentary block>
          <p className="text-xs text-muted-foreground">
            Agent가 틀린 것이 아니라 입력이 불완전했다 — 처음 입력에는 대행 로그가 연결되지 않았다. 담당자가 대행 확인 기록과 공급 가능일을 더해
            원인을 확정했다(CT606·607).
          </p>
        </Commentary>
      </div>
    </div>
  );
}
