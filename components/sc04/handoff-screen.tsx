"use client";

import { CheckCircle2, CircleDashed } from "lucide-react";

import { useUserName } from "@/components/sc01/bits";
import { Mn, Sc04Body, Sc04Header, StatusPills, WaitingForms } from "@/components/sc04/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { GATE_LABEL, gapWord, OUTCOME_LABEL } from "@/lib/sc04/format";
import type { Sc04View } from "@/lib/sc04/types";

/**
 * U408 종료 요건과 장면 5 인계 — 서버가 요건을 모두 검사한 뒤 HANDOFF41과 SC04_COMPLETED를 함께 저장한다. 장면 4 완료 /
 * 장면 5 계획 대기 / 실행 조건 미충족 / 위험 미해소를 따로 보인다. 예상 효과를 실적으로 보이지 않는다.
 */
export function Sc04HandoffScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc04Header id="U408" title="인계·종료 — 결정 실행·계획 갱신으로" question="실행 준비를 마쳤는가 — 성과는 아직 확인되지 않았다는 것까지 넘기는가?" />
      <Sc04Body>{(view) => <Handoff view={view} />}</Sc04Body>
    </main>
  );
}

function Handoff({ view }: { view: Sc04View }) {
  const name = useUserName();
  const h = view.handoff;
  const c = view.completion;
  return (
    <>
      <WaitingForms view={view} nodes={["Complete_Scene"]} labels={{ Complete_Scene: "개선안 검토·실행 승인 완료" }} />
      <StatusPills view={view} />
      <Card>
        <CardHeader>
          <CardTitle>종료 요건 {c.items.filter((i) => i.ok).length}/{c.items.length}</CardTitle>
          <CardDescription>버튼 노출만으로 완료되지 않는다 — 엔진이 다시 검사한다. CON41 미충족은 차단이 아니다.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <ul className="space-y-1 text-sm">
            {c.items.map((i) => (
              <li key={i.id} className="flex items-center gap-1.5">
                {i.ok ? (
                  <CheckCircle2 aria-hidden className="size-3.5" style={{ color: "var(--viz-status-good)" }} />
                ) : (
                  <CircleDashed aria-hidden className="size-3.5 text-muted-foreground" />
                )}
                {i.label}
              </li>
            ))}
          </ul>
          {!c.met && c.blocking.length ? (
            <p className="text-xs text-muted-foreground">남은 항목: {c.blocking.join(" · ")}</p>
          ) : null}
          {c.open_conditions.length ? (
            <p className="text-xs text-muted-foreground">미충족 조건 {c.open_conditions.join(", ")} — 계획 수립은 가능, 해당 실행 착수는 제한</p>
          ) : null}
        </CardContent>
      </Card>

      {h ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>인계 {h.handoff_id}</CardTitle>
              <CardDescription>
                {formatClock(h.as_of)} · {name(h.completed_by)} · {h.source_handoff} → {h.meeting} → {h.report} · {h.decision} · {h.approval} · {h.minutes}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
                <span>
                  기준 관리손익 <Mn value={h.financial_snapshot.baseline} /> · Target <Mn value={h.financial_snapshot.target} />
                </span>
                <span>
                  승인 범위 예상효과 <Mn value={h.financial_snapshot.effect} /> (조건부분 <Mn value={h.financial_snapshot.conditional_effect} />)
                </span>
                <span className="font-medium">
                  연간 남는 {gapWord(h.financial_snapshot.gap)} <Mn value={h.financial_snapshot.gap} />백만원 — 추가 발굴 DIR41
                </span>
                <span className="text-muted-foreground">
                  조건부 제외 비교 <Mn value={h.financial_snapshot.gap_excl_conditional} /> · 정상 연간 참고 <Mn value={h.financial_snapshot.normal_annual_reference} /> — 합산 금지
                </span>
              </div>
              <table className="w-full text-xs" aria-label="인계 실행과제">
                <thead className="text-left text-muted-foreground">
                  <tr>
                    <th className="py-1 pr-3 font-medium">과제</th>
                    <th className="py-1 pr-3 font-medium">책임</th>
                    <th className="py-1 pr-3 font-medium">계획 · 완료</th>
                    <th className="py-1 font-medium">실행 착수</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {h.actions.map((a) => (
                    <tr key={a.target_id}>
                      <th scope="row" className="py-1 pr-3 text-left font-normal">
                        <span className="font-mono">{a.target_id}</span> {a.alt_id} · {OUTCOME_LABEL[a.decision ?? ""]} · v{a.assignment_version}
                      </th>
                      <td className="py-1 pr-3">{name(a.owner)}</td>
                      <td className="py-1 pr-3">
                        {formatClock(a.plan_due)} · {formatClock(a.completion_due)}
                      </td>
                      <td className="py-1">{GATE_LABEL[a.execution_gate ?? ""] ?? a.execution_gate}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-xs text-muted-foreground">
                총괄 한도 <Mn value={h.budget.total} /> · 예정 <Mn value={h.budget.planned} /> · 여력 <Mn value={h.budget.headroom} /> · 상세 계획 {h.detail_plan === "PLAN_PENDING" ? "결정 실행·계획 갱신 수립 대기(빈 계획은 완료가 아니다)" : h.detail_plan}
              </p>
              {h.excluded.length ? (
                <p className="text-xs text-muted-foreground">
                  실행과제 없음: {h.excluded.map((e) => `${e.alt_id}${e.decision ? ` ${OUTCOME_LABEL[e.decision]}` : " 검토 후 제외"}`).join(", ")}
                </p>
              ) : null}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>다음 업무</CardTitle>
              <CardDescription>결정 실행·계획 갱신 — 세부 활동·일정·자원 배치의 상세 실행계획 수립</CardDescription>
            </CardHeader>
            <CardContent className="space-y-1 text-xs text-muted-foreground">
              <p>결정 실행·계획 갱신 이후(상세 계획 · 실행 품의 · 효과 검증 · Rolling)는 기획안에 이야기만 있다 — 설계표·데이터가 나오면 만든다. 수치를 지어내지 않는다.</p>
              <Commentary>
                <p>승인 이후 범위·책임·한도·기한이 바뀌면 새 판단·승인 버전과 대표 재확인으로 잇고, 원 인계는 그대로 둔 채 결정 실행·계획 갱신에 다시 알린다.</p>
              </Commentary>
            </CardContent>
          </Card>
        </>
      ) : null}

      <Disclosure summary={`감사 이력 — 최근 5건 / ${view.audit.length}건`}>
        <ul className="space-y-0.5 text-xs">
          {view.audit.slice(-5).map((a) => (
            <li key={a.seq}>
              {formatClock(a.at)} · {a.actor_name} · {a.action}
              {a.event_code ? <span className="ml-1 font-mono text-muted-foreground">{a.event_code}</span> : null}
            </li>
          ))}
        </ul>
      </Disclosure>
    </>
  );
}
