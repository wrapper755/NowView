/**
 * 장면 시작의 배경 진행 — 엔진 `app/preparation.py`의 화면 쪽.
 *
 * 장면 2~6의 시작(`POST …/demo-runs`)은 앞 장면을 각본으로 끝까지 실제로 실행한다. Center 실행이면 몇 분이 걸려
 * 엔진이 20초 안에 끝나지 않으면 **202와 준비 상태**를 돌려준다(한 요청을 몇 분 붙잡으면 BFF가 300초, 운영계의
 * Cloudflare가 약 100초에 끊는다). 화면은 `…/preparation`을 짧게 읽다가 끝나면 문서를 받는다 — 호출하는 쪽(시작
 * 카드·플레이어)은 그대로 `create`의 결과를 기다리면 된다.
 */

export interface PreparationStep {
  /** `sc01`~`sc05` — 화면 글에는 업무 이름으로 바꿔 쓴다(`WORKS`). */
  scene: string;
  step: string | null;
  bpm: string | null;
}

export interface Preparation {
  preparing: boolean;
  scene: string;
  demoRunId: string;
  state: "running" | "done" | "failed";
  startedAt?: string;
  finishedAt?: string | null;
  error?: string | null;
  status?: number | null;
  progress?: PreparationStep[];
}

type Failure = { ok: false; status: number; error: string };
type Outcome<T> = { ok: true; data: T } | Failure;

export function isPreparing(body: unknown): body is Preparation {
  return typeof body === "object" && body !== null && (body as Preparation).preparing === true;
}

const POLL_MS = 3000;
/** 준비 상태를 읽지 못해도 바로 실패로 보지 않는다 — 엔진이 reload 중일 수 있다. */
const READ_RETRIES = 5;

/**
 * 시작 응답이 준비 중(202)이면 끝날 때까지 기다린 뒤 `get`으로 문서를 받는다. 아니면 그대로 돌려준다. 실패는
 * 엔진이 남긴 사유·상태 코드 그대로다(조용히 숨기지 않는다).
 */
export async function afterPreparation<T, R extends Outcome<T>>(
  base: string,
  first: Outcome<T | Preparation>,
  get: (demoRunId: string) => Promise<R>,
  onProgress?: (p: Preparation) => void,
): Promise<R | Failure> {
  if (!first.ok || !isPreparing(first.data)) return first as R | Failure;
  const id = first.data.demoRunId;
  onProgress?.(first.data);
  let misses = 0;
  for (;;) {
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
    let state: Preparation | null = null;
    let status = 503;
    let error = "준비 상태를 읽지 못했다";
    try {
      const response = await fetch(`${base}/demo-runs/${id}/preparation`, { cache: "no-store" });
      const body = await response.json().catch(() => null);
      if (response.ok) state = body as Preparation;
      else {
        status = response.status;
        const detail = body?.detail ?? body?.error;
        error = typeof detail === "string" ? detail : `엔진 오류 (${response.status})`;
      }
    } catch (cause) {
      error = `엔진에 연결할 수 없다 — ${String(cause)}`;
    }
    if (state === null) {
      // 404는 이 엔진이 모르는 준비다(엔진이 다시 떴다) — 기다려도 오지 않는다
      if (status === 404 || ++misses > READ_RETRIES) return { ok: false, status, error };
      continue;
    }
    misses = 0;
    if (state.state === "done") return get(id);
    if (state.state === "failed") {
      return { ok: false, status: state.status ?? 500, error: state.error ?? "준비가 실패했다" };
    }
    onProgress?.(state);
  }
}
