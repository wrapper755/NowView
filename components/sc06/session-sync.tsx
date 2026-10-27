"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";

import { sc06Api } from "@/lib/sc06/client";
import type { Sc06Meta } from "@/lib/sc06/types";
import { useSc01 } from "@/lib/store/sc01";
import { toLoad, useSc06 } from "@/lib/store/sc06";

const POLL_MS = 15_000;

/**
 * 장면 6을 받는 **유일한** 자리(장면 1~5 수신과 같은 원칙, 4.6). 장면 6 화면(`/sc06/*`)에 있을 때만 돈다.
 *
 * * **장면 6을 저절로 열지 않는다** — 열면 장면 5가 완료 전일 때 장면 5 각본까지 실행된다. 없으면(404) `missing`을 켜고
 *   화면이 「장면 6 열기」를 묻는다.
 * * **문서 머리(확인 절차)는 SSE로 받는다** — 결재가 닫히면(Center는 폴러가 읽은 뒤) 바뀐다. 서 있지 않은 동안만 폴링.
 * * **조회(요약·보고·상세)는 멱등이다**(구현명세 10장) — 행위자·데모 실행·보고본, 그리고 확인 기록이 늘거나 보고본
 *   상태가 바뀔 때만 다시 받는다(조회 응답의 확인 이력·결론이 그 때 바뀐다).
 * * **늦은 응답이 새 선택을 덮지 않는다** — 조회마다 일련번호를 붙여 최신 것만 반영한다(10장 「요청 식별자 대조」).
 */
export function Sc06SessionSync() {
  const pathname = usePathname();
  const active = pathname.startsWith("/sc06");
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const version = useSc06((s) => (s.meta?.demoRunId === demoRunId ? s.meta.reportVersion : null));
  const loaded = useSc06((s) => s.meta?.demoRunId === demoRunId && demoRunId !== null);
  // 보고본 상태 · 남은 확인 기록 수 — 바뀌면 조회를 다시 받는다(그 사이에는 멱등이다)
  const progress = useSc06((s) =>
    s.meta?.demoRunId === demoRunId
      ? `${s.meta.reportState}:${s.meta.status.confirmed.length}:${s.meta.procedure?.steps.filter((p) => p.record).length ?? 0}`
      : null,
  );
  const detailOpen = useSc06((s) => s.detailOpen);
  const task = useSc06((s) => s.selectedTask);
  const readSeq = useRef(0);
  const varianceSeq = useRef(0);

  useEffect(() => {
    if (!active) return;
    void useSc06.persist.rehydrate();
    void sc06Api.process().then((r) => useSc06.getState().setTopology(r.ok ? r.data : null));
  }, [active]);

  useEffect(() => {
    if (!active || !demoRunId) return;
    let cancelled = false;
    void sc06Api.meta(demoRunId).then((r) => {
      if (cancelled) return;
      const { setMeta } = useSc06.getState();
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
      const r = await sc06Api.meta(demoRunId);
      if (r.ok) useSc06.getState().setMeta(r.data);
      else useSc06.getState().setConnection("offline");
    };
    const startPolling = () => {
      if (poll) return;
      useSc06.getState().setConnection("polling");
      poll = setInterval(() => void refetch(), POLL_MS);
    };
    const stopPolling = () => {
      if (poll) clearInterval(poll);
      poll = null;
    };
    useSc06.getState().setConnection("connecting");
    const source = new EventSource(sc06Api.eventsUrl(demoRunId));
    source.addEventListener("snapshot", (event) => {
      useSc06.getState().setMeta(JSON.parse((event as MessageEvent).data) as Sc06Meta);
    });
    source.addEventListener("ready", () => {
      stopPolling();
      useSc06.getState().setConnection("live");
    });
    source.onerror = () => startPolling();
    return () => {
      source.close();
      stopPolling();
    };
  }, [active, demoRunId, loaded]);

  useEffect(() => {
    if (!active || !demoRunId || !version) return;
    const mine = ++readSeq.current;
    const { setSummary, setReport } = useSc06.getState();
    setSummary({ state: "loading" });
    setReport({ state: "loading" });
    void sc06Api.summary(demoRunId, version, actor).then((r) => {
      if (mine === readSeq.current) setSummary(toLoad(r));
    });
    void sc06Api.report(demoRunId, version, actor).then((r) => {
      if (mine === readSeq.current) setReport(toLoad(r));
    });
  }, [active, demoRunId, version, actor, progress]);

  useEffect(() => {
    if (!active || !demoRunId || !version || !detailOpen) return;
    const mine = ++varianceSeq.current;
    useSc06.getState().setVariance({ state: "loading" });
    void sc06Api.variance(demoRunId, task, version, actor).then((r) => {
      if (mine === varianceSeq.current) useSc06.getState().setVariance(toLoad(r));
    });
  }, [active, demoRunId, version, actor, detailOpen, task]);

  return null;
}
