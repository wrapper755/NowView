"use client";

import { useEffect } from "react";
import { useScenePath as usePathname } from "@/lib/company-nav";

import { sc02Api } from "@/lib/sc02/client";
import type { Sc02View } from "@/lib/sc02/types";
import { useSc01 } from "@/lib/store/sc01";
import { useSc02 } from "@/lib/store/sc02";

const POLL_MS = 15_000;

/**
 * 장면 2 문서를 받는 **유일한** 자리 — `Sc01SessionSync`와 같은 원칙(4.6). 장면 2 화면(`/sc02/*`)에 있을
 * 때만 돈다. 데모 실행 id는 장면 1 스토어의 것이다(같은 실행).
 *
 * **장면 2를 저절로 만들지 않는다.** 만들면 장면 1이 인계 전일 때 장면 1 각본까지 실행된다 — 화면에
 * 들어왔을 뿐인데 장면 1 상태가 바뀌면 안 된다. 없으면(404) `missing`을 켜고 화면이 「장면 2 시작」을 묻는다.
 */
export function Sc02SessionSync() {
  const pathname = usePathname();
  const active = pathname.startsWith("/sc02");
  const demoRunId = useSc01((s) => s.demoRunId);
  const loaded = useSc02((s) => s.live?.demoRunId === demoRunId && demoRunId !== null);
  const caseId = useSc02((s) => s.live?.caseId ?? null);

  useEffect(() => {
    if (!active) return;
    void useSc02.persist.rehydrate();
    void Promise.all([sc02Api.process(), sc02Api.rules(), sc02Api.cases()]).then(([p, r, c]) => {
      useSc02.getState().setStatic(p.ok ? p.data : null, r.ok ? r.data : {}, c.ok ? c.data : []);
    });
  }, [active]);

  // 문서 확보 — 데모 실행이 바뀌면 다시.
  useEffect(() => {
    if (!active || !demoRunId) return;
    let cancelled = false;
    void sc02Api.get(demoRunId).then((r) => {
      if (cancelled) return;
      if (r.ok) {
        useSc02.getState().setLive(r.data);
      } else if (r.status === 404) {
        useSc02.getState().clearLive(true);
      } else {
        useSc02.getState().setConnection("offline");
        useSc02.getState().setError(r.error);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [active, demoRunId]);

  // 각본 — 사례마다 단계가 다르다(X01은 D08에서 끝난다).
  useEffect(() => {
    if (!active || !caseId) return;
    void fetch(`/api/engine/sc02/script?case_id=${encodeURIComponent(caseId)}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then((s) => useSc02.getState().setScript(s))
      .catch(() => useSc02.getState().setScript([]));
  }, [active, caseId]);

  // 변경 수신 — 문서가 있을 때만(없는 실행에 붙으면 404로 폴링만 돈다).
  useEffect(() => {
    if (!active || !demoRunId || !loaded) return;
    let poll: ReturnType<typeof setInterval> | null = null;
    const refetch = async () => {
      const r = await sc02Api.get(demoRunId);
      if (r.ok) useSc02.getState().setLive(r.data);
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
