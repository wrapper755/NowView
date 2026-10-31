"use client";

import { useEffect } from "react";
import { useScenePath as usePathname } from "@/lib/company-nav";

import { sc03Api } from "@/lib/sc03/client";
import type { Sc03View } from "@/lib/sc03/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc03 } from "@/lib/store/sc03";

const POLL_MS = 15_000;

/**
 * 장면 3 문서를 받는 **유일한** 자리 — 장면 1·2 수신과 같은 원칙(4.6). 장면 3 화면(`/sc03/*`)에 있을 때만 돈다.
 * **장면 3을 저절로 만들지 않는다** — 만들면 장면 2가 인수 전일 때 장면 2 각본까지 실행된다. 없으면(404)
 * `missing`을 켜고 화면이 「장면 3 시작」을 묻는다.
 */
export function Sc03SessionSync() {
  const pathname = usePathname();
  const active = pathname.startsWith("/sc03");
  const demoRunId = useSc01((s) => s.demoRunId);
  const loaded = useSc03((s) => s.live?.demoRunId === demoRunId && demoRunId !== null);
  const caseId = useSc03((s) => s.live?.caseId ?? null);

  useEffect(() => {
    if (!active) return;
    void useSc03.persist.rehydrate();
    void Promise.all([sc03Api.process(), sc03Api.cases()]).then(([p, c]) => {
      useSc03.getState().setStatic(p.ok ? p.data : null, c.ok ? c.data : []);
    });
  }, [active]);

  useEffect(() => {
    if (!active || !demoRunId) return;
    let cancelled = false;
    void sc03Api.get(demoRunId).then((r) => {
      if (cancelled) return;
      if (r.ok) useSc03.getState().setLive(r.data);
      else if (r.status === 404) useSc03.getState().clearLive(true);
      else {
        useSc03.getState().setConnection("offline");
        useSc03.getState().setError(r.error);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [active, demoRunId]);

  // 각본 — 사례마다 단계가 다르다(E31은 이견·보완·재확인이 끼어든다).
  useEffect(() => {
    if (!active || !caseId) return;
    void sc03Api.script(caseId).then((r) => useSc03.getState().setScript(r.ok ? r.data : []));
  }, [active, caseId]);

  useEffect(() => {
    if (!active || !demoRunId || !loaded) return;
    let poll: ReturnType<typeof setInterval> | null = null;
    const refetch = async () => {
      const r = await sc03Api.get(demoRunId);
      if (r.ok) useSc03.getState().setLive(r.data);
      else useSc03.getState().setConnection("offline");
    };
    const startPolling = () => {
      if (poll) return;
      useSc03.getState().setConnection("polling");
      poll = setInterval(() => void refetch(), POLL_MS);
    };
    const stopPolling = () => {
      if (poll) clearInterval(poll);
      poll = null;
    };
    useSc03.getState().setConnection("connecting");
    const source = new EventSource(sc03Api.eventsUrl(demoRunId));
    source.addEventListener("snapshot", (event) => {
      useSc03.getState().setLive(JSON.parse((event as MessageEvent).data) as Sc03View);
    });
    source.addEventListener("ready", () => {
      stopPolling();
      useSc03.getState().setConnection("live");
    });
    source.onerror = () => startPolling();
    return () => {
      source.close();
      stopPolling();
    };
  }, [active, demoRunId, loaded]);

  return null;
}
