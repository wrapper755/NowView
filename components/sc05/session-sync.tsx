"use client";

import { useEffect } from "react";
import { useScenePath as usePathname } from "@/lib/company-nav";

import { sc05Api } from "@/lib/sc05/client";
import type { Sc05View } from "@/lib/sc05/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc05 } from "@/lib/store/sc05";

const POLL_MS = 15_000;

/**
 * 장면 5 문서를 받는 **유일한** 자리 — 장면 1~4 수신과 같은 원칙(4.6). 장면 5 화면(`/sc05/*`)에 있을 때만 돈다.
 * **장면 5를 저절로 만들지 않는다** — 만들면 장면 4가 완료 전일 때 장면 4 각본까지 실행된다. 없으면(404)
 * `missing`을 켜고 화면이 「장면 5 시작」을 묻는다.
 */
export function Sc05SessionSync() {
  const pathname = usePathname();
  const active = pathname.startsWith("/sc05");
  const demoRunId = useSc01((s) => s.demoRunId);
  const loaded = useSc05((s) => s.live?.demoRunId === demoRunId && demoRunId !== null);
  const caseId = useSc05((s) => s.live?.caseId ?? null);

  useEffect(() => {
    if (!active) return;
    void useSc05.persist.rehydrate();
    void Promise.all([sc05Api.process(), sc05Api.cases()]).then(([p, c]) => {
      useSc05.getState().setStatic(p.ok ? p.data : null, c.ok ? c.data : []);
    });
  }, [active]);

  useEffect(() => {
    if (!active || !demoRunId) return;
    let cancelled = false;
    void sc05Api.get(demoRunId).then((r) => {
      if (cancelled) return;
      if (r.ok) useSc05.getState().setLive(r.data);
      else if (r.status === 404) useSc05.getState().clearLive(true);
      else {
        useSc05.getState().setConnection("offline");
        useSc05.getState().setError(r.error);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [active, demoRunId]);

  // 각본 — 사례마다 단계가 다르다(X507은 반려·보완 재작성이 끼어든다).
  useEffect(() => {
    if (!active || !caseId) return;
    void sc05Api.script(caseId).then((r) => useSc05.getState().setScript(r.ok ? r.data : []));
  }, [active, caseId]);

  useEffect(() => {
    if (!active || !demoRunId || !loaded) return;
    let poll: ReturnType<typeof setInterval> | null = null;
    const refetch = async () => {
      const r = await sc05Api.get(demoRunId);
      if (r.ok) useSc05.getState().setLive(r.data);
      else useSc05.getState().setConnection("offline");
    };
    const startPolling = () => {
      if (poll) return;
      useSc05.getState().setConnection("polling");
      poll = setInterval(() => void refetch(), POLL_MS);
    };
    const stopPolling = () => {
      if (poll) clearInterval(poll);
      poll = null;
    };
    useSc05.getState().setConnection("connecting");
    const source = new EventSource(sc05Api.eventsUrl(demoRunId));
    source.addEventListener("snapshot", (event) => {
      useSc05.getState().setLive(JSON.parse((event as MessageEvent).data) as Sc05View);
    });
    source.addEventListener("ready", () => {
      stopPolling();
      useSc05.getState().setConnection("live");
    });
    source.onerror = () => startPolling();
    return () => {
      source.close();
      stopPolling();
    };
  }, [active, demoRunId, loaded]);

  return null;
}
