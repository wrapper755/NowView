import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { DeltaLine } from "@/components/shared/stat-tile";
import { SeverityTag, metricSeverity, severityColor } from "@/components/shared/severity";
import {
  formatEok,
  formatEokSigned,
  formatPercent,
  formatPpSigned,
} from "@/lib/format";
import { gapOf, marginOf, type Division, type OperatingMetric } from "@/lib/types/cockpit";

/** 사업부별 계열색. 엔티티에 고정 배정하며, 목록 순서나 순위에 따라 바뀌지 않는다. */
const DIVISION_COLOR: Record<Division["kind"], string> = {
  legacy: "var(--viz-series-1)",
  growth: "var(--viz-series-2)",
};

const DIVISION_KIND_LABEL: Record<Division["kind"], string> = {
  legacy: "기존 사업",
  growth: "신사업",
};

/**
 * 듀얼 매트릭스 카드 — 기존 사업과 신사업을 같은 축으로 나란히 본다.
 *
 * 색은 사업부 식별(categorical)용이고, 지표의 좋음/나쁨은 상태 팔레트가 따로 담당한다.
 * 두 역할을 한 색에 겹쳐 싣지 않는다.
 */
export function DivisionCard({ division }: { division: Division }) {
  const revenueGap = gapOf(division.revenue);
  const profitGap = gapOf(division.operatingProfit);
  const targetMargin = marginOf(division.revenue.target, division.operatingProfit.target);
  const forecastMargin = marginOf(
    division.revenue.forecast,
    division.operatingProfit.forecast,
  );

  return (
    <Card className="viz-root">
      <CardHeader>
        <div className="flex items-start gap-2.5">
          <span
            aria-hidden
            className="mt-1 h-8 w-1 shrink-0 rounded-full"
            style={{ backgroundColor: DIVISION_COLOR[division.kind] }}
          />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-base font-semibold">{division.name}</h3>
              <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                {DIVISION_KIND_LABEL[division.kind]} · 매출 비중 {division.revenueShare}%
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{division.tagline}</p>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        <dl className="grid grid-cols-3 gap-3">
          <FinancialCell
            term="매출"
            target={formatEok(division.revenue.target)}
            forecast={formatEok(division.revenue.forecast)}
            gap={formatEokSigned(revenueGap)}
            gapIsGood={revenueGap >= 0}
          />
          <FinancialCell
            term="영업이익"
            target={formatEok(division.operatingProfit.target)}
            forecast={formatEok(division.operatingProfit.forecast)}
            gap={formatEokSigned(profitGap)}
            gapIsGood={profitGap >= 0}
          />
          <FinancialCell
            term="영업이익률"
            target={formatPercent(targetMargin)}
            forecast={formatPercent(forecastMargin)}
            gap={formatPpSigned(forecastMargin - targetMargin)}
            gapIsGood={forecastMargin >= targetMargin}
          />
        </dl>

        <Separator />

        <div className="space-y-3.5">
          <h4 className="text-xs font-medium text-muted-foreground">운영 선행지표</h4>
          {division.metrics.map((metric) => (
            <MetricMeter key={metric.id} metric={metric} />
          ))}
        </div>

        <Separator />

        <div>
          <h4 className="text-xs font-medium text-muted-foreground">핵심 고민</h4>
          <ul className="mt-2 space-y-1.5">
            {division.concerns.map((concern) => (
              <li
                key={concern}
                className="flex gap-2 text-xs leading-relaxed text-foreground"
              >
                <span aria-hidden className="text-muted-foreground">
                  ·
                </span>
                {concern}
              </li>
            ))}
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}

function FinancialCell({
  term,
  target,
  forecast,
  gap,
  gapIsGood,
}: {
  term: string;
  target: string;
  forecast: string;
  gap: string;
  gapIsGood: boolean;
}) {
  return (
    <div className="space-y-1">
      <dt className="text-xs text-muted-foreground">{term}</dt>
      <dd className="space-y-1">
        <span className="block text-lg leading-none font-semibold tabular-nums">
          {forecast}
        </span>
        <span className="block text-xs text-muted-foreground tabular-nums">
          Target {target}
        </span>
        <DeltaLine
          text={gap}
          direction={gap.startsWith("+") ? "up" : gap.startsWith("-") ? "down" : "flat"}
          isGood={gapIsGood}
        />
      </dd>
    </div>
  );
}

/**
 * 미터 — 목표 대비 달성 비율.
 *
 * 채움은 상태 등급색, 트랙은 같은 램프의 밝은 스텝을 쓴다(파랑 위 파랑).
 * 100%를 넘는 경우에도 막대는 100%에서 멈추고 수치가 초과를 말한다.
 */
function MetricMeter({ metric }: { metric: OperatingMetric }) {
  const severity = metricSeverity(metric.value, metric.target, metric.higherIsBetter);
  const ratio = metric.higherIsBetter
    ? metric.value / metric.target
    : metric.target / metric.value;
  const fillPercent = Math.min(100, Math.max(0, ratio * 100));

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs text-foreground">{metric.label}</span>
        <span className="text-xs text-muted-foreground tabular-nums">
          <span className="font-medium text-foreground">
            {metric.value}
            {metric.unit}
          </span>
          {" / 목표 "}
          {metric.target}
          {metric.unit}
        </span>
      </div>
      <div className="flex items-center gap-2.5">
        <div
          className="h-1.5 flex-1 overflow-hidden rounded-full"
          style={{ backgroundColor: "var(--viz-track)" }}
          role="meter"
          aria-valuenow={metric.value}
          aria-valuemin={0}
          aria-valuemax={metric.target}
          aria-label={`${metric.label} ${metric.value}${metric.unit}, 목표 ${metric.target}${metric.unit}`}
        >
          <div
            className="h-full rounded-full"
            style={{
              width: `${fillPercent}%`,
              backgroundColor: severityColor(severity),
            }}
          />
        </div>
        <SeverityTag severity={severity} />
      </div>
    </div>
  );
}
