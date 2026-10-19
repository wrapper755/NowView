"use client";

import { useState } from "react";
import { Lock, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { sc01Api } from "@/lib/sc01/client";
import type { FormField, Waiting } from "@/lib/sc01/types";
import { useSc01 } from "@/lib/store/sc01";

/**
 * BPM이 기다리는 사람 업무 하나에 답하는 폼. **칸은 BPMN의 `chk:approval.fields`에서 온다**
 * — 화면이 폼을 따로 정의하면 BPMN과 갈라진다.
 *
 * 검사는 엔진이 한다(역할·담당자 403, 필수 칸·의견 422, 상태 409). 버튼 비활성은 편의일
 * 뿐이고, 거절되면 엔진이 준 사유를 그대로 보여 주고 입력은 지우지 않는다(4.6).
 */
export function ActionForm({
  waiting,
  submitLabel = "제출",
  initial,
}: {
  waiting: Waiting;
  submitLabel?: string;
  /** 시연 편의용 초안. 사람이 고쳐 쓸 수 있다 — 자동 제출하지 않는다. */
  initial?: Record<string, unknown>;
}) {
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const users = useSc01((s) => s.users);
  const historical = useSc01((s) => s.past !== null);
  const setLive = useSc01((s) => s.setLive);

  const [values, setValues] = useState<Record<string, unknown>>(() => ({
    ...Object.fromEntries(waiting.fields.map((f) => [f.key, f.default ?? (f.type === "bool" ? false : "")])),
    ...initial,
  }));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const me = users.find((u) => u.userId === actor);
  const wrongRole = waiting.role !== null && me?.role !== waiting.role;
  const missing = waiting.fields.some(
    (f) => f.required && f.type !== "bool" && !String(values[f.key] ?? "").trim(),
  );

  const submit = async () => {
    if (!demoRunId) return;
    setBusy(true);
    setError(null);
    const r = await sc01Api.act(demoRunId, waiting.nodeId, values, actor);
    setBusy(false);
    if (r.ok) setLive(r.data);
    else setError(`${r.status} — ${r.error}`);
  };

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      {waiting.fields.map((f) => (
        <Field
          key={f.key}
          field={f}
          value={values[f.key]}
          users={users}
          onChange={(v) => setValues((s) => ({ ...s, [f.key]: v }))}
        />
      ))}
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" size="sm" disabled={busy || historical || wrongRole || missing}>
          <Send aria-hidden className="size-3.5" />
          {busy ? "보내는 중…" : submitLabel}
        </Button>
        {wrongRole ? (
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Lock aria-hidden className="size-3" />
            {waiting.role} 역할만 할 수 있다 — 상단에서 역할을 바꾼다
          </span>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className="text-xs" style={{ color: "var(--viz-status-critical)" }}>
          거절됨: {error}
        </p>
      ) : null}
    </form>
  );
}

function Field({
  field,
  value,
  users,
  onChange,
}: {
  field: FormField;
  value: unknown;
  users: { userId: string; name: string; role: string }[];
  onChange: (v: unknown) => void;
}) {
  const id = `f-${field.key}`;
  const label = (
    <label htmlFor={id} className="text-xs font-medium">
      {field.label}
      {field.required ? <span className="text-muted-foreground"> (필수)</span> : null}
    </label>
  );

  if (field.type === "bool") {
    return (
      <label className="flex items-center gap-2 text-xs">
        <input id={id} type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
        {field.label}
      </label>
    );
  }
  if (field.type === "choice") {
    return (
      <fieldset className="space-y-1">
        <legend className="text-xs font-medium">{field.label}</legend>
        <div className="flex flex-wrap gap-1">
          {(field.choices ?? []).map((c) => (
            <button
              key={c}
              type="button"
              aria-pressed={value === c}
              onClick={() => onChange(c)}
              className={
                value === c
                  ? "rounded-md border bg-muted px-2.5 py-1 text-xs font-medium"
                  : "rounded-md border px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
              }
            >
              {c}
            </button>
          ))}
        </div>
      </fieldset>
    );
  }
  // 담당자 칸(…담당자)은 사용자 마스터에서 고른다 — 이름을 손으로 치면 배정이 거절된다.
  if (field.key.endsWith("담당자")) {
    return (
      <div className="space-y-1">
        {label}
        <select
          id={id}
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
          className="block w-full rounded-lg border bg-transparent px-2 py-1.5 text-sm"
        >
          <option value="">선택</option>
          {users.map((u) => (
            <option key={u.userId} value={u.userId}>
              {u.name} · {u.role}
            </option>
          ))}
        </select>
      </div>
    );
  }
  return (
    <div className="space-y-1">
      {label}
      <Textarea id={id} rows={2} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
