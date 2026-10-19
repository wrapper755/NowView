"use client";

import { useEffect } from "react";

import { sc01Api } from "@/lib/sc01/client";
import type { DemoRunView } from "@/lib/sc01/types";
import { useSc01 } from "@/lib/store/sc01";
import { useUiPrefs } from "@/lib/store/ui-prefs";

/** SSE가 서 있지 않은 동안의 폴백 주기(4.9). */
const POLL_MS = 15_000;

/**
 * 진행 중인 생성 요청. 개발 모드의 StrictMode는 effect를 두 번 돌리는데, 둘이 각자 만들면
 * 데모 실행이 둘 생긴다(실제로 그랬다). 같은 요청을 함께 기다린다.
 */
let pendingCreate: ReturnType<typeof sc01Api.create> | null = null;

/**
 * 데모 실행을 준비하고 변경을 받는 **유일한** 자리(레이아웃 상주).
 *
 * 화면·패널마다 따로 받으면 같은 화면의 두 패널이 서로 다른 순간을 보고 요청이 패널 수만큼
 * 는다(이전 구현에서 겪었다 — 4.6). 여기서 받아 스토어에 넣고 화면은 스토어만 읽는다.
 *
 * * 저장된 데모 실행 id가 없거나 엔진에 없으면(초기화된 DB 등) 새로 만든다.
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

  // 데모 실행 확보. id가 바뀌면(초기화·새 실행) 다시 돈다.
  useEffect(() => {
    let cancelled = false;
    const ensure = async () => {
      // rehydrate가 끝나기 전 첫 렌더에는 id가 비어 있다 — 그때 만들면 실행이 둘 생긴다.
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
          useSc01.getState().setLive(found.data);
          return;
        }
        if (found.status !== 404) {
          useSc01.getState().setConnection("offline");
          useSc01.getState().setError(found.error);
          return;
        }
      }
      pendingCreate ??= sc01Api.create();
      const created = await pendingCreate;
      pendingCreate = null;
      if (cancelled) return;
      if (created.ok) {
        useSc01.getState().setDemoRunId(created.data.demoRunId);
        useSc01.getState().setLive(created.data);
      } else {
        useSc01.getState().setConnection("offline");
        useSc01.getState().setError(created.error);
      }
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
