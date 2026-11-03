"use client";

import { useEffect } from "react";
import { useScenePath as usePathname } from "@/lib/company-nav";

import { sc04Api } from "@/lib/sc04/client";
import type { Sc04View } from "@/lib/sc04/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc04 } from "@/lib/store/sc04";

const POLL_MS = 15_000;
/** 장면 문서가 아직 없을 때 다시 물어보는 주기 — 회사 사이트가 장면을 열면 NowView 일꾼이 문서를 만든다. */
const MISSING_POLL_MS = 5_000;

/**
 * 장면 4 문서를 받는 **유일한** 자리 — 장면 1 수신과 같은 원칙(4.6). 장면 4 화면(`/sc04/*`)에 있을 때만 돈다.
 * 데모 실행 id는 장면 1 스토어의 것이다(같은 실행).
 *
 * **장면 4를 열지 않는다** — 장면 열기는 회사 사이트의 시연 조작이다(role-split §5.5). 없으면(404) `missing`을 켜고
 * 생길 때까지 짧게 다시 묻는다.
 */
export function Sc04SessionSync() {
  const pathname = usePathname();
  const active = pathname.startsWith("/sc04");
  const demoRunId = useSc01((s) => s.demoRunId);
  const loaded = useSc04((s) => s.live?.demoRunId === demoRunId && demoRunId !== null);

  useEffect(() => {
    if (!active) return;
    void sc04Api.process().then((p) => useSc04.getState().setStatic(p.ok ? p.data : null));
  }, [active]);

  // 문서 확보 — 데모 실행이 바뀌면 다시. 아직 없으면 생길 때까지 다시 묻는다.
  useEffect(() => {
    if (!active || !demoRunId || loaded) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const fetchDoc = () => {
      void sc04Api.get(demoRunId).then((r) => {
        if (cancelled) return;
        if (r.ok) useSc04.getState().setLive(r.data);
        else if (r.status === 404) {
          useSc04.getState().clearLive(true);
          timer = setTimeout(fetchDoc, MISSING_POLL_MS);
        } else {
          useSc04.getState().setConnection("offline");
          useSc04.getState().setError(r.error);
        }
      });
    };
    fetchDoc();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [active, demoRunId, loaded]);

  // 변경 수신 — 문서가 있을 때만(없는 실행에 붙으면 404로 폴링만 돈다).
  useEffect(() => {
    if (!active || !demoRunId || !loaded) return;
    let poll: ReturnType<typeof setInterval> | null = null;
    const refetch = async () => {
      const r = await sc04Api.get(demoRunId);
      if (r.ok) useSc04.getState().setLive(r.data);
      else if (r.status === 404) useSc04.getState().clearLive(true); // 장면만 처음으로(회사 사이트) — 다시 열릴 때까지 기다린다
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
