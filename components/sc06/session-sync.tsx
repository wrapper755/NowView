"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";

import { sc06Api } from "@/lib/sc06/client";
import { useSc01 } from "@/lib/store/sc01";
import { toLoad, useSc06 } from "@/lib/store/sc06";

/**
 * 장면 6 조회를 받는 **유일한** 자리(장면 1~5 수신과 같은 원칙, 4.6). 장면 6 화면(`/sc06/*`)에 있을 때만 돈다.
 *
 * * **장면 6을 저절로 열지 않는다** — 열면 장면 5가 완료 전일 때 장면 5 각본까지 실행된다. 없으면(404) `missing`을 켜고
 *   화면이 「장면 6 열기」를 묻는다.
 * * **변경 수신(SSE)이 없다.** 장면 6 문서는 적재 뒤 바뀌지 않는다 — 조회는 멱등이다(구현명세 10장). 행위자·데모
 *   실행·보고본이 바뀔 때만 다시 받는다.
 * * **늦은 응답이 새 선택을 덮지 않는다** — 조회마다 일련번호를 붙여 최신 것만 반영한다(10장 「요청 식별자 대조」).
 */
export function Sc06SessionSync() {
  const pathname = usePathname();
  const active = pathname.startsWith("/sc06");
  const demoRunId = useSc01((s) => s.demoRunId);
  const actor = useSc01((s) => s.actor);
  const version = useSc06((s) => (s.meta?.demoRunId === demoRunId ? s.meta.reportVersion : null));
  const detailOpen = useSc06((s) => s.detailOpen);
  const task = useSc06((s) => s.selectedTask);
  const readSeq = useRef(0);
  const varianceSeq = useRef(0);

  useEffect(() => {
    if (active) void useSc06.persist.rehydrate();
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
  }, [active, demoRunId, version, actor]);

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
