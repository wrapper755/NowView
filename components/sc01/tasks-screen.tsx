"use client";

import { useState } from "react";
import { AlarmClock } from "lucide-react";

import { ActionForm } from "@/components/sc01/action-form";
import { Loading, ScreenHeader, StatePill, useUserName } from "@/components/sc01/bits";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatClock, TASK_STATUS_LABEL, TASK_TYPE_LABEL } from "@/lib/sc01/format";
import type { Task } from "@/lib/sc01/types";
import { selectView, useSc01 } from "@/lib/store/sc01";

/**
 * UI05 — 검토·승인 업무. 역할별로 확인·작성·인수를 수행한다.
 *
 * * 생산과 자재는 반드시 별도 행이다(UI05-01).
 * * **기한 초과는 진행 상태와 독립된 표시다**(UI05-03) — "진행 중이면서 지연"이 있다.
 * * 인수는 배정된 담당자만 한다. 역할 전환으로 다른 사람이 되어 누르면 엔진이 403으로 막는다.
 */
export function TasksScreen() {
  const view = useSc01(selectView);
  const actor = useSc01((s) => s.actor);
  const [mine, setMine] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  if (!view) {
    return (
      <main className="mx-auto w-full max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        <ScreenHeader id="UI05" title="검토·승인 업무" question="내가 무엇을 검토·작성·승인해야 하는가?" />
        <Loading />
      </main>
    );
  }

  const tasks = view.tasks.filter((t) => !mine || t.assigned_to === actor);
  const task = view.tasks.find((t) => t.task_id === selected) ?? tasks.find((t) => t.status === "ASSIGNED") ?? tasks[0];

  return (
    <main className="viz-root mx-auto w-full max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
      <ScreenHeader id="UI05" title="검토·승인 업무" question="내가 무엇을 검토·작성·승인해야 하는가?" />

      <div className="grid gap-4 [&>*]:min-w-0 lg:grid-cols-[3fr_2fr]">
        <Card>
          <CardHeader>
            <CardTitle>업무 목록 {tasks.length}건</CardTitle>
            <CardDescription>
              일반 업무는 배정 다음 영업일 18시, 손익분석 보고는 두 번째 영업일 18시가 기한이다(데모 달력: 평일
              09~18시).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <label className="inline-flex items-center gap-2 text-xs">
              <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />
              내 업무만
            </label>
            {tasks.length === 0 ? (
              <p className="text-sm text-muted-foreground">업무가 없다.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[40rem] text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs text-muted-foreground">
                      <th scope="col" className="py-2 pr-3 font-medium">업무</th>
                      <th scope="col" className="py-2 pr-3 font-medium">담당</th>
                      <th scope="col" className="py-2 pr-3 font-medium">배정</th>
                      <th scope="col" className="py-2 pr-3 font-medium">기한</th>
                      <th scope="col" className="py-2 font-medium">상태</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tasks.map((t) => (
                      <tr
                        key={t.task_id}
                        onClick={() => setSelected(t.task_id)}
                        className={t.task_id === task?.task_id ? "cursor-pointer border-b bg-muted/60" : "cursor-pointer border-b hover:bg-muted/40"}
                      >
                        <th scope="row" className="text-left py-2 pr-3 font-normal">
                          <span className="font-mono text-xs">{t.task_id}</span> {TASK_TYPE_LABEL[t.type]}
                        </th>
                        <td className="py-2 pr-3">{t.assignedName ?? "배정 필요"} <span className="text-xs text-muted-foreground">{t.owner_role}</span></td>
                        <td className="py-2 pr-3 tabular-nums">{formatClock(t.assigned_at)}</td>
                        <td className="py-2 pr-3 tabular-nums">{formatClock(t.due_at)}</td>
                        <td className="py-2">
                          <span className="inline-flex items-center gap-1.5">
                            {TASK_STATUS_LABEL[t.status]}
                            {t.overdue ? <Overdue /> : null}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {task ? <TaskDetail task={task} /> : null}
      </div>
    </main>
  );
}

function Overdue() {
  return (
    <span className="inline-flex items-center gap-0.5 text-xs font-medium" style={{ color: "var(--viz-status-critical)" }}>
      <AlarmClock aria-hidden className="size-3" /> 기한 초과
    </span>
  );
}

function TaskDetail({ task }: { task: Task }) {
  const view = useSc01(selectView);
  const waiting = view?.bpm?.waiting.find((w) => w.nodeId === task.node_id && w.taskId === task.task_id);
  const isAccept = ["PROD", "MAT", "FIN"].includes(task.type);
  const nameOf = useUserName();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{TASK_TYPE_LABEL[task.type]}</CardTitle>
        <CardDescription>
          <span className="font-mono">{task.task_id}</span> · 근거 계산 {task.run_id ?? "—"} · 원천 {task.source_id ?? "—"}
          {task.issue_id ? ` · ${task.issue_id}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-1.5">
          <StatePill label="상태" value={TASK_STATUS_LABEL[task.status]} tone={task.status === "COMPLETED" ? "good" : "neutral"} />
          <StatePill label="기한" value={formatClock(task.due_at)} tone={task.overdue ? "warn" : "neutral"} />
          {task.accepted_at ? <StatePill label="인수" value={`${formatClock(task.accepted_at)} · ${nameOf(task.accepted_by)}`} tone="good" /> : null}
        </div>

        {waiting ? (
          <div className="space-y-2 border-t pt-3">
            <p className="text-xs font-medium">
              {isAccept ? "인수 — 담당자 본인만" : "처리"} · {waiting.title}
            </p>
            {Object.entries(waiting.review).length > 0 ? (
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
                {Object.entries(waiting.review).map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-muted-foreground">{k}</dt>
                    <dd>{String(v)}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
            <ActionForm waiting={waiting} submitLabel={isAccept ? "인수" : "완료"} />
          </div>
        ) : null}

        {task.type === "FIN" && task.status === "IN_PROGRESS" ? (
          <p className="text-xs text-muted-foreground">
            장면 1에서는 인수까지다 — 통합 손익분석 보고는 다음 장면의 업무로 진행 중이다.
          </p>
        ) : null}

        <div className="space-y-1 border-t pt-3">
          <p className="text-xs font-medium">이력</p>
          <ol className="space-y-0.5 text-xs">
            {task.history.map((h, i) => (
              <li key={i} className="flex gap-2">
                <span className="tabular-nums text-muted-foreground">{formatClock(h.at)}</span>
                <span>{TASK_STATUS_LABEL[h.status as Task["status"]] ?? h.status}</span>
                <span className="text-muted-foreground">{nameOf(h.by)}{h.note ? ` · ${h.note}` : ""}</span>
              </li>
            ))}
          </ol>
        </div>
      </CardContent>
    </Card>
  );
}
