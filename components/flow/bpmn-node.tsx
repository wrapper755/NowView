import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import {
  Bot,
  Check,
  CircleDot,
  Cog,
  Hourglass,
  Minus,
  Play,
  UserRound,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import {
  BPM_STATUS_LABEL,
  type BpmNodeKind,
  type BpmNodeStatus,
} from "@/lib/types/bpm";

/** React Flow v12는 노드 data가 Record<string, unknown>을 만족하기를 요구한다. */
export type BpmnNodeData = {
  label: string;
  kind: BpmNodeKind;
  status: BpmNodeStatus;
  actor?: string;
} & Record<string, unknown>;

export type BpmnFlowNode = Node<BpmnNodeData, "bpmn">;

/** 요소 종류를 나타내는 아이콘. 색이 아니라 아이콘이 종류를 말한다. */
const KIND_ICON: Record<BpmNodeKind, LucideIcon> = {
  start: Play,
  end: CircleDot,
  "agent-task": Bot,
  "user-task": UserRound,
  "service-task": Cog,
  gateway: Minus,
};

const KIND_LABEL: Record<BpmNodeKind, string> = {
  start: "시작 이벤트",
  end: "종료 이벤트",
  "agent-task": "AI Agent",
  "user-task": "사람 수행",
  "service-task": "시스템 자동",
  gateway: "배타 분기",
};

/**
 * 진행 상태 색.
 *
 * `done`/`waiting`은 상태 팔레트를 쓴다 — 완료는 good, 사람 대기는 "지금 조치가 필요"라는
 * 뜻이므로 warning이 의미상 맞다. `active`는 좋음/나쁨이 아닌 중립 진행이라 계열색(파랑)을
 * 쓴다. 이 한 곳에서만 계열색이 진행 상태에 쓰이며, 아이콘+한글 라벨이 항상 동반되므로
 * 색 단독으로 의미를 전달하지 않는다.
 */
const STATUS_COLOR: Record<BpmNodeStatus, string> = {
  done: "var(--viz-status-good)",
  active: "var(--viz-series-1)",
  waiting: "var(--viz-status-warning)",
  pending: "var(--color-muted-foreground)",
  skipped: "var(--color-muted-foreground)",
};

const STATUS_ICON: Record<BpmNodeStatus, LucideIcon> = {
  done: Check,
  active: Play,
  waiting: Hourglass,
  pending: Minus,
  skipped: Minus,
};

export function statusColor(status: BpmNodeStatus): string {
  return STATUS_COLOR[status];
}

export function StatusMark({ status }: { status: BpmNodeStatus }) {
  const Icon = STATUS_ICON[status];
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-medium text-foreground">
      <Icon aria-hidden className="size-3 shrink-0" style={{ color: STATUS_COLOR[status] }} />
      {BPM_STATUS_LABEL[status]}
    </span>
  );
}

/**
 * BPMN 노드 한 개.
 *
 * 캔버스에는 요약만 싣고(폭 176px) 상세는 클릭 시 우측 패널이 담당한다 — 노드 11개를
 * 한 화면에 넣으면서 텍스트 가독성을 지키려면 캔버스 쪽을 줄이는 수밖에 없다.
 */
export function BpmnNode({ data, selected }: NodeProps<BpmnFlowNode>) {
  const { label, kind, status, actor } = data;
  const KindIcon = KIND_ICON[kind];
  const isEvent = kind === "start" || kind === "end";
  const isGateway = kind === "gateway";
  const dimmed = status === "pending" || status === "skipped";

  // 이벤트와 게이트웨이는 BPMN 관례대로 원/다이아몬드로 그리고 라벨을 바깥에 둔다.
  if (isEvent || isGateway) {
    return (
      <div className="relative flex size-14 items-center justify-center">
        <Handle type="target" position={Position.Left} className="!size-1.5 !border-0 !bg-muted-foreground" />
        <div
          className={cn(
            "flex size-14 items-center justify-center border-2 bg-card transition-opacity",
            isGateway ? "rotate-45 rounded-md" : "rounded-full",
            dimmed && "opacity-45",
            selected && "ring-2 ring-offset-2 ring-offset-background",
          )}
          style={{ borderColor: STATUS_COLOR[status] }}
        >
          <KindIcon
            aria-hidden
            className={cn("size-4 text-foreground", isGateway && "-rotate-45")}
          />
        </div>

        {/* 라벨은 도형 밖에 둔다 — 안에 넣으면 잘린다.
            게이트웨이는 분기 엣지가 아래로 빠지므로 라벨을 위에 둬야 엣지 라벨과 겹치지 않는다. */}
        <span
          className={cn(
            "absolute left-1/2 w-32 -translate-x-1/2 text-center text-[10px] leading-tight text-muted-foreground",
            isGateway ? "bottom-full mb-1" : "top-full mt-1",
            dimmed && "opacity-60",
          )}
        >
          {label}
        </span>

        {isGateway ? (
          <>
            <Handle id="main" type="source" position={Position.Right} className="!size-1.5 !border-0 !bg-muted-foreground" />
            <Handle id="branch" type="source" position={Position.Bottom} className="!size-1.5 !border-0 !bg-muted-foreground" />
          </>
        ) : (
          <Handle type="source" position={Position.Right} className="!size-1.5 !border-0 !bg-muted-foreground" />
        )}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "relative w-44 rounded-lg border bg-card p-2.5 text-left shadow-sm transition-opacity",
        dimmed && "opacity-45",
        status === "skipped" && "border-dashed",
        selected && "ring-2 ring-offset-2 ring-offset-background",
      )}
    >
      <Handle type="target" position={Position.Left} className="!size-1.5 !border-0 !bg-muted-foreground" />

      {/* 상태를 왼쪽 띠로도 한 번 더 표현한다 (색 + 아이콘 + 라벨의 삼중 표현). */}
      <span
        aria-hidden
        className="absolute top-2.5 bottom-2.5 left-0 w-0.5 rounded-full"
        style={{ backgroundColor: STATUS_COLOR[status] }}
      />

      <div className="flex items-center gap-1.5">
        <KindIcon aria-hidden className="size-3 shrink-0 text-muted-foreground" />
        <span className="truncate text-[10px] text-muted-foreground">
          {KIND_LABEL[kind]}
        </span>
      </div>

      <p className="mt-1 text-xs leading-snug font-medium text-foreground">{label}</p>

      {actor ? (
        <p className="mt-0.5 truncate text-[10px] text-muted-foreground">{actor}</p>
      ) : null}

      <div className="mt-1.5">
        <StatusMark status={status} />
      </div>

      <Handle type="source" position={Position.Right} className="!size-1.5 !border-0 !bg-muted-foreground" />
    </div>
  );
}
