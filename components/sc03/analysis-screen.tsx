"use client";

import { useState } from "react";

import { useUserName } from "@/components/sc01/bits";
import { Mn, Sc03Body, Sc03Header, StatusPills, WaitingForms } from "@/components/sc03/bits";
import { BridgeChart } from "@/components/sc03/bridge-chart";
import { AgentCard } from "@/components/sc03/agent-card";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock, modelLabel } from "@/lib/sc01/format";
import type { Period, Sc03View } from "@/lib/sc03/types";

const PERIOD_KINDS = ["year", "q3", "remaining", "next12"] as const;
type PeriodKind = (typeof PERIOD_KINDS)[number];
const PERIOD_LABEL: Record<PeriodKind, string> = { year: "2027 연간", q3: "Q3", remaining: "잔여 7~12월", next12: "향후 12개월" };

/**
 * U32 통합 손익영향 분석 — 상단 KPI(Target·통합·전체 부족·신규 영향), 중앙 브리지, 하단 a~e 모델·월별, 근거·가정.
 * **기존 부족과 이번 사건의 추가 악화를 따로 보인다**(DEC37) — 하나만 보이면 사건이 목표 차이 전부를 만든 것처럼 읽힌다.
 */
export function Sc03AnalysisScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc03Header id="U32" title="통합 손익영향 분석" question="무엇이 변했고 목표에 얼마나 영향을 주는가?" />
      <Sc03Body>{(view) => <Analysis view={view} />}</Sc03Body>
    </main>
  );
}

function Analysis({ view }: { view: Sc03View }) {
  const [kind, setKind] = useState<PeriodKind>("year");
  const name = useUserName();
  const passed = [...view.runs].reverse().find((r) => r.result.passed && !r.variant);
  const latest = view.runs.find((r) => r.run_id === view.latestRunId);
  const blocked = latest && !latest.result.passed ? latest : null;
  const p: Period | undefined = passed?.result.periods[kind];
  const year = passed?.result.periods.year;
  return (
    <>
      <StatusPills view={view} />
      <WaitingForms
        view={view}
        nodes={["Save_Analysis", "Fix_Calc", "Request_Confirm"]}
        initial={{ Save_Analysis: { 기준확인: "확인" }, Request_Confirm: { 회신기한: view.schedule.confirm_due } }}
        labels={{ Save_Analysis: "통합 분석 저장", Fix_Calc: "정정·재계산", Request_Confirm: "확인 요청" }}
      />

      {blocked ? (
        <Card>
          <CardHeader>
            <CardTitle>정합 검증 실패 — {blocked.run_id}</CardTitle>
            <CardDescription>보고 확정·부서 확인 요청이 막힌다(CT33). Agent 문장이나 조건부 수용으로 덮지 않는다.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="list-disc space-y-1 pl-4 text-sm" style={{ color: "var(--viz-status-critical)" }}>
              {blocked.result.failed_checks.slice(0, 4).map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {!passed || !year ? (
        <Card>
          <CardHeader>
            <CardTitle>아직 통합 분석이 없다</CardTitle>
            <CardDescription>착수 뒤 경영관리 담당이 기준을 확인하고 분석을 저장한다.</CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi label="2027 Target 관리손익" value={year.target} note="이번 사건으로 바꾸지 않는다" />
            <Kpi label="통합 전망" value={year.combined} note="두 사건 반영 후 공장관리손익" />
            <Kpi label="Target 대비 전체 부족" value={year.total_gap} note={<>기존 부족 <Mn value={year.existing_gap} /> 포함</>} emphasis />
            <Kpi label="이번 사건 영향" value={year.event_effect} note={<>물량 <Mn value={year.volume_effect} /> · 단가 <Mn value={year.cost_effect} /></>} signed />
          </div>
          <p className="text-xs text-muted-foreground">
            두 사건을 해소해도 사건 이전부터 있던 기존 부족 <Mn value={year.existing_gap} /> 백만원이 남는다 — 그 원인은 아직 근거가 없다(새 사건으로 설명하지 않는다).
          </p>

          <Card>
            <CardHeader>
              <CardTitle>손익 브리지</CardTitle>
              <CardDescription>
                {passed.run_id} · {formatClock(passed.created_at)} {name(passed.created_by)}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div role="group" aria-label="기간" className="flex flex-wrap gap-1">
                {PERIOD_KINDS.map((k) => (
                  <button
                    key={k}
                    type="button"
                    onClick={() => setKind(k)}
                    aria-pressed={kind === k}
                    className={`rounded-md border px-2.5 py-1 text-xs ${kind === k ? "bg-muted font-medium" : "text-muted-foreground hover:text-foreground"}`}
                  >
                    {PERIOD_LABEL[k]}
                  </button>
                ))}
              </div>
              {p ? <BridgeChart period={p} /> : null}
              {kind === "next12" ? (
                <p className="text-xs text-muted-foreground">향후 12개월 Target은 미설정 — 부족액은 미산정이다(0이 아니다). 2028 물량은 내부가정이다.</p>
              ) : null}
            </CardContent>
          </Card>

          <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>모델별 공헌이익</CardTitle>
                <CardDescription>{p?.label} · 고정비는 공장 합계에서 한 번만 차감한다(모델 배부 없음)</CardDescription>
              </CardHeader>
              <CardContent className="overflow-x-auto">
                <table aria-label="모델별 공헌이익" className="w-full min-w-[30rem] text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs text-muted-foreground">
                      <th scope="col" className="py-2 pr-3 font-medium">모델</th>
                      <th scope="col" className="py-2 pr-3 text-right font-medium">F01 CM</th>
                      <th scope="col" className="py-2 pr-3 text-right font-medium">물량</th>
                      <th scope="col" className="py-2 pr-3 text-right font-medium">원가</th>
                      <th scope="col" className="py-2 pr-3 text-right font-medium">통합 CM</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(p?.models ?? []).map((m) => (
                      <tr key={m.model_id} className="border-b last:border-0">
                        <th scope="row" className="py-1.5 pr-3 text-left font-normal">{modelLabel(m.model_id)}</th>
                        <td className="py-1.5 pr-3 text-right"><Mn value={m.cm_f01} empty="미산출" /></td>
                        <td className="py-1.5 pr-3 text-right"><Mn value={m.volume_effect} empty="미산출" /></td>
                        <td className="py-1.5 pr-3 text-right"><Mn value={m.cost_effect} empty="미산출" /></td>
                        <td className="py-1.5 pr-3 text-right"><Mn value={m.cm_combined} empty="미산출" /></td>
                      </tr>
                    ))}
                    <tr className="border-t text-xs text-muted-foreground">
                      <th scope="row" className="py-1.5 pr-3 text-left font-normal">공장 고정비</th>
                      <td colSpan={4} className="py-1.5 pr-3 text-right">
                        −<Mn value={p?.fixed} /> (공장 합계 1회)
                      </td>
                    </tr>
                  </tbody>
                </table>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>근거 · 가정</CardTitle>
                <CardDescription>승인 단가·적용일은 장면 2 승인 기록에서 읽는다.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
                  <dt className="text-muted-foreground">물량</dt>
                  <dd className="font-mono text-xs">{passed.result.basis.quantity}</dd>
                  <dt className="text-muted-foreground">원가</dt>
                  <dd className="font-mono text-xs">{passed.result.basis.cost} · {passed.result.basis.price_version}</dd>
                  <dt className="text-muted-foreground">고정비</dt>
                  <dd className="font-mono text-xs">{passed.result.basis.fixed}</dd>
                  <dt className="text-muted-foreground">b 7월</dt>
                  <dd>
                    {passed.result.b_july?.f01.toLocaleString("ko-KR")} → {passed.result.b_july?.f02.toLocaleString("ko-KR")}대분 × 단위 CM{" "}
                    {Number(passed.result.b_july?.unit_cm).toLocaleString("ko-KR")}원
                  </dd>
                  <dt className="text-muted-foreground">공통부품</dt>
                  <dd>
                    {Number(passed.result.basis.old_price).toLocaleString("ko-KR")} → {Number(passed.result.basis.approved_price).toLocaleString("ko-KR")}원 ·{" "}
                    {passed.result.basis.effective_date?.slice(5).replace("-", "/")} · a·b 각 1개
                  </dd>
                  <dt className="text-muted-foreground">구매 증가</dt>
                  <dd>
                    잔여 2027 <Mn value={passed.result.purchase.remaining_increase} /> · 향후 12개월 <Mn value={passed.result.purchase.next12_increase} /> (
                    {passed.result.purchase.next12_qty?.toLocaleString("ko-KR")}개) — 손익 영향과 다른 지표
                  </dd>
                </dl>
                <Disclosure summary={`가정 ${passed.result.assumptions.length}건`}>
                  <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
                    {passed.result.assumptions.map((a) => (
                      <li key={a}>{a}</li>
                    ))}
                  </ul>
                </Disclosure>
                <Disclosure summary="정합 검증 (CT33)">
                  <ul className="space-y-0.5 text-xs">
                    {Object.values(passed.result.periods).flatMap((pp) =>
                      (pp.checks ?? []).map((c) => (
                        <li key={`${pp.kind}-${c.check_id}`}>
                          {c.ok ? "일치" : "불일치"} · {pp.label} · {c.label} (차이 {c.diff}원)
                        </li>
                      )),
                    )}
                  </ul>
                </Disclosure>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>월별 통합 관리손익</CardTitle>
              <CardDescription>2027년 7~12월 · 기간별 값은 해당 기간 원천에서 집계한다</CardDescription>
            </CardHeader>
            <CardContent>
              <Disclosure summary="월별 표 펼치기">
                <div className="overflow-x-auto">
                  <table aria-label="월별 통합 관리손익" className="w-full min-w-[34rem] text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs text-muted-foreground">
                        <th scope="col" className="py-2 pr-3 font-medium">월</th>
                        <th scope="col" className="py-2 pr-3 text-right font-medium">F01</th>
                        <th scope="col" className="py-2 pr-3 text-right font-medium">물량</th>
                        <th scope="col" className="py-2 pr-3 text-right font-medium">단가</th>
                        <th scope="col" className="py-2 pr-3 text-right font-medium">통합</th>
                        <th scope="col" className="py-2 pr-3 text-right font-medium">Target 부족</th>
                      </tr>
                    </thead>
                    <tbody>
                      {passed.result.months.map((m) => (
                        <tr key={m.label} className="border-b last:border-0">
                          <th scope="row" className="py-1.5 pr-3 text-left font-normal">{m.label}</th>
                          <td className="py-1.5 pr-3 text-right"><Mn value={m.f01} /></td>
                          <td className="py-1.5 pr-3 text-right"><Mn value={m.volume_effect} /></td>
                          <td className="py-1.5 pr-3 text-right"><Mn value={m.cost_effect} /></td>
                          <td className="py-1.5 pr-3 text-right"><Mn value={m.combined} /></td>
                          <td className="py-1.5 pr-3 text-right"><Mn value={m.total_gap} empty="미설정" /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Disclosure>
            </CardContent>
          </Card>
        </>
      )}

      <AgentCard view={view} kind="AG30" />
      <Commentary>
        <p className="text-xs text-muted-foreground">
          F01 → F02 물량 영향 뒤에 F02 물량 기준으로 승인 단가를 적용한다 — 교차효과를 따로 더하지 않는다. 요청·협상·승인안을 중복 합산하지 않는다.
        </p>
      </Commentary>
    </>
  );
}

function Kpi({
  label,
  value,
  note,
  emphasis = false,
  signed = false,
}: {
  label: string;
  value: string | null | undefined;
  note: React.ReactNode;
  emphasis?: boolean;
  signed?: boolean;
}) {
  return (
    <Card size="sm" data-index-skip>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl tabular-nums" style={emphasis ? { color: "var(--viz-status-critical)" } : undefined}>
          <Mn value={value} signed={signed} />
          <span className="ml-1 text-xs font-normal text-muted-foreground">백만원</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="text-xs text-muted-foreground">{note}</CardContent>
    </Card>
  );
}
