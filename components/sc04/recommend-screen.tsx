"use client";

import { useUserName } from "@/components/sc01/bits";
import { Mn, Sc04Body, Sc04Header, WaitingForms } from "@/components/sc04/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import type { Sc04View } from "@/lib/sc04/types";

/**
 * U403 우선 실행안 제안 — 개별 대응안의 당해연도 순효과·정상 연간 반복효과(별도 열)·효과 시작·리스크·책임 임원·예산을
 * 비교하고 담당 임원들이 2~3개를 제안한다. 우선순위는 효과액 자동 정렬이 아니다. 대응 조합 비교 화면은 만들지 않는다.
 */
export function Sc04RecommendScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc04Header id="U403" title="우선 실행안 제안" question="대표에게 선택을 떠넘기지 않고 담당 임원이 실행안을 제안하는가?" />
      <Sc04Body>{(view) => <Recommend view={view} />}</Sc04Body>
    </main>
  );
}

function Recommend({ view }: { view: Sc04View }) {
  const name = useUserName();
  const run = view.runs.find((r) => r.run_id === view.verification?.run_id && view.verification?.state === "VERIFIED");
  const rec = view.recommendation;
  const results = Object.fromEntries(view.results.flatMap((r) => r.alts.map((a) => [a, r.versions.at(-1)])));
  return (
    <>
      <WaitingForms view={view} nodes={["Recommend"]} labels={{ Recommend: "공동 제안 확정" }} />
      <Card>
        <CardHeader>
          <CardTitle>{rec ? `공동 제안 ${rec.ref}` : "대응안 비교"}</CardTitle>
          <CardDescription>
            {rec
              ? `${name(rec.confirmed_by)} ${formatClock(rec.confirmed_at)} · 담당 임원 확인 ${rec.owner_confirmations.map((o) => name(o.by)).join(", ")}`
              : run
                ? `${run.run_id} 검증 완료 결과로 비교한다.`
                : "검증을 통과한 계산이 있어야 비교한다."}
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {run ? (
            <table className="w-full min-w-[760px] text-sm" aria-label="대응안 비교">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-1.5 pr-3 font-medium">대응안</th>
                  <th className="py-1.5 pr-3 text-right font-medium">2027 순효과</th>
                  <th className="py-1.5 pr-3 text-right font-medium">정상 연간(참고)</th>
                  <th className="py-1.5 pr-3 font-medium">효과 시작</th>
                  <th className="py-1.5 pr-3 font-medium">책임 임원</th>
                  <th className="py-1.5 pr-3 text-right font-medium">준비 예산</th>
                  <th className="py-1.5 font-medium">우선순위 · 사유</th>
                </tr>
              </thead>
              <tbody className="divide-y align-top">
                {run.result.alts.map((a) => {
                  const it = rec?.items.find((i) => i.alt_id === a.alt_id);
                  const asm = view.assumptions.find((x) => x.alt_id === a.alt_id);
                  return (
                    <tr key={a.alt_id}>
                      <th scope="row" className="py-1.5 pr-3 text-left font-normal">
                        <span className="font-mono text-xs">{a.alt_id}</span> {a.name}
                      </th>
                      <td className="py-1.5 pr-3 text-right">
                        <Mn value={a.net_2027} />
                      </td>
                      <td className="py-1.5 pr-3 text-right text-muted-foreground">
                        <Mn value={a.normal_annual} />
                      </td>
                      <td className="py-1.5 pr-3 text-xs">{a.start.slice(0, 7)}</td>
                      <td className="py-1.5 pr-3 text-xs">{it ? name(it.owner) : "—"}</td>
                      <td className="py-1.5 pr-3 text-right">
                        <Mn value={asm?.budget ?? null} />
                      </td>
                      <td className="py-1.5 text-xs">
                        {it ? (
                          <>
                            {it.recommended ? <span className="font-medium">{it.priority}순위</span> : <span>제외</span>} — {it.reason}
                          </>
                        ) : (
                          <span className="text-muted-foreground">{results[a.alt_id]?.risks ?? ""}</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-muted-foreground">검증 전이다.</p>
          )}
          <Commentary>
            <p className="mt-2 text-xs text-muted-foreground">
              정상 연간 효과는 일회성비를 뺀 12개월 참고값이다 — 당해연도 효과와 더하지 않고, 기존 향후 12개월 전망에도 넣지 않는다. 예산은
              전환·검증·교육 등 일회성 준비비이고 개선효과와 섞지 않는다.
            </p>
          </Commentary>
        </CardContent>
      </Card>
      <Disclosure summary="EXCL44 고객·모델 물량 배분 — 이번 실행 제외(RES43)">
        <p className="text-xs">
          {rec?.excluded[0]?.reason ?? view.results.find((r) => r.result_id === "RES43")?.versions.at(-1)?.reason ?? "AT33 결과 제출 전"}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">효과 미산정 — 합산 제외(0원이 아니다). 분석 지시는 지우지 않고 검토 후 종결로 남는다.</p>
      </Disclosure>
    </>
  );
}
