"use client";

import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import {
  Check,
  CircleDot,
  Cog,
  Diamond,
  Hand,
  Hourglass,
  Inbox,
  Minus,
  Play,
  UserRound,
  type LucideIcon,
} from "lucide-react";

// 이 import가 없으면 노드·엣지가 레이아웃 없이 렌더되어 "아무것도 안 보이는" 상태가 된다.
import "@xyflow/react/dist/style.css";

import { cn } from "@/lib/utils";
import {
  canvasTopology,
  layoutProcess,
  NODE_STATE_LABEL,
  type NodeState,
} from "@/lib/sc01/process-layout";
import type { ProcessTopology } from "@/lib/sc01/types";

/**
 * BPMN 캔버스 — 토폴로지는 엔진이 BPMN 파일에서 읽어 준다(`GET /sc01/process`).
 *
 * 상태색 규칙은 이전 캔버스와 같다: 완료 = good, 사람 대기 = warning(지금 조치가 필요), 진행 =
 * 계열색. 색만으로 말하지 않고 아이콘 + 한글 라벨이 함께 나간다.
 */
type Data = { name: string; kind: string; role: string | null; state: NodeState } & Record<string, unknown>;
type FlowNode = Node<Data, "bpmn">;

/** 화살촉은 CSS 변수를 못 쓴다(색 문자열이 marker id가 된다) — 모드 불변 리터럴만 쓴다. */
const MARKER_DONE = "#0ca30c";
const MARKER_IDLE = "#898781";

const KIND: Record<string, { icon: LucideIcon; label: string }> = {
  startEvent: { icon: Play, label: "시작" },
  endEvent: { icon: CircleDot, label: "종료" },
  userTask: { icon: UserRound, label: "사람 업무" },
  manualTask: { icon: Hand, label: "사람 확인" },
  serviceTask: { icon: Cog, label: "시스템 자동" },
  receiveTask: { icon: Inbox, label: "메시지 대기" },
  exclusiveGateway: { icon: Diamond, label: "배타 분기" },
  inclusiveGateway: { icon: Diamond, label: "포함 분기" },
  parallelGateway: { icon: Diamond, label: "병렬" },
};

const STATE_COLOR: Record<NodeState, string> = {
  done: "var(--viz-status-good)",
  waiting: "var(--viz-status-warning)",
  active: "var(--viz-series-1)",
  pending: "var(--color-muted-foreground)",
  skipped: "var(--color-muted-foreground)",
};
const STATE_ICON: Record<NodeState, LucideIcon> = {
  done: Check,
  waiting: Hourglass,
  active: Play,
  pending: Minus,
  skipped: Minus,
};

function BpmnNode({ data, selected }: NodeProps<FlowNode>) {
  const kind = KIND[data.kind] ?? { icon: Cog, label: data.kind };
  const Icon = kind.icon;
  const StateIcon = STATE_ICON[data.state];
  const isGateway = data.kind.endsWith("Gateway");
  return (
    <div
      className={cn(
        "w-[160px] rounded-lg border bg-card px-2.5 py-2 text-card-foreground shadow-xs",
        isGateway && "w-[120px] border-dashed",
        data.state === "skipped" && "opacity-50",
        selected && "ring-2 ring-ring",
      )}
      style={{ borderColor: data.state === "pending" || data.state === "skipped" ? undefined : STATE_COLOR[data.state] }}
    >
      <Handle type="target" position={Position.Left} className="!size-1.5 !border-0 !bg-transparent" />
      <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
        <Icon aria-hidden className="size-3" />
        {kind.label}
        {data.role ? <span className="truncate">· {data.role}</span> : null}
      </div>
      <p className="mt-0.5 text-xs leading-snug font-medium">{data.name}</p>
      <span className="mt-1 inline-flex items-center gap-1 text-[10px] font-medium">
        <StateIcon aria-hidden className="size-3" style={{ color: STATE_COLOR[data.state] }} />
        {NODE_STATE_LABEL[data.state]}
      </span>
      <Handle type="source" position={Position.Right} className="!size-1.5 !border-0 !bg-transparent" />
    </div>
  );
}

const NODE_TYPES = { bpmn: BpmnNode };

export function Sc01Canvas({
  topology,
  states,
  selected,
  onSelect,
  maxColumns,
}: {
  topology: ProcessTopology;
  states: Record<string, NodeState>;
  selected: string | null;
  onSelect: (id: string) => void;
  /** 한 줄의 층 수 — 기본 5. 장면 2 흐름은 층이 많아 넓게 편다. */
  maxColumns?: number;
}) {
  const placed = useMemo(() => layoutProcess(topology, maxColumns), [topology, maxColumns]);
  // 흐름도 접은 토폴로지에서 — 기록 태스크로 가는 간선은 결재에서 바로 다음으로 이어진다.
  const flows = useMemo(() => canvasTopology(topology).flows, [topology]);

  const nodes = useMemo<FlowNode[]>(
    () =>
      placed.map((p) => ({
        id: p.id,
        type: "bpmn" as const,
        position: { x: p.x, y: p.y },
        selected: p.id === selected,
        data: { name: p.name, kind: p.kind, role: p.role, state: states[p.id] ?? "pending" },
      })),
    [placed, states, selected],
  );

  const edges = useMemo<Edge[]>(
    () =>
      flows.map((f) => {
        const passed = states[f.source] === "done" && states[f.target] !== "pending" && states[f.target] !== "skipped";
        const idle = states[f.target] === "skipped" || states[f.source] === "skipped";
        return {
          id: f.id,
          source: f.source,
          target: f.target,
          type: "smoothstep",
          label: f.condition && f.condition !== "true" ? f.condition : f.default ? "기본" : undefined,
          markerEnd: { type: MarkerType.ArrowClosed, color: passed ? MARKER_DONE : MARKER_IDLE, width: 14, height: 14 },
          style: {
            stroke: passed ? "var(--viz-status-good)" : "var(--color-muted-foreground)",
            strokeWidth: 1.5,
            strokeDasharray: idle ? "4 4" : undefined,
            opacity: passed ? 1 : idle ? 0.45 : 0.6,
          },
          labelStyle: { fill: "var(--color-muted-foreground)", fontSize: 9 },
          labelBgStyle: { fill: "var(--color-background)" },
        };
      }),
    [flows, states],
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={NODE_TYPES}
      onNodeClick={(_, n) => onSelect(n.id)}
      nodesDraggable={false}
      nodesConnectable={false}
      edgesFocusable={false}
      fitView
      fitViewOptions={{ padding: 0.08, maxZoom: 1 }}
      minZoom={0.2}
      maxZoom={1.6}
      aria-label="SC01 BPMN 프로세스"
    >
      <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="var(--viz-grid)" />
      <Controls showInteractive={false} className="!shadow-none" />
    </ReactFlow>
  );
}
