"use client";

import { useRef, useState } from "react";
import { Lock, Send } from "lucide-react";

import { FormField, initialValue, isMissing } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { sc02Api } from "@/lib/sc02/client";
import type { Waiting } from "@/lib/sc02/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc02 } from "@/lib/store/sc02";

/**
 * 장면 2 결재 폼 — 칸은 BPMN(`sc02.bpmn`의 `chk:approval.fields`)에서 온다. SC01 `ActionForm`과 같은
 * 규칙: 검사는 엔진이 하고(403·409·422), 거절되면 사유를 그대로 보이고 **입력은 지우지 않는다**.
 *
 * `expect` — 화면이 본 기안 버전·인계 자료 해시. 그 사이 새 버전이 나왔으면 엔진이 409로 막는다(U25-03).
 * 비운 숫자 칸은 보내지 않는다 — 미합의의 단가는 비어 있는 것이 뜻이다(0원이 아니다).
 */
export function Sc02ActionForm({
  waiting,
  submitLabel = "제출",
  initial,
  expect,
}: {
  waiting: Waiting;
  submitLabel?: string;
  initial?: Record<string, unknown>;
  expect?: Record<string, string>;
}) {
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const users = useSc01((s) => s.users);
  const historical = useSc02((s) => s.past !== null);
  const setLive = useSc02((s) => s.setLive);
  const [values, setValues] = useState<Record<string, unknown>>(() => ({
    ...Object.fromEntries(waiting.fields.map((f) => [f.key, initialValue(f)])),
    ...initial,
  }));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const keyRef = useRef<string | null>(null);

  const me = users.find((u) => u.userId === actor);
  const wrongRole = waiting.role !== null && me?.role !== waiting.role;
  const missing = waiting.fields.some((f) => isMissing(f, values[f.key]));

  const submit = async () => {
    if (!demoRunId) return;
    setBusy(true);
    setError(null);
    keyRef.current ??= crypto.randomUUID();
    const answer = Object.fromEntries(
      Object.entries(values).filter(([, v]) => v !== null && v !== undefined && v !== ""),
    );
    const r = await sc02Api.act(demoRunId, waiting.nodeId, answer, actor, expect, keyRef.current);
    setBusy(false);
    if (r.ok) {
      keyRef.current = null;
      setLive(r.data);
    } else {
      setError(`${r.status} — ${r.error}`);
    }
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
        <FormField
          key={f.key}
          field={f}
          value={values[f.key]}
          users={users}
          onChange={(v) => {
            keyRef.current = null;
            setValues((s) => ({ ...s, [f.key]: v }));
          }}
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
