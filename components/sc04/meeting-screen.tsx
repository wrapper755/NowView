"use client";

import { useState } from "react";
import { Send } from "lucide-react";

import { useUserName } from "@/components/sc01/bits";
import { AgentCard } from "@/components/sc04/agent-card";
import { Mn, Sc04Body, Sc04Header, WaitingForms } from "@/components/sc04/bits";
import { Commentary } from "@/components/shared/commentary";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { sc04Api } from "@/lib/sc04/client";
import { DIRECTIVE_KIND_LABEL, gapWord, RECORD_TYPE_LABEL } from "@/lib/sc04/format";
import type { Sc04View } from "@/lib/sc04/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc04 } from "@/lib/store/sc04";

/**
 * U405 대표 질의와 실행 애로 조정 — 질문·실제 답변·지원 지시를 **다른 유형의 기록**으로 둔다(Agent 초안과 사람이
 * 확인한 발언도 다른 카드다). 질의로 바뀐 가정은 원 보고본을 복제한 판단 초안에서 같은 규칙으로 재계산하고,
 * 보고본과 판단본을 나란히 보인다 — 합산하지 않는다.
 */
export function Sc04MeetingScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc04Header id="U405" title="대표 질의·애로 조정" question="효과 시점·품질·납기·현업 애로를 질문으로 점검하고 해결 방향을 정했는가?" />
      <Sc04Body>{(view) => <Meeting view={view} />}</Sc04Body>
    </main>
  );
}

function Meeting({ view }: { view: Sc04View }) {
  const name = useUserName();
  const m = view.meeting;
  const decision = view.reports.find((r) => r.kind === "DECISION" && r.status !== "SUPERSEDED");
  const rep = view.reports.find((r) => r.report_id === "REP41-v1");
  const repRun = rep ? view.runs.find((r) => r.run_id === rep.run_id) : undefined;
  const decRun = decision ? view.runs.find((r) => r.run_id === decision.run_id) : undefined;
  return (
    <>
      <WaitingForms
        view={view}
        nodes={["Draft_Decision", "Confirm_Decision"]}
        expect={(n) => (n === "Confirm_Decision" && view.decisionId ? { report: view.decisionId } : undefined)}
        labels={{ Draft_Decision: "판단 초안 저장", Confirm_Decision: "판단본 확인" }}
      />
      <Card>
        <CardHeader>
          <CardTitle>회의 기록 {m?.records.length ?? 0}건</CardTitle>
          <CardDescription>
            {m ? `${m.meeting_id} · ${m.state === "IN_PROGRESS" ? "진행 중" : m.state === "HELD" ? "종료" : "개회 전"}` : "MT41 개회 전"} · 질의·지시는 대표, 답변은 담당 임원
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {m?.records.length ? (
            <ol className="space-y-2 text-sm">
              {m.records.map((r) => (
                <li key={r.record_id} className="grid gap-x-3 sm:grid-cols-[9rem_1fr]">
                  <span className="text-xs text-muted-foreground">
                    <span className="font-mono">{r.record_id}</span> {formatClock(r.event_at).slice(-5)} · {RECORD_TYPE_LABEL[r.record_type]}
                  </span>
                  <span>
                    <span className="text-xs text-muted-foreground">{name(r.actor_id)} — </span>
                    {r.content}
                    {r.related_ref ? <span className="ml-1 font-mono text-[10px] text-muted-foreground">[{r.related_ref}]</span> : null}
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-muted-foreground">아직 기록이 없다.</p>
          )}
          {m?.state === "IN_PROGRESS" && !view.historical ? <RecordForm view={view} /> : null}
        </CardContent>
      </Card>
      <AgentCard view={view} kind="AG42" />

      {repRun && decRun ? (
        <Card>
          <CardHeader>
            <CardTitle>보고본 → 판단본</CardTitle>
            <CardDescription>
              {rep!.report_id} → {decision!.report_id}({decision!.status === "CONFIRMED" ? `확인 ${name(decision!.frozen_by)} ${formatClock(decision!.frozen_at)}` : "초안"}) · 변경 사유: {decision!.reason || "—"}
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm" aria-label="보고본과 판단본">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-1.5 pr-3 font-medium">항목</th>
                  <th className="py-1.5 pr-3 text-right font-medium">보고본</th>
                  <th className="py-1.5 pr-3 text-right font-medium">판단본</th>
                  <th className="py-1.5 text-right font-medium">차이</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {decision!.diff?.map((d) => (
                  <tr key={d.alt_id}>
                    <th scope="row" className="py-1.5 pr-3 text-left font-normal">
                      {d.alt_id} 순효과
                      {d.start_before !== d.start_after ? (
                        <span className="ml-1 text-xs text-muted-foreground">
                          (시작 {d.start_before.slice(0, 7)} → {d.start_after.slice(0, 7)})
                        </span>
                      ) : null}
                    </th>
                    <td className="py-1.5 pr-3 text-right">
                      <Mn value={d.before} />
                    </td>
                    <td className="py-1.5 pr-3 text-right">
                      <Mn value={d.after} />
                    </td>
                    <td className="py-1.5 text-right">
                      <Mn value={d.diff} signed />
                    </td>
                  </tr>
                ))}
                <tr className="font-medium">
                  <th scope="row" className="py-1.5 pr-3 text-left">실행안 순효과</th>
                  <td className="py-1.5 pr-3 text-right">
                    <Mn value={repRun.result.effect_total} />
                  </td>
                  <td className="py-1.5 pr-3 text-right">
                    <Mn value={decRun.result.effect_total} />
                  </td>
                  <td className="py-1.5 text-right">
                    <Mn value={String(Number(decRun.result.effect_total) - Number(repRun.result.effect_total))} signed />
                  </td>
                </tr>
                <tr>
                  <th scope="row" className="py-1.5 pr-3 text-left font-normal">연간 목표 {gapWord(decRun.result.periods.year.gap)}</th>
                  <td className="py-1.5 pr-3 text-right">
                    <Mn value={repRun.result.periods.year.gap} />
                  </td>
                  <td className="py-1.5 pr-3 text-right">
                    <Mn value={decRun.result.periods.year.gap} />
                  </td>
                  <td className="py-1.5 text-right" />
                </tr>
              </tbody>
            </table>
            <Commentary>
              <p className="mt-2 text-xs text-muted-foreground">
                시작월을 옮겨도 일회성 준비비는 원래 달에 그대로 남는다(자동으로 함께 움직이지 않는다). 지연은 평균 금액이 아니라 월별 근거로 다시
                계산한다.
              </p>
            </Commentary>
          </CardContent>
        </Card>
      ) : null}

      {view.directives.length ? (
        <Card>
          <CardHeader>
            <CardTitle>조건·지원·추가 지시</CardTitle>
            <CardDescription>책임·협조·확인자·기한이 있어야 승인 대상이다. 조건 충족 전에는 해당 실행 착수가 제한된다.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {view.directives.map((d) => (
                <li key={d.directive_id}>
                  <span className="font-mono text-xs">{d.directive_id}</span> <span className="text-xs text-muted-foreground">{DIRECTIVE_KIND_LABEL[d.kind]}</span> {d.content}
                  <p className="text-xs text-muted-foreground">
                    책임 {name(d.owner)} · 협조 {d.collaborators.map((c) => name(c)).join(", ") || "—"} · 확인 {name(d.verifier)} · 기한 {formatClock(d.due_at)} · 효과{" "}
                    {d.expected_effect === null ? "미산정" : <Mn value={d.expected_effect} />}
                  </p>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </>
  );
}

const TYPES = ["QUESTION", "DIRECTIVE", "ANSWER", "NOTE"] as const;

/** 회의 기록 — 참석자만, 질의·지시는 대표, 답변은 담당 임원(엔진이 검사한다 — 버튼은 편의다). */
function RecordForm({ view }: { view: Sc04View }) {
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const [type, setType] = useState<(typeof TYPES)[number]>(actor === "u-ceo" ? "QUESTION" : "ANSWER");
  const [content, setContent] = useState("");
  const [related, setRelated] = useState("ALT42");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const attendee = view.meeting?.attendance.some((a) => a.actor === actor) ?? false;
  const submit = async () => {
    if (!demoRunId) return;
    setBusy(true);
    setError(null);
    const r = await sc04Api.record(demoRunId, { type, subject: RECORD_TYPE_LABEL[type], content, related }, actor);
    setBusy(false);
    if (r.ok) {
      useSc04.getState().setLive(r.data);
      setContent("");
    } else setError(`${r.status} — ${r.error}`);
  };
  return (
    <form
      className="space-y-2 rounded-md border p-3"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <div className="flex flex-wrap gap-2 text-xs">
        <label className="flex items-center gap-1">
          유형
          <select className="rounded border bg-background px-1 py-0.5" value={type} onChange={(e) => setType(e.target.value as (typeof TYPES)[number])}>
            {TYPES.map((t) => (
              <option key={t} value={t}>
                {RECORD_TYPE_LABEL[t]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1">
          관련
          <input className="w-24 rounded border bg-background px-1 py-0.5" value={related} onChange={(e) => setRelated(e.target.value)} />
        </label>
      </div>
      <textarea
        aria-label="기록 내용"
        className="min-h-16 w-full rounded border bg-background px-2 py-1 text-sm"
        value={content}
        onChange={(e) => setContent(e.target.value)}
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" size="sm" disabled={busy || !attendee || !content.trim()}>
          <Send aria-hidden className="size-3.5" />
          기록
        </Button>
        {!attendee ? <span className="text-xs text-muted-foreground">MT41 참석자만 기록한다 — 상단에서 역할을 바꾼다.</span> : null}
        {error ? (
          <span role="alert" className="text-xs" style={{ color: "var(--viz-status-critical)" }}>
            거절됨: {error}
          </span>
        ) : null}
      </div>
    </form>
  );
}
