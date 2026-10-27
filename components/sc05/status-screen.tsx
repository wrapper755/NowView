"use client";

import { useState } from "react";
import Link from "next/link";
import { PlayCircle } from "lucide-react";

import { useUserName } from "@/components/sc01/bits";
import { Mn, Sc05Body, Sc05Header, StatusPills } from "@/components/sc05/bits";
import { Commentary } from "@/components/shared/commentary";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { sc05Api } from "@/lib/sc05/client";
import { CHECK_LABEL, CONDITION_STATE_LABEL, OPERATION_STATE_LABEL, PLAN_STATE_LABEL, TASK_NAME } from "@/lib/sc05/format";
import type { Sc05View } from "@/lib/sc05/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc05 } from "@/lib/store/sc05";

/**
 * U501 실행과제 현황 — 승인서·총괄 책임 아래 ACT41~43의 계획 확정 · 경영관리 확인 · 조건 · 착수 · 기한 · 예산을 **따로
 * 열로** 보인다(M501·M502·M509). 인수 완료를 착수·조건 충족으로 보이지 않는다. ACT41·43은 요약과 근거만이다.
 */
export function Sc05StatusScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc05Header id="U501" title="실행과제 현황" question="승인한 과제가 누구의 책임으로 어디까지 준비됐는가?" />
      <Sc05Body>{(view) => <Body view={view} />}</Sc05Body>
    </main>
  );
}

function Body({ view }: { view: Sc05View }) {
  const nameOf = useUserName();
  const h = view.sc04.handoff;
  const fs = h.financial_snapshot;
  return (
    <>
      <StatusPills view={view} />
      {view.sceneInfo.started_at === null ? <StartCard view={view} /> : null}

      <Card>
        <CardHeader>
          <CardTitle>개선안 검토·실행 승인 승인서와 전체 책임</CardTitle>
          <CardDescription>
            {view.sc04.approval.approval_id} · 판단본 {h.decision} · 회의록 {h.minutes} · 전체 책임 {nameOf(h.overall_owner)} · 인계 {formatClock(h.as_of)}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 text-sm sm:grid-cols-4">
          <div>
            <p className="text-xs text-muted-foreground">대응 전 연간 목표 부족</p>
            <p className="text-lg font-semibold">
              <Mn value={view.sc04.gap_before} />
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">판단 예상효과(DEC41-v2 · 실적 아님)</p>
            <p className="text-lg font-semibold">
              <Mn value={fs.effect} />
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">반영 후 남는 부족(개선안 검토·실행 승인)</p>
            <p className="text-lg font-semibold">
              <Mn value={fs.gap} />
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">총괄 일회성 한도</p>
            <p className="text-lg font-semibold">
              <Mn value={view.sc04.approval.total_budget} />
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>ACT41~43 실행 상태</CardTitle>
          <CardDescription>계획 확정과 경영관리 확인, 조건, 착수는 서로 다른 상태다. ACT42만 상세 시연이다.</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[56rem] text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th className="py-1.5 pr-3 font-medium">과제</th>
                <th className="pr-3 font-medium">책임 임원</th>
                <th className="pr-3 font-medium">유효 계획</th>
                <th className="pr-3 font-medium">임원 확정</th>
                <th className="pr-3 font-medium">경영관리 확인</th>
                <th className="pr-3 font-medium">조건</th>
                <th className="pr-3 font-medium">운영</th>
                <th className="pr-3 font-medium">완료기한</th>
                <th className="pr-3 text-right font-medium">일회성 한도·집행·가용(백만원)</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {(["ACT41", "ACT42", "ACT43"] as const).map((t) => {
                const a = view.sc04.actions[t];
                const plans = view.plans.filter((p) => p.task_id === t);
                const plan = t === "ACT42" ? (view.plans.find((p) => p.plan_id === view.planPointer) ?? plans.at(-1)) : plans.at(-1);
                const op = view.operation.find((o) => o.task_id === t);
                const b = view.budget.tasks.find((x) => x.task_id === t);
                return (
                  <tr key={t}>
                    <th scope="row" className="py-2 pr-3 text-left font-medium">
                      {t === "ACT42" ? (
                        <Link href="/sc05/plan" className="underline">
                          {t} {TASK_NAME[t]}
                        </Link>
                      ) : (
                        <>
                          {t} {TASK_NAME[t]}
                        </>
                      )}
                      <span className="block text-[11px] font-normal text-muted-foreground">{t === "ACT42" ? "상세 시연" : "배경 요약"}</span>
                    </th>
                    <td className="pr-3">{nameOf(a.owner)}</td>
                    <td className="pr-3">{plan ? `${plan.plan_id} ${PLAN_STATE_LABEL[plan.state] ?? plan.state}` : "작성 전"}</td>
                    <td className="pr-3">{plan?.confirmed_at ? formatClock(plan.confirmed_at) : "—"}</td>
                    <td className="pr-3">{plan ? (CHECK_LABEL[plan.management_check] ?? plan.management_check) : "—"}</td>
                    <td className="pr-3">
                      {a.conditions?.length
                        ? a.conditions.map((c) => `${c} ${CONDITION_STATE_LABEL[view.conditions.find((x) => x.condition_id === c)?.state ?? "OPEN"]}`).join(", ")
                        : "없음"}
                    </td>
                    <td className="pr-3">{op ? (OPERATION_STATE_LABEL[op.state] ?? op.state) : "—"}</td>
                    <td className="pr-3">{formatClock(a.completion_due)}</td>
                    <td className="pr-3 text-right tabular-nums">
                      <Mn value={b?.limit} /> · <Mn value={b?.paid} /> · <Mn value={b?.available} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <Commentary>
            <p className="mt-2 text-xs text-muted-foreground">
              사용가능액 = 한도 − 집행 − 미집행 확정 약정. 운영지원비(OP51)는 별도 운영예산이라 이 표의 일회성 한도와 섞지 않는다.
            </p>
          </Commentary>
        </CardContent>
      </Card>

      <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>미완료 조건·지원·추가과제</CardTitle>
            <CardDescription>인수는 책임을 넘겨받은 것이지 이행 완료가 아니다.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {view.conditions.map((c) => (
              <p key={c.condition_id}>
                <span className="font-medium">{c.condition_id}</span> {CONDITION_STATE_LABEL[c.state] ?? c.state} · 기한 {formatClock(c.due_at)} · {c.content}
              </p>
            ))}
            {view.sc04.directives.DIR41 ? (
              <p>
                <span className="font-medium">DIR41</span> 추가 개선과제 발굴 · 기한 {formatClock(view.sc04.directives.DIR41.due_at)} · 기대효과{" "}
                <span className="text-muted-foreground">미산정 — 전망에 넣지 않는다</span>
                {view.directiveLog.map((d) => (
                  <span key={d.at} className="block text-xs text-muted-foreground">
                    {formatClock(d.at)} 후속 검토 진행 보고({d.ref}) — 후보 조사 지속
                  </span>
                ))}
              </p>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>ACT42 승인 내용</CardTitle>
            <CardDescription>긴급구매 축소 — 구매 임원 책임, 생산 임원 협조(SUP41)</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p>
              당해연도 예상효과 <Mn value={view.sc04.actions.ACT42.expected_effect} /> 백만원 · 실행 준비 한도 <Mn value={view.sc04.actions.ACT42.budget} /> 백만원
            </p>
            <p>
              계획 제출 {formatClock(view.sc04.actions.ACT42.plan_due)} · 효과 개시 2027-09 · 과제 완료 {formatClock(view.sc04.actions.ACT42.completion_due)}
            </p>
            <p className="text-xs text-muted-foreground">
              9~12월 월 반복효과에서 8월 준비비를 뺀 예상치다 — 실적이 아니다. 반복 운영지원비 월 20만원은 기존 운영예산·정상 품의 대상이다.
            </p>
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function StartCard({ view }: { view: Sc05View }) {
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const start = async () => {
    if (!demoRunId) return;
    setBusy(true);
    setError(null);
    const r = await sc05Api.start(demoRunId, actor, crypto.randomUUID());
    setBusy(false);
    if (r.ok) useSc05.getState().setLive(r.data);
    else setError(`${r.status} — ${r.error}`);
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>결정 실행·계획 갱신 착수</CardTitle>
        <CardDescription>경영관리 담당이 HANDOFF41을 기존 검토건 MR-2706-01에 잇는다 — 새 검토건을 만들지 않는다.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <Button size="sm" onClick={() => void start()} disabled={busy || view.historical || actor !== "u-fin"}>
          <PlayCircle aria-hidden className="size-3.5" />
          {busy ? "착수하는 중…" : "결정 실행·계획 갱신 착수"}
        </Button>
        {actor !== "u-fin" ? <p className="text-xs text-muted-foreground">경영관리담당만 할 수 있다 — 상단에서 역할을 바꾼다.</p> : null}
        {error ? (
          <p role="alert" className="text-xs" style={{ color: "var(--viz-status-critical)" }}>
            거절됨: {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
