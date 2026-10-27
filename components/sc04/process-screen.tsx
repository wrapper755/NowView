"use client";

import { useState } from "react";

import { Sc01Canvas } from "@/components/flow/sc01-canvas";
import { Loading } from "@/components/sc01/bits";
import { Sc04Header } from "@/components/sc04/bits";
import { Commentary } from "@/components/shared/commentary";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { nodeStates, NODE_STATE_LABEL } from "@/lib/sc01/process-layout";
import type { DemoRunView } from "@/lib/sc01/types";
import { selectView4, useSc04 } from "@/lib/store/sc04";

/**
 * 장면 4 BPM 흐름 — `engine/processes/sc04.bpmn`을 그대로 그린다. 캔버스·배치·노드 상태 파생은 장면 1과 같은
 * 코드다(BPMN 토폴로지 모양이 같다). 기록 태스크는 결재 노드에 접는다.
 */
export function Sc04ProcessScreen() {
  const view = useSc04(selectView4);
  const topology = useSc04((s) => s.topology);
  const [selected, setSelected] = useState<string | null>(null);
  // 장면 4 BPM 상태는 장면 1 뷰의 bpm과 같은 칸(state·waiting·position·visited)을 쓴다 — 실행 위치와 무관하다.
  const states = topology ? nodeStates(topology, (view?.bpm ?? null) as DemoRunView["bpm"]) : {};
  const node = topology?.nodes.find((n) => n.id === selected);
  const flows = topology?.flows.filter((f) => f.source === selected) ?? [];
  const waiting = view?.bpm?.waiting ?? [];
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc04Header id="BPM" title="SC04 업무 흐름" question="지금 어디까지 왔고 누가 무엇을 기다리는가?" />
      <Card>
        <CardHeader>
          <CardTitle>{topology?.name ?? "프로세스"}</CardTitle>
          <CardDescription>노드를 누르면 아래에 상세가 나온다.</CardDescription>
          <Commentary block>
            <p className="text-[13px] text-muted-foreground">
              Chaeksas BPM이 BPMN을 해석한다. 숫자는 계산 서비스가 낸다. 네 분석과제의 제출·임원 확인은 병렬이고, 보완 요청이면 같은
              부서가 새 버전을 낸다. 검증이 막으면 그 안의 담당 임원이 보완하고 다시 검증한다. 승인서 보완 요청은 초안으로 돌아간다. 책임 인수는
              등록된 대상만 갈래가 열리고(보류 안은 없다), 반려면 승인 범위 안에서 보완한 새 배정버전을 인수한다.
            </p>
          </Commentary>
        </CardHeader>
        <CardContent>
          {!topology ? (
            <Loading what="프로세스 정의" />
          ) : (
            <div className="h-[360px] w-full rounded-md border sm:h-[620px]">
              <Sc01Canvas topology={topology} states={states} selected={selected} onSelect={setSelected} maxColumns={12} />
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
              {view?.executor === "studio" ? "Studio 시험 실행" : view?.executor === "center" ? "Center 서버 실행" : "내장 BPM(시험용)"}{" "}
              {view?.bpm?.runId ?? "— 아직 시작 전"} · 상태 {view?.bpm?.state ?? "—"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {waiting.length === 0 ? (
              <p className="text-sm text-muted-foreground">{view?.bpm?.state === "done" ? "흐름이 끝났다." : "사람을 기다리는 곳이 없다."}</p>
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
    </main>
  );
}
