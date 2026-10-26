"use client";

import { useState } from "react";

import { useUserName } from "@/components/sc01/bits";
import { Sc02Body, Sc02Header, StatusPills, WaitingForms } from "@/components/sc02/bits";
import { Commentary } from "@/components/shared/commentary";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { sc02Api } from "@/lib/sc02/client";
import { KIND_LABEL } from "@/lib/sc02/format";
import type { Sc02View } from "@/lib/sc02/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc02 } from "@/lib/store/sc02";

/**
 * U23 1차 협상 결과 — 기존가·요청가·내부제시가·협상가와 각 적용일을 **구분한다**. 잠정합의는 회사의 최종
 * 승인이 아니고, 저장하면 재분석이 필요하다(U23-03). 미합의는 단가 NULL이다. 대화·외부 발송 기능은 없다.
 */
export function Sc02NegotiationScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc02Header id="U23" title="1차 협상 결과" question="분석을 근거로 가격·조건을 어떻게 협의했는가?" />
      <Sc02Body>{(view) => <Negotiation view={view} />}</Sc02Body>
    </main>
  );
}

function Negotiation({ view }: { view: Sc02View }) {
  const name = useUserName();
  const neg = view.negotiations.at(-1);
  const due = view.request?.negotiation_due;
  const versions = view.priceVersions.filter((p) => ["REQUEST", "OFFER", "NEGOTIATION"].includes(p.kind));
  return (
    <>
      <StatusPills view={view} />
      <WaitingForms
        view={view}
        nodes={["Record_Negotiation"]}
        initial={{ Record_Negotiation: { 협상적용일: view.request?.items[0]?.effective_date ?? "" } }}
        labels={{ Record_Negotiation: "협상 결과 저장" }}
      />

      <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-[3fr_2fr]">
        <Card>
          <CardHeader>
            <CardTitle>단가 구분</CardTitle>
            <CardDescription>요청·내부 제시·협상 잠정안은 서로 다른 값이다. 어느 것도 아직 승인 원가가 아니다.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[28rem] text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th scope="col" className="py-2 pr-3 font-medium">안</th>
                    <th scope="col" className="py-2 pr-3 text-right font-medium">단가</th>
                    <th scope="col" className="py-2 pr-3 font-medium">적용일</th>
                    <th scope="col" className="py-2 font-medium">분석</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-b">
                    <th scope="row" className="py-2 pr-3 text-left font-normal">기존가 (C01)</th>
                    <td className="py-2 pr-3 text-right tabular-nums">
                      {view.request ? `${Number(view.request.items[0].old_price).toLocaleString("ko-KR")}원` : "—"}
                    </td>
                    <td className="py-2 pr-3 text-muted-foreground">—</td>
                    <td className="py-2" />
                  </tr>
                  {versions.map((p) => (
                    <tr key={p.version_id} className="border-b">
                      <th scope="row" className="py-2 pr-3 text-left font-normal">
                        {KIND_LABEL[p.kind]} <span className="font-mono text-xs text-muted-foreground">{p.version_id}</span>
                      </th>
                      <td className="py-2 pr-3 text-right tabular-nums">
                        {p.new_price ? `${Number(p.new_price).toLocaleString("ko-KR")}원` : "미합의"}
                      </td>
                      <td className="py-2 pr-3">{p.effective_date}</td>
                      <td className="py-2 font-mono text-xs">{p.run_id ?? "재분석 필요"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>외부 협상기한</CardTitle>
            <CardDescription>건별로 담당자가 넣는다. 내부 분석기한과 따로이고, 외부 협상만으로 내부 업무기한을 늘리지 않는다.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {due ? (
              <>
                <p className="text-lg font-semibold tabular-nums">{formatClock(due.due_at)}</p>
                <ul className="space-y-0.5 text-xs text-muted-foreground">
                  {due.history.map((h) => (
                    <li key={h.at + h.due_at}>
                      {formatClock(h.at)} {name(h.by)} — {h.previous ? `${formatClock(h.previous)} → ` : ""}
                      {formatClock(h.due_at)} ({h.reason})
                    </li>
                  ))}
                </ul>
                <DueChange />
              </>
            ) : (
              <p className="text-muted-foreground">요청안 분석 때 넣는다.</p>
            )}
          </CardContent>
        </Card>
      </div>

      {neg ? (
        <Card>
          <CardHeader>
            <CardTitle>협상 기록 {neg.negotiation_id}</CardTitle>
            <CardDescription>
              {neg.round_no}차 · {formatClock(neg.held_at)} · {name(neg.recorded_by)} · {neg.outcome}
              {neg.analysis_required ? " — 재분석 필요" : ""}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p>참석자: {neg.participants}</p>
            <p>
              잠정 단가 {neg.price ? `${Number(neg.price).toLocaleString("ko-KR")}원` : "없음(미합의 — 0원이 아니다)"} · 적용일{" "}
              {neg.effective_date}
            </p>
            {neg.unresolved ? <p className="text-xs text-muted-foreground">잠정 조건·미합의: {neg.unresolved}</p> : null}
            {neg.outcome === "미합의" ? <p className="text-xs font-medium">팀장 협의가 필요하다 — 상신하지 않는다.</p> : null}
            <Commentary block>
              <p className="text-xs text-muted-foreground">가격을 낮추지 못한 협상도 결과와 근거를 기록할 수 있다.</p>
            </Commentary>
          </CardContent>
        </Card>
      ) : null}
    </>
  );
}

function DueChange() {
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const historical = useSc02((s) => s.past !== null);
  const [due, setDue] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    if (!demoRunId) return;
    const r = await sc02Api.changeDue(demoRunId, due, reason, actor);
    if (r.ok) {
      useSc02.getState().setLive(r.data);
      setDue("");
      setReason("");
      setError(null);
    } else setError(`${r.status} — ${r.error}`);
  };
  return (
    <form
      className="space-y-2 border-t pt-3"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <p className="text-xs font-medium">기한 변경 (구매담당)</p>
      <input
        aria-label="새 기한"
        placeholder="2027-06-22T18:00:00+09:00"
        value={due}
        onChange={(e) => setDue(e.target.value)}
        className="block w-full rounded-lg border bg-transparent px-2 py-1.5 text-sm"
      />
      <input
        aria-label="변경 사유"
        placeholder="변경 사유"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        className="block w-full rounded-lg border bg-transparent px-2 py-1.5 text-sm"
      />
      <Button type="submit" size="sm" variant="outline" disabled={historical || !due || !reason.trim()}>
        기한 변경
      </Button>
      {error ? (
        <p role="alert" className="text-xs" style={{ color: "var(--viz-status-critical)" }}>
          거절됨: {error}
        </p>
      ) : null}
    </form>
  );
}
