"use client";

import { useEffect } from "react";
import { useScenePath as usePathname } from "@/lib/company-nav";

import { sc02Api } from "@/lib/sc02/client";
import type { Sc02View } from "@/lib/sc02/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc02 } from "@/lib/store/sc02";

const POLL_MS = 15_000;
/** 장면 문서가 아직 없을 때 다시 물어보는 주기 — 회사 사이트가 장면을 열면 NowView 일꾼이 문서를 만든다. */
const MISSING_POLL_MS = 5_000;

/**
 * 장면 2 문서를 받는 **유일한** 자리 — 장면 1 수신과 같은 원칙(4.6). 장면 2 화면(`/sc02/*`)에 있을 때만 돈다.
 * 데모 실행 id는 장면 1 스토어의 것이다(같은 실행).
 *
 * **장면 2를 열지 않는다** — 장면 열기는 회사 사이트의 시연 조작이다(role-split §5.5). 없으면(404) `missing`을 켜고
 * 생길 때까지 짧게 다시 묻는다.
 */
export function Sc02SessionSync() {
  const pathname = usePathname();
  const active = pathname.startsWith("/sc02");
  const demoRunId = useSc01((s) => s.demoRunId);
  const loaded = useSc02((s) => s.live?.demoRunId === demoRunId && demoRunId !== null);

  useEffect(() => {
    if (!active) return;
    void Promise.all([sc02Api.process(), sc02Api.rules()]).then(([p, r]) => {
      useSc02.getState().setStatic(p.ok ? p.data : null, r.ok ? r.data : {});
    });
  }, [active]);

  // 문서 확보 — 데모 실행이 바뀌면 다시. 아직 없으면 생길 때까지 다시 묻는다.
  useEffect(() => {
    if (!active || !demoRunId || loaded) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const fetchDoc = () => {
      void sc02Api.get(demoRunId).then((r) => {
        if (cancelled) return;
        if (r.ok) useSc02.getState().setLive(r.data);
        else if (r.status === 404) {
          useSc02.getState().clearLive(true);
          timer = setTimeout(fetchDoc, MISSING_POLL_MS);
        } else {
          useSc02.getState().setConnection("offline");
          useSc02.getState().setError(r.error);
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
      const r = await sc02Api.get(demoRunId);
      if (r.ok) useSc02.getState().setLive(r.data);
      else if (r.status === 404) useSc02.getState().clearLive(true); // 장면만 처음으로(회사 사이트) — 다시 열릴 때까지 기다린다
      else useSc02.getState().setConnection("offline");
    };
    const startPolling = () => {
      if (poll) return;
      useSc02.getState().setConnection("polling");
      poll = setInterval(() => void refetch(), POLL_MS);
    };
    const stopPolling = () => {
      if (poll) clearInterval(poll);
      poll = null;
    };
    useSc02.getState().setConnection("connecting");
    const source = new EventSource(sc02Api.eventsUrl(demoRunId));
    source.addEventListener("snapshot", (event) => {
      useSc02.getState().setLive(JSON.parse((event as MessageEvent).data) as Sc02View);
    });
    source.addEventListener("ready", () => {
      stopPolling();
      useSc02.getState().setConnection("live");
    });
    source.onerror = () => startPolling();
    return () => {
      source.close();
      stopPolling();
    };
  }, [active, demoRunId, loaded]);

  return null;
}
