"use client";

import { useState } from "react";

import { useUserName } from "@/components/sc01/bits";
import { AgentCard } from "@/components/sc05/agent-card";
import { Mn, Sc05Body, Sc05Header, WaitingForms } from "@/components/sc05/bits";
import { Commentary } from "@/components/shared/commentary";
import { Disclosure } from "@/components/shared/disclosure";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock } from "@/lib/sc01/format";
import { activityLines, CHECK_LABEL, PLAN_STATE_LABEL } from "@/lib/sc05/format";
import type { Activity, Plan, Sc05View } from "@/lib/sc05/types";
import { useSc01 } from "@/lib/store/sc01";

const PLAN_NODES = ["Draft_Plan", "Coordinate_Plan", "Confirm_Plan", "Verify_Plan"];
const CHANGE_NODES = ["Request_Change", "Coordinate_Change", "Confirm_Change", "Verify_Change"];
const SCOPE_LABEL: Record<string, string> = { budget: "승인예산", effect_start: "효과 개시", due_at: "과제 기한" };

/**
 * U502 상세 실행계획·변경 — 상단에 승인 범위, 활동표(담당·일정·선행·협조·비용·완료 근거), 협의, 변경 전후, 확정·확인
 * 이력. 확정본과 변경본을 따로 보존한다 — 변경안이 확정·확인되기 전에는 기존 확정본이 유효하다(T504).
 */
export function Sc05PlanScreen() {
  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <Sc05Header id="U502" title="상세 실행계획·변경" question="ACT42를 누가 어떤 순서로 실행하고, 무엇이 바뀌었는가?" />
      <Sc05Body>{(view) => <Body view={view} />}</Sc05Body>
    </main>
  );
}

function Body({ view }: { view: Sc05View }) {
  const users = useSc01((s) => s.users);
  const plainName = (id: string | null | undefined) => users.find((u) => u.userId === id)?.name ?? id ?? "";
  const mine = view.plans.filter((p) => p.task_id === "ACT42");
  const [picked, setPicked] = useState<string | null>(null);
  const shown = mine.find((p) => p.plan_id === picked) ?? mine.at(-1) ?? null;
  const [initial, setInitial] = useState<Record<string, Record<string, unknown>>>({});
  const [revision, setRevision] = useState(0);
  const waiting = new Set((view.bpm?.waiting ?? []).map((w) => w.nodeId));
  const a = view.sc04.actions.ACT42;
  const use = (node: string, field: string, ref: string, outputId: string) => {
    const output = view.agentOutputs.find((o) => o.output_id === outputId);
    if (!output?.draft?.activities) return;
    setInitial((s) => ({ ...s, [node]: { ...(s[node] ?? {}), [field]: activityLines(output.draft!.activities!, plainName), [ref]: outputId } }));
    setRevision((r) => r + 1);
  };
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>승인 범위</CardTitle>
          <CardDescription>
            {view.sc04.approval.approval_id} — 범위 안의 활동·담당·협조 조정은 담당 임원이 확정하고 경영관리 임원이 확인한다. 예산·효과 개시·최종 기한을
            바꾸면 별도 승인 전 시행 보류다.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm sm:grid-cols-4">
          <p>
            <span className="block text-xs text-muted-foreground">실행 준비 한도</span>
            <Mn value={a.budget} /> 백만원
          </p>
          <p>
            <span className="block text-xs text-muted-foreground">효과 개시</span>
            2027-09
          </p>
          <p>
            <span className="block text-xs text-muted-foreground">과제 완료기한</span>
            {formatClock(a.completion_due)}
          </p>
          <p>
            <span className="block text-xs text-muted-foreground">유효 계획 · 최신 버전</span>
            {view.planPointer ?? "없음"} · {mine.at(-1)?.plan_id ?? "없음"}
          </p>
        </CardContent>
      </Card>

      <WaitingForms
        view={view}
        nodes={[...PLAN_NODES, ...CHANGE_NODES]}
        initial={initial}
        revision={revision}
        expect={(n) => (["Confirm_Plan", "Verify_Plan", "Confirm_Change", "Verify_Change"].includes(n) && mine.at(-1) ? { plan: mine.at(-1)!.plan_id } : undefined)}
        labels={{ Draft_Plan: "초안 저장", Confirm_Plan: "확정", Verify_Plan: "확인", Request_Change: "변경 요청", Confirm_Change: "변경 확정" }}
      />

      <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-2">
        <AgentCard
          view={view}
          kind="AG51"
          canRequest={waiting.has("Draft_Plan")}
          onUse={waiting.has("Draft_Plan") ? (id) => use("Draft_Plan", "계획활동", "계획초안출처", id) : undefined}
          useLabel="초안을 폼으로 — 협조·비용은 직접 채운다"
        />
        <AgentCard
          view={view}
          kind="AG52"
          canRequest={waiting.has("Request_Change")}
          onUse={waiting.has("Request_Change") ? (id) => use("Request_Change", "변경활동", "변경초안출처", id) : undefined}
          useLabel="변경안을 폼으로"
        />
      </div>

      {shown ? (
        <Card>
          <CardHeader>
            <CardTitle>활동표</CardTitle>
            <CardDescription>
              <span className="mr-2 inline-flex flex-wrap gap-1">
                {mine.map((p) => (
                  <button
                    key={p.plan_id}
                    type="button"
                    onClick={() => setPicked(p.plan_id)}
                    aria-pressed={p.plan_id === shown.plan_id}
                    className={p.plan_id === shown.plan_id ? "rounded border bg-muted px-1.5 font-medium text-foreground" : "rounded border px-1.5"}
                  >
                    {p.plan_id}
                  </button>
                ))}
              </span>
              {PLAN_STATE_LABEL[shown.state] ?? shown.state} · {CHECK_LABEL[shown.management_check]}
              {shown.plan_id === view.planPointer ? " · 유효 계획" : ""}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <ActivityTable activities={shown.activities} />
            {shown.problems.length ? (
              <div className="text-xs" style={{ color: "var(--viz-status-serious)" }}>
                <p className="font-medium">확정 전 보완할 것 {shown.problems.length}건 — 초안은 저장됐다</p>
                <ul className="list-disc pl-4">
                  {shown.problems.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {shown.effect_rule ? <p className="text-xs text-muted-foreground">효과 확인 기준 — {shown.effect_rule}</p> : null}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>활동표</CardTitle>
            <CardDescription>상세 계획 초안이 아직 없다 — 구매 담당이 작성한다(계획 제출 {formatClock(a.plan_due)}).</CardDescription>
          </CardHeader>
        </Card>
      )}

      <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>생산·구매 협의</CardTitle>
            <CardDescription>협의는 계획 버전마다 따로 남는다.</CardDescription>
          </CardHeader>
          <CardContent>
            {view.collaborations.length === 0 ? (
              <p className="text-sm text-muted-foreground">아직 협의 기록이 없다.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {view.collaborations.map((c) => (
                  <li key={c.collab_id}>
                    <span className="font-medium">
                      {c.plan_version} {c.kind}
                    </span>{" "}
                    <span className="text-xs text-muted-foreground">
                      {formatClock(c.at)} · 창구 {plainName(c.contact) || "—"}
                    </span>
                    <span className="block text-xs">{c.content}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <ChangeCard plans={mine} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>확정·확인 이력</CardTitle>
          <CardDescription>확정 권한(담당 임원)과 확인 권한(경영관리 임원)을 따로 기록한다.</CardDescription>
        </CardHeader>
        <CardContent>
          <Disclosure summary={`계획 ${mine.length}개 버전의 이력`}>
            <History plans={mine} />
          </Disclosure>
        </CardContent>
      </Card>
    </>
  );
}

function ActivityTable({ activities }: { activities: Activity[] }) {
  const nameOf = useUserName();
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[52rem] text-sm">
        <thead className="text-left text-xs text-muted-foreground">
          <tr>
            <th className="py-1.5 pr-2 font-medium">#</th>
            <th className="pr-2 font-medium">활동</th>
            <th className="pr-2 font-medium">담당</th>
            <th className="pr-2 font-medium">일정</th>
            <th className="pr-2 font-medium">선행</th>
            <th className="pr-2 font-medium">협조</th>
            <th className="pr-2 text-right font-medium">비용(원)</th>
            <th className="pr-2 font-medium">완료 근거</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {activities.map((a) => (
            <tr key={a.activity_id}>
              <td className="py-1.5 pr-2 font-mono text-xs">{a.activity_id}</td>
              <th scope="row" className="pr-2 text-left font-medium">
                {a.name}
              </th>
              <td className="pr-2">{nameOf(a.owner)}</td>
              <td className="pr-2 tabular-nums">
                {a.start?.slice(5) ?? "—"} ~ {a.end?.slice(5) ?? "—"}
              </td>
              <td className="pr-2">{a.predecessors.join(", ") || "—"}</td>
              <td className="pr-2">{a.cooperation ?? <span className="text-muted-foreground">미입력</span>}</td>
              <td className="pr-2 text-right tabular-nums">
                {a.cost === null ? <span className="text-muted-foreground">미입력</span> : Number(a.cost).toLocaleString("ko-KR")}
              </td>
              <td className="pr-2 text-xs">
                {a.completion}
                {a.evidence ? <span className="ml-1 font-mono text-muted-foreground">{a.evidence}</span> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ChangeCard({ plans }: { plans: Plan[] }) {
  const change = [...plans].reverse().find((p) => p.parent);
  return (
    <Card>
      <CardHeader>
        <CardTitle>변경 전후</CardTitle>
        <CardDescription>
          {change
            ? `${change.parent} → ${change.plan_id} · ${PLAN_STATE_LABEL[change.state] ?? change.state}`
            : "변경 요청이 아직 없다 — 확정 후 준비 중에 드러난 애로를 반영한다."}
        </CardDescription>
      </CardHeader>
      {change ? (
        <CardContent className="space-y-2 text-sm">
          {change.change_reason ? <p>사유 — {change.change_reason}</p> : null}
          {change.change_impact ? <p className="text-xs text-muted-foreground">영향 — {change.change_impact}</p> : null}
          {change.scope_problems?.length ? (
            <p className="text-xs" style={{ color: "var(--viz-status-serious)" }}>
              승인 범위 이탈 — {change.scope_problems.join(", ")}. 별도 승인 전 시행 보류, 기존 확정본 유지.
            </p>
          ) : null}
          <ul className="space-y-1 text-xs">
            {(change.diff ?? []).map((d) =>
              d.scope ? (
                <li key={d.scope}>
                  {SCOPE_LABEL[d.scope] ?? d.scope}: {d.kept ? "유지" : `${String(d.before)} → ${String(d.after)}`}
                </li>
              ) : (
                <li key={d.activity_id}>
                  활동 {d.activity_id} {d.after?.name} — 바뀐 칸 {d.fields?.join(", ")}
                  {d.before && d.after && d.before.start !== d.after.start ? ` (일정 ${d.before.start} → ${d.after.start})` : ""}
                </li>
              ),
            )}
          </ul>
          <Commentary>
            <p className="text-xs text-muted-foreground">대표 재승인 없음 — 예산·효과 개시·최종 기한이 그대로인 범위 안 조정이다.</p>
          </Commentary>
        </CardContent>
      ) : null}
    </Card>
  );
}

function History({ plans }: { plans: Plan[] }) {
  const nameOf = useUserName();
  return (
    <ul className="space-y-2 text-xs">
      {plans.map((p) => (
        <li key={p.plan_id}>
          <span className="font-medium">{p.plan_id}</span>
          <ul className="ml-3 list-disc pl-3">
            {(p.history ?? []).map((h, i) => (
              <li key={i}>
                {formatClock(h.at)} · {PLAN_STATE_LABEL[h.state] ?? (h.state === "VERIFIED" ? "경영관리 확인" : h.state)} · {nameOf(h.by)}
                {h.note ? ` — ${h.note}` : ""}
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}
