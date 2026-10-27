"use client";

import { useUserName } from "@/components/sc01/bits";
import { AgentCard } from "@/components/sc05/agent-card";
import { Mn, Sc05Body, Sc05Header, Tile, WaitingForms } from "@/components/sc05/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { formatCount, formatMinutes, formatRate } from "@/lib/sc05/format";
import type { Sc05View } from "@/lib/sc05/types";

/**
 * U505 초기 실행 결과 — 관측기간 2027년 9월, A-b·P-COM01. 사업성과(구매 건·긴급·추가비·순개선·납기·품질)와 경영수행
 * (공유·확인 소요·미확인·지연)을 나눈다 — 구매 60건과 변경 6건은 다른 모집단이다. 초기 실적을 연간 달성률로 보이지
 * 않는다. 비교 기준은 장면 4 정규화 가정이지 과거 실제 비용이 아니다. 미확인은 0과 다르다.
 */
export function Sc05ResultsScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc05Header id="U505" title="초기 실행 결과" question="9월 운영 적용에서 무엇이 실제로 바뀌었고, 무엇을 아직 모르는가?" />
      <Sc05Body>{(view) => <Body view={view} />}</Sc05Body>
    </main>
  );
}

function Body({ view }: { view: Sc05View }) {
  const nameOf = useUserName();
  const obs = view.observation ?? view.observationPreview;
  const waiting = new Set((view.bpm?.waiting ?? []).map((w) => w.nodeId));
  if (!obs) {
    return <p className="text-sm text-muted-foreground">운영 적용(START51) 전이다 — 관측할 실행 기록이 없다.</p>;
  }
  return (
    <>
      <p className="text-sm">
        {obs.period} · {obs.scope} ·{" "}
        {view.observation ? (
          <span className="font-medium">
            확인본 {view.observation.observation_id} — {nameOf(view.observation.confirmed_by)} {formatClock(view.observation.confirmed_at)}
          </span>
        ) : (
          <span className="text-muted-foreground">확인 전 미리보기 — 지금 시각까지 들어온 원천만</span>
        )}
      </p>
      <WaitingForms view={view} nodes={["Confirm_Observation"]} labels={{ Confirm_Observation: "초기 결과 확인" }} />
      <AgentCard view={view} kind="AG55" canRequest={waiting.has("Confirm_Observation")} />

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">사업성과</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Tile label="구매 건수 · 긴급" note={`발생률 ${formatRate(obs.urgent_rate)} · 수량 ${obs.qty.toLocaleString("ko-KR")}개`}>
            {obs.orders}건 · {obs.urgent}건
          </Tile>
          <Tile label="긴급 추가비(운송·할증)" note="정상 구매원가 제외">
            <Mn value={obs.extra_cost} />
          </Tile>
          <Tile label="추정 순개선(비교 기준 대비)" note={`기준 ${Number(obs.baseline_cost).toLocaleString("ko-KR")}원 − 추가비 − 지원비`}>
            <Mn value={obs.net} />
          </Tile>
          <Tile label="납기 · 품질 이상" note={obs.unconfirmed_results ? `미확인 ${obs.unconfirmed_results}건 — 정상 0건이 아니다` : "전체 확인 완료"}>
            {formatCount(obs.late)} · {formatCount(obs.quality)}
          </Tile>
        </div>
        <Commentary>
          <p className="text-xs text-muted-foreground">
            {obs.comparison_basis}. 8월 일회성 검증비 {Number(obs.one_off_august).toLocaleString("ko-KR")}원은 9월 순개선에서 다시 빼지 않는다. 초기 개선
            징후를 연간 절감 달성으로 단정하지 않는다.
          </p>
        </Commentary>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">경영수행 — 변경 {obs.changes}건</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Tile label="평균 공유 소요" note={`기준 ${obs.share.limit}분 · 지연 ${obs.share.delayed}건`}>
            {formatMinutes(obs.share.average)}
          </Tile>
          <Tile label="평균 구매 확인 소요" note={`기준 ${obs.ack.limit}분 · 최대 ${formatMinutes(obs.ack.max)}`}>
            {formatMinutes(obs.ack.average)}
          </Tile>
          <Tile label="확인 지연" note="기준 초과부터 지연(같으면 정상)">
            {obs.ack.delayed}건
          </Tile>
          <Tile label="확인 미확인" note="평균에서 빼고 따로 센다">
            {obs.ack.unconfirmed}건
          </Tile>
        </div>
      </section>

      {obs.blocking.length ? (
        <Card>
          <CardHeader>
            <CardTitle>확정 전 보완</CardTitle>
            <CardDescription>미확인·중복이 있으면 결과 확정과 전망 대사를 막는다.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="list-disc pl-4 text-sm">
              {obs.blocking.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>원천 건</CardTitle>
          <CardDescription>주문 ID 단위(분할 납품 합산, 취소 제외). 지표에서 건별 근거를 연다.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <Disclosure summary={`긴급 ${obs.urgent}건`}>
            <ul className="space-y-0.5 text-xs">
              {view.orders
                .filter((o) => o.urgent)
                .map((o) => (
                  <li key={o.order_id}>
                    <span className="font-mono">{o.order_id}</span> {o.qty}개 · 추가비 <Mn value={o.extra} /> · 승인 {nameOf(o.approver)}{" "}
                    {formatClock(o.approved_at)} · 발주 {formatClock(o.ordered_at)}
                    {o.change_ref ? ` · ${o.change_ref}` : ""}
                  </li>
                ))}
            </ul>
          </Disclosure>
          <Disclosure summary={`전체 주문 ${view.orders.length}건`}>
            <ul className="columns-1 space-y-0.5 text-xs sm:columns-2">
              {view.orders.map((o) => (
                <li key={o.order_id}>
                  <span className="font-mono">{o.order_id}</span> {o.qty}개 · {o.urgent ? "긴급" : "정상"} · {o.result_status === "CONFIRMED" ? "확인" : "미확인"}
                </li>
              ))}
            </ul>
          </Disclosure>
          {view.sourceIssues.length ? (
            <p className="text-xs" style={{ color: "var(--viz-status-serious)" }}>
              원천 중복 행: {view.sourceIssues.map((i) => i.order_id).join(", ")}
            </p>
          ) : null}
        </CardContent>
      </Card>
    </>
  );
}
