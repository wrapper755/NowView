"use client";

import { useMemo, useState } from "react";
import { Hourglass } from "lucide-react";

import { AgentActivityPanel } from "@/components/bpm/agent-activity-panel";
import { NodeDetailPanel } from "@/components/bpm/node-detail-panel";
import { StepControls } from "@/components/bpm/step-controls";
import { ProcessCanvas } from "@/components/flow/process-canvas";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useDemoController } from "@/lib/store/demo-controller";
import type { BpmProcessInstance } from "@/lib/types/bpm";
import { agentActivities, runningAgentCount } from "@/services/agent-orchestrator";
import { currentNode, deriveNodeStatuses, isAwaitingHuman } from "@/services/bpm-engine";

/**
 * 트래커 화면의 클라이언트 경계.
 *
 * 프로세스 데이터는 서버에서 내려받고(직렬화 가능한 순수 데이터), 진행 지점은 Zustand에서,
 * 노드 선택은 로컬 상태로 둔다 — 선택은 이 화면 안에서만 의미가 있으므로 전역에 올리지 않는다.
 */
export function BpmTrackerShell({ process }: { process: BpmProcessInstance }) {
  const stepIndex = useDemoController((s) => s.stepIndex);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const statuses = useMemo(() => deriveNodeStatuses(process, stepIndex), [process, stepIndex]);
  const activities = useMemo(() => agentActivities(process, stepIndex), [process, stepIndex]);

  const active = currentNode(process, stepIndex);
  const awaitingHuman = isAwaitingHuman(process, stepIndex);
  const runningCount = runningAgentCount(process, stepIndex);

  // 선택된 노드가 없으면 현재 진행 중인 노드를 보여준다 — 빈 패널보다 유용하다.
  const detailNode = selectedNodeId
    ? (process.nodes.find((n) => n.id === selectedNodeId) ?? null)
    : (active ?? null);
  const detailStatus = detailNode ? statuses[detailNode.id] : undefined;
  // 완료된 노드만 Agent 산출물을 보여준다. 상태를 확인하지 않으면 아직 실행 중인 Agent의
  // 결과가 상세 패널에만 새어 나와, Agent 현황 패널(산출물을 감춘다)과 어긋난다.
  const detailRun =
    detailNode && detailStatus === "done"
      ? process.runs.find((r) => r.nodeId === detailNode.id)
      : undefined;

  return (
    <div className="space-y-4">
      {awaitingHuman ? (
        <div
          className="flex items-start gap-2.5 rounded-lg border p-3"
          style={{ borderColor: "var(--viz-status-warning)" }}
        >
          <Hourglass
            aria-hidden
            className="mt-0.5 size-4 shrink-0"
            style={{ color: "var(--viz-status-warning)" }}
          />
          <div className="min-w-0">
            <p className="text-sm font-medium text-foreground">
              사람의 판단을 기다리는 중 — {active?.label}
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Agent는 수집·분석·시뮬레이션까지 수행했다. 대안 선택과 승인은 {active?.actor}의
              책임이다.
            </p>
          </div>
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">프로세스 진행 상태</CardTitle>
          <CardDescription>
            노드를 클릭하면 수행 주체와 산출물, 참조한 데이터 소스를 볼 수 있다. 점선 경로는
            분기에서 선택되지 않아 실행되지 않은 단계다.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <StepControls process={process} />
          {/* React Flow는 부모에 명시적 높이가 있어야 렌더된다 (100% 높이를 상속받지 못한다). */}
          <div className="viz-root h-[440px] w-full overflow-hidden rounded-lg border">
            <ProcessCanvas
              process={process}
              statuses={statuses}
              selectedNodeId={selectedNodeId}
              onSelectNode={setSelectedNodeId}
            />
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="viz-root lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-base">
              {selectedNodeId ? "선택한 단계" : "현재 단계"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <NodeDetailPanel node={detailNode} status={detailStatus} run={detailRun} />
          </CardContent>
        </Card>

        <Card className="viz-root lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">
              Agent 실행 현황
              {runningCount > 0 ? (
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  실행 중 {runningCount}건
                </span>
              ) : null}
            </CardTitle>
            <CardDescription>
              산출물에는 참조한 데이터 소스를 함께 표시한다. 최종 판단은 사람이 지므로 근거를
              되짚을 수 있어야 한다.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <AgentActivityPanel activities={activities} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
