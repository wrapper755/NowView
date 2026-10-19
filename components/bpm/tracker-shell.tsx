"use client";

import { useMemo, useState } from "react";
import { Hourglass } from "lucide-react";

import { AgentActivityPanel } from "@/components/bpm/agent-activity-panel";
import { NodeDetailPanel } from "@/components/bpm/node-detail-panel";
import { StepControls } from "@/components/bpm/step-controls";
import { ProcessCanvas } from "@/components/flow/process-canvas";
import { Commentary } from "@/components/shared/commentary";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { EnginePanel } from "@/components/engine/engine-panel";
import { useEngineProcess } from "@/components/engine/use-engine-process";
import {
  selectScenario,
  selectStepIndex,
  useDemoController,
} from "@/lib/store/demo-controller";
import { agentActivities, runningAgentCount } from "@/services/agent-orchestrator";
import { currentNode, deriveNodeStatuses, isAwaitingHuman } from "@/services/bpm-engine";

/**
 * 트래커 화면의 클라이언트 경계.
 *
 * 프로세스 데이터는 서버에서 내려받고(직렬화 가능한 순수 데이터), 진행 지점은 Zustand에서,
 * 노드 선택은 로컬 상태로 둔다 — 선택은 이 화면 안에서만 의미가 있으므로 전역에 올리지 않는다.
 *
 * **엔진 모드에서는 같은 자리에 엔진이 돌려준 값이 들어간다.** 컴포넌트 트리는 그대로다 —
 * 화면마다 `if (engineMode)`가 흩어지면 두 경로가 조금씩 달라진다(`services/engine-view.ts`).
 */
export function BpmTrackerShell() {
  const scenario = useDemoController(selectScenario);
  const process = scenario.process;
  const stepIndex = useDemoController(selectStepIndex);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const engine = useEngineProcess(scenario.id, process);

  const mockStatuses = useMemo(
    () => deriveNodeStatuses(process, stepIndex),
    [process, stepIndex],
  );
  const mockActivities = useMemo(
    () => agentActivities(process, stepIndex),
    [process, stepIndex],
  );

  const view = engine.view;
  const statuses = view?.statuses ?? mockStatuses;
  const activities = view?.activities ?? mockActivities;
  const active = view ? view.activeNode : currentNode(process, stepIndex);
  const awaitingHuman = view ? view.awaitingHuman : isAwaitingHuman(process, stepIndex);
  const runningCount = view ? view.runningCount : runningAgentCount(process, stepIndex);

  // 선택된 노드가 없으면 현재 진행 중인 노드를 보여준다 — 빈 패널보다 유용하다.
  const detailNode = selectedNodeId
    ? (process.nodes.find((n) => n.id === selectedNodeId) ?? null)
    : (active ?? null);
  const detailStatus = detailNode ? statuses[detailNode.id] : undefined;
  // 완료된 노드만 Agent 산출물을 보여준다. 상태를 확인하지 않으면 아직 실행 중인 Agent의
  // 결과가 상세 패널에만 새어 나와, Agent 현황 패널(산출물을 감춘다)과 어긋난다.
  const detailRun =
    detailNode && detailStatus === "done"
      ? view
        ? view.runByNode[detailNode.id]
        : process.runs.find((r) => r.nodeId === detailNode.id)
      : undefined;

  return (
    <div className="space-y-4">
      <header className="space-y-2">
        <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
          <h1 className="text-xl font-semibold">Live BPM &amp; Agent Process Tracker</h1>
          <span className="text-sm text-muted-foreground">{process.subject}</span>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted-foreground">
          <span className="rounded bg-muted px-1.5 py-0.5 text-foreground">
            {scenario.shortTitle}
          </span>
          <span className="tabular-nums">
            {process.kri.label}{" "}
            <span className="font-medium text-foreground">{process.kri.value}</span>
            <span className="mx-1 text-muted-foreground/60">/</span>
            임계 {process.kri.threshold}
          </span>
          <span className="tabular-nums">착수 {process.startedAt}</span>
          <span className="font-mono text-[10px]">{process.id}</span>
          <Link
            href="/"
            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-medium text-foreground hover:bg-muted"
          >
            Cockpit의 해당 리스크 보기
            <ArrowUpRight aria-hidden className="size-3" />
          </Link>
        </div>
      </header>

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
            {/* 이 배너는 모든 user-task 단계에서 뜬다. Review 전용 문구를 쓰면
                Management Action 단계에서 "대안 선택"을 말하게 되므로 일반화해 둔다. */}
            <p className="mt-0.5 text-xs text-muted-foreground">
              Agent가 수행할 수 있는 단계는 끝났다. 이 단계의 판단과 실행은{" "}
              {active?.actor ?? "담당자"}의 책임이다.
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
          <EnginePanel {...engine.panelProps} />
          {/* 엔진 모드에서는 단계 버튼을 감춘다. 진행은 실행의 결과이므로 임의로
              앞당길 수 없고, 되짚어 보기는 데모 플레이어가 장면 단위로 한다. */}
          {engine.view ? null : <StepControls process={process} />}
          {/* React Flow는 부모에 명시적 높이가 있어야 렌더된다 (100% 높이를 상속받지 못한다).
              좁은 화면에서는 낮춘다 — 360×640에서 헤더와 데모 바를 뺀 본문이 433px라
              360px짜리 캔버스가 화면을 통째로 먹어 그 아래가 없는 것처럼 보였다. */}
          <div className="viz-root h-[240px] w-full overflow-hidden rounded-lg border sm:h-[360px]">
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
            <Commentary block>
              <CardDescription>
                산출물에는 참조한 데이터 소스를 함께 표시한다. 최종 판단은 사람이 지므로
                근거를 되짚을 수 있어야 한다.
              </CardDescription>
            </Commentary>
          </CardHeader>
          <CardContent>
            <AgentActivityPanel activities={activities} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
