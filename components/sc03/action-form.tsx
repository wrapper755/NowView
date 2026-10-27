"use client";

import { useRef, useState } from "react";
import { Lock, Send } from "lucide-react";

import { FormField, initialValue, isMissing } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { sc03Api } from "@/lib/sc03/client";
import type { Sc03Waiting } from "@/lib/sc03/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc03 } from "@/lib/store/sc03";

/**
 * 장면 3 결재 폼 — 칸은 BPMN(`sc03.bpmn`의 `chk:approval.fields`)에서 온다. 장면 1·2와 같은 규칙: 검사는 엔진이
 * 하고(403·409·422), 거절되면 사유를 그대로 보이고 **입력은 지우지 않는다**. 완료 조건 미충족이면 남은 항목을
 * 목록으로 보인다(구현명세 11장 「완료 실패 예시」).
 *
 * `expect` — 화면이 본 보고버전·배정버전. 그 사이 새 버전이 나왔으면 엔진이 409로 막는다.
 */
export function Sc03ActionForm({
  waiting,
  submitLabel = "제출",
  initial,
  expect,
}: {
  waiting: Sc03Waiting;
  submitLabel?: string;
  initial?: Record<string, unknown>;
  expect?: Record<string, unknown>;
}) {
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const users = useSc01((s) => s.users);
  const historical = useSc03((s) => s.past !== null);
  const elsewhere = useSc03((s) => s.live !== null && !s.live.answerHere);
  const relay = useSc03((s) => s.live?.executor === "center");
  const setLive = useSc03((s) => s.setLive);
  const [values, setValues] = useState<Record<string, unknown>>(() => ({
    ...Object.fromEntries(waiting.fields.map((f) => [f.key, initialValue(f)])),
    ...initial,
  }));
  const [error, setError] = useState<{ text: string; items?: string[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const keyRef = useRef<string | null>(null);

  // 인수는 과제 책임자 한 사람, 나머지는 역할의 사람이다 — 엔진이 같은 것을 검사한다(편의일 뿐).
  const wrongActor = waiting.assignee !== null && waiting.assignee !== actor;
  const missing = waiting.fields.some((f) => isMissing(f, values[f.key]));
  const assigneeName = users.find((u) => u.userId === waiting.assignee)?.name;

  const submit = async () => {
    if (!demoRunId) return;
    setBusy(true);
    setError(null);
    keyRef.current ??= crypto.randomUUID();
    const answer = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== null && v !== undefined && v !== ""));
    const r = await sc03Api.act(demoRunId, waiting.nodeId, answer, actor, expect, keyRef.current);
    setBusy(false);
    if (r.ok) {
      keyRef.current = null;
      setLive(r.data);
    } else {
      setError({ text: `${r.status} — ${r.error}`, items: r.blockingItems });
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
        <Button type="submit" size="sm" disabled={busy || historical || elsewhere || wrongActor || missing}>
          <Send aria-hidden className="size-3.5" />
          {busy ? "보내는 중…" : submitLabel}
        </Button>
        {elsewhere ? (
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Lock aria-hidden className="size-3" />
            바깥 실행이 도는 데모 실행이다 — 결재는 {relay ? "Center 결재함" : "Studio"}에서 답한다
          </span>
        ) : wrongActor ? (
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Lock aria-hidden className="size-3" />
            {assigneeName ?? waiting.role}만 할 수 있다 — 상단에서 역할을 바꾼다
          </span>
        ) : relay ? (
          <span className="text-xs text-muted-foreground">Center 결재함에 대리 답으로 간다</span>
        ) : null}
      </div>
      {error ? (
        <div role="alert" className="space-y-1 text-xs" style={{ color: "var(--viz-status-critical)" }}>
          <p>거절됨: {error.text}</p>
          {error.items?.length ? (
            <ul className="list-disc pl-4">
              {error.items.map((i) => (
                <li key={i}>{i}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </form>
  );
}
