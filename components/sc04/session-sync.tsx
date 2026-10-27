"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

import { sc04Api } from "@/lib/sc04/client";
import type { Sc04View } from "@/lib/sc04/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc04 } from "@/lib/store/sc04";

const POLL_MS = 15_000;

/**
 * 장면 4 문서를 받는 **유일한** 자리 — 장면 1~3 수신과 같은 원칙(4.6). 장면 4 화면(`/sc04/*`)에 있을 때만 돈다.
 * **장면 4를 저절로 만들지 않는다** — 만들면 장면 3이 완료 전일 때 장면 3 각본까지 실행된다. 없으면(404)
 * `missing`을 켜고 화면이 「장면 4 시작」을 묻는다.
 */
export function Sc04SessionSync() {
  const pathname = usePathname();
  const active = pathname.startsWith("/sc04");
  const demoRunId = useSc01((s) => s.demoRunId);
  const loaded = useSc04((s) => s.live?.demoRunId === demoRunId && demoRunId !== null);
  const caseId = useSc04((s) => s.live?.caseId ?? null);

  useEffect(() => {
    if (!active) return;
    void useSc04.persist.rehydrate();
    void Promise.all([sc04Api.process(), sc04Api.cases()]).then(([p, c]) => {
      useSc04.getState().setStatic(p.ok ? p.data : null, c.ok ? c.data : []);
    });
  }, [active]);

  useEffect(() => {
    if (!active || !demoRunId) return;
    let cancelled = false;
    void sc04Api.get(demoRunId).then((r) => {
      if (cancelled) return;
      if (r.ok) useSc04.getState().setLive(r.data);
      else if (r.status === 404) useSc04.getState().clearLive(true);
      else {
        useSc04.getState().setConnection("offline");
        useSc04.getState().setError(r.error);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [active, demoRunId]);

  // 각본 — 사례마다 단계가 다르다(E405는 반려·보완·재인수가 끼어든다).
  useEffect(() => {
    if (!active || !caseId) return;
    void sc04Api.script(caseId).then((r) => useSc04.getState().setScript(r.ok ? r.data : []));
  }, [active, caseId]);

  useEffect(() => {
    if (!active || !demoRunId || !loaded) return;
    let poll: ReturnType<typeof setInterval> | null = null;
    const refetch = async () => {
      const r = await sc04Api.get(demoRunId);
      if (r.ok) useSc04.getState().setLive(r.data);
      else useSc04.getState().setConnection("offline");
    };
    const startPolling = () => {
      if (poll) return;
      useSc04.getState().setConnection("polling");
      poll = setInterval(() => void refetch(), POLL_MS);
    };
    const stopPolling = () => {
      if (poll) clearInterval(poll);
      poll = null;
    };
    useSc04.getState().setConnection("connecting");
    const source = new EventSource(sc04Api.eventsUrl(demoRunId));
    source.addEventListener("snapshot", (event) => {
      useSc04.getState().setLive(JSON.parse((event as MessageEvent).data) as Sc04View);
    });
    source.addEventListener("ready", () => {
      stopPolling();
      useSc04.getState().setConnection("live");
    });
    source.onerror = () => startPolling();
    return () => {
      source.close();
      stopPolling();
    };
  }, [active, demoRunId, loaded]);

  return null;
}
