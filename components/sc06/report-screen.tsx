"use client";

import { CompanyLink as Link } from "@/components/shared/company-link";
import { ArrowLeft, CalendarClock, Wrench, Lightbulb } from "lucide-react";

import { EvidenceChip, LoadGate, Mn, personName, Problem, Sc06Body, Sc06Header, StateTag } from "@/components/sc06/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { gapWord } from "@/lib/sc04/format";
import {
  CAUSE_LABEL,
  COLLECTION_LABEL,
  estimationText,
  FOLLOWUP_STATE_LABEL,
  JUDGMENT_LABEL,
  million,
  monthLabel,
  RECORD_STATE_LABEL,
  shortClock,
  signedMillion,
} from "@/lib/sc06/format";
import type { Followup, Report } from "@/lib/sc06/types";
import { useSc06 } from "@/lib/store/sc06";

/**
 * U602 보완조치·추가 과제와 보고 요약 — 동작 ③. 확인된 보고본 RPT61-v1을 **조회**한다 — 승인·발의·확정 같은 행위 버튼이
 * 없다(구현명세 5장). 활동 완료 · 성과 기대 미달 · 운영 보완 · 추가 발의 · 위험 지속을 한 색으로 뭉치지 않는다(J609).
 */
export function Sc06ReportScreen() {
  const report = useSc06((s) => s.report);
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc06Header id="U602" title="보완조치·추가 과제와 보고 요약" question="남은 차이를 줄이기 위해 무엇을 보완하고, 무엇을 새로 검토하는가?" />
      <Sc06Body>
        <LoadGate load={report} what="보고 요약">
          {(r) => <Body r={r} />}
        </LoadGate>
      </Sc06Body>
    </main>
  );
}

function Body({ r }: { r: Report }) {
  const fup = (id: string) => r.followups.find((f) => f.followup_id === id);
  const fup61 = fup("FUP61");
  const prop61 = fup("PROP61");
  const fup62 = fup("FUP62");
  const risk61 = fup("RISK61");
  return (
    <>
      {r.newer_calculation ? (
        <Problem
          text={`보고본 뒤에 새 산정 ${r.newer_calculation.calculation_version}이 생겼다 — 이 보고 문구와 숫자는 ${r.calculation_version} 기준이다. 새 보고 버전에서 ${r.newer_calculation.reconfirm.join(
            " → ",
          )}를 다시 확인한다.`}
        />
      ) : null}
      {r.problems.map((p) => (
        <Problem key={p} text={p} />
      ))}
      {r.state !== "REPORTED" ? (
        <Problem
          text={`보고본 ${r.report_version}은 아직 ${r.state === "FINALIZED" ? "확정 뒤 대표 보고 전" : "확인 중(확정 전)"}이다 — 확인 ${r.confirmations.length}/5 단계. 아래 숫자는 적재 때 계산된 산정 ${r.calculation_version}이고, 확인 절차 화면에서 남은 결재를 진행한다.`}
        />
      ) : null}

      {/* U602-01 — 보고 결론 */}
      <Card>
        <CardHeader>
          <CardTitle>보고 결론</CardTitle>
          <CardDescription>
            {r.report_version} · 대표 월간 보고 {shortClock(r.report_date)} · 같은 분기(2027 Q4)·같은 범위의 비교 수치만
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3" data-index-skip>
            <Figure label="3과제 Q4 기대 → 확인 효과">
              <Mn won={r.totals.expected_krw} /> → <Mn won={r.totals.actual_krw} empty="산정 보류" />
            </Figure>
            <Figure label="기대 대비 차이">{signedMillion(r.totals.variance_krw)}</Figure>
            <Figure label="ACT42 긴급구매 축소">
              <Mn won={r.focus.expected_krw} /> → <Mn won={r.focus.actual_krw} empty="산정 보류" />{" "}
              <span className="text-sm font-normal">({signedMillion(r.focus.variance_krw)})</span>
            </Figure>
          </div>
          {r.conclusion ? (
            <blockquote className="border-l-2 pl-3 text-sm leading-relaxed">
              {r.conclusion.content}
              <footer className="mt-1 text-xs text-muted-foreground">
                {personName(r.conclusion.actor)} 작성 · {RECORD_STATE_LABEL[r.conclusion.state] ?? r.conclusion.state} {shortClock(r.conclusion.at)} ·{" "}
                {r.conclusion.state === "FINALIZED"
                  ? `확인된 문구다 (숫자는 산정 ${r.calculation_version}과 대조됨)`
                  : "초안이다 — 숫자는 확정 때 산정과 대조된다"}
              </footer>
            </blockquote>
          ) : null}
          <p className="flex flex-wrap gap-x-4 gap-y-1">
            <StateTag tone="good">활동 완료 확인(3과제)</StateTag>
            <StateTag tone="warn">ACT42 일부 기대 미달</StateTag>
            <StateTag tone="open">운영 보완 진행 · 추가 검토 발의</StateTag>
            <StateTag tone="open">위험 {r.risk.risk_id} {r.risk.state}</StateTag>
          </p>
        </CardContent>
      </Card>

      {/* U602-02 · U602-03 — 운영 보완 / 추가 발의 */}
      <section aria-label="후속 대응" className="grid gap-4 lg:grid-cols-2">
        {fup61 ? <FollowupCard f={fup61} icon="fix" /> : null}
        {prop61 ? <FollowupCard f={prop61} icon="new" proposal={r.proposal_evidence?.evidence_id} /> : null}
      </section>

      {/* U602-04 — 남는 사항 */}
      <Card>
        <CardHeader>
          <CardTitle>남는 사항</CardTitle>
          <CardDescription>자료 미비와 성과 미달은 다른 문제다 · 검토 가능 판단 뒤에도 미비 항목을 지우지 않는다</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm md:grid-cols-2">
          {r.judgment && fup62 ? (
            <div className="space-y-1 rounded-md border p-3">
              <p className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-muted-foreground">{fup62.followup_id} · {r.judgment.judgment_id}</span>
                <StateTag tone="open">자료 {COLLECTION_LABEL[r.judgment.collection_state]}</StateTag>
                <StateTag tone={r.judgment.judgment_state === "REVIEWABLE" ? "good" : "warn"}>{JUDGMENT_LABEL[r.judgment.judgment_state]}</StateTag>
              </p>
              <p>{fup62.content}</p>
              <p className="text-xs text-muted-foreground">
                대체 근거 {r.judgment.alternatives.join(" · ")} · 보완 {personName(r.judgment.owner)} {shortClock(fup62.due_at)}까지 · 효과{" "}
                {estimationText(fup62.effect)}(성과를 새로 산정하는 조치가 아니다)
              </p>
            </div>
          ) : null}
          {risk61 ? (
            <div className="space-y-1 rounded-md border p-3">
              <p className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-muted-foreground">{risk61.followup_id} ← {risk61.links.join(" · ")}</span>
                <StateTag tone="open">{risk61.state}</StateTag>
              </p>
              <p>{risk61.content}</p>
              <p className="text-xs text-muted-foreground">
                관리 {personName(risk61.owner)} · 다음 확인 {shortClock(risk61.next_check_at)} · {risk61.scope_check}
              </p>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* U602-05 · U602-06 — 확인 상태와 다음 확인 */}
      <section aria-label="확인 상태와 다음 확인" className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>확인 상태</CardTitle>
            <CardDescription>
              같은 {r.report_version} · {r.confirmations.length}/5 단계 · 결재는 확인 절차 화면에서 한다 · 보고본 확정은 추가 과제의 실행·예산
              승인이 아니다
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="space-y-1.5 text-sm">
              {r.confirmations.map((c) => (
                <li key={c.record_id} className="grid grid-cols-[1fr_auto] gap-x-3 sm:grid-cols-[11rem_1fr_auto]">
                  <span className="text-muted-foreground">{c.step}</span>
                  <span className="hidden text-xs sm:block">
                    {personName(c.actor)} · {c.content}
                  </span>
                  <span className="text-right">
                    <StateTag tone="good">
                      {RECORD_STATE_LABEL[c.state] ?? c.state} {shortClock(c.at)}
                    </StateTag>
                  </span>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>다음 확인</CardTitle>
            <CardDescription>다음 월간 보고 {shortClock(r.next_review)}에서 보완 결과와 검토안을 본다</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1.5 text-sm">
            {[...r.followups]
              .filter((f) => f.due_at)
              .sort((a, b) => (a.due_at ?? "").localeCompare(b.due_at ?? ""))
              .map((f) => (
                <p key={f.followup_id} className="flex items-center gap-2">
                  <CalendarClock aria-hidden className="size-3.5 text-muted-foreground" />
                  <span className="tabular-nums font-medium">{shortClock(f.due_at)}</span>
                  <span>
                    {f.followup_id} {f.kind} · {personName(f.owner)}
                  </span>
                </p>
              ))}
            {r.note ? <p className="pt-1 text-xs text-muted-foreground">{r.note.content}</p> : null}
          </CardContent>
        </Card>
      </section>

      <Disclosure summary="보조 정보 — Q4 관리손익과 연간 공식 전망">
        <div className="space-y-2 text-xs">
          <p>
            Q4 관리손익(다른 FC51 요인이 같다는 가정, 효과 차이만 반영):{" "}
            {r.quarter_profit.months.map((m) => (
              <span key={m.period} className="mr-3 tabular-nums">
                {monthLabel(m.period ?? "")} <Mn won={m.profit} />
              </span>
            ))}
            · Q4 <Mn won={r.quarter_profit.quarter.profit} /> vs 목표 <Mn won={r.quarter_profit.quarter.target} /> ({signedMillion(r.quarter_profit.quarter.vs_target)}, 실적 − 목표)
          </p>
          <p className="text-muted-foreground">
            과제 기대효과 일부 미달과 분기 목표 초과는 함께 성립한다 · 분기 효과 미달을 연간 목표 부족에 더하지 않는다.
          </p>
          <p>
            연간 공식 전망 {r.annual.official} {million(Number(r.annual.annual))} · Target {million(Number(r.annual.target))} · {gapWord(r.annual.gap)}{" "}
            {million(Math.abs(Number(r.annual.gap)))}백만원 — 완료·성과 검토는 자동으로 바꾸지 않는다(새 Forecast 승인 아님).
          </p>
          {r.monitoring ? (
            <p className="text-muted-foreground">
              분기 중 점검: <EvidenceChip id={r.monitoring.evidence_id} /> — 12월말까지 개입을 미루지 않았다.
            </p>
          ) : null}
        </div>
      </Disclosure>

      <Button asChild variant="outline" size="sm">
        <Link href="/sc06">
          <ArrowLeft aria-hidden className="size-3.5" />
          완료·성과 검토로
        </Link>
      </Button>
    </>
  );
}

function Figure({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-xl font-semibold tabular-nums">{children}</p>
    </div>
  );
}

function FollowupCard({ f, icon, proposal }: { f: Followup; icon: "fix" | "new"; proposal?: string }) {
  const Icon = icon === "fix" ? Wrench : Lightbulb;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Icon aria-hidden className="size-4 text-muted-foreground" />
          {f.kind} {f.followup_id}
        </CardTitle>
        <CardDescription>
          {f.causes.map((c) => CAUSE_LABEL[c] ?? c).join(" · ")} → {f.links.join(" · ")}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p>
          <StateTag tone="open">{FOLLOWUP_STATE_LABEL[f.state] ?? f.state}</StateTag>
        </p>
        <p>{f.content}</p>
        <p className="text-xs text-muted-foreground">
          책임 {personName(f.owner)} · 협조 {f.cooperation.map((p) => personName(p)).join(", ")} · 기한 {shortClock(f.due_at)} · 다음 확인{" "}
          {shortClock(f.next_check_at)}
        </p>
        <p className="text-xs">
          효과 <span className="font-medium">{estimationText(f.effect)}</span> · 예산 <span className="font-medium">{estimationText(f.budget)}</span>
          {f.budget.note && f.budget.estimation_status === "CONFIRMED" ? ` (${f.budget.note})` : ""}
        </p>
        <p className="text-xs text-muted-foreground">{f.scope_check}</p>
        {proposal ? (
          <p className="text-xs">
            발의 검토 근거 <EvidenceChip id={proposal} />
          </p>
        ) : null}
        {icon === "new" ? (
          <Commentary block>
            <p className="text-xs text-muted-foreground">
              발의는 실행 승인이나 예산 배정이 아니다 — 운송비 절감만이 아니라 재고·자금·보관·진부화·품질·납기 영향을 함께 비교한다. 미산정 효과를
              현재 성과나 전망에 더하지 않는다.
            </p>
          </Commentary>
        ) : null}
      </CardContent>
    </Card>
  );
}
