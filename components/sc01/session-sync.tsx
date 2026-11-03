"use client";

import { useEffect } from "react";

import { sc01Api } from "@/lib/sc01/client";
import type { DemoRunView } from "@/lib/sc01/types";
import { useSc01 } from "@/lib/store/sc01";
import { useUiPrefs } from "@/lib/store/ui-prefs";

/** SSE가 서 있지 않은 동안의 폴백 주기(4.9). */
const POLL_MS = 15_000;

/**
 * 데모 실행을 고르고 변경을 받는 **유일한** 자리(레이아웃 상주).
 *
 * 화면·패널마다 따로 받으면 같은 화면의 두 패널이 서로 다른 순간을 보고 요청이 패널 수만큼
 * 는다(이전 구현에서 겪었다 — 4.6). 여기서 받아 스토어에 넣고 화면은 스토어만 읽는다.
 *
 * * **데모 실행을 만들지 않는다**(2026-11-03, `docs/role-split.md` §5.5) — 세계(= 데모 실행)는 회사 사이트가 기간계에 만들고
 *   NowView 일꾼이 같은 id로 장면 1을 연다. 저장된 id가 없거나 엔진에 없으면 가장 최근 데모 실행을 본다. 하나도 없으면 그렇게 말한다.
 * * **SSE가 기본이고 폴링이 폴백이다.** `EventSource`는 스스로 다시 붙으므로 `onerror`는
 *   "영구 실패"가 아니라 "지금은 서 있지 않다"이고, 그 동안만 폴링이 돈다.
 */
export function Sc01SessionSync() {
  const demoRunId = useSc01((s) => s.demoRunId);

  // 저장된 상태 복원 — skipHydration이라 mount 이후에 한다(4.2).
  useEffect(() => {
    void useSc01.persist.rehydrate();
    void useUiPrefs.persist.rehydrate();
    void Promise.all([sc01Api.process(), sc01Api.users(), sc01Api.rules()]).then(([p, u, r]) => {
      useSc01.getState().setStatic(p.ok ? p.data : null, u.ok ? u.data : [], r.ok ? r.data : {});
    });
  }, []);

  // 데모 실행 고르기. id가 바뀌면 다시 돈다.
  useEffect(() => {
    let cancelled = false;
    const ensure = async () => {
      // rehydrate가 끝나기 전 첫 렌더에는 id가 비어 있다 — 그때 고르면 저장된 선택을 덮는다.
      if (!useSc01.persist.hasHydrated()) {
        await new Promise<void>((resolve) => {
          const off = useSc01.persist.onFinishHydration(() => {
            off();
            resolve();
          });
        });
      }
      if (cancelled) return;
      const id = useSc01.getState().demoRunId;
      if (id) {
        const found = await sc01Api.get(id);
        if (cancelled) return;
        if (found.ok) {
          useSc01.getState().setNoRun(false);
          useSc01.getState().setLive(found.data);
          return;
        }
        if (found.status !== 404) {
          useSc01.getState().setConnection("offline");
          useSc01.getState().setError(found.error);
          return;
        }
      }
      const runs = await sc01Api.list();
      if (cancelled) return;
      if (!runs.ok) {
        useSc01.getState().setConnection("offline");
        useSc01.getState().setError(runs.error);
        return;
      }
      const latest = runs.data[0]?.demoRunId ?? null;
      if (latest && latest !== id) useSc01.getState().setDemoRunId(latest);
      else useSc01.getState().setNoRun(latest === null);
    };
    void ensure();
    return () => {
      cancelled = true;
    };
  }, [demoRunId]);

  // 변경 수신.
  useEffect(() => {
    if (!demoRunId) return;
    const store = useSc01.getState();
    let poll: ReturnType<typeof setInterval> | null = null;

    const refetch = async () => {
      const r = await sc01Api.get(demoRunId);
      if (r.ok) useSc01.getState().setLive(r.data);
      else useSc01.getState().setConnection("offline");
    };
    const startPolling = () => {
      if (poll) return;
      useSc01.getState().setConnection("polling");
      poll = setInterval(() => void refetch(), POLL_MS);
    };
    const stopPolling = () => {
      if (poll) clearInterval(poll);
      poll = null;
    };

    store.setConnection("connecting");
    const source = new EventSource(sc01Api.eventsUrl(demoRunId));
    source.addEventListener("snapshot", (event) => {
      useSc01.getState().setLive(JSON.parse((event as MessageEvent).data) as DemoRunView);
    });
    source.addEventListener("ready", () => {
      stopPolling();
      useSc01.getState().setConnection("live");
    });
    source.onerror = () => startPolling();

    return () => {
      source.close();
      stopPolling();
    };
  }, [demoRunId]);

  return null;
}
