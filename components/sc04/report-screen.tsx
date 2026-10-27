"use client";

import { useState } from "react";

import { useUserName } from "@/components/sc01/bits";
import { Mn, Sc04Body, Sc04Header, WaitingForms } from "@/components/sc04/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { gapWord } from "@/lib/sc04/format";
import type { EffectRun, PeriodResult, Sc04View } from "@/lib/sc04/types";

const PERIODS: Array<[PeriodResult["kind"], string]> = [
  ["year", "2027 연간"],
  ["q3", "Q3"],
  ["q4", "Q4"],
  ["remaining", "잔여 7~12월"],
];

/**
 * U404 월간 경영회의 보고 — 대응 전 부족 · 보고 효과 · 보고 후 부족을 위에, 기준 전망 → 추천안 반영 전망과 월별
 * 근거를 아래에 둔다. **보고 시점에는 REP41-v1만 본다** — 판단본이 생겨도 원 보고값을 덮지 않는다. 보고본 열람·배포는
 * 대표 승인이 아니다.
 */
export function Sc04ReportScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc04Header id="U404" title="월간 경영회의 보고" question="목표 미달 가능성을 숨기지 않고 개선 범위를 보고하는가?" />
      <Sc04Body>{(view) => <Report view={view} />}</Sc04Body>
    </main>
  );
}

function Report({ view }: { view: Sc04View }) {
  const name = useUserName();
  const rep = view.reports.find((r) => r.report_id === "REP41-v1");
  const run = rep ? view.runs.find((r) => r.run_id === rep.run_id) : undefined;
  const m = view.meeting;
  return (
    <>
      <WaitingForms view={view} nodes={["Freeze_Report", "Report_Meeting"]} labels={{ Freeze_Report: "보고본 확정·배포", Report_Meeting: "회의 개회·보고" }} />
      {run ? (
        <>
          <Kpis run={run} />
          <Card>
            <CardHeader>
              <CardTitle>보고 결론 — {rep!.report_id}</CardTitle>
              <CardDescription>
                확정 {name(rep!.frozen_by)} {formatClock(rep!.frozen_at)} · 해시 <span className="font-mono">{rep!.content_hash}</span> · 추천{" "}
                {(rep!.snapshot?.recommended as string[] | undefined)?.join(" · ")}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>{rep!.conclusion}</p>
              {rep!.distribution ? (
                <p className="text-xs text-muted-foreground">
                  내부 배포 {formatClock(rep!.distribution.at)} — {rep!.distribution.recipients.join(", ")} · 배포는 승인이 아니다(메일 없음)
                </p>
              ) : null}
            </CardContent>
          </Card>
          <Periods run={run} />
        </>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>보고본 확정 전</CardTitle>
            <CardDescription>공동 추천이 끝나면 경영관리 임원이 REP41-v1을 확정·배포한다.</CardDescription>
          </CardHeader>
        </Card>
      )}
      {m ? (
        <Card>
          <CardHeader>
            <CardTitle>
              {m.meeting_id} {m.subject}
            </CardTitle>
            <CardDescription>
              {formatClock(m.scheduled_at)} · 주재 {name(m.chair)} · 보고 {name(m.reporter)} · 보고본 {m.report_version} ·{" "}
              {m.state === "READY" ? "개회 전" : m.state === "IN_PROGRESS" ? "진행 중" : "종료"}
            </CardDescription>
          </CardHeader>
          {m.attendance.length ? (
            <CardContent className="text-xs text-muted-foreground">참석 {m.attendance.map((a) => name(a.actor)).join(", ")}</CardContent>
          ) : null}
        </Card>
      ) : null}
    </>
  );
}

function Kpis({ run }: { run: EffectRun }) {
  const y = run.result.periods.year;
  const tiles: Array<[string, string, string]> = [
    ["대응 전 목표 부족", y.gap_before, "Target − 수익성 통합 분석 기준 전망"],
    ["보고 개선효과", y.effect, "3개 실행안 · 중복 조정 후"],
    [`보고 후 ${gapWord(y.gap)}`, y.gap, "목표 미달 가능성이 남는다"],
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {tiles.map(([label, value, note]) => (
        <Card key={label} data-index-skip>
          <CardHeader>
            <CardDescription>{label}</CardDescription>
            <CardTitle className="text-2xl">
              <Mn value={value} />
              <span className="ml-1 text-xs font-normal text-muted-foreground">백만원</span>
            </CardTitle>
            <p className="text-xs text-muted-foreground">{note}</p>
          </CardHeader>
        </Card>
      ))}
    </div>
  );
}

function Periods({ run }: { run: EffectRun }) {
  const [kind, setKind] = useState<PeriodResult["kind"]>("year");
  const p = run.result.periods[kind];
  return (
    <Card>
      <CardHeader>
        <CardTitle>기준 전망 → 추천안 반영 전망</CardTitle>
        <CardDescription>
          {p.label} · 공장관리손익(전사 영업이익이 아니다). 보고본 한 버전만 집계한다 — 판단본과 섞지 않는다.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div role="group" aria-label="기간" className="flex flex-wrap gap-1">
          {PERIODS.map(([k, label]) => (
            <button
              key={k}
              type="button"
              aria-pressed={kind === k}
              onClick={() => setKind(k)}
              className={`rounded-md border px-2 py-1 text-xs ${kind === k ? "bg-muted font-medium" : "text-muted-foreground"}`}
            >
              {label}
            </button>
          ))}
        </div>
        <table className="w-full max-w-xl text-sm" aria-label={`${p.label} 손익 증감`}>
          <tbody className="divide-y">
            <Row label="Target" value={p.target} />
            <Row label="수익성 통합 분석 기준 관리손익" value={p.base} />
            <Row label={`대응 전 ${gapWord(p.gap_before)}`} value={p.gap_before} />
            <Row label="추천안 순효과(예상)" value={p.effect} signed />
            <Row label="추천안 반영 전망" value={p.forecast} strong />
            <Row label={`반영 후 ${gapWord(p.gap)}`} value={p.gap} strong />
          </tbody>
        </table>
        <p className="text-xs text-muted-foreground">
          {Number(p.gap) < 0 ? `${p.label}은 목표 초과다 — 음의 부족을 위험으로 읽지 않는다. 연간은 상반기 부족을 포함한다.` : null}
        </p>
        <Disclosure summary="월별 근거 — 1~6월은 미적용(0)">
          <table className="w-full text-xs" aria-label="월별 손익">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-1 pr-3 font-medium">월</th>
                <th className="py-1 pr-3 text-right font-medium">Target</th>
                <th className="py-1 pr-3 text-right font-medium">기준</th>
                <th className="py-1 pr-3 text-right font-medium">순효과</th>
                <th className="py-1 text-right font-medium">부족</th>
              </tr>
            </thead>
            <tbody>
              {run.result.months.map((mo) => (
                <tr key={mo.period}>
                  <th scope="row" className="py-1 pr-3 text-left font-normal">
                    {mo.period.slice(0, 7)}
                  </th>
                  <td className="py-1 pr-3 text-right">
                    <Mn value={mo.target} />
                  </td>
                  <td className="py-1 pr-3 text-right">
                    <Mn value={mo.base} />
                  </td>
                  <td className="py-1 pr-3 text-right">
                    <Mn value={mo.effect} signed />
                  </td>
                  <td className="py-1 text-right">
                    <Mn value={String(Number(mo.target) - Number(mo.base) - Number(mo.effect))} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Disclosure>
        <Commentary>
          <p className="text-xs text-muted-foreground">
            기존 부족(사건 이전)과 이번 사건 악화는 수익성 통합 분석에서 나눴다 — 대응안은 둘 다를 줄이지만 상반기 부족은 되돌리지 못한다.
          </p>
        </Commentary>
      </CardContent>
    </Card>
  );
}

function Row({ label, value, strong, signed }: { label: string; value: string; strong?: boolean; signed?: boolean }) {
  return (
    <tr>
      <th scope="row" className={`py-1.5 pr-3 text-left ${strong ? "font-medium" : "font-normal text-muted-foreground"}`}>
        {label}
      </th>
      <td className={`py-1.5 text-right ${strong ? "font-medium" : ""}`}>
        <Mn value={value} signed={signed} />
      </td>
    </tr>
  );
}
