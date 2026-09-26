import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DivisionCard } from "@/components/cockpit/division-card";
import { OpBridgeChart } from "@/components/cockpit/op-bridge-chart";
import { RiskSignalList } from "@/components/cockpit/risk-signal-list";
import { StatTile } from "@/components/shared/stat-tile";
import { nextAutomotive } from "@/lib/mock-data/next-automotive";
import {
  formatEok,
  formatEokSigned,
  formatPercent,
  formatPpSigned,
} from "@/lib/format";
import { gapOf, marginOf } from "@/lib/types/cockpit";

export default function ExecutiveCockpitPage() {
  const company = nextAutomotive;
  const revenueGap = gapOf(company.revenue);
  const profitGap = gapOf(company.operatingProfit);
  const targetMargin = marginOf(company.revenue.target, company.operatingProfit.target);
  const forecastMargin = marginOf(
    company.revenue.forecast,
    company.operatingProfit.forecast,
  );
  const criticalCount = company.risks.filter((r) => r.severity === "critical").length;

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
      <header className="space-y-1">
        <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
          <h1 className="text-xl font-semibold">Executive Cockpit</h1>
          <span className="text-sm text-muted-foreground">
            {company.name} · {company.englishName}
          </span>
        </div>
        <p className="text-xs text-muted-foreground">{company.period}</p>
      </header>

      {/* Hero figure — 이 화면이 이끄는 단 하나의 숫자. 뷰당 1개만 둔다. */}
      <Card className="viz-root">
        <CardContent className="flex flex-wrap items-end justify-between gap-6">
          <div className="space-y-1.5">
            <p className="text-sm text-muted-foreground">
              영업이익 Gap <span className="text-xs">(Forecast − Target)</span>
            </p>
            <p className="text-5xl leading-none font-semibold text-foreground">
              {formatEokSigned(profitGap)}
            </p>
            <p className="text-xs text-muted-foreground">
              Target {formatEok(company.operatingProfit.target)}은 변경하지 않는다.
              차이는 Forecast에만 반영하고 잔여 Gap으로 명시한다.
            </p>
          </div>

          <dl className="grid grid-cols-2 gap-x-8 gap-y-3 sm:flex sm:items-end sm:gap-8">
            <StatTile
              label="영업이익 Forecast"
              value={formatEok(company.operatingProfit.forecast)}
              delta={{
                text: formatEokSigned(profitGap),
                direction: profitGap >= 0 ? "up" : "down",
                isGood: profitGap >= 0,
              }}
              caption={`Target ${formatEok(company.operatingProfit.target)}`}
            />
            <StatTile
              label="매출 Forecast"
              value={formatEok(company.revenue.forecast)}
              delta={{
                text: formatEokSigned(revenueGap),
                direction: revenueGap >= 0 ? "up" : "down",
                isGood: revenueGap >= 0,
              }}
              caption={`Target ${formatEok(company.revenue.target)}`}
            />
            <StatTile
              label="영업이익률 Forecast"
              value={formatPercent(forecastMargin)}
              delta={{
                text: formatPpSigned(forecastMargin - targetMargin),
                direction: forecastMargin >= targetMargin ? "up" : "down",
                isGood: forecastMargin >= targetMargin,
              }}
              caption={`Target ${formatPercent(targetMargin)}`}
            />
            <StatTile
              label="확정 Action 회수액"
              value={formatEok(company.committedActionRecovery)}
              caption={`잔여 Gap ${formatEok(Math.abs(profitGap))}`}
            />
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">영업이익 Target → Forecast 브릿지</CardTitle>
          <CardDescription>
            목표와 전망의 차이를 물량·단가·원가·수율·Action 요인으로 분해한다. 요인 합계는
            Gap {formatEokSigned(profitGap)}과 정확히 일치한다.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <OpBridgeChart bridge={company.bridge} />
        </CardContent>
      </Card>

      <section className="space-y-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-base font-semibold">사업부 듀얼 매트릭스</h2>
          <p className="text-xs text-muted-foreground">
            기존 사업과 신사업은 평가 기준이 다르므로 같은 축에 합산하지 않고 나란히 본다.
          </p>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          {company.divisions.map((division) => (
            <DivisionCard key={division.id} division={division} />
          ))}
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Risk Sensing — 감지된 신호 {company.risks.length}건
          </CardTitle>
          <CardDescription>
            {criticalCount > 0
              ? `심각 ${criticalCount}건은 Management Review 안건으로 에스컬레이션 대상이다.`
              : "현재 심각 등급 신호는 없다."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <RiskSignalList risks={company.risks} />
        </CardContent>
      </Card>

      <p className="pb-2 text-xs text-muted-foreground">
        본 화면의 수치는 CLAUDE.md 2장 가상 고객사 스펙에 기반한 Mock 데이터다. 실제 재무
        데이터가 아니다.
      </p>
    </main>
  );
}
