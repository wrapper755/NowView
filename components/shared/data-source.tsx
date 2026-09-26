import {
  CircleAlert,
  CircleCheck,
  CircleHelp,
  Clock,
  HelpCircle,
  type LucideIcon,
} from "lucide-react";

import {
  CONFIDENCE_LABEL,
  DATA_QUALITY_LABEL,
  incompleteSources,
  type AgentEscalation,
  type Confidence,
  type DataQuality,
  type DataSource,
} from "@/lib/types/agent";

const QUALITY_ICON: Record<DataQuality, LucideIcon> = {
  complete: CircleCheck,
  partial: CircleAlert,
  stale: Clock,
  estimated: CircleHelp,
};

/**
 * 데이터 품질 색.
 *
 * `complete`만 문제없음이고 나머지는 결론을 그만큼 덜 믿어야 한다는 신호다.
 * 다만 결손이 곧 오류는 아니므로 위험(critical)이 아니라 주의(warning) 계열을 쓴다.
 */
const QUALITY_COLOR: Record<DataQuality, string> = {
  complete: "var(--viz-status-good)",
  partial: "var(--viz-status-serious)",
  stale: "var(--viz-status-warning)",
  estimated: "var(--viz-status-warning)",
};

const CONFIDENCE_COLOR: Record<Confidence, string> = {
  high: "var(--viz-status-good)",
  medium: "var(--viz-status-warning)",
  low: "var(--viz-status-critical)",
};

/** 소스 하나. 불완전하면 무엇이 문제인지 툴팁으로 붙인다. */
export function DataSourceChip({ source }: { source: DataSource }) {
  const Icon = QUALITY_ICON[source.quality];
  return (
    <span
      className="inline-flex max-w-full items-center gap-1 rounded border px-1.5 py-0.5 text-[10px]"
      title={source.caveat ?? DATA_QUALITY_LABEL[source.quality]}
    >
      <Icon
        aria-hidden
        className="size-2.5 shrink-0"
        style={{ color: QUALITY_COLOR[source.quality] }}
      />
      <span className="truncate text-muted-foreground">{source.name}</span>
      {source.quality !== "complete" ? (
        <span className="shrink-0 text-foreground">
          {DATA_QUALITY_LABEL[source.quality]}
        </span>
      ) : null}
    </span>
  );
}

/**
 * 소스 목록 + 불완전한 것들의 구체 내용.
 *
 * 툴팁에만 넣지 않는다 — 데이터가 어떻게 불완전한지는 결론을 읽을 때 같이 보여야 하는
 * 정보이지, 마우스를 올려야 알 수 있는 부가 정보가 아니다.
 */
export function DataSourceList({ sources }: { sources: DataSource[] }) {
  const incomplete = incompleteSources(sources);

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap gap-1">
        {sources.map((source) => (
          <DataSourceChip key={source.name} source={source} />
        ))}
      </div>
      {incomplete.map((source) => (
        <p
          key={source.name}
          className="text-[10px] leading-relaxed text-muted-foreground"
        >
          <span className="text-foreground">{source.name}</span> {source.caveat}
        </p>
      ))}
    </div>
  );
}

/** 산출물 신뢰도 배지. `high`가 아니면 이유를 함께 보여 준다. */
export function ConfidenceTag({
  confidence,
  note,
}: {
  confidence: Confidence;
  note?: string;
}) {
  return (
    <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
      <span
        aria-hidden
        className="size-1.5 rounded-full"
        style={{ backgroundColor: CONFIDENCE_COLOR[confidence] }}
      />
      신뢰도 <span className="text-foreground">{CONFIDENCE_LABEL[confidence]}</span>
      {note ? <span className="text-muted-foreground">— {note}</span> : null}
    </span>
  );
}

/**
 * Agent가 사람에게 넘긴 질문.
 *
 * 정보가 부족할 때 Agent는 추측하지 않고 묻는다. 답을 받지 못한 채 진행할 때 어떤 가정
 * 위에 서게 되는지(`ifUnanswered`)를 함께 적어, 나중에 결론이 틀렸을 때 어디서 갈렸는지
 * 되짚을 수 있게 한다.
 */
export function EscalationCard({ escalation }: { escalation: AgentEscalation }) {
  return (
    <li className="rounded-lg border p-3">
      <div className="flex items-start gap-2">
        <HelpCircle
          aria-hidden
          className="mt-0.5 size-3.5 shrink-0"
          style={{ color: "var(--viz-status-warning)" }}
        />
        <div className="min-w-0 space-y-1.5">
          <p className="text-xs font-medium text-foreground">{escalation.question}</p>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            <span className="text-foreground">Agent가 답할 수 없는 이유</span>{" "}
            {escalation.reason}
          </p>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            <span className="text-foreground">답을 받지 못한 채 진행하면</span>{" "}
            {escalation.ifUnanswered}
          </p>
          <p className="text-[10px] text-muted-foreground">답할 사람 {escalation.owner}</p>
        </div>
      </div>
    </li>
  );
}
