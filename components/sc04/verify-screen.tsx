"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";

import { useUserName } from "@/components/sc01/bits";
import { AgentCard } from "@/components/sc04/agent-card";
import { Mn, Sc04Body, Sc04Header, WaitingForms } from "@/components/sc04/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import type { EffectRun, Sc04View } from "@/lib/sc04/types";

const ALTS = ["ALT41", "ALT42", "ALT43"];

/**
 * U402 비용·중복 효과 검증 — 월별 물량·단가·시작월·전환비, 회피 비용·추가 비용·잔존 고정비·중복 구간을 나눠
 * 보인다. 계산 서비스가 검증하고 차단 오류는 보고 확정을 막는다(조건부 승인으로 우회할 수 없다). 기존 감가상각비는
 * 기준 손익에 그대로 있는 잔존 고정비다 — 절감·추가 지출이 아니다(DEC406).
 */
export function Sc04VerifyScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc04Header id="U402" title="비용·중복 효과 검증" question="보고 금액이 아니라 실제로 줄일 수 있는 비용만 효과로 남았는가?" />
      <Sc04Body>{(view) => <Verify view={view} />}</Sc04Body>
    </main>
  );
}

function Verify({ view }: { view: Sc04View }) {
  const name = useUserName();
  const verifyRuns = view.runs.filter((r) => r.kind === "VERIFY");
  const run = verifyRuns.at(-1);
  const v = view.verification;
  const openRework = view.rework.filter((r) => r.state === "OPEN");
  return (
    <>
      <WaitingForms view={view} nodes={["Verify_Effects", "Correct_Effects"]} labels={{ Verify_Effects: "검증 실행", Correct_Effects: "보완·재확인" }} />
      <Card data-index-skip>
        <CardHeader>
          <CardTitle>
            검증 상태 —{" "}
            {v === null ? "검증 전" : v.state === "VERIFIED" ? "검증 완료" : v.state === "STALE" ? "보완 뒤 재검증 필요" : "차단"}
          </CardTitle>
          <CardDescription>
            {v?.verified_at ? `${name(v.verified_by)} ${formatClock(v.verified_at)} · ${v.run_id}` : run ? `${run.run_id} · ${formatClock(run.calculated_at)}` : "확인된 분석 결과가 모이면 경영관리가 검증한다."}
          </CardDescription>
        </CardHeader>
        {run ? (
          <CardContent className="space-y-2 text-sm">
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs">
              <span>
                당해연도 순효과 <Mn value={run.result.effect_total} />백만원
              </span>
              <span>
                중복 제거 <Mn value={run.result.duplicate_total} />
              </span>
              <span>
                고정비 절감 <Mn value={run.result.fixed_saving_total} />
              </span>
              <span>
                공장 고정비 월 <Mn value={run.result.fixed_cost_monthly} /> — 유지
              </span>
            </div>
            {run.result.errors.length ? (
              <ul className="space-y-1 text-xs">
                {run.result.errors.map((e) => (
                  <li key={`${e.alt_id}-${e.code}`} className="flex gap-1.5">
                    <AlertTriangle aria-hidden className="mt-0.5 size-3.5 shrink-0" style={{ color: "var(--viz-status-critical)" }} />
                    <span>
                      <span className="font-mono">{e.alt_id}</span> {e.message}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="flex items-center gap-1.5 text-xs">
                <CheckCircle2 aria-hidden className="size-3.5" style={{ color: "var(--viz-status-good)" }} />
                차단 오류 없음 — 근거 없는 회피 비용·중복·적용량 초과·일회성비 누락이 없다.
              </p>
            )}
          </CardContent>
        ) : null}
      </Card>

      {openRework.map((r) => (
        <Card key={r.rework_id}>
          <CardHeader>
            <CardTitle>보완 요청 {r.rework_id}</CardTitle>
            <CardDescription>
              {r.alt_id} · 담당 {name(r.owner)} · 기한 {formatClock(r.due_at)} · 요청 {name(r.requested_by)}
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm">{r.reason}</CardContent>
        </Card>
      ))}

      {run ? <Lines run={run} /> : null}
      <AgentCard view={view} kind="AG41" />

      <Card>
        <CardHeader>
          <CardTitle>잔존 고정비와 회피 비용</CardTitle>
          <CardDescription>EVDC45 — 월 공장 고정비 370백만원은 그대로다. 감가상각 120 · 기타 250은 설명용 세분이다.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-1 text-xs text-muted-foreground">
          <p>외주로 돌려도 기존 인건비·감가상각비는 계속 발생한다 — 회피 고정비 0, 신규 설비투자 없음.</p>
          <p>실제로 줄어드는 것은 변동가공비의 회피 가능 부분이고, 추가 외주비·물류비·전환비를 뺀다.</p>
          <Commentary>
            <p>실제 회사 일반론으로 모든 감가상각을 항상 회피 불가로 규정하는 것은 아니다 — 이 대안의 근거가 그렇다는 것이다.</p>
          </Commentary>
        </CardContent>
      </Card>

      {view.assumptions.length ? (
        <Disclosure summary={`산정 가정 ${view.assumptions.length}건 · 변경 이력 ${view.assumptionLog.length}건`}>
          <ul className="space-y-1 text-xs">
            {view.assumptions.map((a) => (
              <li key={a.alt_id}>
                <span className="font-mono">
                  {a.alt_id}-v{a.version}
                </span>{" "}
                {a.name} · {a.model_id} {a.cost_item} · 시작 {a.start.slice(0, 7)} · 일회성 {a.one_off_cost === null ? "미입력" : Number(a.one_off_cost).toLocaleString("ko-KR")}원({a.one_off_month.slice(0, 7)})
              </li>
            ))}
          </ul>
          <ul className="mt-2 space-y-0.5 text-xs text-muted-foreground">
            {view.assumptionLog.map((l) => (
              <li key={`${l.alt_id}-${l.version}`}>
                {formatClock(l.at)} {l.alt_id}-v{l.version} {name(l.by)} — {l.note}
              </li>
            ))}
          </ul>
        </Disclosure>
      ) : null}
    </>
  );
}

function Lines({ run }: { run: EffectRun }) {
  const [alt, setAlt] = useState("ALT41");
  const lines = run.result.lines.filter((l) => l.alt_id === alt);
  const cols: Array<[keyof (typeof lines)[number], string]> = [
    ["avoided", "회피액"],
    ["added", "추가 거래비"],
    ["logistics", "추가 물류비"],
    ["support", "운영지원비"],
    ["one_off", "일회성비"],
    ["draft_discount", "초안 할인"],
    ["duplicate", "중복 제거"],
    ["fixed_saving", "고정비 절감"],
    ["net", "순효과"],
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle>월별 효과 내역</CardTitle>
        <CardDescription>{run.run_id} · 원 단위로 계산, 백만원 표시. 순효과 = 회피액 − 추가비 − 지원비 − 일회성비 + 초안 할인 − 중복 제거.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <div role="group" aria-label="대안" className="flex flex-wrap gap-1">
          {ALTS.map((a) => (
            <button
              key={a}
              type="button"
              aria-pressed={alt === a}
              onClick={() => setAlt(a)}
              className={`rounded-md border px-2 py-1 text-xs ${alt === a ? "bg-muted font-medium" : "text-muted-foreground"}`}
            >
              {a}
            </button>
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-xs" aria-label={`${alt} 월별 효과`}>
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-1 pr-2 font-medium">월</th>
                <th className="py-1 pr-2 text-right font-medium">대상량</th>
                {cols.map(([, label]) => (
                  <th key={label} className="py-1 pr-2 text-right font-medium">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y">
              {lines.map((l) => (
                <tr key={l.month} className={l.applied ? undefined : "text-muted-foreground"}>
                  <th scope="row" className="py-1 pr-2 text-left font-normal">
                    {l.month.slice(0, 7)}
                  </th>
                  <td className="py-1 pr-2 text-right tabular-nums">{l.qty.toLocaleString("ko-KR")}</td>
                  {cols.map(([key]) => (
                    <td key={String(key)} className={`py-1 pr-2 text-right ${key === "net" ? "font-medium" : ""}`}>
                      <Mn value={String(l[key])} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
