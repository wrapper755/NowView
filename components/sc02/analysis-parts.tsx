"use client";

import { AlertTriangle } from "lucide-react";

import { RiskTag } from "@/components/sc01/bits";
import { Won } from "@/components/sc02/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock, formatQty, formatRatio, modelLabel } from "@/lib/sc01/format";
import { formatPeriod, KIND_LABEL } from "@/lib/sc02/format";
import type { Analysis, PeriodPnl, Run } from "@/lib/sc02/types";

/**
 * U22 분석 표시 조각 — 숫자는 전부 엔진 규칙 계산이다(CALC-21). 화면은 단위만 바꾼다.
 *
 * * **구매 증가와 손익 영향을 가른다**(U22-02) — 이 데모는 시차·재고 0이라 절대값이 같을 뿐이다(CALC-24).
 * * 당해연도 잔여기간과 향후 12개월은 따로 보이고 **더하지 않는다**(DEC24).
 * * 위험 등급과 대표 승인선은 다른 칸이다 — 승인선은 금액 기준(AUTH02-v1)이 정한다.
 */

export function RunMeta({ run }: { run: Run }) {
  const r = run.result;
  return (
    <p className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
      <span>
        <span className="font-mono">{run.run_id}</span> · {KIND_LABEL[run.kind]} {r.new_price ? `${Number(r.new_price).toLocaleString("ko-KR")}원` : "단가 없음"}
      </span>
      <span>적용일 {r.effective_date}</span>
      <span>
        물량 {r.versions.quantity} · 원가 {r.versions.cost} · 고정비 {r.versions.fixed} · 위험 {r.versions.rule} · 권한{" "}
        {r.versions.authority}
      </span>
      <span>계산 {formatClock(run.at)}</span>
      {run.is_stale ? <span className="font-medium text-foreground">이전 결과 — 입력이 바뀌었다</span> : null}
    </p>
  );
}

export function Problems({ analysis }: { analysis: Analysis }) {
  if (analysis.problems.length === 0) return null;
  return (
    <div role="alert" className="space-y-1 rounded-md border px-3 py-2 text-xs">
      <p className="flex items-center gap-1.5 font-medium">
        <AlertTriangle aria-hidden className="size-3.5" style={{ color: "var(--viz-status-serious)" }} />
        {analysis.computable ? "확인할 자료" : "분석 미산출 — 상신할 수 없다"}
      </p>
      <ul className="space-y-0.5">
        {analysis.problems.slice(0, 6).map((p) => (
          <li key={`${p.code}-${p.field}`}>
            <span className="font-mono">{p.code}</span> {p.message} — <span className="text-muted-foreground">{p.action}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const CEO_LABEL = { true: "대표 승인 대상", false: "대표 비대상" } as const;

/** 구매 영향 · 손익 영향 · 위험·승인 — U22 중앙 카드 셋. */
export function AnalysisCards({ run }: { run: Run }) {
  const a = run.result;
  const year = a.periods.find((p) => p.kind === "year");
  const next12 = a.periods.find((p) => p.kind === "next12");
  return (
    <div className="grid gap-4 [&>*]:min-w-0 md:grid-cols-3">
      <Card>
        <CardHeader>
          <CardTitle>구매 영향</CardTitle>
          <CardDescription>부품 구매수량 × (선택 단가 − 기존 단가). 공급사 요청건 합계, VAT 제외.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="space-y-3 text-sm">
            {[a.remaining, a.next12].map((p, i) => (
              <div key={p.from + p.to}>
                <dt className="text-xs text-muted-foreground">
                  {i === 0 ? "당해연도 잔여" : "적용일부터 12개월"} ({formatPeriod(p.from, p.to)})
                </dt>
                <dd className="text-xl font-semibold">
                  <Won value={p.increase} />
                </dd>
                <dd className="text-xs text-muted-foreground">부품 {formatQty(p.purchase_qty)}개</dd>
              </div>
            ))}
          </dl>
          <Commentary block>
            <p className="mt-2 text-xs text-muted-foreground">두 기간은 겹친다 — 더하지 않는다(DEC24).</p>
          </Commentary>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>손익 영향</CardTitle>
          <CardDescription>F02 물량에 단가 차이를 적용한 공헌이익 변화. 공장관리손익은 전사 영업이익이 아니다.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-xs text-muted-foreground">2027 단가 추가 영향</dt>
              <dd className="text-xl font-semibold">
                <Won value={year?.computable ? year.cost_effect : null} />
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">2027 통합 관리손익 · Target 대비 부족</dt>
              <dd>
                <Won value={year?.computable ? year.profit_combined : null} /> ·{" "}
                <Won value={year?.computable ? year.target_gap : null} />
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">향후 12개월 통합 관리손익</dt>
              <dd>
                <Won value={next12?.computable ? next12.profit_combined : null} />{" "}
                <span className="text-xs text-muted-foreground">Target 미설정 — 차이 미산출</span>
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>위험 · 승인선</CardTitle>
          <CardDescription>위험(R02-v1)과 승인권한(AUTH02-v1)은 따로 판정한다.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-sm">
            <dt className="text-xs text-muted-foreground">인상률 {formatRatio(a.rate)}</dt>
            <dd>
              <RiskTag risk={a.rate_risk} />
            </dd>
            <dt className="text-xs text-muted-foreground">12개월 구매 증가</dt>
            <dd>
              <RiskTag risk={a.amount_risk} />
            </dd>
            <dt className="text-xs text-muted-foreground">종합(높은 쪽)</dt>
            <dd>
              <RiskTag risk={a.risk} />
            </dd>
            <dt className="text-xs text-muted-foreground">예상 승인선</dt>
            <dd className="text-xs font-medium">
              {a.ceo_required === null ? "판정 보류 — 12개월 금액 미산출" : CEO_LABEL[`${a.ceo_required}`]}
            </dd>
          </dl>
          <Commentary block>
            <p className="mt-2 text-xs text-muted-foreground">
              승인선은 최종 기안으로 확정한다 — 여기 값은 미리보기다. 위험이 중요여도 금액 미만이면 대표를 더하지 않는다.
            </p>
          </Commentary>
        </CardContent>
      </Card>
    </div>
  );
}

/** 요청안 대비 부담 감소(M25) — 같은 비교기간. 기존 대비 원가 상승은 남는다. */
export function ComparisonNote({ analysis }: { analysis: Analysis }) {
  const c = analysis.comparison;
  if (!c || analysis.kind === "REQUEST") return null;
  return (
    <p className="rounded-md border px-3 py-2 text-sm">
      요청안 대비 12개월 부담 감소 <Won value={c.reduction} /> ({formatPeriod(c.from, c.to)} 같은 기간) — 기존 대비로는{" "}
      <Won value={c.increase} /> 오른다. 감소는 원가 절감이 아니다.
      {Number(c.deferral_effect) !== 0 ? (
        <span className="block text-xs text-muted-foreground">
          가격 효과 <Won value={c.price_effect} /> · 적용일 연기 효과 <Won value={c.deferral_effect} /> (따로 설명한다)
        </span>
      ) : null}
    </p>
  );
}

/** 통합 손익 표 — 기준(F01+C01) → 물량 후(F02+C01) → 단가 후(F02+선택안). 표가 원천이다(차트 없음). */
export function BridgeTable({ periods, kinds }: { periods: PeriodPnl[]; kinds: PeriodPnl["kind"][] }) {
  const rows = periods.filter((p) => kinds.includes(p.kind));
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[46rem] text-sm" aria-label="장면 1·2 통합 손익 연결">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th scope="col" className="py-2 pr-3 font-medium">기간</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">기준 손익 F01</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">장면 1 물량</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">장면 2 단가</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">통합 손익</th>
            <th scope="col" className="py-2 text-right font-medium">Target 대비 부족</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.label} className="border-b">
              <th scope="row" className="py-2 pr-3 text-left font-normal">
                {p.label}
                <span className="block text-[11px] text-muted-foreground">{formatPeriod(p.from, p.to)}</span>
              </th>
              {p.computable ? (
                <>
                  <td className="py-2 pr-3 text-right"><Won value={p.profit_f01} /></td>
                  <td className="py-2 pr-3 text-right"><Won value={p.volume_effect} signed /></td>
                  <td className="py-2 pr-3 text-right"><Won value={p.cost_effect} signed /></td>
                  <td className="py-2 pr-3 text-right font-medium"><Won value={p.profit_combined} /></td>
                  <td className="py-2 text-right">
                    {p.target_gap === null ? <span className="text-xs text-muted-foreground">Target 미설정</span> : <Won value={p.target_gap} />}
                  </td>
                </>
              ) : (
                <td colSpan={5} className="py-2 text-xs text-muted-foreground">미산출 — {p.reason}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** 모델별 월 상세 — a~e 전체. c~e 직접 단가영향 0을 그대로 보인다(U22-02 「배경 모델」). */
export function MonthlyTable({ analysis }: { analysis: Analysis }) {
  const months = [...new Set(analysis.monthly.map((m) => m.period))];
  const models = [...new Set(analysis.monthly.map((m) => m.model_id))];
  if (months.length === 0) return null;
  return (
    <Disclosure summary={`모델별 월 상세 (${months.length}개월 × ${models.length}모델 — 부품 구매수량·단가 영향)`}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[48rem] text-xs" aria-label="모델별 월 부품 구매수량과 단가 영향">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th scope="col" className="py-1.5 pr-2 font-medium">월</th>
              {models.map((m) => (
                <th key={m} scope="col" className="py-1.5 pr-2 text-right font-medium">{modelLabel(m)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {months.map((p) => (
              <tr key={p} className="border-b">
                <th scope="row" className="py-1.5 pr-2 text-left font-normal">
                  {p.slice(0, 7)}
                  {analysis.monthly.find((m) => m.period === p)?.assumed ? (
                    <span className="ml-1 rounded border px-1 text-[10px] text-muted-foreground">내부가정</span>
                  ) : null}
                </th>
                {models.map((model) => {
                  const m = analysis.monthly.find((x) => x.period === p && x.model_id === model);
                  return (
                    <td key={model} className="py-1.5 pr-2 text-right tabular-nums">
                      {m?.f02 === null ? (
                        <span title="물량 누락 — 0이 아니다">누락</span>
                      ) : (
                        <>
                          {formatQty(m?.part_qty)}개
                          <span className="block text-muted-foreground">
                            <Won value={m?.cost ?? null} />
                          </span>
                        </>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Disclosure>
  );
}

export function Assumptions({ analysis }: { analysis: Analysis }) {
  return (
    <ul className="space-y-0.5 text-xs text-muted-foreground">
      {Object.entries(analysis.assumptions).map(([k, v]) => (
        <li key={k}>· {v}</li>
      ))}
    </ul>
  );
}
