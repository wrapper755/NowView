"use client";

import { useUserName } from "@/components/sc01/bits";
import { AgentCard } from "@/components/sc05/agent-card";
import { Mn, Sc05Body, Sc05Header, Tile, WaitingForms } from "@/components/sc05/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { CAUSE_LABEL, FORECAST_STATE_LABEL, gapWord } from "@/lib/sc05/format";
import type { Sc05View } from "@/lib/sc05/types";

const NODES = ["Draft_Forecast", "Confirm_FC_BUY", "Confirm_FC_PROD", "Confirm_FC_SALES", "Submit_Forecast", "Approve_Forecast", "Publish_Forecast"];
const DEPT_LABEL: Record<string, string> = { BUY: "구매", PROD: "생산", SALES: "판매 물량" };

/**
 * U507 Forecast 검토·승인 — Target · 종전 공식본 · 이번 검토안 · 목표 부족을 위에 두고, 월별 마감 Actual·잔여
 * Forecast, 변경 원인 대사, 부서 확인·대표 승인 이력을 보인다. **검토안은 공식 지표를 덮어쓰지 않는다** — 승인·게시
 * 뒤에만 공식 포인터가 바뀐다. 장면 4 판단 검토안(DEC41-v2)은 별도 참고이고 공식본이 아니다.
 */
export function Sc05ForecastScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc05Header id="U507" title="공식 Forecast 검토·승인" question="최신 실적과 남은 기간 가정으로 연간 전망은 얼마이고, 왜 바뀌었는가?" />
      <Sc05Body>{(view) => <Body view={view} />}</Sc05Body>
    </main>
  );
}

function Body({ view }: { view: Sc05View }) {
  const nameOf = useUserName();
  const waiting = new Set((view.bpm?.waiting ?? []).map((w) => w.nodeId));
  const official = view.forecasts.find((f) => f.forecast_id === view.official);
  const review = view.forecasts.find((f) => f.forecast_id === view.reviewForecastId);
  const run = view.runs.find((r) => r.run_id === review?.run_id);
  const fc50 = view.forecasts.find((f) => f.forecast_id === "FC50");
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile label="Target(연간 · 유지)" note="전망·계획으로 바꾸지 않는다">
          <Mn value={run?.target ?? null} empty="—" />
        </Tile>
        <Tile label={`공식본 ${view.official ?? ""}`} note={official ? `승인 ${formatClock(official.approved_at)}` : "해당 시점 공식본 미적재"}>
          <Mn value={official?.annual ?? null} empty="미적재" />
        </Tile>
        <Tile label={`이번 검토안 ${review?.forecast_id ?? ""}`} note={review ? (FORECAST_STATE_LABEL[review.state] ?? review.state) : "작성 전"}>
          <Mn value={run?.annual ?? null} empty="—" />
        </Tile>
        <Tile label={`남는 연간 ${gapWord(run?.gap)}`} note="Target − 이번 전망 · Risk OPEN">
          <Mn value={run?.gap ?? null} empty="—" />
        </Tile>
      </div>

      <WaitingForms
        view={view}
        nodes={NODES}
        expect={(n) => (review && n !== "Draft_Forecast" && n !== "Publish_Forecast" ? { forecast: review.forecast_id, run: review.run_id } : undefined)}
        labels={{ Draft_Forecast: "작성·대사", Submit_Forecast: "대표 승인 요청", Approve_Forecast: "결정", Publish_Forecast: "게시·공유" }}
      />
      {view.forecastBlocking.length && review && review.state !== "PUBLISHED" && review.state !== "APPROVED" ? (
        <p className="rounded-md border px-3 py-2 text-xs">
          제출 전 남은 것: {view.forecastBlocking.join(" · ")}
        </p>
      ) : null}
      <AgentCard view={view} kind="AG57" canRequest={waiting.has("Draft_Forecast")} />

      {run ? (
        <Card>
          <CardHeader>
            <CardTitle>월별 관리손익 — {run.run_id}</CardTitle>
            <CardDescription>
              1~9월 마감 Actual(읽기 전용) + 10~12월 Forecast. 과제 전 기초 손익에 과제 순효과를 한 번 더하고 공장 고정비를 한 번 뺀다. FC50과 같은 행에 두되
              더하지 않는다.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full min-w-[48rem] text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-1.5 pr-3 font-medium">월</th>
                  <th className="pr-3 font-medium">구분</th>
                  <th className="pr-3 text-right font-medium">Target</th>
                  <th className="pr-3 text-right font-medium">과제 전</th>
                  <th className="pr-3 text-right font-medium">과제 순효과</th>
                  <th className="pr-3 text-right font-medium">이번 전망</th>
                  <th className="pr-3 text-right font-medium">FC50</th>
                  <th className="pr-3 text-right font-medium">목표 부족</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {run.months.map((m) => {
                  const old = fc50?.months?.find((x) => x.period === m.period);
                  return (
                    <tr key={m.period}>
                      <th scope="row" className="py-1.5 pr-3 text-left font-medium">
                        {Number(m.period.slice(5, 7))}월
                      </th>
                      <td className="pr-3 text-xs">{m.kind === "ACTUAL" ? "마감" : "전망"}</td>
                      <td className="pr-3 text-right">
                        <Mn value={m.target} />
                      </td>
                      <td className="pr-3 text-right">
                        <Mn value={m.basis_profit} />
                      </td>
                      <td className="pr-3 text-right">
                        <Mn value={m.effect} signed />
                      </td>
                      <td className="pr-3 text-right font-medium">
                        <Mn value={m.profit} />
                      </td>
                      <td className="pr-3 text-right text-muted-foreground">
                        <Mn value={old?.profit ?? null} empty="—" />
                      </td>
                      <td className="pr-3 text-right">
                        <Mn value={m.gap} />
                      </td>
                    </tr>
                  );
                })}
                {(["closed", "forecast", "year"] as const).map((k) => (
                  <tr key={k} className="font-medium">
                    <th scope="row" className="py-1.5 pr-3 text-left">
                      {run.periods[k].label}
                    </th>
                    <td />
                    <td className="pr-3 text-right">
                      <Mn value={run.periods[k].target} />
                    </td>
                    <td className="pr-3 text-right">
                      <Mn value={run.periods[k].basis_profit} />
                    </td>
                    <td className="pr-3 text-right">
                      <Mn value={run.periods[k].effect} signed />
                    </td>
                    <td className="pr-3 text-right">
                      <Mn value={run.periods[k].profit} />
                    </td>
                    <td className="pr-3 text-right text-muted-foreground">{k === "year" ? <Mn value={fc50?.annual ?? null} empty="—" /> : null}</td>
                    <td className="pr-3 text-right">
                      <Mn value={run.periods[k].gap} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-1 text-xs text-muted-foreground">
              음수 목표 부족은 목표 초과다. 마감기간 과제효과 {Number(run.periods.closed.effect).toLocaleString("ko-KR")}원도 회피비용 비교모형을 포함한다 — 연간
              전체를 실현효과로 보이지 않는다.
            </p>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-2">
        {run ? (
          <Card>
            <CardHeader>
              <CardTitle>변경 원인 대사 — 종전 {run.prior_official} 대비</CardTitle>
              <CardDescription>서로 배타적인 원인만 더한다. 설명되지 않는 차이가 0이어야 제출할 수 있다.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>
                종전 <Mn value={run.reconciliation.prior_total} /> → 이번 <Mn value={run.reconciliation.new_total} /> · 변화{" "}
                <Mn value={run.reconciliation.delta} signed />
              </p>
              <ul className="space-y-0.5 text-xs">
                {run.reconciliation.rows.map((r) => (
                  <li key={`${r.cause}-${r.month}`}>
                    {Number(r.month.slice(5, 7))}월 {CAUSE_LABEL[r.cause] ?? r.cause} <Mn value={r.amount} signed />
                  </li>
                ))}
                {run.reconciliation.rows.length === 0 ? <li>변화 원인 없음</li> : null}
              </ul>
              <p className={run.reconciliation.ok ? "text-xs" : "text-xs font-medium"} style={run.reconciliation.ok ? undefined : { color: "var(--viz-status-critical)" }}>
                대사 차이 {Number(run.reconciliation.residual).toLocaleString("ko-KR")}원{run.reconciliation.ok ? "" : " — 이미 반영된 효과를 다시 더했는지 본다"}
              </p>
              {run.errors.length ? (
                <ul className="list-disc pl-4 text-xs" style={{ color: "var(--viz-status-serious)" }}>
                  {run.errors.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              ) : null}
            </CardContent>
          </Card>
        ) : null}
        <Card>
          <CardHeader>
            <CardTitle>버전과 승인 이력</CardTitle>
            <CardDescription>검토안과 공식본은 같은 RUN의 승인 전후 참조다 — 버전 행을 합산하지 않는다.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p className="text-xs text-muted-foreground">
              참고(공식본 아님): 개선안 검토·실행 승인 판단 검토안 {view.sc04.handoff.decision} — 예상효과 <Mn value={view.sc04.handoff.financial_snapshot.effect} /> 백만원
            </p>
            {view.forecasts.map((f) => (
              <div key={f.forecast_id} className="text-xs">
                <p className="font-medium">
                  {f.forecast_id} · {f.kind === "OFFICIAL" ? "공식본" : "검토안"} · {FORECAST_STATE_LABEL[f.state] ?? f.state}
                  {f.forecast_id === view.official ? " · 지금 공식본" : ""}
                </p>
                {f.confirmations && Object.keys(f.confirmations).length ? (
                  <p className="text-muted-foreground">
                    부서 확인 —{" "}
                    {Object.entries(f.confirmations)
                      .map(([d, c]) => `${DEPT_LABEL[d] ?? d} ${nameOf(c.by)} ${c.at.slice(11, 16)}`)
                      .join(" · ")}
                  </p>
                ) : null}
                {f.approved_at ? (
                  <p className="text-muted-foreground">
                    대표 승인 {formatClock(f.approved_at)}
                    {f.published_at ? ` · 게시 ${formatClock(f.published_at)}` : ""}
                  </p>
                ) : null}
                {f.return_reason ? <p style={{ color: "var(--viz-status-serious)" }}>반려 — {f.return_reason}</p> : null}
                {f.stale_reason ? <p className="text-muted-foreground">낡음 — {f.stale_reason}</p> : null}
                {f.note ? <p className="text-muted-foreground">{f.note}</p> : null}
              </div>
            ))}
            {view.forecasts.length === 0 ? <p className="text-xs text-muted-foreground">이 시점에는 공식 전망이 적재되지 않았다(FC50은 9/6 승인).</p> : null}
            <Disclosure summary={`공유 기록 ${view.shares.length}건`}>
              <ul className="text-xs">
                {view.shares.map((s) => (
                  <li key={s.share_id}>
                    {s.share_id} {s.object} → {s.recipients} · {formatClock(s.at)}
                  </li>
                ))}
              </ul>
            </Disclosure>
            <Commentary>
              <p className="text-xs text-muted-foreground">
                대표의 승인은 공식 성과 전망의 갱신이다 — 승인 범위 안에서 이미 확정된 실행계획을 다시 승인하는 절차와 다르다. 반려되면 종전 공식본이 그대로다.
              </p>
            </Commentary>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
