import { Hourglass } from "lucide-react";

import { Separator } from "@/components/ui/separator";
import { ConfidenceTag, DataSourceList } from "@/components/shared/data-source";
import { StatusMark } from "@/components/flow/bpmn-node";
import { MANAGEMENT_STAGE_LABEL } from "@/lib/types/cockpit";
import type { AgentRun, BpmNodeSpec, BpmNodeStatus } from "@/lib/types/bpm";

const KIND_LABEL: Record<BpmNodeSpec["kind"], string> = {
  start: "시작 이벤트",
  end: "종료 이벤트",
  "agent-task": "AI Agent 수행",
  "user-task": "사람 수행 (Human-in-the-Loop)",
  "service-task": "시스템 자동 수행",
  gateway: "배타 분기",
};

/**
 * 선택한 노드의 상세.
 *
 * 캔버스 노드는 폭 176px로 요약만 싣기 때문에 상세는 전부 여기서 읽는다.
 * 아직 수행되지 않은 노드는 산출물을 보여주지 않는다 — 미래 결과를 미리 노출하면
 * 이미 분석이 끝난 것처럼 읽힌다.
 */
export function NodeDetailPanel({
  node,
  status,
  run,
}: {
  node: BpmNodeSpec | null;
  status: BpmNodeStatus | undefined;
  run: AgentRun | undefined;
}) {
  if (!node || !status) {
    return (
      <p className="text-xs leading-relaxed text-muted-foreground">
        다이어그램에서 노드를 선택하면 수행 주체, 산출물, 참조한 데이터 소스를 볼 수 있다.
      </p>
    );
  }

  /**
   * `outcome`은 완료된 결과를 서술한 문장이다("…산출 완료" 같은).
   *
   * `active`(아직 수행 중)에 이를 보여 주면 Agent 현황 패널이 같은 결론을 감추고 있는 것과
   * 어긋난다 — 실제로 "진행 중"인 노드에 기여도 62%와 "손익 영향 산출 완료"가 표시됐다.
   * `waiting`은 사람의 판단을 기다리는 상태라 outcome이 결과가 아닌 대기 사유이므로 보여 준다.
   */
  const showsOutcome = status === "done" || status === "waiting";

  return (
    <div className="space-y-3.5">
      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <StatusMark status={status} />
          <span className="text-[10px] text-muted-foreground">
            {MANAGEMENT_STAGE_LABEL[node.stage]}
          </span>
        </div>
        <h4 className="text-sm leading-snug font-semibold text-foreground">{node.label}</h4>
        <p className="text-[10px] text-muted-foreground">{KIND_LABEL[node.kind]}</p>
      </div>

      <Separator />

      <dl className="space-y-2 text-xs">
        {node.actor ? (
          <div className="flex gap-2">
            <dt className="w-16 shrink-0 text-muted-foreground">수행 주체</dt>
            <dd className="min-w-0 text-foreground">{node.actor}</dd>
          </div>
        ) : null}
        {node.duration ? (
          <div className="flex gap-2">
            <dt className="w-16 shrink-0 text-muted-foreground">소요 시간</dt>
            <dd className="min-w-0 text-foreground tabular-nums">{node.duration}</dd>
          </div>
        ) : null}
      </dl>

      {showsOutcome && node.outcome ? (
        <>
          <Separator />
          <div className="space-y-1.5">
            <h5 className="text-xs font-medium text-muted-foreground">
              {status === "done" ? "산출물" : "진행 상황"}
            </h5>
            <p className="text-xs leading-relaxed text-foreground">{node.outcome}</p>
          </div>
        </>
      ) : null}

      {status === "active" ? (
        <>
          <Separator />
          <p className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <Hourglass aria-hidden className="size-3 shrink-0" />
            수행 중 — 산출물 확정 전
          </p>
        </>
      ) : null}

      {run ? (
        <>
          <Separator />
          <div className="space-y-1.5">
            <h5 className="text-xs font-medium text-muted-foreground">Agent 분석 결과</h5>
            <p className="text-xs leading-relaxed text-foreground">{run.output}</p>
            <ConfidenceTag confidence={run.confidence} note={run.confidenceNote} />
          </div>
          <div className="space-y-1.5">
            <h5 className="text-xs font-medium text-muted-foreground">
              참조 데이터 소스
            </h5>
            <DataSourceList sources={run.sources} />
          </div>
        </>
      ) : null}

      {status === "pending" ? (
        <p className="text-xs leading-relaxed text-muted-foreground">
          아직 수행되지 않은 단계다.
        </p>
      ) : null}

      {status === "skipped" ? (
        <p className="text-xs leading-relaxed text-muted-foreground">
          분기에서 선택되지 않아 실행되지 않았다.
        </p>
      ) : null}
    </div>
  );
}
