"use client";

import { ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock, formatPercent, type SupplyBoard } from "@/lib/dashboard";

/** 시각만(같은 날 비교) — `2026-11-05T06:15:00+09:00` → `06:15`. */
function hm(at: string): string {
  const m = /T(\d{2}:\d{2})/.exec(at);
  return m ? m[1] : at;
}

/** 등록일 — `2026-11-04T09:00:00+09:00` → `11/4`. */
function md(at: string): string {
  const m = /^\d{4}-(\d{2})-(\d{2})/.exec(at);
  return m ? `${Number(m[1])}/${Number(m[2])}` : at;
}

/**
 * 납기 상황판(공통 화면 UI-D01, 시나리오 2 장면 1 D01) — 성과(직전 마감 OTD)·위험(현재 공급 경보)·통제(사건 처리 상태)를
 * **서로 다른 단위로** 나란히 둔다. 실적 정상과 경보가 함께 보일 수 있다. 「사건 열기」는 회사 사이트의 Case 화면(UI-B02)이다
 * — 승인 버튼은 없다. 숫자는 경영 기록 `dashboard`의 본문 그대로다(계산하지 않는다).
 */
export function SupplyBoardView({ board, openCase }: { board: SupplyBoard; openCase: (commitment?: string) => string | null }) {
  const { kpi, kri, control } = board;
  const metTarget = kpi.meets_target === true;
  return (
    <section aria-label="납기 상황판" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">납기 상황판</h2>
        <p className="text-xs text-muted-foreground">
          {board.scope.label} · 조회 기준 {formatClock(board.as_of)} KST
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardDescription>성과 · 직전 마감기간({kpi.period.label})</CardDescription>
            <CardTitle className="text-2xl tabular-nums">
              납기준수율 {formatPercent(kpi.otd)}{" "}
              <span className="text-sm font-normal text-muted-foreground">/ 목표 {formatPercent(kpi.target)}</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p className="tabular-nums">
              전량 정시 인수 {kpi.numerator} / {kpi.denominator}건
            </p>
            <Badge variant={metTarget ? "secondary" : "destructive"}>{metTarget ? "목표 충족" : kpi.meets_target === null ? "대상 없음" : "목표 미달"}</Badge>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>위험 · 현재 경보</CardDescription>
            <CardTitle className="text-2xl tabular-nums">
              공급 경보 {kri.alerts}건 <span className="text-sm font-normal text-muted-foreground">/ 영향 납기약정 {kri.affected_commitments}건</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {kri.alerts > 0 ? `${kri.risk_label} — 경보는 경영검토 요청이나 납기 미준수 확정이 아니다` : "경보 없음"}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>통제 · 사건 처리 상태</CardDescription>
            <CardTitle className="text-xl">{control.label}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {control.analysis_version ? `영향 분석 v${control.analysis_version}` : "분석 전"} · 수행 완료를 위험 해소로 표시하지 않는다
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>관심 사건 · 구매 입고예정 변경</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          {board.cases.length === 0 ? (
            <p className="text-muted-foreground">열린 사건이 없다 — 경보가 아닌 변경은 이력만 남긴다.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead className="text-xs text-muted-foreground">
                  <tr>
                    <th className="py-1.5 pr-3 font-medium">사건</th>
                    <th className="py-1.5 pr-3 font-medium">발생 시각</th>
                    <th className="py-1.5 pr-3 font-medium">부품</th>
                    <th className="py-1.5 pr-3 font-medium">경보 사유</th>
                    <th className="py-1.5 pr-3 font-medium">영향 약정</th>
                    <th className="py-1.5 font-medium">
                      <span className="sr-only">동작</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {board.cases.map((c) => {
                    const href = openCase();
                    return (
                      <tr key={c.case_id} className="border-t align-top">
                        <td className="py-2 pr-3 font-mono text-xs">{c.case_id}</td>
                        <td className="py-2 pr-3 tabular-nums">{formatClock(c.opened_at)}</td>
                        <td className="py-2 pr-3">공통부품 {c.part_id}</td>
                        <td className="py-2 pr-3">{c.reason}</td>
                        <td className="py-2 pr-3">
                          {c.commitments.map((x) => x.replace(/^COM-/, "")).join(" · ")} ({c.commitments.length}건)
                        </td>
                        <td className="py-2 whitespace-nowrap">
                          {href ? (
                            <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium text-brand hover:underline">
                              사건 열기 <ExternalLink aria-hidden className="size-3.5" />
                            </a>
                          ) : (
                            <span className="text-muted-foreground">회사 사이트 주소 없음</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {board.revisions.length > 0 && (
            <div>
              <p className="text-xs text-muted-foreground">변경 전후 · 11/5 입고예정(실제 입고 아님)</p>
              <ol className="mt-1 flex flex-wrap gap-2">
                {board.revisions.map((r, i) => (
                  <li key={r.revision_id} className="rounded-md border px-2 py-1 text-xs">
                    <span className="font-medium">{i === 0 ? "최초" : `${i}차`}</span> · {md(r.registered_at)} 등록 /{" "}
                    <span className="tabular-nums">{r.lots.map((l) => `${hm(l.planned_at)} ${l.qty}개`).join(" + ")}</span> ·{" "}
                    <span className={r.judgment === "ALERT" ? "font-semibold text-destructive" : "text-muted-foreground"}>{r.judgment_label}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-3 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>모델별 마감 실적</CardTitle>
            <CardDescription>과거 지연은 현재 사건과 별개다</CardDescription>
          </CardHeader>
          <CardContent>
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr>
                  <th className="py-1 font-medium">모델</th>
                  <th className="py-1 font-medium">마감 약정</th>
                  <th className="py-1 font-medium">정시</th>
                  <th className="py-1 font-medium">OTD</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {kpi.by_model.map((m) => (
                  <tr key={m.model} className="border-t">
                    <td className="py-1">{m.model}</td>
                    <td className="py-1">{m.due}</td>
                    <td className="py-1">{m.on_time}</td>
                    <td className="py-1">{formatPercent(m.otd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>도래 전 납기약정</CardTitle>
            <CardDescription>대표 사건 외 정상 모델도 같은 계산으로 유지한다</CardDescription>
          </CardHeader>
          <CardContent>
            {board.open_commitments.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                조회 기준 시각에 아직 도래하지 않은 납기약정이 없다 — 지난 약정은 마감 실적·사건 기록에 있다
              </p>
            ) : (
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr>
                    <th className="py-1 font-medium">약정</th>
                    <th className="py-1 font-medium">모델 · 수량</th>
                    <th className="py-1 font-medium">고객 약정</th>
                    <th className="py-1 font-medium">기존 착수 차질</th>
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  {board.open_commitments.map((c) => (
                    <tr key={c.commitment_id} className="border-t">
                      <td className="py-1">
                        {c.commitment_id}
                        {c.demo_role === "representative" && <span className="ml-1 text-xs text-destructive">사건</span>}
                      </td>
                      <td className="py-1">
                        {c.model} · {c.qty}
                      </td>
                      <td className="py-1">{formatClock(c.promised_at)}</td>
                      <td className="py-1">{c.start_delay_min === null ? "미확인" : `${c.start_delay_min}분`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>
      <p className="text-xs text-muted-foreground">{board.notice}</p>
    </section>
  );
}
