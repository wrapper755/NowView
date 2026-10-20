"use client";

import { useState } from "react";

import { Sc01Canvas } from "@/components/flow/sc01-canvas";
import { Loading, ScreenHeader } from "@/components/sc01/bits";
import { Commentary } from "@/components/shared/commentary";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { nodeStates, NODE_STATE_LABEL } from "@/lib/sc01/process-layout";
import { selectView, useSc01 } from "@/lib/store/sc01";

/**
 * BPM 프로세스 — Chaeksas 엔진이 해석하는 BPMN(`engine/processes/sc01.bpmn`)을 그대로 그린다.
 *
 * 노드 상태는 엔진이 준 "지나온 곳 · 기다리는 곳 · 토큰 위치"에서 파생한다. 실행 중에는 아직 안
 * 간 분기를 미실행으로 칠하지 않는다 — 게이트웨이가 돌기 전에는 갈 수도 있다.
 */
export function ProcessScreen() {
  const view = useSc01(selectView);
  const topology = useSc01((s) => s.topology);
  const users = useSc01((s) => s.users);
  const [selected, setSelected] = useState<string | null>(null);

  const states = topology ? nodeStates(topology, view?.bpm ?? null) : {};
  const node = topology?.nodes.find((n) => n.id === selected);
  const waiting = view?.bpm?.waiting ?? [];
  const flows = topology?.flows.filter((f) => f.source === selected) ?? [];

  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <ScreenHeader id="BPM" title="SC01 업무 흐름" question="지금 어디까지 왔고 누가 무엇을 기다리는가?" />

      <Card>
        <CardHeader>
          <CardTitle>{topology?.name ?? "프로세스"}</CardTitle>
          <CardDescription>노드를 누르면 아래에 상세가 나온다.</CardDescription>
          <Commentary block>
            <p className="text-[13px] text-muted-foreground">
              Chaeksas BPM이 BPMN 파일을 그대로 해석한다. 숫자는 BPM이 아니라 계산 서비스가 낸다. 현업 검토(항상)와
              Management Review(중요 또는 수동 요청)는 포함 게이트웨이로 함께 열리고, 생산·자재는 병렬 별도 업무다.
            </p>
          </Commentary>
        </CardHeader>
        <CardContent>
          {!topology ? (
            <Loading what="프로세스 정의" />
          ) : (
            // React Flow는 부모에 명시적 높이가 있어야 한다.
            <div className="h-[360px] w-full rounded-md border sm:h-[560px]">
              <Sc01Canvas topology={topology} states={states} selected={selected} onSelect={setSelected} />
            </div>
          )}
          <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {Object.entries(NODE_STATE_LABEL).map(([k, v]) => (
              <li key={k}>{v}</li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>지금 기다리는 사람 업무 {waiting.length}건</CardTitle>
            <Commentary block>
              <CardDescription>
                BPM 실행 {view?.bpm?.runId ?? "— 아직 시작 전"} · 상태 {view?.bpm?.state ?? "—"}
              </CardDescription>
            </Commentary>
          </CardHeader>
          <CardContent>
            {waiting.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {view?.bpm?.state === "done" ? "흐름이 끝났다 — 장면 1 인계 완료." : "사람을 기다리는 곳이 없다."}
              </p>
            ) : (
              <ul className="divide-y text-sm">
                {waiting.map((w) => (
                  <li key={w.nodeId} className="flex items-center justify-between gap-3 py-2">
                    <span>{w.title}</span>
                    <span className="text-xs text-muted-foreground">{w.role}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{node ? (node.name ?? node.id) : "노드를 고른다"}</CardTitle>
            <CardDescription>
              {node ? `${node.role ? `담당 역할 ${node.role}` : node.kind}` : "캔버스에서 노드를 누르면 상세가 나온다."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {node ? (
              <>
                <p>상태: {NODE_STATE_LABEL[states[node.id] ?? "pending"]}</p>
                {node.role ? (
                  <p className="text-xs text-muted-foreground">
                    할 수 있는 사람: {users.filter((u) => u.role === node.role).map((u) => u.name).join(", ") || "—"}
                  </p>
                ) : null}
                {flows.length > 0 ? (
                  <ul className="space-y-0.5 text-xs">
                    {flows.map((f) => (
                      <li key={f.id}>
                        → {topology?.nodes.find((n) => n.id === f.target)?.name ?? f.target}
                        {f.condition && f.condition !== "true" ? <code className="ml-1 rounded bg-muted px-1">{f.condition}</code> : null}
                        {f.default ? <span className="ml-1 text-muted-foreground">(기본 흐름)</span> : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
