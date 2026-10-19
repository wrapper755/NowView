"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight } from "lucide-react";

import { Commentary } from "@/components/shared/commentary";
import { ProfitTrendChart } from "@/components/sc01/profit-trend-chart";
import { Loading, RiskTag, ScreenHeader } from "@/components/sc01/bits";
import { useDashboard } from "@/components/sc01/use-dashboard";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  formatKrw,
  formatKrwSigned,
  formatQty,
  formatRatio,
  formatWonExact,
  modelLabel,
  TASK_STATUS_LABEL,
  TASK_TYPE_LABEL,
} from "@/lib/sc01/format";
import type { Dashboard, Pnl } from "@/lib/sc01/types";
import { selectView, useSc01 } from "@/lib/store/sc01";

const PERIODS = ["연간", "Q1", "Q2", "Q3", "Q4", "7월", "8월", "9월"];
const VERSION_LABEL: Record<string, string> = { T01: "Target", F01: "승인 전망 F01", F02: "검토 전망 F02" };

/**
 * UI01 — A제품 경영 현황. 사건 전후의 전체 상황을 보여 주고 검토할 모델과 업무로 들어간다.
 *
 * * 첫 화면은 **승인 전망 F01**이다. 계산이 성공하기 전에는 검토 전망 F02를 내놓지 않는다(AT01).
 * * 공장관리손익은 전사 영업이익이 아니다 — 상시 표기한다(UI01 근거 정보).
 * * 목표 부족액(T − F02)과 이번 사건 영향(F02 − F01)을 나란히 둔다 — 섞으면 사건이
 *   목표 차이 전부를 만든 것처럼 읽힌다(AT07).
 */
export function OverviewScreen() {
  const [period, setPeriod] = useState("연간");
  const [month, setMonth] = useState(7);
  const { dashboard, error } = useDashboard(period, month);
  const view = useSc01(selectView);

  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
      <ScreenHeader id="UI01" title="A제품 경영 현황" question="전체 성과와 전망은 어떠하며 무엇을 살펴봐야 하는가?" />

      <div role="tablist" aria-label="조회 기간" className="flex flex-wrap gap-1">
        {PERIODS.map((p) => (
          <button
            key={p}
            role="tab"
            type="button"
            aria-selected={p === period}
            onClick={() => setPeriod(p)}
            className={
              p === period
                ? "rounded-md bg-muted px-2.5 py-1 text-xs font-medium"
                : "rounded-md px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
            }
          >
            {p}
          </button>
        ))}
      </div>

      {error ? <p className="text-sm">{error}</p> : null}
      {!dashboard ? (
        <Loading what="경영 현황" />
      ) : (
        <>
          <ProfitCards dashboard={dashboard} />

          <Card>
            <CardHeader>
              <CardTitle>월별 공장관리손익</CardTitle>
              <CardDescription>
                Target·승인 전망{dashboard.review ? "·검토 전망" : ""}. 연간·분기는 월 금액의 합이다.
                <Commentary> 비율을 평균하지 않고 합산한 금액에서 다시 계산한다(CALC-04).</Commentary>
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ProfitTrendChart dashboard={dashboard} />
            </CardContent>
          </Card>

          <ModelTable dashboard={dashboard} month={month} setMonth={setMonth} />
        </>
      )}

      {view ? <WorkSummary /> : null}

      {dashboard ? (
        <Card size="sm">
          <CardHeader>
            <CardTitle>근거 정보</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-xs text-muted-foreground">
            <p>{dashboard.scope.note}</p>
            <p>
              실적 컷오프 {dashboard.asOf.actualCutoff} · 승인 전망 {dashboard.approved}
              {dashboard.review ? ` · 검토 전망 ${dashboard.review}(미승인)` : ""} · 원가 C01 · 경보 규칙 R01-v1
            </p>
            <p>회사 전체 매출 약 1조원은 배경이다. 이 화면의 수치는 A제품·울산공장 a~e모델 범위만이다.</p>
          </CardContent>
        </Card>
      ) : null}
    </main>
  );
}

function ProfitCards({ dashboard }: { dashboard: Dashboard }) {
  const t = dashboard.totals.T01;
  const approved = dashboard.totals[dashboard.approved];
  const review = dashboard.review ? dashboard.totals[dashboard.review] : null;
  const rows: { key: keyof Pnl; label: string }[] = [
    { key: "revenue", label: "매출" },
    { key: "cm", label: "공헌이익" },
    { key: "mgmtProfit", label: "공장관리손익" },
  ];
  const gap = (p: Pnl) => Number(p.mgmtProfit) - Number(t.mgmtProfit);
  const event = review ? Number(review.mgmtProfit) - Number(approved.mgmtProfit) : null;

  return (
    <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-[2fr_1fr]">
      <Card>
        <CardHeader>
          <CardTitle>{dashboard.period} 성과 요약</CardTitle>
          <CardDescription>숫자에 마우스를 올리면 원 단위 값이 나온다.</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[28rem] text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th scope="col" className="py-2 pr-3 font-medium">항목</th>
                {dashboard.versions.map((v) => (
                  <th key={v} scope="col" className="py-2 pr-3 text-right font-medium">{VERSION_LABEL[v] ?? v}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key} className="border-b last:border-0">
                  <th scope="row" className="text-left py-2 pr-3 font-normal">{r.label}</th>
                  {dashboard.versions.map((v) => (
                    <td key={v} className="py-2 pr-3 text-right tabular-nums" title={formatWonExact(dashboard.totals[v][r.key])}>
                      {formatKrw(dashboard.totals[v][r.key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>목표 차이</CardTitle>
          <CardDescription>공장관리손익 기준. Target은 바뀌지 않는다.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Figure label="승인 전망 F01 − Target" value={gap(approved)} />
          {review ? (
            <>
              <Figure label={`검토 전망 ${dashboard.review} − Target`} value={gap(review)} strong />
              <Figure label={`이번 사건 영향 (${dashboard.review} − F01)`} value={event ?? 0} />
              <p className="text-[11px] text-muted-foreground">
                사건 영향은 물량 변화만 반영한 초기 공헌이익 영향이다. 단가·원가 변동은 다음 장면에서 분석한다.
              </p>
            </>
          ) : (
            <p className="text-[11px] text-muted-foreground">검토 전망은 비교 계산이 끝나야 나온다.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Figure({ label, value, strong = false }: { label: string; value: number; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span
        className={strong ? "text-2xl font-semibold tabular-nums" : "text-sm font-medium tabular-nums"}
        title={formatWonExact(value)}
      >
        {formatKrwSigned(value)}
      </span>
    </div>
  );
}

function ModelTable({
  dashboard,
  month,
  setMonth,
}: {
  dashboard: Dashboard;
  month: number;
  setMonth: (m: number) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>모델별 현황</CardTitle>
        <CardDescription>
          a~e모델의 목표·직전 승인·최신 전망과 위험. 공장 합계가 괜찮아도 모델 경보는 유지된다.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-1">
          {[7, 8, 9].map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={m === month}
              onClick={() => setMonth(m)}
              className={
                m === month
                  ? "rounded-md bg-muted px-2.5 py-1 text-xs font-medium"
                  : "rounded-md px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
              }
            >
              {m}월
            </button>
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th scope="col" className="py-2 pr-3 font-medium">모델</th>
                <th scope="col" className="py-2 pr-3 text-right font-medium">목표</th>
                <th scope="col" className="py-2 pr-3 text-right font-medium">직전 승인</th>
                <th scope="col" className="py-2 pr-3 text-right font-medium">최신</th>
                <th scope="col" className="py-2 pr-3 text-right font-medium">달성률</th>
                <th scope="col" className="py-2 pr-3 font-medium">위험</th>
                <th scope="col" aria-label="상세" className="py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {dashboard.models.map((m) => (
                <tr key={m.modelId} className="border-b last:border-0">
                  <th scope="row" className="text-left py-2 pr-3 font-normal">{modelLabel(m.modelId)}</th>
                  <td className="py-2 pr-3 text-right tabular-nums">{formatQty(m.target)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{formatQty(m.prior)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">
                    {formatQty(m.latest)}
                    {m.latest !== m.prior ? (
                      <span className="ml-1 text-xs text-muted-foreground">({formatQty(m.latest - m.prior)})</span>
                    ) : null}
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums">{formatRatio(m.achievement, 1)}</td>
                  <td className="py-2 pr-3"><RiskTag risk={m.risk} /></td>
                  <td className="py-2 text-right">
                    <Link href="/risk" className="inline-flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground">
                      상세 <ArrowRight aria-hidden className="size-3" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-[11px] text-muted-foreground">단위 대분. 위험은 고객계획 대상 월(7~9월)만 평가한다.</p>
      </CardContent>
    </Card>
  );
}

function WorkSummary() {
  const view = useSc01(selectView);
  if (!view) return null;
  const open = view.issues.filter((i) => i.status === "OPEN");
  const tasks = view.tasks;
  const count = (pred: (t: (typeof tasks)[number]) => boolean) => tasks.filter(pred).length;

  return (
    <div className="grid gap-4 [&>*]:min-w-0 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>미해결 이슈 {open.length}건</CardTitle>
          <CardDescription>위험 건수는 고유 이슈로 센다 — 월별 평가 행 수와 다르다.</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="divide-y text-sm">
            {open.map((i) => (
              <li key={i.issue_id} className="flex items-center justify-between gap-3 py-2">
                <span>
                  <span className="font-mono text-xs">{i.issue_id}</span>{" "}
                  {modelLabel(i.model_id)} {Number(i.period.slice(5, 7))}월 고객 물량
                </span>
                <RiskTag risk={i.risk} />
              </li>
            ))}
          </ul>
          <Link href="/handoff" className="mt-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            이슈·인계 현황 <ArrowRight aria-hidden className="size-3" />
          </Link>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>업무 {tasks.length}건</CardTitle>
          <CardDescription>
            인수 전 {count((t) => t.status === "ASSIGNED")} · 진행 {count((t) => t.status === "IN_PROGRESS")} · 완료{" "}
            {count((t) => t.status === "COMPLETED")} · 기한 초과 {count((t) => t.overdue)}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {tasks.length === 0 ? (
            <p className="text-sm text-muted-foreground">아직 배정된 업무가 없다.</p>
          ) : (
            <ul className="divide-y text-sm">
              {tasks.map((t) => (
                <li key={t.task_id} className="flex items-center justify-between gap-3 py-2">
                  <span>{TASK_TYPE_LABEL[t.type]} · {t.assignedName ?? "배정 필요"}</span>
                  <span className="text-xs text-muted-foreground">{TASK_STATUS_LABEL[t.status]}</span>
                </li>
              ))}
            </ul>
          )}
          <Link href="/tasks" className="mt-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            검토·승인 업무 <ArrowRight aria-hidden className="size-3" />
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
