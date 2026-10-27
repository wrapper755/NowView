"use client";

import { useUserName } from "@/components/sc01/bits";
import { AgentCard } from "@/components/sc05/agent-card";
import { Mn, Requirements, Sc05Body, Sc05Header, StatusPills, Tile, WaitingForms } from "@/components/sc05/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { gapWord, OPERATION_STATE_LABEL, TASK_NAME } from "@/lib/sc05/format";
import type { Sc05View } from "@/lib/sc05/types";

/** 후속 목록 틀 — 담당·기한은 경영관리 임원이 확정한다(비워 두면 완료가 막힌다, T531). */
const TEMPLATE = [
  "FUP51 | ACT42 |  |  | 긴급건수 가정·확인 지연 재발 점검",
  "FUP52 | ACT41 |  |  | 품질·납기·외주 조건 월별 확인",
  "FUP53 | ACT43 |  |  | 적용 후 안정화 확인",
  "DIR41 | 추가과제 |  |  | 후보 조사 지속 — 근거 미확정 효과는 미산정",
  "RISK51 | 기존 MR-2706-01 위험 연결 |  |  | 목표 미달 가능성과 미실현 전망 위험 유지",
].join("\n");

/**
 * U508 실행·위험 후속 관리 — 장면 완료 요건과 새 공식 전망, 과제별 상태·다음 확인일, 남는 목표 부족·Risk OPEN,
 * DIR41·미확인 항목의 책임자·기한. 장면 완료로 과제 완료·위험 종결을 자동 처리하지 않는다.
 */
export function Sc05HandoffScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc05Header id="U508" title="실행·위험 후속 관리" question="무엇이 남았고, 누가 언제까지 확인하는가?" />
      <Sc05Body>{(view) => <Body view={view} />}</Sc05Body>
    </main>
  );
}

function Body({ view }: { view: Sc05View }) {
  const nameOf = useUserName();
  const waiting = new Set((view.bpm?.waiting ?? []).map((w) => w.nodeId));
  const official = view.forecasts.find((f) => f.forecast_id === view.official);
  const run = view.runs.find((r) => r.run_id === official?.run_id);
  const h = view.handoff;
  const followups = h?.followups ?? view.followups;
  return (
    <>
      <StatusPills view={view} />
      <div className="grid gap-3 sm:grid-cols-3">
        <Tile label={`공식 전망 ${view.official ?? ""}`} note={official?.published_at ? `게시 ${formatClock(official.published_at)}` : "새 공식본 게시 전"}>
          <Mn value={official?.annual ?? null} empty="—" />
        </Tile>
        <Tile label={`남는 연간 ${gapWord(run?.gap)}`} note="Target 유지 · Risk OPEN">
          <Mn value={run?.gap ?? null} empty="—" />
        </Tile>
        <Tile label="연간 과제효과(마감 + 잔여)" note={run ? `마감 ${Number(run.periods.closed.effect).toLocaleString("ko-KR")} · 잔여 ${Number(run.periods.forecast.effect).toLocaleString("ko-KR")}원` : ""}>
          <Mn value={run?.periods.year.effect ?? null} empty="—" />
        </Tile>
      </div>

      <WaitingForms view={view} nodes={["Complete_Scene"]} initial={{ Complete_Scene: { 후속목록: TEMPLATE } }} labels={{ Complete_Scene: "결정 실행·계획 갱신 인계 완료" }} />
      <AgentCard view={view} kind="AG58" canRequest={waiting.has("Complete_Scene")} />

      <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>업무 완료 요건</CardTitle>
            <CardDescription>{h ? `${h.handoff_id} — ${nameOf(h.completed_by)} ${formatClock(h.completed_at)}` : "확정 계획부터 공식 전망·후속 책임까지 연결돼야 마친다."}</CardDescription>
          </CardHeader>
          <CardContent>{view.completion ? <Requirements items={view.completion.items} /> : <p className="text-sm text-muted-foreground">착수 전이다.</p>}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>실행과제별 상태</CardTitle>
            <CardDescription>과제 기한 도래만으로 완료하지 않는다 — 운영 정착 기준으로 확인한다.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {view.operation.map((o) => (
                <li key={o.task_id}>
                  <span className="font-medium">
                    {o.task_id} {TASK_NAME[o.task_id]}
                  </span>{" "}
                  · {OPERATION_STATE_LABEL[o.state] ?? o.state} · 책임 {nameOf(o.owner)}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>후속 책임·기한</CardTitle>
          <CardDescription>DIR41 추가과제의 미확정 효과는 금액에 넣지 않는다(미산정). RISK51은 기존 검토건 위험의 상태 참조다 — 새 위험을 만들지 않는다.</CardDescription>
        </CardHeader>
        <CardContent>
          {followups.length === 0 ? (
            <p className="text-sm text-muted-foreground">아직 확정 전이다 — 업무 인계 때 경영관리 임원이 확정한다.</p>
          ) : (
            <ul className="divide-y text-sm">
              {followups.map((f) => (
                <li key={f.followup_id} className="py-1.5">
                  <span className="font-medium">{f.followup_id}</span> {f.target} · {nameOf(f.owner)} · {formatClock(f.due_at)}
                  {f.state ? ` · ${f.state}` : ""}
                  <span className="block text-xs text-muted-foreground">{f.content}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>연결 기록</CardTitle>
          <CardDescription>계획·조건·품의·실행·결과·승인 기록 — 근거는 작성·확인 시각이 지난 것만 보인다.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <Disclosure summary={`근거 ${view.evidence.length}건`}>
            <ul className="space-y-1 text-xs">
              {view.evidence.map((e) => (
                <li key={e.evidence_id}>
                  <span className="font-mono">{e.evidence_id}</span> {e.type} · {formatClock(e.written_at)}
                  {e.confirmed_at ? ` · 확인 ${nameOf(e.confirmed_by)}` : " · 확인 전"}
                  <span className="block text-muted-foreground">{e.body}</span>
                </li>
              ))}
            </ul>
          </Disclosure>
          <Disclosure summary={`감사 이력 최근 ${Math.min(view.audit.length, 30)}건`}>
            <ul className="space-y-0.5 text-xs">
              {view.audit
                .slice(-30)
                .reverse()
                .map((a) => (
                  <li key={a.seq}>
                    {formatClock(a.at)} {a.event_code ? <span className="font-mono">{a.event_code}</span> : null} {a.actor_name} · {a.action}
                  </li>
                ))}
            </ul>
          </Disclosure>
          <Commentary>
            <p className="text-xs text-muted-foreground">
              업무 완료 · 개별 실행과제 완료 · 연간 목표 달성 · 위험 해소는 서로 다른 상태다. Management Evolution(프레임워크·프로세스·Agent 개선 확정)은 후속
              업무다.
            </p>
          </Commentary>
        </CardContent>
      </Card>
    </>
  );
}
