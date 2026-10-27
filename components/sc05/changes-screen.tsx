"use client";

import { useState } from "react";

import { useUserName } from "@/components/sc01/bits";
import { AgentCard } from "@/components/sc05/agent-card";
import { Mn, Sc05Body, Sc05Header, WaitingForms } from "@/components/sc05/bits";
import { Commentary } from "@/components/shared/commentary";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { CHANGE_STATE_LABEL, formatMinutes } from "@/lib/sc05/format";
import type { ChangeCase, Sc05View } from "@/lib/sc05/types";

const NODES = ["Receive_Change", "Share_Change", "Ack_Change", "Respond_Change", "Approve_Urgent", "Execute_Order"];

/**
 * U504 생산 변경정보·구매 대응 — 왼쪽 변경 건, 가운데 고객 원문(a~e 전후, 변동 없는 모델도), 아래 대응·예외. 공유
 * (접수 후 60분)와 구매 확인(공유 후 120분)을 따로 보인다. 미확인을 0분으로 보이지 않는다. 미승인 긴급 예외는 실행
 * 완료로 처리하지 않는다. 고객 원문과 담당자 판단을 구분한다.
 */
export function Sc05ChangesScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc05Header id="U504" title="생산 변경정보·구매 대응" question="생산 변화를 구매가 제때 알고 대응했는가?" />
      <Sc05Body>{(view) => <Body view={view} />}</Sc05Body>
    </main>
  );
}

function Body({ view }: { view: Sc05View }) {
  const nameOf = useUserName();
  const [picked, setPicked] = useState<string | null>(null);
  const [changedOnly, setChangedOnly] = useState(true);
  const waiting = new Set((view.bpm?.waiting ?? []).map((w) => w.nodeId));
  const current = view.changes.find((c) => c.change_id === picked) ?? [...view.changes].reverse().find((c) => !c.background) ?? view.changes.at(-1);
  const plan = view.customerPlans.find((p) => p.plan_ref === current?.plan_ref);
  const order = view.orders.find((o) => o.order_id === current?.order_ref);
  return (
    <>
      {view.start === null ? (
        <p className="rounded-md border px-3 py-2 text-xs text-muted-foreground">운영 적용(START51) 전이다 — 변경 공유 기준은 착수 뒤에 쓴다.</p>
      ) : null}
      <WaitingForms
        view={view}
        nodes={NODES}
        labels={{ Receive_Change: "접수", Share_Change: "공유", Ack_Change: "확인", Respond_Change: "대응 등록", Approve_Urgent: "결정", Execute_Order: "실행 기록" }}
      />
      <AgentCard view={view} kind="AG54" canRequest={waiting.has("Share_Change")} />

      <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-[18rem_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>변경 건 {view.changes.length}건</CardTitle>
            <CardDescription>대표 두 건은 BPM 결재로, 나머지는 같은 기준의 배경 기록이다.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {view.changes.map((c) => (
                <li key={c.change_id}>
                  <button
                    type="button"
                    onClick={() => setPicked(c.change_id)}
                    aria-pressed={c.change_id === current?.change_id}
                    className={`w-full rounded-md border px-2 py-1.5 text-left ${c.change_id === current?.change_id ? "bg-muted" : ""}`}
                  >
                    <span className="font-medium">{c.change_id}</span> <span className="text-xs text-muted-foreground">{c.plan_ref} · {c.model_id}</span>
                    <span className="block text-xs">
                      {CHANGE_STATE_LABEL[c.state] ?? c.state}
                      {c.decision ? ` · ${c.decision === "URGENT" ? "긴급" : "정상"}` : ""}
                      {c.background ? " · 배경" : ""}
                    </span>
                  </button>
                </li>
              ))}
              {view.changes.length === 0 ? <li className="text-muted-foreground">아직 접수한 변경이 없다.</li> : null}
            </ul>
          </CardContent>
        </Card>

        {current ? (
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>
                  {current.change_id} — 접수·공유·구매 확인
                </CardTitle>
                <CardDescription>공유는 접수 후 60분, 구매 확인은 공유 후 120분 이내가 기준이다(달력 경과분). 정확히 기준이면 정상이다.</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3 text-sm sm:grid-cols-3">
                <p>
                  <span className="block text-xs text-muted-foreground">접수</span>
                  {formatClock(current.received_at)}
                </p>
                <p>
                  <span className="block text-xs text-muted-foreground">생산 공유 · 소요</span>
                  {current.shared_at ? formatClock(current.shared_at) : "미공유"} · {formatMinutes(current.share_minutes)}
                </p>
                <p>
                  <span className="block text-xs text-muted-foreground">구매 확인 · 소요</span>
                  {current.ack_at ? formatClock(current.ack_at) : "미확인"} · {formatMinutes(current.ack_minutes)}
                  {current.ack_by ? ` · ${nameOf(current.ack_by)}${current.delegate ? "(지정 대행)" : ""}` : ""}
                </p>
                <Alerts view={view} change={current} />
              </CardContent>
            </Card>

            {plan ? (
              <Card>
                <CardHeader>
                  <CardTitle>고객 원문 {plan.plan_ref} — 9월 a~e 전후 물량(대분)</CardTitle>
                  <CardDescription>
                    월 합계는 그대로이고 구간만 바뀐다 — 월 손익 물량효과는 0이다. 두 요청창(CP51·CP52)을 합산하지 않는다.{" "}
                    <label className="ml-1 inline-flex items-center gap-1">
                      <input type="checkbox" checked={changedOnly} onChange={(e) => setChangedOnly(e.target.checked)} />
                      바뀐 모델만
                    </label>
                  </CardDescription>
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  <table className="w-full min-w-[40rem] text-sm">
                    <thead className="text-left text-xs text-muted-foreground">
                      <tr>
                        <th className="py-1.5 pr-3 font-medium">모델</th>
                        {plan.lines[0]?.windows.map((w) => (
                          <th key={w} className="pr-3 text-right font-medium">
                            {w}
                          </th>
                        ))}
                        <th className="pr-3 text-right font-medium">월 합계</th>
                        <th className="pr-3 text-right font-medium">합계 변화</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {plan.lines
                        .filter((ln) => !changedOnly || ln.changed)
                        .map((ln) => (
                          <tr key={ln.model_id}>
                            <th scope="row" className="py-1.5 pr-3 text-left font-medium">
                              {ln.model_id}
                            </th>
                            {ln.before.map((b, i) => (
                              <td key={i} className="pr-3 text-right tabular-nums">
                                {b === ln.after[i] ? (
                                  b.toLocaleString("ko-KR")
                                ) : (
                                  <>
                                    {b.toLocaleString("ko-KR")} → <span className="font-semibold">{ln.after[i].toLocaleString("ko-KR")}</span>
                                  </>
                                )}
                              </td>
                            ))}
                            <td className="pr-3 text-right tabular-nums">{ln.month_total.toLocaleString("ko-KR")}</td>
                            <td className="pr-3 text-right tabular-nums">{ln.month_diff}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                  {changedOnly ? (
                    <p className="mt-1 text-xs text-muted-foreground">
                      변동 없는 모델 {plan.lines.filter((l) => !l.changed).map((l) => l.model_id).join("·")}은 감췄다 — 필터를 풀면 보인다.
                    </p>
                  ) : null}
                </CardContent>
              </Card>
            ) : null}

            {current.response || order ? (
              <Card>
                <CardHeader>
                  <CardTitle>구매 대응{current.decision === "URGENT" ? " · 긴급 예외" : ""}</CardTitle>
                  <CardDescription>담당자 판단이다 — 고객 원문과 구분한다. 긴급구매를 무조건 금지하지 않고, 승인·비용·납기 근거를 남긴다.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {current.response ? (
                    <p>
                      재고 {current.response.inventory} · 기발주 {current.response.open_orders} · 필요일 {current.response.need_date}
                      {current.response.normal_date ? ` · 정상조달 ${current.response.normal_date}` : " · 재고·기발주로 충당"}
                      <span className="block text-xs text-muted-foreground">{current.response.rationale}</span>
                    </p>
                  ) : current.note ? (
                    <p className="text-xs">{current.note}</p>
                  ) : null}
                  {order ? (
                    <p>
                      주문 <span className="font-mono">{order.order_id}</span> {order.qty}개 · {order.urgent ? "긴급" : "정상"} · 추가비{" "}
                      <Mn value={order.extra} /> 백만원
                      {order.urgent ? ` (운송 ${Number(order.transport).toLocaleString("ko-KR")}원 + 할증 ${Number(order.premium).toLocaleString("ko-KR")}원)` : ""}
                      <span className="block text-xs text-muted-foreground">
                        {order.approved_at ? `긴급 승인 ${nameOf(order.approver)} ${formatClock(order.approved_at)} · ` : order.urgent ? "긴급 승인 대기 · " : ""}
                        발주 {order.ordered_at ? formatClock(order.ordered_at) : "전"} · 처리기록 {order.recorded_at ? formatClock(order.recorded_at) : "전"} · 납기·품질{" "}
                        {order.result_status === "CONFIRMED" ? `이상 ${order.late}·${order.quality}건` : "미확인(월마감 확인 전)"}
                      </span>
                    </p>
                  ) : null}
                  <Commentary>
                    <p className="text-xs text-muted-foreground">
                      추가비 200만원 이하는 구매 임원 전결(기존 구매 전결)이다 — 넘으면 상위 전결 확인 전 실행을 막는다. 대표 주문량과 납품 영향량(200·120대분)은
                      다른 집계 단위다.
                    </p>
                  </Commentary>
                </CardContent>
              </Card>
            ) : null}
          </div>
        ) : null}
      </div>
    </>
  );
}

function Alerts({ view, change }: { view: Sc05View; change: ChangeCase }) {
  const alerts = view.alerts.filter((a) => a.target === change.change_id);
  if (alerts.length === 0) return null;
  return (
    <p className="text-xs sm:col-span-3" style={{ color: "var(--viz-status-serious)" }}>
      {alerts.map((a) => `${formatClock(a.at)} ${a.message}`).join(" · ")} — 알림은 업무 승인을 대신하지 않는다
    </p>
  );
}
