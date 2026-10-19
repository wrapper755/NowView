"use client";

import { useState } from "react";

import { ActionForm } from "@/components/sc01/action-form";
import { Loading, RiskTag, ScreenHeader, StatePill, useUserName } from "@/components/sc01/bits";
import { Commentary } from "@/components/shared/commentary";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  formatClock,
  formatKrw,
  formatKrwSigned,
  formatMetric,
  formatQty,
  formatRatio,
  METRIC_LABEL,
  modelLabel,
  riskLabel,
  SOURCE_STATUS_LABEL,
} from "@/lib/sc01/format";
import type { Assessment, CalcRun, DemoRunView } from "@/lib/sc01/types";
import { selectView, useSc01 } from "@/lib/store/sc01";

/** 지표 → R01-v1 임계값 키(엔진 시드의 이름). */
const THRESHOLD: Record<string, { attention: string; critical: string }> = {
  KRI01: { attention: "감소율_관심", critical: "감소율_중요" },
  KRI02: { attention: "감소액_관심", critical: "감소액_중요" },
  KRI03: { attention: "부족률_관심", critical: "부족률_중요" },
};

/**
 * UI04 — 공급전망 변동 및 Risk 검토. 성과 변동을 위험 신호로 잇고 영업 책임자가 후속 경로를
 * 판단한다.
 *
 * * 상태를 칩 하나로 뭉치지 않는다 — 원천 확인·계산·위험·영업 검토·전망 승인이 각각 따로다(UI04-01).
 * * "이번 추가 감소"와 "목표 대비 부족"을 나란히 둔다 — 하나만 보면 사건 크기를 잘못 읽는다.
 * * 위험 판정은 사람이 바꾸지 않는다. 다르게 판단하면 의견에 사유를 남긴다(UI04-05).
 */
export function RiskScreen() {
  const view = useSc01(selectView);
  const [pick, setPick] = useState<{ model: string; period: string }>({ model: "A-b", period: "2027-07-01" });

  const run = view?.calcRuns.find((r) => r.run_id === view.latestRunId && r.run_id !== "RUN-F01-001");

  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
      <ScreenHeader id="UI04" title="공급전망 변동 · 위험 검토" question="무엇이 변했고 목표·손익에 어떤 영향을 주는가?" />
      {!view ? (
        <Loading />
      ) : !run ? (
        <Card>
          <CardContent className="text-sm text-muted-foreground">
            아직 비교 계산 결과가 없다. 고객계획 화면에서 원천을 확인하고 비교 계산을 실행한다.
          </CardContent>
        </Card>
      ) : (
        <>
          <StateRow view={view} run={run} />
          <RiskDetail run={run} pick={pick} />
          <ModelCompare run={run} pick={pick} onPick={setPick} />
          <IssueHistory view={view} />
          <Decisions view={view} />
        </>
      )}
    </main>
  );
}

function StateRow({ view, run }: { view: DemoRunView; run: CalcRun }) {
  const source = view.sources.find((s) => s.source_id === run.source_id);
  const review = view.reviews.find((r) => r.run_id === run.run_id);
  const forecast = view.forecasts.find((f) => f.version_id === run.versions.latest);
  const top = run.results
    .filter((r) => r.metrics.M01.value !== "0")
    .reduce<Assessment | null>((a, r) => (a === null || rank(r) > rank(a) ? r : a), null);
  return (
    <Card size="sm">
      <CardContent className="space-y-2">
        <div className="flex flex-wrap gap-1.5">
          <StatePill label="원천" value={source ? SOURCE_STATUS_LABEL[source.status] : "—"} tone="good" />
          <StatePill label="계산" value={run.status === "SUCCEEDED" ? "계산 완료" : "실패"} tone="good" />
          <StatePill label="위험" value={riskLabel(top?.risk ?? "NORMAL")} tone={top?.risk === "CRITICAL" ? "warn" : "neutral"} />
          <StatePill label="영업 검토" value={review ? `완료 ${formatClock(review.at)}` : "검토 중"} tone={review ? "good" : "neutral"} />
          <StatePill label="전망" value={`${forecast?.version_id ?? "—"} 미승인 (검토 중)`} />
        </div>
        <p className="text-xs text-muted-foreground">
          비교 기준: Target <b>{run.versions.target}</b> · 직전 승인 <b>{run.versions.prior}</b> · 최신 확인{" "}
          <b>{run.versions.latest}</b> · 원가 {run.versions.cost} · 규칙 {run.versions.rule} · 계산{" "}
          <span className="font-mono">{run.run_id}</span> ({formatClock(run.at)})
        </p>
      </CardContent>
    </Card>
  );
}

const ORDER = { NORMAL: 0, ATTENTION: 1, CRITICAL: 2 } as const;
const rank = (a: Assessment) => (a.risk ? ORDER[a.risk] : -1);

function RiskDetail({ run, pick }: { run: CalcRun; pick: { model: string; period: string } }) {
  const rules = useSc01((s) => s.rules);
  const a = run.results.find((r) => r.model_id === pick.model && r.period === pick.period);
  if (!a) return null;
  const m = a.metrics;

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {modelLabel(a.model_id)} {Number(a.period.slice(5, 7))}월 — <RiskTag risk={a.risk} className="align-middle text-sm" />
        </CardTitle>
        <CardDescription>
          목표 {formatQty(a.target)} · 직전 승인 {formatQty(a.prior)} · 최신 {formatQty(a.latest)}대분 · 기준 단위 공헌이익{" "}
          {Number(a.unit_cm).toLocaleString("ko-KR")}원
          {a.partial ? " · 일부 지표 미산출" : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 [&>*]:min-w-0 sm:grid-cols-2 lg:grid-cols-4">
          <Tile label={METRIC_LABEL.KPI01} value={formatMetric("ratio", m.KPI01.value)} note={m.KPI01.reason ?? "최신 ÷ 목표"} />
          {(["KRI01", "KRI02", "KRI03"] as const).map((id) => {
            const t = THRESHOLD[id];
            const unit = m[id].unit;
            const fmt = (k: string) => (unit === "krw" ? `${formatKrw(rules[k])}원` : formatRatio(rules[k], 0));
            return (
              <Tile
                key={id}
                label={METRIC_LABEL[id]}
                value={formatMetric(unit, m[id].value)}
                risk={m[id].risk_level}
                computable={m[id].computable}
                note={
                  m[id].reason ??
                  (rules[t.attention] ? `관심 ≥ ${fmt(t.attention)} · 중요 ≥ ${fmt(t.critical)}` : "")
                }
              />
            );
          })}
        </div>

        <div className="grid gap-3 rounded-md border p-3 text-sm sm:grid-cols-3">
          <div>
            <p className="text-xs text-muted-foreground">이번 추가 감소 (직전 − 최신)</p>
            <p className="text-lg font-semibold tabular-nums">{formatMetric("qty", m.M01.value)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">목표 대비 부족 (목표 − 최신)</p>
            <p className="text-lg font-semibold tabular-nums">{formatMetric("qty", m.M02.value)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">물량 변동 순손익 영향 (부호 유지)</p>
            <p className="text-lg font-semibold tabular-nums">
              {m.M03.value === null ? "미산출" : `${formatKrwSigned(m.M03.value)}원`}
            </p>
          </div>
        </div>
        <p className="text-[11px] text-muted-foreground">
          감소액은 물량 변화만 반영한 초기 공헌이익 영향이다 — 전체 영업이익 변화로 읽지 않는다. 판정은 지표별
          임계값 중 가장 높은 수준이다(R01).
          <Commentary> 비율은 소수 8자리로 반올림한 뒤 판정해 엑셀 기준값과 경계에서 같은 결과를 낸다.</Commentary>
        </p>
      </CardContent>
    </Card>
  );
}

function Tile({
  label,
  value,
  note,
  risk,
  computable = true,
}: {
  label: string;
  value: string;
  note?: string;
  risk?: Assessment["risk"];
  computable?: boolean;
}) {
  return (
    <div className="space-y-1 rounded-md border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-2xl leading-none font-semibold">{value}</p>
      {risk !== undefined ? <RiskTag risk={computable ? risk : null} /> : null}
      {note ? <p className="text-[11px] text-muted-foreground">{note}</p> : null}
    </div>
  );
}

function ModelCompare({
  run,
  pick,
  onPick,
}: {
  run: CalcRun;
  pick: { model: string; period: string };
  onPick: (p: { model: string; period: string }) => void;
}) {
  const totalNet = run.results.reduce((s, r) => s + Number(r.metrics.M03.value ?? 0), 0);
  return (
    <Card>
      <CardHeader>
        <CardTitle>모델별 비교 — {run.versions.prior} → {run.versions.latest}</CardTitle>
        <CardDescription>
          7~9월 × a~e모델. 행을 누르면 위 상세가 바뀐다. 공장 순영향 합계 {formatKrwSigned(totalNet)}원 — 합계가
          상쇄돼도 모델 경보는 그대로다.
        </CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full min-w-[44rem] text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th scope="col" className="py-2 pr-3 font-medium">모델·월</th>
              <th scope="col" className="py-2 pr-3 text-right font-medium">목표</th>
              <th scope="col" className="py-2 pr-3 text-right font-medium">직전</th>
              <th scope="col" className="py-2 pr-3 text-right font-medium">최신</th>
              <th scope="col" className="py-2 pr-3 text-right font-medium">감소율</th>
              <th scope="col" className="py-2 pr-3 text-right font-medium">감소액</th>
              <th scope="col" className="py-2 pr-3 text-right font-medium">부족률</th>
              <th scope="col" className="py-2 font-medium">위험</th>
            </tr>
          </thead>
          <tbody>
            {run.results.map((r) => {
              const on = r.model_id === pick.model && r.period === pick.period;
              return (
                <tr
                  key={`${r.model_id}${r.period}`}
                  className={on ? "cursor-pointer border-b bg-muted/60" : "cursor-pointer border-b hover:bg-muted/40"}
                  onClick={() => onPick({ model: r.model_id, period: r.period })}
                >
                  <th scope="row" className="text-left py-1.5 pr-3 font-normal">
                    {modelLabel(r.model_id)} {Number(r.period.slice(5, 7))}월
                  </th>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{formatQty(r.target)}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{formatQty(r.prior)}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{formatQty(r.latest)}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{formatRatio(r.metrics.KRI01.value)}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{formatKrw(r.metrics.KRI02.value)}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{formatRatio(r.metrics.KRI03.value)}</td>
                  <td className="py-1.5"><RiskTag risk={r.risk} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function IssueHistory({ view }: { view: DemoRunView }) {
  const issues = view.issues.filter((i) => i.history.length > 1 || i.risk === "CRITICAL");
  if (issues.length === 0) return null;
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>이슈 이력</CardTitle>
        <CardDescription>같은 고객·공장·모델·월·원인의 열린 이슈에 새 계산을 잇는다 — 새 이슈를 만들지 않는다.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="space-y-1 text-sm">
          {issues.map((i) => (
            <li key={i.issue_id} className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs">{i.issue_id}</span>
              {i.history.map((h, n) => (
                <span key={h.run_id} className="inline-flex items-center gap-1 text-xs">
                  {n > 0 ? <span className="text-muted-foreground">→</span> : null}
                  <RiskTag risk={h.risk} />
                  <span className="text-muted-foreground">({h.run_id})</span>
                </span>
              ))}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function Decisions({ view }: { view: DemoRunView }) {
  const waiting = view.bpm?.waiting ?? [];
  const sales = waiting.find((w) => w.nodeId === "Approve_Sales");
  const dispatch = waiting.find((w) => w.nodeId === "Approve_Dispatch");
  const reviewReq = waiting.find((w) => w.nodeId === "Approve_Review");
  const review = view.reviews.at(-1);
  const nameOf = useUserName();

  return (
    <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>영업 검토 (CT02)</CardTitle>
          <CardDescription>
            변경의 의미·지속성·고객 재확인 필요성과 처리 경로. 검토 완료에는 사람의 의견과 근거가 필요하다.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {sales ? (
            <ActionForm waiting={sales} submitLabel="검토 완료" />
          ) : review ? (
            <div className="space-y-1 text-sm">
              <p className="text-xs text-muted-foreground">{formatClock(review.at)} · {nameOf(review.by)}</p>
              <p>{review.opinion}</p>
              <p className="text-xs text-muted-foreground">근거: {review.evidence}</p>
              {review.manual_review ? <p className="text-xs">경영 검토 수동 요청</p> : null}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">아직 검토할 차례가 아니다.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>후속 처리</CardTitle>
          <CardDescription>
            현업 영향 검토는 경보와 무관하게 항상 간다. 중요이거나 수동 요청이면 Management Review가 함께 열린다.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {dispatch ? (
            <div className="space-y-2">
              <p className="text-xs font-medium">생산·자재 영향 검토 배정 (CT03)</p>
              <ActionForm waiting={dispatch} submitLabel="배정" />
            </div>
          ) : null}
          {reviewReq ? (
            <div className="space-y-2 border-t pt-3">
              <p className="text-xs font-medium">Management Review 요청</p>
              <ActionForm waiting={reviewReq} submitLabel="요청" />
            </div>
          ) : null}
          {!dispatch && !reviewReq ? (
            <p className="text-sm text-muted-foreground">
              {view.tasks.some((t) => ["PROD", "MAT", "FIN"].includes(t.type))
                ? "배정·요청이 끝났다 — 업무 화면에서 인수 상태를 본다."
                : "영업 검토가 끝나면 열린다."}
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
