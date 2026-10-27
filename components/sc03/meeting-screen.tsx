"use client";

import { useState } from "react";

import { useUserName } from "@/components/sc01/bits";
import { AgentCard } from "@/components/sc03/agent-card";
import { Mn, Sc03Body, Sc03Header, StatusPills, WaitingForms } from "@/components/sc03/bits";
import { Commentary } from "@/components/shared/commentary";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { sc03Api } from "@/lib/sc03/client";
import { DEPT_LABEL, OUTCOME_LABEL } from "@/lib/sc03/format";
import type { Sc03View } from "@/lib/sc03/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc03 } from "@/lib/store/sc03";

/**
 * U34 수시회의 준비 · U35 경영검토와 대안 가능성 탐색. 보고는 **확정본 고정**이다 — 확정본과 최신 초안을 함께
 * 구분해 보인다. 후보는 정성적 탐색이다 — 효과액·우선순위·선택안 확정 버튼은 두지 않는다(UI41).
 */
export function Sc03MeetingScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc03Header id="U34·U35" title="수시 경영검토회의" question="통합 영향을 검토하고 무엇을 더 분석할지 정했는가?" />
      <Sc03Body>{(view) => <Meeting view={view} />}</Sc03Body>
    </main>
  );
}

function Meeting({ view }: { view: Sc03View }) {
  const name = useUserName();
  const mt = view.meetings.find((m) => m.meeting_id === "MT31");
  const frozen = view.reports.find((r) => r.report_id === view.frozenReportId);
  const draft = view.reports.find((r) => r.report_id === view.currentDraftId);
  return (
    <>
      <StatusPills view={view} />
      <WaitingForms
        view={view}
        nodes={["Freeze_Report", "Distribute", "Report_Meeting"]}
        expect={(n) => (n === "Freeze_Report" && view.currentDraftId ? { report: view.currentDraftId } : undefined)}
        labels={{ Freeze_Report: "자료 확정", Distribute: "내부 배포", Report_Meeting: "개회 · 보고" }}
      />

      <Card>
        <CardHeader>
          <CardTitle>MT31 수시 경영검토회의</CardTitle>
          <CardDescription>
            {formatClock(view.schedule.meeting_at)} · 주재 경영관리 임원(강민서) · 자료 확정 {formatClock(view.schedule.freeze_at)}
            {mt ? ` · ${mt.state === "IN_PROGRESS" ? "진행 중" : mt.state === "HELD" ? "개최됨" : "준비 완료"}` : " · 자료 확정 전"}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 text-sm lg:grid-cols-2">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">보고자료</p>
            {frozen ? (
              <p>
                <span className="font-mono">{frozen.report_id}</span> 확정 — {name(frozen.frozen_by)} {formatClock(frozen.frozen_at)}
                {frozen.distributed_at ? ` · 배포 ${formatClock(frozen.distributed_at)}` : " · 배포 전"}
                <span className="block text-xs text-muted-foreground">
                  {frozen.basis_text} · 해시 <span className="font-mono">{frozen.source_hash}</span>
                </span>
              </p>
            ) : (
              <p className="text-muted-foreground">확정본 없음</p>
            )}
            {draft && draft.status !== "CONFIRMED" ? (
              <p className="text-xs text-muted-foreground">
                최신 초안 <span className="font-mono">{draft.report_id}</span> — 미확정
              </p>
            ) : null}
            {frozen ? (
              <p className="text-xs">
                전체 부족 <Mn value={frozen.kpis.total_gap} /> = 기존 부족 <Mn value={frozen.kpis.existing_gap} /> − 이번 사건 영향(
                <Mn value={frozen.kpis.event_effect} />) 백만원
              </p>
            ) : null}
          </div>
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">참석</p>
            {mt?.attendance.length ? (
              <p>{mt.attendance.map((a) => name(a.actor)).join(" · ")}</p>
            ) : (
              <p className="text-muted-foreground">경영관리 임원 · 경영관리 담당·책임자 · 영업·구매·생산 책임자(개회 때 기록)</p>
            )}
            <p className="text-xs text-muted-foreground">품질·대표는 이 회의의 참석·승인자가 아니다 — 대표는 7/12 MT41 주재.</p>
          </div>
        </CardContent>
      </Card>

      {view.revisions.length ? (
        <Card>
          <CardHeader>
            <CardTitle>새 전망 버전 — 재확인 대기</CardTitle>
            <CardDescription>확정본은 그대로다. 새 자료는 임원 재확인 뒤에 쓴다(E34).</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {view.revisions.map((r) => (
                <li key={r.report_id}>
                  <span className="font-mono">{r.report_id}</span> ← {r.base_report} · {r.reason}
                  <span className="block text-xs text-muted-foreground">
                    {r.changes.map((c) => `${c.label} ${Number(c.diff).toLocaleString("ko-KR")}원`).join(" · ")}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      {mt && mt.state !== "READY" ? <Records view={view} /> : null}

      <Card>
        <CardHeader>
          <CardTitle>대응 후보 가능성 탐색</CardTitle>
          <CardDescription>정성적 설명 — 효과액은 미산정이다. 포함은 상세 분석 지시이지 실행안 선택이 아니다.</CardDescription>
        </CardHeader>
        <CardContent>
          {view.candidates.length === 0 ? (
            <p className="text-sm text-muted-foreground">회의가 열리면 부서가 준비한 후보 설명이 보인다.</p>
          ) : (
            <ul className="grid gap-2 sm:grid-cols-2">
              {view.candidates.map((c) => (
                <li key={c.candidate_id} className="space-y-1 rounded-md border px-3 py-2 text-sm">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs">{c.candidate_id}</span>
                    <span className="text-xs text-muted-foreground">{DEPT_LABEL[c.dept] ?? c.dept}</span>
                    {c.decision ? (
                      <span
                        className="rounded border px-1.5 py-0.5 text-[10px] font-medium"
                        style={{ color: c.decision === "INCLUDE" ? "var(--viz-delta-good)" : undefined }}
                      >
                        {c.decision === "INCLUDE" ? `상세 분석 → ${c.task_id ?? ""}` : "이번 분석 제외"}
                      </span>
                    ) : null}
                  </p>
                  <p className="font-medium">{c.candidate}</p>
                  <p className="text-xs">기대 작용: {c.mechanism}</p>
                  <p className="text-xs text-muted-foreground">확인 필요: {c.constraints} · 근거 {c.evidence_ref}</p>
                  {c.decision_reason ? <p className="text-xs">판단: {c.decision_reason}</p> : null}
                  <p className="text-[11px] text-muted-foreground">효과 2027 미산정 · 12개월 미산정</p>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <AgentCard view={view} kind="AG31" />
      <WaitingForms
        view={view}
        nodes={["Decide_Review"]}
        expect={() => (view.frozenReportId ? { report: view.frozenReportId } : undefined)}
        labels={{ Decide_Review: "결론 · 후보 판단 확정" }}
      />

      {view.decision ? (
        <Card>
          <CardHeader>
            <CardTitle>검토 결론 {view.decision.decision_id}</CardTitle>
            <CardDescription>
              {OUTCOME_LABEL[view.decision.outcome]} · {name(view.decision.decided_by)} {formatClock(view.decision.decided_at)} — 공식 Forecast 승인과 무관하다
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p>{view.decision.content}</p>
            {view.decision.conditions ? <p className="text-xs text-muted-foreground">조건: {view.decision.conditions}</p> : null}
          </CardContent>
        </Card>
      ) : null}
      <Commentary>
        <p className="text-xs text-muted-foreground">
          회의는 계산값 확인에 그치지 않고 어떤 가정에 따라 결과가 달라지는지, 무엇이 일시적이고 무엇을 계속 볼지 검토한다. 상세 비교·선택은 대표 주재 월간회의다.
        </p>
      </Commentary>
    </>
  );
}

const RECORD_LABEL: Record<string, string> = { QUESTION: "질의", ANSWER: "답변", EXPLANATION: "설명", NOTE: "메모" };

/** 회의 질의·답변·설명 — 참석자만 적는다(BPM 밖의 회의 기록). */
function Records({ view }: { view: Sc03View }) {
  const name = useUserName();
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const mt = view.meetings.find((m) => m.meeting_id === "MT31")!;
  const [type, setType] = useState("QUESTION");
  const [content, setContent] = useState("");
  const [error, setError] = useState<string | null>(null);
  const attendee = mt.attendance.some((a) => a.actor === actor);
  const submit = async () => {
    if (!demoRunId) return;
    setError(null);
    const r = await sc03Api.record(demoRunId, { type, subject: RECORD_LABEL[type], content, related: "" }, actor);
    if (r.ok) {
      useSc03.getState().setLive(r.data);
      setContent("");
    } else setError(`${r.status} — ${r.error}`);
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>질의 · 답변 기록</CardTitle>
        <CardDescription>참석자가 적는다 — 결론과 다른 기록이다.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {mt.records.length === 0 ? (
          <p className="text-muted-foreground">아직 기록이 없다.</p>
        ) : (
          <ul className="divide-y">
            {mt.records.map((r) => (
              <li key={r.record_id} className="py-1.5">
                <span className="font-mono text-xs">{r.record_id}</span>{" "}
                <span className="text-xs text-muted-foreground">
                  {RECORD_LABEL[r.record_type] ?? r.record_type} · {name(r.actor_id)} {formatClock(r.event_at).slice(-5)}
                </span>
                <p>{r.content}</p>
              </li>
            ))}
          </ul>
        )}
        {mt.state === "IN_PROGRESS" && !view.historical ? (
          <form
            className="flex flex-wrap items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <select value={type} onChange={(e) => setType(e.target.value)} aria-label="기록 종류" className="h-8 rounded-md border bg-transparent px-1 text-xs">
              {Object.entries(RECORD_LABEL).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
            <input
              value={content}
              onChange={(e) => setContent(e.target.value)}
              aria-label="내용"
              placeholder={attendee ? "내용" : "MT31 참석자만 기록한다"}
              className="h-8 min-w-[12rem] flex-1 rounded-md border bg-transparent px-2 text-sm"
            />
            <Button type="submit" size="sm" disabled={!attendee || !content.trim()}>
              기록
            </Button>
          </form>
        ) : null}
        {error ? (
          <p role="alert" className="text-xs" style={{ color: "var(--viz-status-critical)" }}>
            거절됨: {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
