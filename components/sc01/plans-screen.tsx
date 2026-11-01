"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Inbox, XCircle } from "lucide-react";

import { ActionForm } from "@/components/sc01/action-form";
import { Loading, ScreenHeader, StatePill, useUserName } from "@/components/sc01/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { sc01Api } from "@/lib/sc01/client";
import { formatClock, formatQty, modelLabel, SOURCE_STATUS_LABEL } from "@/lib/sc01/format";
import type { CustomerPlanRow, Source } from "@/lib/sc01/types";
import { selectView, useSc01 } from "@/lib/store/sc01";

/** 시연 원천 — 엔진 `domain.FIXTURES`. 기본은 CP02, 나머지는 선택 시연 경로(설계서 2.11). */
const FIXTURES: { id: string; label: string }[] = [
  { id: "CP02", label: "CP02 기본 — b모델 7월 감소" },
  { id: "EX01", label: "EX01 경보 없는 소폭 변경(c모델)" },
  { id: "EX02", label: "EX02 b모델 7월 수량 누락" },
  { id: "EX04", label: "EX04 c모델 증가로 합계 상쇄" },
  { id: "EX05", label: "EX05 b모델 7월 확인된 0" },
  { id: "CP03", label: "CP03 정정본 — b모델 7월 9,000" },
];

/**
 * UI02 고객 생산계획 수신 + UI03 고객계획 확인. 한 화면에 둔 이유: 시연 순서 2·3이 같은
 * 원천을 이어서 다루고, 수신 목록에서 고른 원천이 곧 확인 대상이다.
 *
 * * "시연 계획 수신"은 데모 실행 기능이다 — 고객 시스템에서 자동 수신된 것처럼 보이지 않게
 *   한다(UI02 기능 표).
 * * 이 비교는 **고객 원천 사이**(CP01 → 수신본)다. 직전 승인 전망 F01과의 비교는 UI04다(UI02-02).
 * * 원본을 고치는 기능은 없다. 오류는 보완 요청 → 정정본 수신으로만 바뀐다.
 */
export function PlansScreen() {
  const view = useSc01(selectView);
  const [baseline, setBaseline] = useState<CustomerPlanRow[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    void sc01Api.customerPlan("CP01").then((r) => r.ok && setBaseline(r.data));
  }, []);

  if (!view) {
    return (
      <main className="mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
        <ScreenHeader id="UI02·03" title="고객 생산계획" question="어떤 계획이 들어왔고 무엇을 처리해야 하는가?" />
        <Loading />
      </main>
    );
  }

  const latest = view.sources.at(-1) ?? null;
  const source = view.sources.find((s) => s.source_id === selected) ?? latest;

  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <ScreenHeader id="UI02·03" title="고객 생산계획" question="어떤 계획이 들어왔고 무엇을 처리해야 하는가?" />

      <ReceiveCard sources={view.sources} selected={source?.source_id ?? null} onSelect={setSelected} />

      {source ? (
        <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-[3fr_2fr]">
          <CompareCard source={source} baseline={baseline} />
          <VerifyCard source={source} />
        </div>
      ) : (
        <Card>
          <CardContent className="flex items-center gap-2 text-sm text-muted-foreground">
            <Inbox aria-hidden className="size-4" />
            아직 수신된 새 고객계획이 없다. 직전 원천은 6/1 수신한 CP01(시드)이다.
          </CardContent>
        </Card>
      )}
    </main>
  );
}

function ReceiveCard({
  sources,
  selected,
  onSelect,
}: {
  sources: Source[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const users = useSc01((s) => s.users);
  const historical = useSc01((s) => s.past !== null);
  const setLive = useSc01((s) => s.setLive);
  const [fixture, setFixture] = useState("CP02");
  const [error, setError] = useState<string | null>(null);
  const isSales = users.find((u) => u.userId === actor)?.role === "영업담당";

  const receive = async () => {
    if (!demoRunId) return;
    setError(null);
    const r = await sc01Api.receive(demoRunId, fixture, actor);
    if (r.ok) setLive(r.data);
    else setError(`${r.status} — ${r.error}`);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>수신 현황</CardTitle>
        <Commentary block>
          <CardDescription>
            고객이 월 2회 공유하는 생산계획. 수신 자료는 당사 배정·월 전체 물량이다. 같은 내용을 다시 받으면
            기존 접수를 돌려주고, 정정본은 이전 자료를 지우지 않고 잇는다.
          </CardDescription>
        </Commentary>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th scope="col" className="py-2 pr-3 font-medium">수신번호</th>
                <th scope="col" className="py-2 pr-3 font-medium">버전</th>
                <th scope="col" className="py-2 pr-3 font-medium">대상 기간</th>
                <th scope="col" className="py-2 pr-3 font-medium">수신 시각</th>
                <th scope="col" className="py-2 pr-3 font-medium">확인 상태</th>
                <th scope="col" className="py-2 font-medium">관계</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b text-muted-foreground">
                <td className="py-2 pr-3 font-mono text-xs">SRC01</td>
                <td className="py-2 pr-3">CP01</td>
                <td className="py-2 pr-3">2027-07~09</td>
                <td className="py-2 pr-3">6/1 09:00</td>
                <td className="py-2 pr-3">고객 확인 (시드)</td>
                <td className="py-2">직전 원천</td>
              </tr>
              {sources.map((s) => (
                <tr
                  key={s.source_id}
                  className={s.source_id === selected ? "border-b bg-muted/60" : "border-b"}
                >
                  <td className="py-2 pr-3">
                    <button type="button" className="font-mono text-xs underline" onClick={() => onSelect(s.source_id)}>
                      {s.source_id}
                    </button>
                  </td>
                  <td className="py-2 pr-3">{s.customer_plan_id}</td>
                  <td className="py-2 pr-3">2027-07~09</td>
                  <td className="py-2 pr-3">{formatClock(s.received_at)}</td>
                  <td className="py-2 pr-3">{SOURCE_STATUS_LABEL[s.status]}</td>
                  <td className="py-2 text-xs text-muted-foreground">
                    {s.corrects ? `${s.corrects}의 정정본` : "신규"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-center gap-2 rounded-md border border-dashed p-2">
          <span className="text-xs text-muted-foreground">시연</span>
          <select
            value={fixture}
            onChange={(e) => setFixture(e.target.value)}
            className="rounded-md border bg-transparent px-2 py-1 text-xs"
            aria-label="시연 원천 선택"
          >
            {FIXTURES.map((f) => (
              <option key={f.id} value={f.id}>{f.label}</option>
            ))}
          </select>
          <Button size="sm" onClick={() => void receive()} disabled={historical || !isSales}>
            시연 계획 수신
          </Button>
          {!isSales ? <span className="text-xs text-muted-foreground">영업담당 역할만 수신할 수 있다</span> : null}
        </div>
        {error ? (
          <p role="alert" className="text-xs" style={{ color: "var(--viz-status-critical)" }}>
            거절됨: {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function CompareCard({ source, baseline }: { source: Source; baseline: CustomerPlanRow[] | null }) {
  const before = new Map((baseline ?? []).map((r) => [`${r.modelId}|${r.period}`, r.quantity]));
  const prevOf = (r: Source["rows"][number]) => before.get(`${r.model_id}|${r.period}`) ?? null;
  const changed = source.rows.filter((r) => prevOf(r) !== r.quantity);

  return (
    <Card>
      <CardHeader>
        <CardTitle>변경 비교 — CP01 → {source.customer_plan_id}</CardTitle>
        <CardDescription>15행 중 {changed.length}행이 바뀌었다.</CardDescription>
        <Commentary block>
          <p className="text-[13px] text-muted-foreground">
            고객 원천끼리의 비교다. 직전 승인 전망과의 비교는 위험 검토 화면이다(UI02-02).
          </p>
        </Commentary>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 바뀐 행만 먼저 — 변경 없는 14행을 늘어놓으면 정작 바뀐 한 행이 묻힌다. */}
        {changed.length > 0 ? <CompareTable rows={changed} prevOf={prevOf} planId={source.customer_plan_id} /> : (
          <p className="text-sm text-muted-foreground">바뀐 행이 없다.</p>
        )}
        <Disclosure summary="15행 전체 보기">
          <CompareTable rows={source.rows} prevOf={prevOf} planId={source.customer_plan_id} />
        </Disclosure>
      </CardContent>
    </Card>
  );
}

function CompareTable({
  rows,
  prevOf,
  planId,
}: {
  rows: Source["rows"];
  prevOf: (r: Source["rows"][number]) => number | null;
  planId: string;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[24rem] text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th scope="col" className="py-2 pr-3 font-medium">모델·월</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">CP01</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">{planId}</th>
            <th scope="col" className="py-2 text-right font-medium">변화</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const prev = prevOf(r);
            const isChanged = prev !== r.quantity;
            return (
              <tr key={`${r.model_id}${r.period}`} className="border-b last:border-0">
                <th scope="row" className="py-2 pr-3 text-left font-normal">
                  {modelLabel(r.model_id)} {Number(r.period.slice(5, 7))}월
                </th>
                <td className="py-2 pr-3 text-right tabular-nums text-muted-foreground">{formatQty(prev)}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{formatQty(r.quantity)}</td>
                <td className="py-2 text-right tabular-nums">
                  {!isChanged ? (
                    <span className="text-xs text-muted-foreground">—</span>
                  ) : r.quantity === null || prev === null ? (
                    "확인 필요"
                  ) : (
                    <span className="font-semibold">{formatQty(r.quantity - prev)}</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const CHECKS = [
  "필수값 · 고객·공장·모델 매핑",
  "정수·비음수 수량, 0과 누락 구분",
  "모델·월 중복 없음, 15행 완전",
  "월 전체 물량 · 당사 배정 물량(40% 재적용 금지)",
];

function VerifyCard({ source }: { source: Source }) {
  const view = useSc01(selectView);
  const waiting = view?.bpm?.waiting ?? [];
  const dq = waiting.find((w) => w.nodeId === "Approve_DQ");
  const calc = waiting.find((w) => w.nodeId === "Confirm_Calc");
  const isLatest = view?.sources.at(-1)?.source_id === source.source_id;
  const passed = source.errors.length === 0;
  const nameOf = useUserName();

  return (
    <Card>
      <CardHeader>
        <CardTitle>원천 확인</CardTitle>
        <Commentary block>
          <CardDescription>
            CT01 — 당사 공급전망으로 쓸 수 있는 자료인지 확인한다. 확인은 전망 승인이 아니다.
          </CardDescription>
        </Commentary>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-1.5">
          <StatePill label="자료" value={SOURCE_STATUS_LABEL[source.status]} tone={source.status === "VERIFIED" ? "good" : source.status === "NEEDS_INFO" ? "warn" : "neutral"} />
          <StatePill label="자동 검증" value={passed ? "통과" : `오류 ${source.errors.length}건`} tone={passed ? "good" : "warn"} />
        </div>

        {/* 통과면 한 줄로 접는다. 오류는 접지 않는다 — 고칠 것이므로 바로 보여야 한다. */}
        {passed ? (
          <Disclosure summary={`자동 검증 ${CHECKS.length}개 항목`}>
            <ul className="space-y-1 text-xs">
              {CHECKS.map((c) => (
                <li key={c} className="flex items-center gap-1.5">
                  <CheckCircle2 aria-hidden className="size-3.5" style={{ color: "var(--viz-status-good)" }} /> {c}
                </li>
              ))}
            </ul>
          </Disclosure>
        ) : (
          <ul className="space-y-1 text-xs">
            {source.errors.map((e) => (
              <li key={`${e.row}${e.code}`} className="flex items-center gap-1.5">
                <XCircle aria-hidden className="size-3.5" style={{ color: "var(--viz-status-critical)" }} />
                {e.row} — {e.message}
              </li>
            ))}
          </ul>
        )}

        {source.verified_by ? (
          <div className="rounded-md border p-2 text-xs">
            <p className="font-medium">확인 기록 · {formatClock(source.verified_at)} · {nameOf(source.verified_by)}</p>
            <p className="text-muted-foreground">{source.opinion}</p>
            <p className="text-muted-foreground">근거: {source.evidence}</p>
          </div>
        ) : null}

        {isLatest && dq ? (
          <div className="space-y-2 border-t pt-3">
            <p className="text-xs font-medium">담당자 확인 — {dq.role}</p>
            {!passed ? (
              <p className="text-xs text-muted-foreground">검증 오류가 있으면 확인 완료가 막힌다 — 보완 요청 후 정정본을 받는다.</p>
            ) : null}
            <ActionForm waiting={dq} submitLabel="확인 결과 저장" />
          </div>
        ) : null}

        {isLatest && calc ? (
          <div className="space-y-2 border-t pt-3">
            <p className="text-xs font-medium">비교 계산</p>
            <Commentary block>
              <p className="text-xs text-muted-foreground">T01 · F01 · 확인된 원천 · 원가 C01 · 규칙 R01-v1</p>
            </Commentary>
            <ActionForm waiting={calc} submitLabel="비교 계산 실행" />
          </div>
        ) : null}

        {isLatest && waiting.some((w) => w.nodeId === "Approve_Sales") ? (
          <p className="text-xs text-muted-foreground">계산이 끝났다 — 위험 검토 화면에서 결과를 본다.</p>
        ) : null}
        {source.status === "NEEDS_INFO" && !dq ? (
          <p className="text-xs text-muted-foreground">보완 요청됨 — 정정본을 수신하면 다시 검증한다.</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
