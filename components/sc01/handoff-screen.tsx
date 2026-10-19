"use client";

import { CheckCircle2, CircleDashed } from "lucide-react";

import { Loading, RiskTag, ScreenHeader, StatePill, useUserName } from "@/components/sc01/bits";
import { Commentary } from "@/components/shared/commentary";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock, modelLabel, SCENE_LABEL, TASK_STATUS_LABEL, TASK_TYPE_LABEL } from "@/lib/sc01/format";
import type { AuditEntry, DemoRunView } from "@/lib/sc01/types";
import { selectView, useSc01 } from "@/lib/store/sc01";

const CONDITION_LABEL: Record<string, string> = {
  valid_evidence: "확인된 원천과 성공한 계산이 같은 근거로 연결됨",
  sales_reviewed: "영업 검토 의견·근거·검토자 존재",
  follow_ups_accepted: "필수 후속 업무가 각각 인수됨",
  not_blocked: "미해결 데이터 오류·재검토 대기 없음",
};

const ACTION_LABEL: Record<string, string> = {
  demo_run_created: "기준 적재(S0)",
  demo_run_reset: "데모 초기화",
  clock_moved: "가상시계 이동",
  source_received: "고객계획 수신",
  task_assigned: "업무 배정",
  task_completed: "업무 완료",
  task_accepted: "업무 인수",
  task_needs_info: "보완 요청",
  calculation_requested: "비교 계산 요청",
  calculated: "비교 계산 완료",
  dispatched: "현업 검토 배정",
  review_requested: "Management Review 요청",
  SCENE_HANDED_OFF: "장면 1 인계 완료",
  task_reconfirmed: "새 근거 재확인",
  agent_requested: "Agent 초안 요청",
  agent_succeeded: "Agent 초안 검증 통과",
  agent_failed: "Agent 초안 실패",
  agent_adopted: "초안을 의견에 가져옴",
  bpm_superseded: "정정본으로 실행 대체",
  overdue_alert: "기한 초과 알림",
};

/**
 * 기획안 v0.5 6장의 후속 장면. **이야기만 있고 설계표·데이터가 아직 없다** — 수치를 지어내지
 * 않고 무엇이 이어지는지만 적는다(D18: 100→85→97억은 설명용 예시다).
 */
const NEXT_SCENES = [
  { id: "장면 2", title: "원재료·외주단가 인상 기안이 같은 이슈에 연결된다", input: "TASK-MAT 결과, 단가 변경 기안" },
  { id: "장면 3", title: "부문별 변화를 하나의 손익 전망으로 — 통합 손익 검토", input: "TASK-FIN, 원가 버전 C02" },
  { id: "장면 4", title: "대응 대안을 비교하고 사람이 결정한다", input: "통합 손익 분석" },
  { id: "장면 5", title: "결정이 실행과제와 Rolling Plan 갱신으로", input: "승인된 과제" },
  { id: "장면 6", title: "과제 완료와 성과 실현을 구분해 검토한다", input: "다음 월간 Review" },
  { id: "장면 7", title: "실제 경험을 관리모델 개선(Evolution)에 반영한다", input: "이번 대응의 지연·누락 기록" },
];

/**
 * UI06 — 경영이슈 상세 및 후속 연결. 한 이슈에서 자료·분석·판단·업무를 잇고 장면 1의 인계를
 * 확인한다.
 *
 * **"장면 1 인계 완료" · "전망 승인" · "위험 해소"는 서로 다른 말이다**(UI06-02). 인계가
 * 끝나도 F02는 검토 중이고 이슈는 열린 중요다 — 셋을 따로 보여 준다.
 */
export function HandoffScreen() {
  const view = useSc01(selectView);
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
      <ScreenHeader id="UI06" title="경영이슈 · 인계 현황" question="어떤 판단이 이루어졌고 누가 후속 업무를 인수했는가?" />
      {!view ? <Loading /> : <Body view={view} />}
    </main>
  );
}

function Body({ view }: { view: DemoRunView }) {
  const issue = view.issues.find((i) => i.risk === "CRITICAL") ?? view.issues.find((i) => i.issue_id === "ISSUE-B07");
  const run = view.calcRuns.find((r) => r.run_id === view.latestRunId);
  const review = view.reviews.at(-1);
  const forecast = view.forecasts.at(-1);
  const check = view.handoffCheck;
  const nameOf = useUserName();

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>
            {issue ? `${issue.issue_id} · ${modelLabel(issue.model_id)} ${Number(issue.period.slice(5, 7))}월 고객 물량` : "이슈"}
          </CardTitle>
          <CardDescription>원인 유형 CUSTOMER_VOLUME · 소유 {issue?.owner_role ?? "—"}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-1.5">
            <StatePill label="장면" value={SCENE_LABEL[view.scene]} tone={view.scene === "HANDED_OFF" ? "good" : "neutral"} />
            <StatePill label="위험" value={issue?.risk ? ({ NORMAL: "기준 이내", ATTENTION: "관심", CRITICAL: "중요" } as const)[issue.risk] : "—"} tone={issue?.risk === "CRITICAL" ? "warn" : "neutral"} />
            <StatePill label="이슈" value={issue?.status === "OPEN" ? "미해결" : "해결"} />
            <StatePill label="전망" value={forecast ? `${forecast.version_id} 검토 중(미승인)` : "F01 승인"} />
          </div>
          {view.scene === "HANDED_OFF" ? (
            <p className="text-sm font-medium">장면 1 인계 완료 — 현업 검토와 손익분석 진행 중</p>
          ) : null}
          <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
            <Row label="원천" value={run ? `${run.source_id}` : "—"} />
            <Row label="계산" value={run ? `${run.run_id} (${formatClock(run.at)})` : "—"} />
            <Row label="비교 버전" value={run ? `${run.versions.target} · ${run.versions.prior} → ${run.versions.latest} · ${run.versions.cost} · ${run.versions.rule}` : "—"} />
            <Row label="영업 판단" value={review ? `${review.opinion} (${nameOf(review.by)}, ${formatClock(review.at)})` : "검토 전"} />
          </dl>
          {issue ? (
            <p className="flex flex-wrap items-center gap-1.5 text-xs">
              위험 이력:
              {issue.history.map((h, n) => (
                <span key={h.run_id} className="inline-flex items-center gap-1">
                  {n > 0 ? "→" : null}
                  <RiskTag risk={h.risk} />
                </span>
              ))}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>장면 완료 조건</CardTitle>
            <CardDescription>조건을 다시 확인한 뒤 인계 기록(SCENE_HANDED_OFF)을 한 번만 남긴다.</CardDescription>
          </CardHeader>
          <CardContent>
            {check ? (
              <ul className="space-y-1.5 text-sm">
                {Object.entries(check.conditions).map(([k, ok]) => (
                  <li key={k} className="flex items-start gap-2">
                    {ok ? (
                      <CheckCircle2 aria-hidden className="mt-0.5 size-4 shrink-0" style={{ color: "var(--viz-status-good)" }} />
                    ) : (
                      <CircleDashed aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    )}
                    <span>
                      {CONDITION_LABEL[k]}
                      <span className="ml-1 text-xs text-muted-foreground">{ok ? "충족" : "미충족"}</span>
                    </span>
                  </li>
                ))}
                {check.reasons.length > 0 ? (
                  <li className="text-xs text-muted-foreground">남은 것: {check.reasons.join(", ")}</li>
                ) : null}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">비교 계산 전이다.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>후속 업무</CardTitle>
            <CardDescription>인수는 장면 종료 조건이다. 인수 후에도 업무는 계속 진행된다.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y text-sm">
              {view.tasks
                .filter((t) => ["PROD", "MAT", "FIN"].includes(t.type))
                .map((t) => (
                  <li key={t.task_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <span>
                      <span className="font-mono text-xs">{t.task_id}</span> {TASK_TYPE_LABEL[t.type]} · {t.assignedName}
                      {t.reconfirm ? <span className="ml-1 text-xs">(재확인 요청)</span> : null}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {TASK_STATUS_LABEL[t.status]}
                      {t.accepted_at ? ` · 인수 ${formatClock(t.accepted_at)}` : ""} · 기한 {formatClock(t.due_at)}
                    </span>
                  </li>
                ))}
            </ul>
            {view.tasks.every((t) => !["PROD", "MAT", "FIN"].includes(t.type)) ? (
              <p className="text-sm text-muted-foreground">아직 배정 전이다.</p>
            ) : null}
          </CardContent>
        </Card>
      </div>

      {view.bpmHistory.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>정정 이력</CardTitle>
            <CardDescription>
              정정본이 오면 이전 실행과 인계를 지우지 않고 이력으로 옮긴다. 최신 계산에 대한 인수 확인이 끝나야 다시
              인계된다.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {view.bpmHistory.map((b) => (
                <li key={b.run_id} className="flex flex-wrap gap-x-2">
                  <span className="tabular-nums text-muted-foreground">{formatClock(b.superseded_at)}</span>
                  <span>
                    BPM 실행 {b.run_id.slice(-6)} ({b.state === "cancelled" ? "진행 중 취소" : "완료 후 대체"}) →{" "}
                    {b.by_source} 수신으로 새 실행
                  </span>
                </li>
              ))}
              {view.handoffHistory.map((h) => (
                <li key={h.run_id + h.at} className="flex flex-wrap gap-x-2">
                  <span className="tabular-nums text-muted-foreground">{formatClock(h.at)}</span>
                  <span>이전 인계 ({h.run_id}) — 역사로 보존</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>이력</CardTitle>
          <CardDescription>수신 → 확인 → 계산 → 영업 검토 → 배정·인수 → 인계. 모든 변경에 행위자·시각이 있다.</CardDescription>
        </CardHeader>
        <CardContent>
          <Timeline entries={view.audit} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>다음 장면</CardTitle>
          <CardDescription>
            기획안 v0.5의 경영 이야기에는 있지만 아직 장면별 설계표와 데이터가 없다. 수치를 만들지 않고 무엇이 이어지는지만
            보인다.
            <Commentary> 연간 100억 → 85억 → 97억은 설명용 예시이고, 이 데이터의 손익(34.77억 목표)과 다르다(데이터 설계 D18).</Commentary>
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="space-y-1.5 text-sm">
            {NEXT_SCENES.map((s) => (
              <li key={s.id} className="flex flex-wrap gap-x-2">
                <span className="w-14 shrink-0 text-xs text-muted-foreground">{s.id}</span>
                <span>{s.title}</span>
                <span className="text-xs text-muted-foreground">← {s.input}</span>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <dt className="w-16 shrink-0 text-muted-foreground">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function Timeline({ entries }: { entries: AuditEntry[] }) {
  const shown = entries.filter((e) => e.action !== "clock_moved");
  return (
    <ol className="space-y-1 text-xs">
      {shown.map((e) => (
        <li key={e.seq} className="grid grid-cols-[4.5rem_1fr] gap-2 sm:grid-cols-[4.5rem_10rem_1fr]">
          <span className="tabular-nums text-muted-foreground">{formatClock(e.at)}</span>
          <span className="font-medium">{ACTION_LABEL[e.action] ?? e.action}</span>
          <span className="col-span-2 text-muted-foreground sm:col-span-1">
            {e.actor_role === "system" ? "시스템" : `${e.actor_role} ${e.actor_name}`}
            {Object.keys(e.detail).length > 0
              ? ` · ${Object.entries(e.detail)
                  .map(([k, v]) => `${k}=${String(v)}`)
                  .join(", ")}`
              : ""}
          </span>
        </li>
      ))}
    </ol>
  );
}
