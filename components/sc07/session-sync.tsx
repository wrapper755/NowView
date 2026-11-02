"use client";

import { useEffect, useRef } from "react";
import { useScenePath as usePathname } from "@/lib/company-nav";

import { sc07Api } from "@/lib/sc07/client";
import type { Sc07Meta } from "@/lib/sc07/types";
import { useSc01 } from "@/lib/store/sc01";
import { toLoad, useSc07 } from "@/lib/store/sc07";

const POLL_MS = 15_000;

/**
 * 장면 7을 받는 **유일한** 자리(장면 1~6 수신과 같은 원칙, 4.6). 장면 7 화면(`/sc07/*`)에 있을 때만 돈다.
 *
 * * **장면 7을 저절로 열지 않는다** — 열면 장면 6이 보고 전일 때 장면 6 각본까지 실행된다. 없으면(404) `missing`을 켜고 화면이
 *   「관리모델 개선 열기」를 묻는다.
 * * **문서 머리(확인·적용 절차)는 SSE로 받는다.** 서 있지 않은 동안만 폴링.
 * * **조회 셋(개선·검증·적용)은 멱등이다**(구현명세 6장) — 행위자·데모 실행·데이터 버전, 그리고 절차 진행(검증·확인·설정)이
 *   바뀔 때만 다시 받는다. 늦은 응답이 새 결과를 덮지 않게 일련번호를 붙인다.
 */
export function Sc07SessionSync() {
  const pathname = usePathname();
  const active = pathname.startsWith("/sc07");
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const dataset = useSc07((s) => (s.meta?.demoRunId === demoRunId ? s.meta.datasetVersion : null));
  const loaded = useSc07((s) => s.meta?.demoRunId === demoRunId && demoRunId !== null);
  const progress = useSc07((s) =>
    s.meta?.demoRunId === demoRunId
      ? `${s.meta.status.verification}:${s.meta.status.confirmed.length}:${s.meta.status.application}:${s.meta.status.followUp}:${s.meta.procedure.steps.filter((p) => p.record).length}`
      : null,
  );
  const readSeq = useRef(0);

  useEffect(() => {
    if (!active) return;
    void useSc07.persist.rehydrate();
    void sc07Api.process().then((r) => useSc07.getState().setTopology(r.ok ? r.data : null));
  }, [active]);

  useEffect(() => {
    if (!active || !demoRunId) return;
    let cancelled = false;
    void sc07Api.meta(demoRunId).then((r) => {
      if (cancelled) return;
      const { setMeta } = useSc07.getState();
      if (r.ok) setMeta(r.data);
      else if (r.status === 404) setMeta(null, true);
      else setMeta(null, false, r.error);
    });
    return () => {
      cancelled = true;
    };
  }, [active, demoRunId]);

  useEffect(() => {
    if (!active || !demoRunId || !loaded) return;
    let poll: ReturnType<typeof setInterval> | null = null;
    const refetch = async () => {
      const r = await sc07Api.meta(demoRunId);
      if (r.ok) useSc07.getState().setMeta(r.data);
      else useSc07.getState().setConnection("offline");
    };
    const startPolling = () => {
      if (poll) return;
      useSc07.getState().setConnection("polling");
      poll = setInterval(() => void refetch(), POLL_MS);
    };
    const stopPolling = () => {
      if (poll) clearInterval(poll);
      poll = null;
    };
    useSc07.getState().setConnection("connecting");
    const source = new EventSource(sc07Api.eventsUrl(demoRunId));
    source.addEventListener("snapshot", (event) => {
      useSc07.getState().setMeta(JSON.parse((event as MessageEvent).data) as Sc07Meta);
    });
    source.addEventListener("ready", () => {
      stopPolling();
      useSc07.getState().setConnection("live");
    });
    source.onerror = () => startPolling();
    return () => {
      source.close();
      stopPolling();
    };
  }, [active, demoRunId, loaded]);

  useEffect(() => {
    if (!active || !demoRunId || !dataset) return;
    const mine = ++readSeq.current;
    const { setImprovement, setVerification, setApplication } = useSc07.getState();
    setImprovement({ state: "loading" });
    setVerification({ state: "loading" });
    setApplication({ state: "loading" });
    void sc07Api.improvement(demoRunId, dataset, actor).then((r) => {
      if (mine === readSeq.current) setImprovement(toLoad(r));
    });
    void sc07Api.verification(demoRunId, dataset, actor).then((r) => {
      if (mine === readSeq.current) setVerification(toLoad(r));
    });
    void sc07Api.application(demoRunId, dataset, actor).then((r) => {
      if (mine === readSeq.current) setApplication(toLoad(r));
    });
  }, [active, demoRunId, dataset, actor, progress]);

  return null;
}
