"use client";

import { useState } from "react";
import Link from "next/link";
import { CheckCircle2, CircleDashed, PlayCircle } from "lucide-react";

import { useUserName } from "@/components/sc01/bits";
import { Mn, Sc04Body, Sc04Header, StatusPills, WaitingForms } from "@/components/sc04/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { sc04Api } from "@/lib/sc04/client";
import { RESULT_STATE_LABEL } from "@/lib/sc04/format";
import type { AnalysisResult, Sc04View } from "@/lib/sc04/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc04 } from "@/lib/store/sc04";

/** 진행 단계(업무설계표 SC04-S01~S14) — 기록에서 파생한다. */
const STAGES: { id: string; label: string; done: (v: Sc04View) => boolean; href: string }[] = [
  { id: "S01·02", label: "착수 · 결과 제출·확인", done: (v) => v.results.length > 0 && v.results.every((r) => r.state === "CONFIRMED"), href: "/sc04" },
  { id: "S03·04", label: "비용·중복 검증", done: (v) => v.verification?.state === "VERIFIED", href: "/sc04/verify" },
  { id: "S05", label: "우선 실행안 제안", done: (v) => v.recommendation !== null, href: "/sc04/recommend" },
  { id: "S06·07", label: "보고본 · 월간회의 보고", done: (v) => v.meeting !== null && v.meeting.state !== "READY", href: "/sc04/report" },
  { id: "S08·09", label: "대표 질의 · 판단본", done: (v) => v.reports.some((r) => r.kind === "DECISION" && r.status === "CONFIRMED"), href: "/sc04/meeting" },
  { id: "S10·11", label: "대표 결정 · 승인서", done: (v) => v.approvals.length > 0, href: "/sc04/approval" },
  { id: "S12·13", label: "과제 등록 · 책임 인수", done: (v) => v.completion.rate.assigned > 0 && v.completion.rate.accepted === v.completion.rate.assigned && v.completion.rate.overall_accepted, href: "/sc04/actions" },
  { id: "S14", label: "인계 · 종료", done: (v) => v.handoff !== null, href: "/sc04/handoff" },
];

const TITLE: Record<string, string> = {
  AT31: "부분 공정·외주 비중 조정",
  AT32: "구매조건·긴급구매·대체 공급업체",
  AT33: "고객·모델 물량 배분",
  AT34: "기존 목표 부족 원인",
};

/**
 * U401 분석 결과 업무함 — 장면 3 인계(HANDOFF31)와 MT41 일정, AT31~AT34의 제출·임원 확인 현황, 선택한 결과의
 * 근거·가정·리스크·애로·제외 사유. 착수는 경영관리 담당이 한다(S01). 미제출과 검토 후 제외는 다르다(AC402).
 */
export function Sc04InboxScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc04Header id="U401" title="분석 결과 업무함" question="수익성 통합 분석의 분석 지시가 결과로 돌아와 의사결정의 입력이 됐는가?" />
      <Sc04Body>{(view) => <Inbox view={view} />}</Sc04Body>
    </main>
  );
}

function StartButton({ view }: { view: Sc04View }) {
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (view.review.started_at !== null || view.historical) return null;
  const start = async () => {
    if (!demoRunId) return;
    setBusy(true);
    setError(null);
    const r = await sc04Api.start(demoRunId, actor, crypto.randomUUID());
    setBusy(false);
    if (r.ok) useSc04.getState().setLive(r.data);
    else setError(`${r.status} — ${r.error}`);
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>지금 할 일 — 개선안 검토·실행 승인 착수</CardTitle>
        <CardDescription>담당 경영관리 담당 · 기존 검토건 MR-2706-01에 HANDOFF31과 AT31~AT34를 잇는다(수익성 통합 분석을 다시 승인하지 않는다).</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <Button size="sm" onClick={() => void start()} disabled={busy || actor !== "u-fin"}>
          <PlayCircle aria-hidden className="size-3.5" />
          {busy ? "착수하는 중…" : "개선안 검토·실행 승인 착수"}
        </Button>
        {actor !== "u-fin" ? <p className="text-xs text-muted-foreground">경영관리 담당(정하윤) 역할만 착수한다 — 상단에서 역할을 바꾼다.</p> : null}
        {error ? (
          <p role="alert" className="text-xs" style={{ color: "var(--viz-status-critical)" }}>
            거절됨: {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Inbox({ view }: { view: Sc04View }) {
  const name = useUserName();
  const [picked, setPicked] = useState("RES41");
  const h = view.sc03.handoff;
  const result = view.results.find((r) => r.result_id === picked) ?? view.results[0];
  const kpis = view.sc03.kpis;
  return (
    <>
      <StartButton view={view} />
      <WaitingForms
        view={view}
        nodes={["Submit_AT31", "Confirm_AT31", "Submit_AT32", "Confirm_AT32", "Submit_AT33", "Confirm_AT33", "Submit_AT34", "Confirm_AT34"]}
        labels={Object.fromEntries(["AT31", "AT32", "AT33", "AT34"].flatMap((t) => [[`Submit_${t}`, "결과 제출"], [`Confirm_${t}`, "확인 기록"]]))}
      />
      <StatusPills view={view} />

      <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>수익성 통합 분석 인계 — {h.handoff_id}</CardTitle>
            <CardDescription>
              {String(h.report_version)} · {String(h.minutes_version)} · 대응 전 Target 대비 부족 <Mn value={kpis.total_gap ?? null} />백만원
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
              <dt className="text-muted-foreground">분석 제출기한</dt>
              <dd>{formatClock(h.analysis_due)}</dd>
              <dt className="text-muted-foreground">경영관리 취합</dt>
              <dd>{formatClock(h.consolidation_due)}</dd>
              <dt className="text-muted-foreground">월간 경영회의</dt>
              <dd>
                {h.next_meeting.meeting_id} · {formatClock(h.next_meeting.at)} · 대표이사 주재
              </dd>
              <dt className="text-muted-foreground">기준 관리손익</dt>
              <dd>
                <Mn value={kpis.combined ?? null} />백만원 (Target <Mn value={kpis.target ?? null} />)
              </dd>
            </dl>
            <Commentary>
              <p className="text-xs text-muted-foreground">
                수익성 통합 분석은 손익영향과 추가 분석 범위를 정했고, 개선안 검토·실행 승인은 그 분석 결과로 실행을 승인한다. 승인만으로 예상 효과를 실적으로 보거나
                목표 미달 위험을 해소된 것으로 보지 않는다.
              </p>
            </Commentary>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>진행 단계</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="space-y-1 text-xs">
              {STAGES.map((s) => (
                <li key={s.id}>
                  <Link href={s.href} className="flex items-center gap-1.5 hover:underline">
                    {s.done(view) ? (
                      <CheckCircle2 aria-hidden className="size-3.5" style={{ color: "var(--viz-status-good)" }} />
                    ) : (
                      <CircleDashed aria-hidden className="size-3.5 text-muted-foreground" />
                    )}
                    <span className="font-mono text-muted-foreground">{s.id}</span> {s.label}
                  </Link>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>분석과제 결과 {view.results.filter((r) => r.state === "CONFIRMED").length}/4 확인</CardTitle>
          <CardDescription>작성은 부서 책임자, 확인은 담당 임원 — 서로 다른 사람이다. 행을 누르면 아래에 상세가 나온다.</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {view.results.length === 0 ? (
            <p className="text-sm text-muted-foreground">착수 전이다 — 제출 현황은 착수 뒤에 생긴다.</p>
          ) : (
            <table className="w-full min-w-[640px] text-sm" aria-label="분석과제 결과">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-1.5 pr-3 font-medium">과제 → 결과</th>
                  <th className="py-1.5 pr-3 font-medium">작성</th>
                  <th className="py-1.5 pr-3 font-medium">확인</th>
                  <th className="py-1.5 pr-3 font-medium">상태</th>
                  <th className="py-1.5 font-medium">제출</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {view.results.map((r) => {
                  const cur = r.versions.at(-1);
                  return (
                    <tr key={r.result_id} className={picked === r.result_id ? "bg-muted/50" : undefined}>
                      <th scope="row" className="py-1.5 pr-3 text-left font-normal">
                        <button type="button" className="text-left hover:underline" onClick={() => setPicked(r.result_id)}>
                          <span className="font-mono text-xs">{r.task_id} → {cur?.ref ?? r.result_id}</span> {TITLE[r.task_id]}
                          {cur?.outcome === "EXCLUDED" ? <span className="ml-1 rounded border px-1 text-[10px]">검토 후 제외</span> : null}
                        </button>
                      </th>
                      <td className="py-1.5 pr-3 text-xs">{name(r.writer)}</td>
                      <td className="py-1.5 pr-3 text-xs">{name(r.confirmer)}</td>
                      <td className="py-1.5 pr-3 text-xs">{RESULT_STATE_LABEL[r.state]}</td>
                      <td className="py-1.5 text-xs">{cur ? formatClock(cur.submitted_at) : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {result && result.versions.length > 0 ? <ResultDetail result={result} /> : null}

      {view.followups.length ? (
        <Card>
          <CardHeader>
            <CardTitle>수익성 통합 분석 미확인 사항의 후속 확인</CardTitle>
            <CardDescription>과거 상태는 그대로 두고 7월 확인 이력만 더한다 — 위험 해소가 아니다.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {view.followups.map((q) => (
                <li key={q.question_id}>
                  <span className="font-mono text-xs">{q.question_id}</span> {q.question}
                  <ul className="mt-0.5 space-y-0.5 pl-4 text-xs text-muted-foreground">
                    {q.history.map((x) => (
                      <li key={`${x.at}-${x.note}`}>
                        {formatClock(x.at)} — {x.note}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </>
  );
}

function ResultDetail({ result }: { result: AnalysisResult }) {
  const name = useUserName();
  const cur = result.versions.at(-1)!;
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {cur.ref} — {cur.outcome === "EXCLUDED" ? "검토 후 제외" : "제출 결과"}
        </CardTitle>
        <CardDescription>
          작성 {name(cur.submitted_by)} {formatClock(cur.submitted_at)}
          {cur.confirmation
            ? ` · ${cur.confirmation.decision === "CONFIRMED" ? "확인" : "보완 요청"} ${name(cur.confirmation.by)} ${formatClock(cur.confirmation.at)}`
            : " · 임원 확인 전"}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p>{cur.conclusion}</p>
        {cur.reason ? (
          <p className="text-xs">
            <span className="text-muted-foreground">제외 사유</span> {cur.reason}
          </p>
        ) : null}
        {cur.risks ? (
          <p className="text-xs">
            <span className="text-muted-foreground">리스크·애로</span> {cur.risks}
          </p>
        ) : null}
        <p className="text-xs text-muted-foreground">
          근거 {cur.evidence_refs.join(" · ")}
          {cur.assumption_refs.length ? ` · 가정 ${cur.assumption_refs.join(" · ")}` : ""}
          {cur.confirmation?.opinion ? ` · 확인 의견: ${cur.confirmation.opinion}` : ""}
        </p>
        {cur.causes ? (
          <Disclosure summary="기존 부족 원인 — 모델별 산술 기여(T01 − F01 수량 × C01 단위CM)">
            <table className="w-full text-xs" aria-label="기존 부족 원인">
              <thead className="text-left text-muted-foreground">
                <tr>
                  <th className="py-1 pr-3 font-medium">모델</th>
                  <th className="py-1 pr-3 text-right font-medium">T01</th>
                  <th className="py-1 pr-3 text-right font-medium">F01</th>
                  <th className="py-1 text-right font-medium">기여(백만원)</th>
                </tr>
              </thead>
              <tbody>
                {cur.causes.map((c) => (
                  <tr key={c.model_id}>
                    <th scope="row" className="py-1 pr-3 text-left font-normal">{c.model_id}</th>
                    <td className="py-1 pr-3 text-right tabular-nums">{c.t01.toLocaleString("ko-KR")}</td>
                    <td className="py-1 pr-3 text-right tabular-nums">{c.f01.toLocaleString("ko-KR")}</td>
                    <td className="py-1 text-right">
                      <Mn value={c.contribution} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-1 text-xs text-muted-foreground">원인분석 결과 자체를 새 절감효과로 계상하지 않는다 — 남는 부족은 추가 발굴(DIR41)로 잇는다.</p>
          </Disclosure>
        ) : null}
        {result.versions.length > 1 ? (
          <Disclosure summary={`이전 버전 ${result.versions.length - 1}건`}>
            <ul className="space-y-0.5 text-xs text-muted-foreground">
              {result.versions.slice(0, -1).map((v) => (
                <li key={v.ref}>
                  {v.ref} · {formatClock(v.submitted_at)} · {v.confirmation?.decision === "REWORK_REQUESTED" ? `보완 요청 — ${v.confirmation.opinion}` : (v.change ?? "")}
                </li>
              ))}
            </ul>
          </Disclosure>
        ) : null}
      </CardContent>
    </Card>
  );
}
