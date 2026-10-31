"use client";

import { useCallback, useEffect, useState } from "react";

import { StatusPanel } from "@/components/admin/status-panel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

/**
 * NowView 관리자 모드 — 로그인 뒤에만 열린다(`docs/worker-interfaces.md` §1). 공개 화면에는 이곳으로 가는 링크가 없다.
 * 설정(회사·회사 시스템 주소·BPM 프로세스 매핑·토픽)은 엔진 DB에 있고 여기서만 고친다. 키·비밀번호는 설정이 아니라
 * 서버 환경 파일에 있다.
 */

type Session = { configured: boolean; loggedIn: boolean };

type ConfigView = {
  config: unknown;
  updatedAt: string | null;
  scenes: Record<string, string>;
  extension: { id: string; version: string; operations: string[] };
};

export function AdminConsole() {
  const [session, setSession] = useState<Session | null>(null);
  // 로그인·로그아웃 뒤 세션을 다시 읽는다 — 값이 바뀌면 아래 effect가 다시 돈다.
  const [round, setRound] = useState(0);
  const check = useCallback(async () => setRound((n) => n + 1), []);
  useEffect(() => {
    let alive = true;
    fetch("/api/admin/session", { cache: "no-store" })
      .then((response) => response.json() as Promise<Session>)
      .then((found) => alive && setSession(found))
      .catch(() => alive && setSession({ configured: false, loggedIn: false }));
    return () => {
      alive = false;
    };
  }, [round]);

  if (!session) return <p className="text-sm text-muted-foreground">읽는 중…</p>;
  if (!session.configured) {
    return (
      <p className="rounded-md border p-3 text-sm">
        관리자 모드가 꺼져 있다 — 서버 환경에 <span className="font-mono">NOWVIEW_ADMIN_PASSWORD</span>·
        <span className="font-mono">NOWVIEW_ADMIN_SECRET</span>·<span className="font-mono">NOWVIEW_ADMIN_KEY</span>가 있어야 한다.
      </p>
    );
  }
  if (!session.loggedIn) return <Login onDone={check} />;
  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button
          size="sm"
          variant="outline"
          onClick={async () => {
            await fetch("/api/admin/login", { method: "DELETE" });
            await check();
          }}
        >
          로그아웃
        </Button>
      </div>
      <StatusPanel />
      <ConfigEditor />
    </div>
  );
}

function Login({ onDone }: { onDone: () => Promise<void> }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Card className="mx-auto max-w-sm">
      <CardHeader>
        <CardTitle>관리자 로그인</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-3"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            const response = await fetch("/api/admin/login", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ password }),
            });
            setBusy(false);
            if (!response.ok) {
              setError(((await response.json()) as { error?: string }).error ?? `로그인 실패 (${response.status})`);
              return;
            }
            setPassword("");
            await onDone();
          }}
        >
          <label className="grid gap-1 text-sm">
            비밀번호
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="rounded-md border bg-transparent px-2 py-1.5"
            />
          </label>
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
          <Button type="submit" disabled={busy || !password}>
            로그인
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

/**
 * 설정 편집 — JSON 하나를 고쳐 저장한다. 검사는 엔진이 한다(회사 id·매핑의 회사·업무 번호·토픽 겹침). 거절되면 사유를 그대로
 * 보이고 입력은 지우지 않는다.
 */
function ConfigEditor() {
  const [view, setView] = useState<ConfigView | null>(null);
  const [text, setText] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; lines: string[] } | null>(null);
  const [busy, setBusy] = useState(false);

  // 저장·되돌리기 뒤 다시 읽는다 — 값이 바뀌면 아래 effect가 다시 돈다.
  const [round, setRound] = useState(0);
  const load = useCallback(() => setRound((n) => n + 1), []);
  useEffect(() => {
    let alive = true;
    fetch("/api/admin/config", { cache: "no-store" }).then(async (response) => {
      if (!alive) return;
      if (!response.ok) {
        setMessage({ ok: false, lines: [`설정을 읽지 못했다 (${response.status})`] });
        return;
      }
      const body = (await response.json()) as ConfigView;
      if (!alive) return;
      setView(body);
      setText(JSON.stringify(body.config, null, 2));
    });
    return () => {
      alive = false;
    };
  }, [round]);

  if (!view) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>설정</CardTitle>
        <CardDescription>
          회사(<span className="font-mono">companies</span>) · BPM 프로세스 → 회사·업무(
          <span className="font-mono">processes</span>) · 일꾼 토픽(<span className="font-mono">topics</span>). 마지막 저장{" "}
          {view.updatedAt ?? "—"}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        <p className="text-xs text-muted-foreground">
          업무 번호: {Object.entries(view.scenes).map(([no, work]) => `${no} ${work}`).join(" · ")}
        </p>
        <p className="text-xs text-muted-foreground">
          고정 확장 <span className="font-mono">{view.extension.id}</span> {view.extension.version} — 작업{" "}
          <span className="font-mono">{view.extension.operations.join(", ")}</span> (NowView 판과 함께 바뀐다, 여기서 고치지 않는다)
        </p>
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          spellCheck={false}
          className="min-h-96 font-mono text-xs"
          aria-label="설정 JSON"
        />
        {message ? (
          <div className={message.ok ? "rounded-md border p-3" : "rounded-md border border-destructive/40 bg-destructive/5 p-3"}>
            {message.lines.map((line) => (
              <p key={line}>{line}</p>
            ))}
          </div>
        ) : null}
        <div className="flex gap-2">
          <Button
            disabled={busy}
            onClick={async () => {
              let body: unknown;
              try {
                body = JSON.parse(text);
              } catch (cause) {
                setMessage({ ok: false, lines: [`JSON이 아니다 — ${String(cause)}`] });
                return;
              }
              setBusy(true);
              const response = await fetch("/api/admin/config", {
                method: "PUT",
                headers: { "content-type": "application/json" },
                body: JSON.stringify(body),
              });
              setBusy(false);
              const result = (await response.json()) as {
                detail?: { message?: string; reasons?: string[] } | string;
                updatedAt?: string;
                restartRequired?: boolean;
              };
              if (!response.ok) {
                const detail = typeof result.detail === "string" ? { message: result.detail } : (result.detail ?? {});
                setMessage({ ok: false, lines: [detail.message ?? `저장하지 못했다 (${response.status})`, ...(detail.reasons ?? [])] });
                return;
              }
              setMessage({
                ok: true,
                lines: [
                  `저장했다 — ${result.updatedAt}`,
                  ...(result.restartRequired ? ["토픽이 바뀌었다 — 엔진을 다시 띄워야 일꾼에 반영된다."] : []),
                ],
              });
              load();
            }}
          >
            저장
          </Button>
          <Button variant="outline" disabled={busy} onClick={load}>
            되돌리기
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
