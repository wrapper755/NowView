import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DivisionCard } from "@/components/cockpit/division-card";
import {
  FrameworkChainTable,
  FrameworkSummaryLine,
} from "@/components/cockpit/framework-chain-table";
import { OpBridgeChart } from "@/components/cockpit/op-bridge-chart";
import {
  ExecutionPerformanceSection,
  RiskSignalSection,
} from "@/components/cockpit/live-sections";
import { StatTile } from "@/components/shared/stat-tile";
import { managementFramework } from "@/lib/mock-data/framework";
import { nextAutomotive } from "@/lib/mock-data/next-automotive";
import { executionMetrics } from "@/services/execution-performance";
import { buildChains, summarize } from "@/services/framework";
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
  const observedCount = company.risks.filter((r) => r.origin === "observed").length;
  const leadingCount = company.risks.length - observedCount;
  // 끊어진 연결(존재하지 않는 KPI·통제 참조)이 있으면 여기서 즉시 터진다.
  const frameworkChains = buildChains(managementFramework);
  const frameworkSummary = summarize(managementFramework);
  // 시스템 산출값 4종은 Agent 기록·과제·백테스트에서 계산된다.
  const executionPerformance = executionMetrics();

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
            경영 수행 성과 — 속도 · 정확성 · 실행력
          </CardTitle>
          <CardDescription>
            위쪽이 사업 성과(손익·품질·재고)라면 이것은 그 결과를 만드는 경영 활동 자체의
            품질이다. 둘을 섞으면 &ldquo;손익은 나빠졌지만 대응은 빨라졌다&rdquo;를 말할 수
            없다.
          </CardDescription>
        </CardHeader>
        <CardContent className="viz-root">
          {/* 엔진이 돌았으면 Agent 소요시간이 실측값으로 바뀐다. 페이지는 서버
              컴포넌트로 남고 이 조각만 클라이언트에서 채운다 — 정적 렌더를 잃지 않는다. */}
          <ExecutionPerformanceSection fallback={executionPerformance} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Management Framework — KPI · KRI · Control 연결
          </CardTitle>
          <CardDescription>
            무엇을 보고 어떻게 판단할지에 대한 공통 기준이다. 지표를 나열하는 것이 아니라
            연결이 어디서 끊기는지를 본다 — 임계치를 벗어났는데 예방 통제가 없거나 통제가
            예외·미수행이면 그 자리가 구멍이다.
          </CardDescription>
        </CardHeader>
        <CardContent className="viz-root space-y-3">
          <FrameworkSummaryLine {...frameworkSummary} />
          <FrameworkChainTable chains={frameworkChains} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Risk Sensing — 감지된 신호 {company.risks.length}건
          </CardTitle>
          <CardDescription>
            {criticalCount > 0
              ? `심각 ${criticalCount}건은 Management Review 안건으로 에스컬레이션 대상이다. `
              : "현재 심각 등급 신호는 없다. "}
            현재 실적에서 관측된 편차 {observedCount}건, 아직 실적에 나타나지 않은 선행 위험{" "}
            {leadingCount}건이며, 선행 위험은 딛고 선 가정을 함께 표시한다.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {/* 엔진 인스턴스가 있는 안건은 Mock에 적힌 단계가 아니라 실제 진행 지점을 쓴다. */}
          <RiskSignalSection risks={company.risks} />
        </CardContent>
      </Card>

      <p className="pb-2 text-xs text-muted-foreground">
        본 화면의 수치는 CLAUDE.md 2장 가상 고객사 스펙에 기반한 Mock 데이터다. 실제 재무
        데이터가 아니다.
      </p>
    </main>
  );
}
