"use client";

import { Textarea } from "@/components/ui/textarea";
import type { DemoUser, FormField as FormFieldSpec } from "@/lib/sc01/types";

/**
 * 결재 폼 칸 하나 — 칸 정의는 BPMN의 `chk:approval.fields`에서 온다(화면이 폼을 따로 정의하지 않는다).
 * 장면 1·2가 같은 칸 규칙을 쓴다: 참·거짓 · 선택 · 숫자 · 글, 그리고 `…담당자` 칸은 사용자 마스터에서 고른다
 * (이름을 손으로 치면 배정이 거절된다).
 *
 * **숫자 칸의 빈 값은 `null`이다** — 0이 아니다. 협상 미합의의 단가처럼 비워 두는 것이 뜻이 있는 칸이 있다.
 */
export function FormField({
  field,
  value,
  users,
  onChange,
}: {
  field: FormFieldSpec;
  value: unknown;
  users: DemoUser[];
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
  if (field.type === "number") {
    return (
      <div className="space-y-1">
        {label}
        <input
          id={id}
          type="number"
          inputMode="numeric"
          value={value === null || value === undefined ? "" : String(value)}
          onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
          className="block w-full rounded-lg border bg-transparent px-2 py-1.5 text-sm tabular-nums"
        />
      </div>
    );
  }
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

/** 칸의 첫 값 — 기본값, 참·거짓은 false, 숫자는 null(빈 칸), 나머지는 빈 글. */
export function initialValue(field: FormFieldSpec): unknown {
  if (field.default !== undefined && field.default !== null) return field.default;
  if (field.type === "bool") return false;
  if (field.type === "number") return null;
  return "";
}

/** 필수 칸이 비었나. 참·거짓은 언제나 값이 있다. */
export function isMissing(field: FormFieldSpec, value: unknown): boolean {
  if (!field.required || field.type === "bool") return false;
  if (field.type === "number") return value === null || value === undefined || Number.isNaN(value);
  return !String(value ?? "").trim();
}
