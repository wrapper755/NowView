import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  OctagonAlert,
  type LucideIcon,
} from "lucide-react";

import { SEVERITY_LABEL, type Severity } from "@/lib/types/cockpit";

/**
 * 상태 등급 표현.
 *
 * 색은 절대 단독으로 의미를 전달하지 않는다 — 아이콘과 한글 라벨이 항상 함께 나간다.
 * 라이트 서피스에서 warning/serious는 대비 3:1 미만이므로(팔레트 규정) 이 조합이 완화 수단이다.
 */
const SEVERITY_ICON: Record<Severity, LucideIcon> = {
  good: CheckCircle2,
  warning: CircleAlert,
  serious: AlertTriangle,
  critical: OctagonAlert,
};

const SEVERITY_COLOR_VAR: Record<Severity, string> = {
  good: "var(--viz-status-good)",
  warning: "var(--viz-status-warning)",
  serious: "var(--viz-status-serious)",
  critical: "var(--viz-status-critical)",
};

export function severityColor(severity: Severity): string {
  return SEVERITY_COLOR_VAR[severity];
}

/** 아이콘 + 한글 라벨 한 쌍. 텍스트는 상태색이 아닌 텍스트 토큰을 쓴다. */
export function SeverityTag({ severity }: { severity: Severity }) {
  const Icon = SEVERITY_ICON[severity];
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-foreground">
      <Icon
        aria-hidden
        className="size-3.5 shrink-0"
        style={{ color: severityColor(severity) }}
      />
      {SEVERITY_LABEL[severity]}
    </span>
  );
}

/**
 * 목표 대비 달성 정도를 상태 등급으로 환산한다.
 * `higherIsBetter=false`(리드타임 등)면 비율을 역수로 뒤집어 같은 임계값을 쓴다.
 */
export function metricSeverity(
  value: number,
  target: number,
  higherIsBetter: boolean,
): Severity {
  const ratio = higherIsBetter ? value / target : target / value;
  if (ratio >= 1) return "good";
  if (ratio >= 0.95) return "warning";
  if (ratio >= 0.85) return "serious";
  return "critical";
}
