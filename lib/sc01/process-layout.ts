/**
 * BPMN 토폴로지 → 캔버스 배치와 노드 상태.
 *
 * **BPMN 파일에는 다이어그램(DI)이 없다**(`engine/processes/sc01.bpmn`). 그래서 배치는 화면이
 * 계산한다 — 시작에서부터의 층(최장 경로)으로 열을 정하고, 되돌아가는 흐름(보완 → 재검증)은
 * 층 계산에서 뺀다. 좌표를 손으로 적어 두면 BPMN이 바뀔 때 조용히 어긋난다(4.15와 같은 이유).
 */

import type { DemoRunView, ProcessTopology } from "@/lib/sc01/types";

export type NodeState = "done" | "waiting" | "active" | "pending" | "skipped";

export const NODE_STATE_LABEL: Record<NodeState, string> = {
  done: "완료",
  waiting: "사람 대기",
  active: "진행 중",
  pending: "대기 전",
  skipped: "미실행 분기",
};

export interface PlacedNode {
  id: string;
  kind: string;
  name: string;
  role: string | null;
  rank: number;
  x: number;
  y: number;
}

const COLUMN = 185;
const ROW = 105;
/** 한 줄에 놓는 층 수의 상한. 넘으면 아래 줄로 접는다 — 한 줄로 펴면 캔버스 폭에 맞추느라 글자가 읽히지 않는다. */
const MAX_COLUMNS = 5;

/** 되돌아가는 흐름을 찾는다(DFS에서 회색 노드로 돌아가는 간선). */
function backEdges(topology: ProcessTopology, start: string): Set<string> {
  const out = new Map<string, { id: string; target: string }[]>();
  for (const f of topology.flows) {
    out.set(f.source, [...(out.get(f.source) ?? []), { id: f.id, target: f.target }]);
  }
  const color = new Map<string, "gray" | "black">();
  const back = new Set<string>();
  const visit = (node: string) => {
    color.set(node, "gray");
    for (const edge of out.get(node) ?? []) {
      const c = color.get(edge.target);
      if (c === "gray") back.add(edge.id);
      else if (c === undefined) visit(edge.target);
    }
    color.set(node, "black");
  };
  visit(start);
  return back;
}

/**
 * 캔버스가 그릴 토폴로지 — 결정 기록 태스크(`recordOf`)를 그 결재 노드에 접는다.
 *
 * 기록 태스크는 결재마다 하나씩 붙는 NowView 쪽 장부다(바깥 Chaeksas에서도 결정이 NowView에 닿게
 * 하는 길). 그대로 그리면 노드가 20개에서 27개로 늘어 캔버스 글자가 읽히지 않았다(실측) — 업무
 * 흐름으로는 결재와 한 걸음이므로 결재 노드 하나로 보인다. BPMN 자체는 바꾸지 않는다.
 *
 * 기록 태스크의 오류 경계(「기록 거절」 → 같은 결재)도 접힌다 — 접고 나면 결재에서 자기에게 도는
 * 고리라 그리지 않는다. 거절은 업무 흐름의 갈래가 아니라 「다시 답한다」이고, 사유는 감사 이력에 있다.
 */
export function canvasTopology(topology: ProcessTopology): ProcessTopology {
  const folded = new Map(
    topology.nodes.filter((n) => n.recordOf).map((n) => [n.id, n.recordOf as string]),
  );
  if (folded.size === 0) return topology;
  return {
    ...topology,
    nodes: topology.nodes.filter((n) => !folded.has(n.id)),
    flows: topology.flows
      .filter((f) => !folded.has(f.target))
      .map((f) => (folded.has(f.source) ? { ...f, source: folded.get(f.source)! } : f))
      .filter((f) => f.source !== f.target),
  };
}

/**
 * `maxColumns` — 한 줄에 놓는 층 수. 장면 2처럼 층이 많은 흐름은 넓게 펴야 세로 줄이 줄어 글자가 커진다
 * (fitView는 폭·높이 중 작은 배율을 쓴다).
 */
export function layoutProcess(full: ProcessTopology, maxColumns = MAX_COLUMNS): PlacedNode[] {
  const topology = canvasTopology(full);
  const start =
    topology.nodes.find((n) => n.kind === "startEvent")?.id ?? topology.nodes[0]?.id;
  if (!start) return [];
  const back = backEdges(topology, start);
  const forward = topology.flows.filter((f) => !back.has(f.id));

  // 최장 경로 층. 간선 수만큼 반복하면 DAG에서 수렴한다.
  const rank = new Map<string, number>([[start, 0]]);
  for (let i = 0; i < topology.nodes.length; i++) {
    let changed = false;
    for (const f of forward) {
      const from = rank.get(f.source);
      if (from === undefined) continue;
      if ((rank.get(f.target) ?? -1) < from + 1) {
        rank.set(f.target, from + 1);
        changed = true;
      }
    }
    if (!changed) break;
  }

  // 같은 층 안에서는 BPMN에 적힌 순서를 따른다 — 생산·자재처럼 짝인 노드가 나란히 선다.
  const byRank = new Map<number, string[]>();
  for (const n of topology.nodes) {
    const r = rank.get(n.id) ?? 0;
    byRank.set(r, [...(byRank.get(r) ?? []), n.id]);
  }
  // 층을 줄(band)로 접는다. 줄 높이는 가장 붐비는 층에 맞춘다.
  const ranks = Math.max(...rank.values()) + 1;
  const bands = Math.ceil(ranks / maxColumns);
  const perBand = Math.ceil(ranks / bands);
  const widest = Math.max(...[...byRank.values()].map((c) => c.length));
  const bandHeight = (widest + 0.6) * ROW;

  return topology.nodes.map((n) => {
    const r = rank.get(n.id) ?? 0;
    const column = byRank.get(r) ?? [n.id];
    const i = column.indexOf(n.id);
    return {
      id: n.id,
      kind: n.kind,
      name: n.name ?? n.id,
      role: n.role,
      rank: r,
      x: (r % perBand) * COLUMN,
      y: Math.floor(r / perBand) * bandHeight + (i - (column.length - 1) / 2) * ROW,
    };
  });
}

/**
 * 노드 상태 — 엔진이 준 "지나온 곳 · 기다리는 곳 · 토큰 위치"에서 파생한다.
 *
 * 실행 중에는 아직 안 간 분기를 `skipped`로 보지 않는다 — 게이트웨이가 돌기 전에는 갈 수도
 * 있다(4.5 "미실행 판정"). 실행이 끝났을 때만 안 간 노드가 미실행 분기다.
 *
 * **바깥 실행(N2)은 끝나도 미실행을 칠하지 않는다.** `visited`는 작업 호출이 알려 준 노드뿐이라
 * 시작·게이트웨이·메시지 대기처럼 호출이 없는 노드는 지나왔어도 빠져 있다 — 모르는 것이다.
 */
export function nodeStates(
  topology: ProcessTopology,
  bpm: DemoRunView["bpm"],
): Record<string, NodeState> {
  const states: Record<string, NodeState> = {};
  const visited = new Set(bpm?.visited ?? []);
  const waiting = new Set((bpm?.waiting ?? []).map((w) => w.nodeId));
  const position = new Set(bpm?.position ?? []);
  const finished = bpm?.state === "done";
  const known = (bpm?.executor ?? "embedded") === "embedded";
  // 도달한 종료가 기록된 실행(장면 2 — 종료가 여럿)이면 그 종료만 완료다. 기록이 없으면(장면 1) 끝났을 때
  // 종료를 완료로 본다.
  const endsRecorded = topology.nodes.some((n) => n.kind === "endEvent" && visited.has(n.id));
  for (const n of topology.nodes) {
    if (waiting.has(n.id)) states[n.id] = "waiting";
    else if (position.has(n.id)) states[n.id] = "active";
    else if (visited.has(n.id)) states[n.id] = "done";
    // 종료 이벤트는 완료 기록을 남기지 않는다 — 실행이 끝났으면 도달한 것이다.
    else if (finished && n.kind === "endEvent" && !endsRecorded) states[n.id] = "done";
    else states[n.id] = finished && known ? "skipped" : "pending";
  }
  return states;
}
