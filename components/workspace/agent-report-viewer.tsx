import { FileText } from "lucide-react";

import { Separator } from "@/components/ui/separator";
import type { AgentReportSection } from "@/lib/types/workspace";

/**
 * Agent 보고서 뷰어.
 *
 * 절마다 근거 소스를 붙여 둔다 — 사람이 최종 판단을 지려면 결론만이 아니라 무엇을 보고
 * 그렇게 말했는지 되짚을 수 있어야 한다. 소스 없는 절은 데이터에서부터 두지 않는다.
 */
export function AgentReportViewer({ report }: { report: AgentReportSection[] }) {
  return (
    <ol className="space-y-4">
      {report.map((section, index) => (
        <li key={section.id} className="space-y-2">
          <div className="flex items-center gap-2">
            <span
              aria-hidden
              className="flex size-5 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-medium text-muted-foreground tabular-nums"
            >
              {index + 1}
            </span>
            <h4 className="text-sm font-medium text-foreground">{section.title}</h4>
          </div>

          <p className="text-xs leading-relaxed text-foreground">{section.body}</p>

          <div className="flex flex-wrap items-center gap-1.5">
            <FileText aria-hidden className="size-3 shrink-0 text-muted-foreground" />
            {section.sources.map((source) => (
              <span
                key={source}
                className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
              >
                {source}
              </span>
            ))}
          </div>

          {index < report.length - 1 ? <Separator className="mt-4" /> : null}
        </li>
      ))}
    </ol>
  );
}
