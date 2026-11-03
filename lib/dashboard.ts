/**
 * 회사 대시보드(화면 쪽) — 엔진 `GET /companies/{회사}/dashboard`의 모양과 표기.
 *
 * 숫자는 엔진의 규칙 계산 그대로다(회사에 적는 경영 기록에서 고른 값, `engine/app/dashboard.py`). 화면은 단위만 바꾼다 —
 * 금액은 문자열 DECIMAL로 오고, 값이 없으면 `null`이다(0이 아니다 — 「미산출」로 쓴다).
 */

export type Metric = { label: string; kind: "krw" | "text"; value: string | null; signed?: boolean };

export type WorkerEntry = { at: string | null; operation: string | null; ok: boolean; reason: string | null };

export type Work = {
  scene: number;
  work: string;
  /** BPM 실행 상태 — `none`은 그 업무 문서가 아직 없다(시작 전), `not_started`는 문서는 있고 실행 전이다. */
  state: string;
  clock: string | null;
  progress: { approvals: number; passed: number } | null;
  waiting: { nodeId: string | null; title: string | null }[];
  metrics: Metric[];
  worker: { count: number; failed: number; recent: WorkerEntry[] };
};

export type World = {
  worldId: string;
  /** `site` — 회사 사이트가 만든 세계. 그 밖은 예전(엔진이 만든) 세계다. */
  origin: string | null;
  caseId: string | null;
  generation: number | null;
  clock: string | null;
};

export type Dashboard = {
  company: { id: string; name: string; description: string; siteUrl: string | null };
  worlds: World[];
  world: string | null;
  problem: string | null;
  works: Work[];
};

export const STATE_LABEL: Record<string, string> = {
  none: "시작 전",
  not_started: "착수 전",
  running: "진행 중",
  done: "흐름 끝",
  failed: "멈춤",
  cancelled: "멈춤",
};

const MINUS = "−";

/** 원 단위 금액 → 억(소수 둘째 자리)·만·원. `signed`면 양수에 +를 붙인다. 없으면 「미산출」. */
export function formatKrw(value: string | null, signed = false): string {
  if (value === null) return "미산출";
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  const sign = n < 0 ? MINUS : signed && n > 0 ? "+" : "";
  const abs = Math.abs(n);
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}억`;
  if (abs >= 1e4) return `${sign}${Math.round(abs / 1e4).toLocaleString("ko-KR")}만`;
  return `${sign}${abs.toLocaleString("ko-KR")}원`;
}

/** 원 단위 그대로(쉼표) — 제목(`title`)에 둔다. */
export function formatWon(value: string | null): string {
  if (value === null) return "미산출";
  const n = Number(value);
  return Number.isFinite(n) ? `${n < 0 ? MINUS : ""}${Math.abs(n).toLocaleString("ko-KR")}원` : value;
}

export function formatMetric(m: Metric): string {
  if (m.kind === "text") return m.value ?? "미확인";
  return formatKrw(m.value, m.signed);
}

/** 가상시각 `2027-06-16T11:45:00+09:00` → `2027-06-16 11:45`. 엔진이 KST로 준다 — 브라우저 시간대로 바꾸지 않는다. */
export function formatClock(at: string | null): string {
  if (!at) return "—";
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(at);
  return m ? `${m[1]} ${m[2]}` : at;
}

/** 회사 사이트의 그 업무 화면 — `{site}/work/{회차}/sc0N`. 회차 = 세계 = 데모 실행 id. */
export function workUrl(siteUrl: string | null, world: string | null, scene: number): string | null {
  if (!siteUrl || !world) return null;
  return `${siteUrl}/work/${encodeURIComponent(world)}/sc${String(scene).padStart(2, "0")}`;
}
