"use client";

import Link from "next/link";
import { AlarmClock } from "lucide-react";

import { RiskTag, useUserName } from "@/components/sc01/bits";
import { Sc02Body, Sc02Header, StatusPills, Won } from "@/components/sc02/bits";
import { Commentary } from "@/components/shared/commentary";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { TASK2_LABEL } from "@/lib/sc02/format";
import { ROUTE_OF_NODE } from "@/lib/sc02/scenes";
import type { Sc02View } from "@/lib/sc02/types";
import { useSc01 } from "@/lib/store/sc01";

/**
 * 장면 2 현황 — D00 「장면 1 결과 확인」과 공통 업무함. 장면 1의 물량 이슈가 열린 채로 원가 요청이 들어온다.
 * 장면 1 공통 대시보드(`/`)를 바꾸지 않는다 — 장면 2의 손익 연결은 U27에 있다.
 */
export function Sc02OverviewScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc02Header id="SC02" title="장면 2 — 단가 인상 검토 현황" question="물량 감소 대응 중에 원가 상승이 들어오면 무엇을 보고 누가 판단하는가?" />
      <Sc02Body>{(view) => <Overview view={view} />}</Sc02Body>
    </main>
  );
}

function Overview({ view }: { view: Sc02View }) {
  const name = useUserName();
  const actor = useSc01((s) => s.actor);
  const issue = view.sc01.issue;
  const waiting = view.bpm?.waiting ?? [];
  const year = view.runs.find((r) => r.run_id === view.selectedRunId)?.result.periods.find((p) => p.kind === "year");
  return (
    <>
      <StatusPills view={view} />

      <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>장면 1 결과</CardTitle>
            <CardDescription>
              {formatClock(view.sc01.handed_off_at)} 인계 · <span className="font-mono">{view.sc01.run_id}</span>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p className="flex flex-wrap items-center gap-2">
              <span className="font-mono">{issue.issue_id}</span> b모델 7월 물량 감소 <RiskTag risk={issue.risk} /> · 열림
            </p>
            <p>
              검토 전망 {view.sc01.forecast} — <span className="font-medium">승인 전</span>. 2027 물량 영향 −1,400만원은 장면 1의
              계산이다.
            </p>
            <Commentary block>
              <p className="text-xs text-muted-foreground">
                장면 2는 장면 1 인계 시점의 결과를 근거로 쓴다(스냅샷). 장면 1을 초기화해도 장면 2의 근거는 바뀌지 않는다.
              </p>
            </Commentary>
            <Link href="/handoff" className="text-xs underline">
              장면 1 인계 화면
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>지금 기다리는 업무 {waiting.length}건</CardTitle>
            <CardDescription>
              {view.request === null
                ? "요청 접수 전 — 구매담당이 공문을 등록한다"
                : view.bpm?.runId
                  ? `BPM ${view.bpm.runId} · ${view.bpm.state}`
                  : "바깥 실행이 아직 NowView를 부르지 않았다"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {waiting.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {view.bpm?.state === "done" ? "흐름이 끝났다." : view.request ? "사람을 기다리는 곳이 없다." : (
                  <Link href="/sc02/request" className="underline">
                    단가 인상 요청 접수 화면으로
                  </Link>
                )}
              </p>
            ) : (
              <ul className="divide-y text-sm">
                {waiting.map((w) => (
                  <li key={w.nodeId} className="flex items-center justify-between gap-3 py-2">
                    <Link href={ROUTE_OF_NODE[w.nodeId] ?? "/sc02"} className="underline">
                      {w.title}
                    </Link>
                    <span className="text-xs text-muted-foreground">{w.role}</span>
                  </li>
                ))}
              </ul>
            )}
            {year?.computable ? (
              <p className="mt-3 border-t pt-3 text-sm">
                2027 통합 관리손익 <Won value={year.profit_combined} /> · Target 대비 부족 <Won value={year.target_gap} />{" "}
                <span className="text-xs text-muted-foreground">({view.selectedProvisional ? "잠정" : "승인안"} 기준)</span>
              </p>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>업무함 {view.tasks.length}건</CardTitle>
          <Commentary block>
            <CardDescription>
              확인·승인은 배정 다음 영업일 18시, 분석은 두 번째 영업일 18시가 기한이다. 외부 협상기한은 구매담당이 건별로 넣는다.
            </CardDescription>
          </Commentary>
        </CardHeader>
        <CardContent>
          {view.alerts.filter((a) => a.to.includes(actor)).map((a) => (
            <p key={a.alert_id} className="mb-2 flex items-center gap-1.5 text-xs">
              <AlarmClock aria-hidden className="size-3.5" style={{ color: "var(--viz-status-critical)" }} />
              {a.message}
            </p>
          ))}
          {view.tasks.length === 0 ? (
            <p className="text-sm text-muted-foreground">업무가 없다.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[40rem] text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th scope="col" className="py-2 pr-3 font-medium">업무</th>
                    <th scope="col" className="py-2 pr-3 font-medium">담당</th>
                    <th scope="col" className="py-2 pr-3 font-medium">배정</th>
                    <th scope="col" className="py-2 pr-3 font-medium">기한</th>
                    <th scope="col" className="py-2 font-medium">상태</th>
                  </tr>
                </thead>
                <tbody>
                  {view.tasks.map((t) => (
                    <tr key={t.task_id} className="border-b">
                      <th scope="row" className="py-2 pr-3 text-left font-normal">
                        <span className="font-mono text-xs">{t.task_id}</span> {TASK2_LABEL[t.type] ?? t.type}
                        {t.reopens ? <span className="block text-[11px] text-muted-foreground">{t.reopens}의 재작업</span> : null}
                      </th>
                      <td className="py-2 pr-3">{name(t.assigned_to)}</td>
                      <td className="py-2 pr-3 tabular-nums">{formatClock(t.assigned_at)}</td>
                      <td className="py-2 pr-3 tabular-nums">{formatClock(t.due_at)}</td>
                      <td className="py-2">
                        {t.status === "COMPLETED" ? "완료" : "진행 전"}
                        {t.overdue ? (
                          <span className="ml-1.5 inline-flex items-center gap-1 text-xs font-medium">
                            <AlarmClock aria-hidden className="size-3" style={{ color: "var(--viz-status-critical)" }} />
                            기한 초과
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}
