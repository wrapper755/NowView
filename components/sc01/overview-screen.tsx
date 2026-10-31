"use client";

import { CompanyLink as Link } from "@/components/shared/company-link";
import { useState } from "react";
import { ArrowRight } from "lucide-react";

import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { ProfitTrendChart } from "@/components/sc01/profit-trend-chart";
import { Loading, RiskTag, ScreenHeader } from "@/components/sc01/bits";
import { useDashboard } from "@/components/sc01/use-dashboard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  formatKrw,
  formatKrwSigned,
  formatQty,
  formatRatio,
  formatWonExact,
  modelLabel,
} from "@/lib/sc01/format";
import type { Dashboard, Pnl } from "@/lib/sc01/types";
import { selectView, useSc01 } from "@/lib/store/sc01";

const PERIODS = ["연간", "Q1", "Q2", "Q3", "Q4", "7월", "8월", "9월"];
const VERSION_LABEL: Record<string, string> = { T01: "Target", F01: "승인 전망 F01", F02: "검토 전망 F02" };

/**
 * UI01 — A제품 경영 현황. **한 숫자가 화면을 이끈다**: 공장관리손익 전망과 목표 차이.
 *
 * * 첫 화면은 **승인 전망 F01**이다. 계산이 성공하기 전에는 검토 전망 F02를 내놓지 않는다(AT01).
 * * 공장관리손익은 전사 영업이익이 아니다 — 상시 표기한다(UI01 근거 정보).
 * * 목표 부족액(T − F02)과 이번 사건 영향(F02 − F01)을 나란히 둔다 — 섞으면 사건이
 *   목표 차이 전부를 만든 것처럼 읽힌다(AT07).
 * * 버전별 표·근거 정보는 접어 둔다 — 화면이 글자로 꽉 차 답답하다는 지적(CLAUDE.md 4.6).
 */
export function OverviewScreen() {
  const [period, setPeriod] = useState("연간");
  const [month, setMonth] = useState(7);
  const { dashboard, error } = useDashboard(period, month);

  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <ScreenHeader id="UI01" title="A제품 경영 현황" question="전체 성과와 전망은 어떠하며 무엇을 살펴봐야 하는가?" />

      {error ? <p className="text-sm">{error}</p> : null}
      {!dashboard ? (
        <Loading what="경영 현황" />
      ) : (
        <>
          <Hero dashboard={dashboard} period={period} setPeriod={setPeriod} />

          <Card>
            <CardHeader>
              <CardTitle>월별 공장관리손익</CardTitle>
              <Commentary block>
                <p className="text-[13px] text-muted-foreground">
                  연간·분기는 월 금액의 합이다 — 비율을 평균하지 않고 합산한 금액에서 다시 계산한다(CALC-04).
                </p>
              </Commentary>
            </CardHeader>
            <CardContent>
              <ProfitTrendChart dashboard={dashboard} />
            </CardContent>
          </Card>

          <div className="grid gap-6 [&>*]:min-w-0 lg:grid-cols-[2fr_1fr]">
            <ModelTable dashboard={dashboard} month={month} setMonth={setMonth} />
            <WorkSummary />
          </div>

          <Disclosure summary="근거 정보">
            <div className="space-y-1 text-xs text-muted-foreground">
              <p>
                실적 컷오프 {dashboard.asOf.actualCutoff} · 승인 전망 {dashboard.approved}
                {dashboard.review ? ` · 검토 전망 ${dashboard.review}(미승인)` : ""} · 원가 C01 · 경보 규칙 R01-v1
              </p>
              <p>회사 전체 매출 약 1조원은 배경이다. 이 화면의 수치는 A제품·울산공장 a~e모델 범위만이다.</p>
            </div>
          </Disclosure>
        </>
      )}
    </main>
  );
}

function Hero({
  dashboard,
  period,
  setPeriod,
}: {
  dashboard: Dashboard;
  period: string;
  setPeriod: (p: string) => void;
}) {
  const t = dashboard.totals.T01;
  const approved = dashboard.totals[dashboard.approved];
  const latestKey = dashboard.review ?? dashboard.approved;
  const latest = dashboard.totals[latestKey];
  const gap = Number(latest.mgmtProfit) - Number(t.mgmtProfit);
  const event = dashboard.review ? Number(latest.mgmtProfit) - Number(approved.mgmtProfit) : null;
  const short = gap < 0;

  return (
    <Card>
      <CardContent className="space-y-6">
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

        <div className="flex flex-wrap items-end justify-between gap-x-12 gap-y-6">
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              공장관리손익 {dashboard.period} · {VERSION_LABEL[latestKey]}
            </p>
            <p className="text-5xl leading-none font-semibold tabular-nums" title={formatWonExact(latest.mgmtProfit)}>
              {formatKrw(latest.mgmtProfit)}
            </p>
            <p className="text-sm">
              목표 {formatKrw(t.mgmtProfit)} 대비{" "}
              <span
                className="font-semibold tabular-nums"
                style={{ color: short ? "var(--viz-status-critical)" : "var(--viz-delta-good)" }}
                title={formatWonExact(gap)}
              >
                {formatKrwSigned(gap)}
              </span>
              {event !== null ? (
                <span className="text-muted-foreground">
                  {" "}
                  · 이번 사건 영향{" "}
                  <span className="font-medium text-foreground tabular-nums">{formatKrwSigned(event)}</span>
                </span>
              ) : null}
            </p>
          </div>

          <dl className="flex gap-10">
            <Stat label="매출" value={latest.revenue} />
            <Stat label="공헌이익" value={latest.cm} />
          </dl>
        </div>

        <p className="text-xs text-muted-foreground">
          공장관리손익 = 공헌이익 − 공장고정비. 전사 영업이익이 아니다.
          {event !== null ? " 사건 영향은 물량 변화만 반영한 초기 영향이다." : " 검토 전망은 비교 계산 뒤에 나온다."}
        </p>

        <Disclosure summary="버전별 자세히">
          <VersionTable dashboard={dashboard} />
        </Disclosure>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-xl font-semibold tabular-nums" title={formatWonExact(value)}>
        {formatKrw(value)}
      </dd>
    </div>
  );
}

function VersionTable({ dashboard }: { dashboard: Dashboard }) {
  const rows: { key: keyof Pnl; label: string }[] = [
    { key: "revenue", label: "매출" },
    { key: "cm", label: "공헌이익" },
    { key: "mgmtProfit", label: "공장관리손익" },
  ];
  return (
    <div className="overflow-x-auto">
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
              <th scope="row" className="py-2 pr-3 text-left font-normal">{r.label}</th>
              {dashboard.versions.map((v) => (
                <td key={v} className="py-2 pr-3 text-right tabular-nums" title={formatWonExact(dashboard.totals[v][r.key])}>
                  {formatKrw(dashboard.totals[v][r.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] text-muted-foreground">숫자에 마우스를 올리면 원 단위 값이 나온다.</p>
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
        {/* 월 버튼을 제목 밖에 둔다 — 섹션 탭이 제목 글자를 그대로 쓴다(4.10). */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>모델별 현황</CardTitle>
          <span className="flex gap-1">
            {[7, 8, 9].map((m) => (
              <button
                key={m}
                type="button"
                aria-pressed={m === month}
                onClick={() => setMonth(m)}
                className={
                  m === month
                    ? "rounded-md bg-muted px-2.5 py-1 text-xs font-medium"
                    : "rounded-md px-2.5 py-1 text-xs font-normal text-muted-foreground hover:text-foreground"
                }
              >
                {m}월
              </button>
            ))}
          </span>
        </div>
        <Commentary block>
          <p className="text-[13px] text-muted-foreground">
            공장 합계가 괜찮아도 모델 경보는 유지된다. 위험은 고객계획 대상 월(7~9월)만 평가한다.
          </p>
        </Commentary>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full min-w-[30rem] text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th scope="col" className="py-2 pr-3 font-medium">모델</th>
              <th scope="col" className="py-2 pr-3 text-right font-medium">목표</th>
              <th scope="col" className="py-2 pr-3 text-right font-medium">최신 전망</th>
              <th scope="col" className="py-2 pr-3 text-right font-medium">달성률</th>
              <th scope="col" className="py-2 font-medium">위험</th>
            </tr>
          </thead>
          <tbody>
            {dashboard.models.map((m) => (
              <tr key={m.modelId} className="border-b last:border-0">
                <th scope="row" className="py-2.5 pr-3 text-left font-normal">{modelLabel(m.modelId)}</th>
                <td className="py-2.5 pr-3 text-right tabular-nums text-muted-foreground">{formatQty(m.target)}</td>
                <td className="py-2.5 pr-3 text-right tabular-nums">
                  {formatQty(m.latest)}
                  {m.latest !== m.prior ? (
                    <span className="ml-1 text-xs text-muted-foreground">({formatQty(m.latest - m.prior)})</span>
                  ) : null}
                </td>
                <td className="py-2.5 pr-3 text-right tabular-nums">{formatRatio(m.achievement, 1)}</td>
                <td className="py-2.5">
                  <RiskTag risk={m.risk} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-[11px] text-muted-foreground">단위 대분. 괄호는 직전 승인 전망 대비 변화.</p>
      </CardContent>
    </Card>
  );
}

function WorkSummary() {
  const view = useSc01(selectView);
  if (!view) return null;
  const open = view.issues.filter((i) => i.status === "OPEN");
  const active = view.tasks.filter((t) => t.status !== "COMPLETED");
  const overdue = view.tasks.filter((t) => t.overdue).length;

  return (
    <Card>
      <CardHeader>
        <CardTitle>지금 챙길 것</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <Link href="/sc01/handoff" className="group block space-y-2">
          <p className="flex items-baseline justify-between">
            <span className="text-sm text-muted-foreground">미해결 이슈</span>
            <span className="text-3xl font-semibold tabular-nums">{open.length}</span>
          </p>
          <ul className="space-y-1">
            {open.map((i) => (
              <li key={i.issue_id} className="flex items-center justify-between text-sm">
                <span>
                  {modelLabel(i.model_id)} {Number(i.period.slice(5, 7))}월
                </span>
                <RiskTag risk={i.risk} />
              </li>
            ))}
          </ul>
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground group-hover:text-foreground">
            이슈·인계 <ArrowRight aria-hidden className="size-3" />
          </span>
        </Link>

        <Link href="/sc01/tasks" className="group block space-y-2 border-t pt-5">
          <p className="flex items-baseline justify-between">
            <span className="text-sm text-muted-foreground">진행 중 업무</span>
            <span className="text-3xl font-semibold tabular-nums">{active.length}</span>
          </p>
          {overdue > 0 ? (
            <p className="text-sm" style={{ color: "var(--viz-status-critical)" }}>기한 초과 {overdue}건</p>
          ) : null}
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground group-hover:text-foreground">
            업무 <ArrowRight aria-hidden className="size-3" />
          </span>
        </Link>
      </CardContent>
    </Card>
  );
}
