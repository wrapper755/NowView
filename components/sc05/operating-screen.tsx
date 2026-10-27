"use client";

import { useUserName } from "@/components/sc01/bits";
import { AgentCard } from "@/components/sc05/agent-card";
import { Sc05Body, Sc05Header, WaitingForms } from "@/components/sc05/bits";
import { Commentary } from "@/components/shared/commentary";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { OPERATION_STATE_LABEL, TASK_NAME } from "@/lib/sc05/format";
import type { Sc05View } from "@/lib/sc05/types";

const NODES = ["Confirm_OPL51", "Confirm_OPL52", "Confirm_OPL53", "Verify_OPL51", "Verify_OPL52", "Verify_OPL53"];
const PLAN_TASK: Record<string, string> = { OPL51: "ACT42", OPL52: "ACT41", OPL53: "ACT43" };

/**
 * U506 월간 운영계획 — 9월까지 마감 실적을 잠그고 10~12월 가정만 고친다. 담당 임원 확정과 경영관리 확인이 따로다.
 * ACT41·43은 요약과 반영 근거만 — 상세 활동 시연은 없다. 자료가 확인되지 않은 효과는 확정 반영하지 않는다.
 */
export function Sc05OperatingScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc05Header id="U506" title="월간 운영계획" question="9월 실적과 최신 조건으로 남은 석 달의 계획을 어떻게 바꾸는가?" />
      <Sc05Body>{(view) => <Body view={view} />}</Sc05Body>
    </main>
  );
}

function Body({ view }: { view: Sc05View }) {
  const nameOf = useUserName();
  const waiting = new Set((view.bpm?.waiting ?? []).map((w) => w.nodeId));
  return (
    <>
      <p className="text-sm">
        Rolling 기준 — 실적 마감 2027-09(1~9월 잠금) · 전망 10~12월
        {view.observation ? ` · 초기 결과 ${view.observation.observation_id} 확인` : " · 초기 결과 확인 전"}
      </p>
      <WaitingForms view={view} nodes={NODES} labels={{ Confirm_OPL51: "확정", Confirm_OPL52: "확정", Confirm_OPL53: "확정" }} />
      <AgentCard view={view} kind="AG56" canRequest={waiting.has("Confirm_OPL51")} />

      <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-3">
        {(["OPL51", "OPL52", "OPL53"] as const).map((pid) => {
          const p = view.operatingPlans.find((x) => x.plan_id === pid);
          const task = PLAN_TASK[pid];
          const op = view.operation.find((o) => o.task_id === task);
          const bg = view.plans.find((x) => x.task_id === task && x.background);
          return (
            <Card key={pid}>
              <CardHeader>
                <CardTitle>
                  {pid} {task} {TASK_NAME[task]}
                </CardTitle>
                <CardDescription>
                  {task === "ACT42" ? "상세 시연 과제" : "배경 과제 — 요약·근거만"} · 운영 {op ? (OPERATION_STATE_LABEL[op.state] ?? op.state) : "—"}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                {p ? (
                  <>
                    <p>{p.remaining_plan}</p>
                    {p.assumptions.urgent ? (
                      <p className="tabular-nums">
                        긴급 건수 가정 — 10월 {p.assumptions.urgent["2027-10-01"]}건 · 11월 {p.assumptions.urgent["2027-11-01"]}건 · 12월{" "}
                        {p.assumptions.urgent["2027-12-01"]}건
                      </p>
                    ) : null}
                    {p.assumptions.qty !== undefined ? <p className="tabular-nums">월 적용량 {p.assumptions.qty.toLocaleString("ko-KR")}</p> : null}
                    {p.assumptions.fixed_saving !== undefined ? <p className="text-xs">고정비 절감 0 — 공장 고정비 월 370백만원 유지</p> : null}
                    {p.assumptions.stabilize_due ? <p className="text-xs">안정화 확인 {formatClock(p.assumptions.stabilize_due)} — 기한 미도래를 완료로 보지 않는다</p> : null}
                    {p.assumption_note ? <p className="text-xs text-muted-foreground">{p.assumption_note}</p> : null}
                    <p className="text-xs">
                      확정 {nameOf(p.owner_confirm.by)} {formatClock(p.owner_confirm.at)} · 경영관리{" "}
                      {p.management_verify ? `${nameOf(p.management_verify.by)} ${formatClock(p.management_verify.at)}` : "확인 대기"}
                    </p>
                    {p.progress ? <p className="text-xs text-muted-foreground">진행 — {p.progress}</p> : null}
                  </>
                ) : (
                  <p className="text-muted-foreground">아직 제출 전이다.</p>
                )}
                {bg ? (
                  <p className="text-xs text-muted-foreground">
                    상세 계획 {bg.plan_id} — {bg.summary} · 경영관리 확인 {formatClock(bg.verified_at)}
                  </p>
                ) : null}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>배경 과제의 반영 근거</CardTitle>
          <CardDescription>공식 전망이 세 과제의 효과를 포함하므로 두 과제의 현재 상태와 가정도 근거로 확인한다.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {view.evidence
            .filter((e) => ["DOC54", "DOC55", "DOC54-H"].includes(e.evidence_id))
            .map((e) => (
              <p key={e.evidence_id}>
                <span className="font-mono text-xs">{e.evidence_id}</span> {e.type} — {e.body}
                <span className="block text-xs text-muted-foreground">
                  작성 {formatClock(e.written_at)}
                  {e.confirmed_at ? ` · 확인 ${nameOf(e.confirmed_by)} ${formatClock(e.confirmed_at)}` : " · 확인 전"}
                </span>
              </p>
            ))}
          <Commentary>
            <p className="text-xs text-muted-foreground">
              상세 화면을 시연하지 않는다는 이유로 효과를 무조건 실현 가능으로 처리하지 않는다 — 각 담당 임원이 가정을 확정하고 경영관리가 확인해야 전망 작성
              자료가 된다.
            </p>
          </Commentary>
        </CardContent>
      </Card>
    </>
  );
}
