"use client";

import { useState } from "react";

import { Sc01Canvas } from "@/components/flow/sc01-canvas";
import { Loading } from "@/components/sc01/bits";
import { Sc06Body, Sc06Header } from "@/components/sc06/bits";
import { Commentary } from "@/components/shared/commentary";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { nodeStates, NODE_STATE_LABEL } from "@/lib/sc01/process-layout";
import type { DemoRunView } from "@/lib/sc01/types";
import { useSc06 } from "@/lib/store/sc06";

const EXECUTOR_LABEL: Record<string, string> = { center: "Center 서버 실행", studio: "Studio 시험 실행", embedded: "내장 BPM(시험용)" };

/**
 * 장면 6 BPM 흐름 — `engine/processes/sc06.bpmn`(확인 절차)을 그대로 그린다. 캔버스·배치·노드 상태 파생은 장면 1~5와 같은
 * 코드다(BPMN 토폴로지 모양이 같다). 기록 태스크·오류 경계는 결재 노드에 접는다.
 */
export function Sc06ProcessScreen() {
  const meta = useSc06((s) => s.meta);
  const topology = useSc06((s) => s.topology);
  const [selected, setSelected] = useState<string | null>(null);
  const states = topology ? nodeStates(topology, (meta?.bpm ?? null) as DemoRunView["bpm"]) : {};
  const node = topology?.nodes.find((n) => n.id === selected);
  const flows = topology?.flows.filter((f) => f.source === selected) ?? [];
  const waiting = meta?.bpm?.waiting ?? [];
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc06Header id="BPM" title="SC06 확인 절차 흐름" question="확인이 어디까지 왔고 누가 무엇을 기다리는가?" />
      <Sc06Body>
        <Card>
          <CardHeader>
            <CardTitle>{topology?.name ?? "프로세스"}</CardTitle>
            <CardDescription>노드를 누르면 아래에 상세가 나온다.</CardDescription>
            <Commentary block>
              <p className="text-[13px] text-muted-foreground">
                Chaeksas BPM이 BPMN을 해석한다. 생산·구매 담당 임원 확인은 병렬이고 둘 다 끝나야 경영관리 종합 확인이 열린다. 종합 확인이 재확인을
                요청하면 두 확인을 다시 받는다. 결론 → 확정 → 대표 보고 순이고, 확정은 결론 숫자가 산정과 같아야 되며 보완을 요청하면 결론을 다시
                쓴다. 숫자는 적재 때 계산 서비스가 냈다.
              </p>
            </Commentary>
          </CardHeader>
          <CardContent>
            {!topology ? (
              <Loading what="프로세스 정의" />
            ) : (
              <div className="h-[300px] w-full rounded-md border sm:h-[440px]">
                <Sc01Canvas topology={topology} states={states} selected={selected} onSelect={setSelected} maxColumns={8} />
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
              <CardDescription>
                {meta?.executor ? EXECUTOR_LABEL[meta.executor] : "확인 기록을 끝난 것으로 적재"} {meta?.bpm?.runId ?? "— 아직 시작 전"} · 상태{" "}
                {meta?.bpm?.state ?? "—"}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {waiting.length === 0 ? (
                <p className="text-sm text-muted-foreground">{meta?.bpm?.state === "done" ? "흐름이 끝났다." : "사람을 기다리는 곳이 없다."}</p>
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
              <CardDescription>{node ? (node.role ? `담당 역할 ${node.role}` : node.kind) : "캔버스에서 노드를 누른다."}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {node ? (
                <>
                  <p>상태: {NODE_STATE_LABEL[states[node.id] ?? "pending"]}</p>
                  <ul className="space-y-0.5 text-xs">
                    {flows.map((f) => (
                      <li key={f.id}>
                        → {topology?.nodes.find((n) => n.id === f.target)?.name ?? f.target}
                        {f.condition && f.condition !== "true" ? <code className="ml-1 rounded bg-muted px-1">{f.condition}</code> : null}
                        {f.default ? <span className="ml-1 text-muted-foreground">(기본 흐름)</span> : null}
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
            </CardContent>
          </Card>
        </div>
      </Sc06Body>
    </main>
  );
}
