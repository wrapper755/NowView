"use client";

import { useUserName } from "@/components/sc01/bits";
import { Sc03Body, Sc03Header, StatusPills, WaitingForms } from "@/components/sc03/bits";
import { Commentary } from "@/components/shared/commentary";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { CATEGORY_LABEL, DEPT_LABEL, DEPT_STATE_LABEL, QUESTION_STATE_LABEL } from "@/lib/sc03/format";
import type { Sc03View } from "@/lib/sc03/types";

/**
 * U33 부서 확인과 쟁점 정리 — 부서별 응답 현황, 사실·가정·미확인, 이견·보완, 차단 여부·담당·기한.
 * **무응답은 동의가 아니다**(CT34). 초안이 그 부서 범위를 바꾸면 이전 확인은 「재확인 필요」다.
 */
export function Sc03ConfirmScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc03Header id="U33" title="부서 확인 · 쟁점 정리" question="분석의 사실·가정·미확인을 각 부서가 확인했는가?" />
      <Sc03Body>{(view) => <Confirm view={view} />}</Sc03Body>
    </main>
  );
}

const STATE_TONE: Record<string, string | undefined> = {
  RESPONDED: "var(--viz-status-good)",
  DISPUTED: "var(--viz-status-critical)",
  STALE: "var(--viz-status-serious)",
};

function Confirm({ view }: { view: Sc03View }) {
  const name = useUserName();
  const confirmNodes = ["Confirm_Sales", "Confirm_Buy", "Confirm_Prod", "Revise_Sales", "Revise_Buy", "Revise_Prod"];
  return (
    <>
      <StatusPills view={view} />
      <Card>
        <CardHeader>
          <CardTitle>부서 응답 현황</CardTitle>
          <CardDescription>
            {view.confirmation
              ? `${view.confirmation.report_id} 확인 요청 · ${formatClock(view.confirmation.requested_at)} · 회신기한 ${formatClock(view.confirmation.due_at)}`
              : "아직 확인 요청 전이다 — 통합 분석 저장 뒤 경영관리가 요청한다."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="grid gap-2 sm:grid-cols-3">
            {view.departments.map((d) => (
              <li key={d.dept} className="rounded-md border px-3 py-2 text-sm">
                <p className="flex items-center justify-between gap-2">
                  <span className="font-medium">{d.label}</span>
                  <span className="text-xs" style={{ color: STATE_TONE[d.state] }}>
                    {DEPT_STATE_LABEL[d.state]}
                  </span>
                </p>
                <p className="text-xs text-muted-foreground">
                  {name(d.user)}
                  {d.reply ? ` · ${formatClock(d.reply.at)} · ${d.reply.report_id}` : ""}
                </p>
                {d.reply?.opinion ? <p className="mt-1 text-xs">의견: {d.reply.opinion}</p> : null}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <WaitingForms
        view={view}
        nodes={confirmNodes}
        labels={Object.fromEntries(confirmNodes.map((n) => [n, n.startsWith("Revise") ? "보완 — 새 버전" : "회신"]))}
      />

      <Card>
        <CardHeader>
          <CardTitle>사실 · 가정 · 미확인</CardTitle>
          <CardDescription>확인부서·확인자·시각과 근거. 가정은 사실이 아니고, 미확인은 0이 아니다.</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {view.facts.length === 0 ? (
            <p className="text-sm text-muted-foreground">아직 회신이 없다.</p>
          ) : (
            <table aria-label="사실 확인표" className="w-full min-w-[40rem] text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th scope="col" className="py-2 pr-3 font-medium">id</th>
                  <th scope="col" className="py-2 pr-3 font-medium">부서</th>
                  <th scope="col" className="py-2 pr-3 font-medium">분류</th>
                  <th scope="col" className="py-2 pr-3 font-medium">내용</th>
                  <th scope="col" className="py-2 pr-3 font-medium">확인</th>
                </tr>
              </thead>
              <tbody>
                {view.facts.map((f) => (
                  <tr key={f.fact_id} className="border-b align-top last:border-0">
                    <th scope="row" className="py-1.5 pr-3 text-left font-mono text-xs font-normal">{f.fact_id}</th>
                    <td className="py-1.5 pr-3 text-xs">{DEPT_LABEL[f.dept] ?? f.dept}</td>
                    <td className="py-1.5 pr-3 text-xs">
                      {CATEGORY_LABEL[f.category]}
                      {f.state === "DISPUTED" ? <span style={{ color: "var(--viz-status-critical)" }}> · 이견</span> : null}
                    </td>
                    <td className="py-1.5 pr-3">
                      {f.statement}
                      <span className="block text-xs text-muted-foreground">근거 {f.evidence_ref}{f.followup_ref ? ` · 후속 ${f.followup_ref}` : ""}</span>
                    </td>
                    <td className="py-1.5 pr-3 text-xs text-muted-foreground">
                      {name(f.reviewer)}
                      <br />
                      {formatClock(f.confirmed_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <WaitingForms
        view={view}
        nodes={["Register_Gap", "Judge_Questions"]}
        initial={{ Judge_Questions: { Q31담당자: "u-prod-lead", Q32담당자: "u-fin-lead" } }}
        labels={{ Register_Gap: "쟁점 등록", Judge_Questions: "처리 확정" }}
      />

      <Card>
        <CardHeader>
          <CardTitle>쟁점 · 미확인 처리</CardTitle>
          <CardDescription>계산 오류·핵심 조건 불명은 차단, 비핵심 미확인은 담당·기한·처리방향을 붙여 조건부 보고(CT35).</CardDescription>
        </CardHeader>
        <CardContent>
          {view.questions.length === 0 ? (
            <p className="text-sm text-muted-foreground">쟁점이 없다.</p>
          ) : (
            <ul className="divide-y text-sm">
              {view.questions.map((q) => (
                <li key={q.question_id} className="space-y-0.5 py-2">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs">{q.question_id}</span>
                    <span className="text-xs text-muted-foreground">← {q.fact_ref}</span>
                    <span
                      className="rounded border px-1.5 py-0.5 text-[10px]"
                      style={{ color: q.state === "BLOCKING" || (q.kind === "DISPUTE" && q.state === "OPEN") ? "var(--viz-status-critical)" : undefined }}
                    >
                      {q.kind === "DISPUTE" ? "이견 · " : ""}
                      {QUESTION_STATE_LABEL[q.state] ?? q.state}
                    </span>
                  </p>
                  <p>{q.question}</p>
                  {q.treatment ? (
                    <p className="text-xs text-muted-foreground">
                      담당 {name(q.owner)} · 기한 {formatClock(q.due_at)} · {q.treatment} — {name(q.decision_by)} {formatClock(q.decided_at)}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          {view.freezeProblems.length ? (
            <p className="mt-3 text-xs" style={{ color: "var(--viz-status-serious)" }}>
              자료 확정 전 남은 것: {view.freezeProblems.join(" · ")}
            </p>
          ) : null}
          <Commentary>
            <p className="mt-2 text-xs text-muted-foreground">
              Q31(회피가능 고정비)·Q32(기존 부족 원인)는 현재 손익 계산을 바꾸는 오류가 아니다 — 비차단으로 두고 분석과제 AT31·AT34로 잇는다.
            </p>
          </Commentary>
        </CardContent>
      </Card>
    </>
  );
}
