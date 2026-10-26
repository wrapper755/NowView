"use client";

import { useRef, useState } from "react";
import { Lock, Send } from "lucide-react";

import { FormField, initialValue, isMissing } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { sc01Api } from "@/lib/sc01/client";
import type { Waiting } from "@/lib/sc01/types";
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
  /**
   * Studio 실행의 결재는 Studio에서 답한다(N2). Center 실행은 대리 답 설정이 있으면 여기서 답한다(N3)
   * — 엔진도 409·503으로 거절한다. 버튼은 편의다.
   */
  const external = useSc01((s) => s.live !== null && !s.live.answerHere);
  const relay = useSc01((s) => s.live?.executor === "center");
  const setLive = useSc01((s) => s.setLive);

  const [values, setValues] = useState<Record<string, unknown>>(() => ({
    ...Object.fromEntries(waiting.fields.map((f) => [f.key, initialValue(f)])),
    ...initial,
  }));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /**
   * 멱등키 — 같은 입력으로 다시 누르면(응답을 못 받은 재시도) 같은 키를 보내 엔진이 두 번
   * 실행하지 않게 한다. 입력을 고치면 다른 요청이므로 새 키다(같은 키 + 다른 본문 = 409).
   */
  const keyRef = useRef<string | null>(null);

  const me = users.find((u) => u.userId === actor);
  const wrongRole = waiting.role !== null && me?.role !== waiting.role;
  const missing = waiting.fields.some((f) => isMissing(f, values[f.key]));

  const submit = async () => {
    if (!demoRunId) return;
    setBusy(true);
    setError(null);
    keyRef.current ??= crypto.randomUUID();
    const r = await sc01Api.act(demoRunId, waiting.nodeId, values, actor, keyRef.current);
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
        <Button type="submit" size="sm" disabled={busy || historical || external || wrongRole || missing}>
          <Send aria-hidden className="size-3.5" />
          {busy ? "보내는 중…" : submitLabel}
        </Button>
        {external ? (
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Lock aria-hidden className="size-3" />
            바깥 실행이 도는 데모 실행이다 — 결재는 바깥에서 답한다
          </span>
        ) : relay ? (
          <span className="text-xs text-muted-foreground">Center 결재함에 대리 답으로 간다</span>
        ) : wrongRole ? (
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
