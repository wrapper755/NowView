"use client";

import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  ConnectionLineType,
  Controls,
  MarkerType,
  ReactFlow,
  type Edge,
} from "@xyflow/react";

// 이 import가 없으면 노드·엣지가 레이아웃 없이 렌더되어 "아무것도 안 보이는" 상태가 된다.
import "@xyflow/react/dist/style.css";

import { BpmnNode, type BpmnFlowNode } from "@/components/flow/bpmn-node";
import type { BpmNodeStatus, BpmProcessInstance } from "@/lib/types/bpm";

/** nodeTypes는 렌더마다 새 객체가 되면 React Flow가 경고하므로 모듈 스코프에 고정한다. */
const NODE_TYPES = { bpmn: BpmnNode };

/**
 * 화살촉 색은 CSS 변수를 쓸 수 없다.
 *
 * React Flow는 marker 색 문자열을 DOM id에 그대로 끼워 넣고 `url(#...)`로 참조한다.
 * `var(--x)`에는 괄호가 있어 그 참조가 깨지고 화살촉이 사라진다. 그래서 여기서는
 * **라이트/다크에서 값이 같은** 팔레트 스텝만 리터럴로 쓴다
 * (`#0ca30c` status-good, `#898781` muted — 둘 다 모드 불변이다).
 * 선(path) 자체는 style로 칠하므로 CSS 변수를 그대로 쓸 수 있다.
 */
const MARKER_COLOR_DONE = "#0ca30c";
const MARKER_COLOR_IDLE = "#898781";

/**
 * 엣지 외형: 이미 지나온 경로는 또렷하게, 앞으로 갈 경로와 미실행 분기는 물러나게.
 * 미실행 분기는 점선으로 한 번 더 구분한다 (색만으로 구분하지 않는다).
 */
function edgeAppearance(
  sourceStatus: BpmNodeStatus,
  targetStatus: BpmNodeStatus,
): { stroke: string; markerColor: string; dashed: boolean; opacity: number } {
  if (targetStatus === "skipped" || sourceStatus === "skipped") {
    return {
      stroke: "var(--color-muted-foreground)",
      markerColor: MARKER_COLOR_IDLE,
      dashed: true,
      opacity: 0.45,
    };
  }
  if (sourceStatus === "done") {
    return {
      stroke: "var(--viz-status-good)",
      markerColor: MARKER_COLOR_DONE,
      dashed: false,
      opacity: 1,
    };
  }
  return {
    stroke: "var(--color-muted-foreground)",
    markerColor: MARKER_COLOR_IDLE,
    dashed: false,
    opacity: 0.6,
  };
}

export function ProcessCanvas({
  process,
  statuses,
  selectedNodeId,
  onSelectNode,
}: {
  process: BpmProcessInstance;
  statuses: Record<string, BpmNodeStatus>;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
}) {
  const nodes = useMemo<BpmnFlowNode[]>(
    () =>
      process.nodes.map((node) => ({
        id: node.id,
        type: "bpmn" as const,
        position: node.position,
        selected: node.id === selectedNodeId,
        data: {
          label: node.label,
          kind: node.kind,
          status: statuses[node.id],
          actor: node.actor,
        },
      })),
    [process.nodes, statuses, selectedNodeId],
  );

  const edges = useMemo<Edge[]>(
    () =>
      process.edges.map((edge) => {
        const { stroke, markerColor, dashed, opacity } = edgeAppearance(
          statuses[edge.source],
          statuses[edge.target],
        );
        return {
          id: edge.id,
          source: edge.source,
          target: edge.target,
          sourceHandle: edge.sourceHandle,
          label: edge.label,
          type: "smoothstep",
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: markerColor,
            width: 14,
            height: 14,
          },
          style: {
            stroke,
            strokeWidth: 1.5,
            strokeDasharray: dashed ? "4 4" : undefined,
            opacity,
          },
          labelStyle: { fill: "var(--color-muted-foreground)", fontSize: 10 },
          labelBgStyle: { fill: "var(--color-background)" },
          labelBgPadding: [4, 2] as [number, number],
        };
      }),
    [process.edges, statuses],
  );

  return (
    // colorMode는 쓰지 않는다 — prefers-color-scheme 기반이라 클래스 기반 테마 토글과
    // 어긋날 수 있다. 노드는 전부 커스텀이고 엣지·배경은 아래에서 직접 토큰을 지정한다.
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={NODE_TYPES}
      onNodeClick={(_, node) => onSelectNode(node.id)}
      connectionLineType={ConnectionLineType.SmoothStep}
      nodesDraggable={false}
      nodesConnectable={false}
      edgesFocusable={false}
      fitView
      fitViewOptions={{ padding: 0.12, maxZoom: 1 }}
      minZoom={0.3}
      maxZoom={1.6}
      proOptions={{ hideAttribution: false }}
      aria-label="BPM 프로세스 다이어그램"
    >
      <Background
        variant={BackgroundVariant.Dots}
        gap={18}
        size={1}
        color="var(--viz-grid)"
      />
      <Controls showInteractive={false} className="!shadow-none" />
    </ReactFlow>
  );
}
