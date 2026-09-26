import { ArrowDown, ArrowUp, Cpu, FileText, Minus } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  EXECUTION_CATEGORY_LABEL,
  PROVENANCE_LABEL,
  improvementOf,
  meetsTarget,
  type ExecutionCategory,
  type ExecutionMetric,
} from "@/lib/types/execution-performance";

/** 소수 자리는 지표마다 다르다 — 0.4시간과 67%를 같은 규칙으로 찍으면 어느 쪽이든 어색하다. */
function formatValue(value: number, unit: string): string {
  const rounded = Number.isInteger(value) ? value : Number(value.toFixed(1));
  return `${rounded}${unit}`;
}

/**
 * 개선량 한 줄.
 *
 * 화살표 방향은 **값의 증감**이 아니라 **좋아졌는지**를 가리킨다 — 소요시간이 줄어든 것은
 * 위로 향한 개선이다. 숫자는 원래 방향(줄었으면 감소)으로 적어 오해를 막는다.
 */
function Improvement({ metric }: { metric: ExecutionMetric }) {
  const improvement = improvementOf(metric);
  const raw = metric.current - metric.previous;

  if (improvement === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
        <Minus aria-hidden className="size-3" />
        직전 주기와 동일
      </span>
    );
  }

  const Icon = improvement > 0 ? ArrowUp : ArrowDown;
  const color = improvement > 0 ? "var(--viz-delta-good)" : "var(--viz-status-critical)";

  return (
    <span
      className="inline-flex items-center gap-1 text-[11px] font-medium tabular-nums"
      style={{ color }}
    >
      <Icon aria-hidden className="size-3 shrink-0" />
      {raw > 0 ? "+" : ""}
      {formatValue(raw, metric.unit)}
      <span className="font-normal text-muted-foreground">
        직전 {formatValue(metric.previous, metric.unit)}
      </span>
    </span>
  );
}

function ProvenanceBadge({ metric }: { metric: ExecutionMetric }) {
  const isSystem = metric.provenance === "system";
  const Icon = isSystem ? Cpu : FileText;
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] text-muted-foreground"
      title={
        isSystem
          ? "실제 데이터에서 계산한 값이다."
          : "시스템이 관측할 수 없어 시나리오에서 설정한 값이다."
      }
    >
      <Icon aria-hidden className="size-2.5" />
      {PROVENANCE_LABEL[metric.provenance]}
    </span>
  );
}

const CATEGORY_ORDER: ExecutionCategory[] = ["speed", "accuracy", "execution"];

/**
 * 경영 수행 성과 패널.
 *
 * 사업 성과(손익·품질·재고)와 **별도 관점**으로 둔다. 둘을 섞으면 "손익은 나빠졌지만
 * 대응은 빨라졌다"를 말할 수 없다(기획안 2.3).
 *
 * 지표마다 출처를 표시한다 — 어디까지가 실제로 돌아간 결과이고 어디부터가 시나리오
 * 설정값인지 구분되지 않으면 데모의 주장을 검증할 수 없다.
 */
export function ExecutionPerformancePanel({ metrics }: { metrics: ExecutionMetric[] }) {
  const systemCount = metrics.filter((m) => m.provenance === "system").length;

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground tabular-nums">
        지표 {metrics.length}개 중{" "}
        <span className="font-medium text-foreground">{systemCount}개는 시스템 산출값</span>
        , 나머지는 시나리오 설정값이다.
      </p>

      {CATEGORY_ORDER.map((category) => {
        const group = metrics.filter((m) => m.category === category);
        if (group.length === 0) return null;

        return (
          <section key={category} className="space-y-2">
            <h4 className="text-xs font-medium text-muted-foreground">
              {EXECUTION_CATEGORY_LABEL[category]}
            </h4>
            <ul className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
              {group.map((metric) => {
                const hit = meetsTarget(metric);
                return (
                  <li key={metric.id} className="rounded-lg border p-3">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-xs text-foreground">{metric.label}</span>
                      <ProvenanceBadge metric={metric} />
                    </div>

                    <p className="mt-1.5 text-xl leading-none font-semibold text-foreground">
                      {formatValue(metric.current, metric.unit)}
                    </p>

                    <div className="mt-1.5">
                      <Improvement metric={metric} />
                    </div>

                    {metric.target !== undefined ? (
                      <p
                        className={cn(
                          "mt-1 text-[10px] tabular-nums",
                          hit ? "text-muted-foreground" : "text-foreground",
                        )}
                      >
                        목표 {formatValue(metric.target, metric.unit)}
                        {hit ? " 달성" : " 미달"}
                      </p>
                    ) : null}

                    <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">
                      {metric.definition}
                    </p>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
