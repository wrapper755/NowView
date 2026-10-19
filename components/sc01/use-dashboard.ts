"use client";

import { useEffect, useState } from "react";

import { sc01Api } from "@/lib/sc01/client";
import type { Dashboard } from "@/lib/sc01/types";
import { useSc01 } from "@/lib/store/sc01";

/**
 * UI01 대시보드 — 엔진이 시드 + 이 실행의 전망에서 매번 계산한다.
 *
 * 문서가 바뀔 때(`revision`)와 기간을 바꿀 때 다시 읽는다. 지난 시점을 보고 있으면 그 시점의
 * 문서로 계산한 값을 읽는다 — 그래야 S0 장면에 F02가 보이지 않는다(AT01).
 */
export function useDashboard(period: string, month: number) {
  const demoRunId = useSc01((s) => s.demoRunId);
  const revision = useSc01((s) => s.revision);
  const seq = useSc01((s) => s.past?.seq ?? null);
  const [state, setState] = useState<{ key: string; data: Dashboard | null; error: string | null }>({
    key: "",
    data: null,
    error: null,
  });
  const key = `${demoRunId}|${period}|${month}|${seq}|${revision}`;

  useEffect(() => {
    if (!demoRunId) return;
    let cancelled = false;
    void sc01Api.dashboard(demoRunId, { period, month, seq }).then((r) => {
      if (cancelled) return;
      setState(r.ok ? { key, data: r.data, error: null } : { key, data: null, error: r.error });
    });
    return () => {
      cancelled = true;
    };
  }, [demoRunId, period, month, seq, key]);

  // 새 값이 오기 전까지는 직전 값을 그대로 보여 준다 — 비웠다 채우면 화면이 깜빡인다.
  return { dashboard: state.data, error: state.error, stale: state.key !== key };
}
