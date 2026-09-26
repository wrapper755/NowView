import { Badge } from "@/components/ui/badge";
import { SeverityTag, severityColor } from "@/components/cockpit/severity";
import {
  MANAGEMENT_STAGE_LABEL,
  type RiskSignal,
  type Severity,
} from "@/lib/types/cockpit";

/** 심각도 내림차순. 경영진이 위에서부터 읽으면 되도록 고정 정렬한다. */
const SEVERITY_RANK: Record<Severity, number> = {
  critical: 0,
  serious: 1,
  warning: 2,
  good: 3,
};

/**
 * 감지된 리스크 신호 목록 (루프 1단계 Risk Sensing 산출물).
 *
 * KRI 현재값과 감지 임계치를 나란히 놓아 "왜 걸렸는지"가 목록에서 바로 읽히게 한다.
 */
export function RiskSignalList({ risks }: { risks: RiskSignal[] }) {
  const sorted = [...risks].sort(
    (a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity],
  );

  return (
    <ul className="viz-root divide-y">
      {sorted.map((risk) => (
        <li key={risk.id} className="flex gap-3 py-3.5 first:pt-0 last:pb-0">
          {/* 심각도를 색 하나로만 말하지 않도록 왼쪽 띠 + SeverityTag를 함께 쓴다. */}
          <span
            aria-hidden
            className="mt-0.5 w-0.5 shrink-0 rounded-full"
            style={{ backgroundColor: severityColor(risk.severity) }}
          />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
              <SeverityTag severity={risk.severity} />
              <span className="text-sm font-medium text-foreground">{risk.title}</span>
            </div>

            <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
              {risk.detail}
            </p>

            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs">
              <span className="text-muted-foreground tabular-nums">
                {risk.kri.label}{" "}
                <span className="font-medium text-foreground">{risk.kri.value}</span>
                <span className="mx-1 text-muted-foreground/60">/</span>
                임계 {risk.kri.threshold}
              </span>
              <Badge variant="secondary" className="font-normal">
                {MANAGEMENT_STAGE_LABEL[risk.stage]}
              </Badge>
              <span className="text-muted-foreground">
                {risk.division} · {risk.owner}
              </span>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
