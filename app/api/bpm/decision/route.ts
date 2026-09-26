import { bpmProcess } from "@/lib/mock-data/bpm-process";
import { reviewCase } from "@/lib/mock-data/review-case";
import { rollingPlan } from "@/lib/mock-data/rolling-plan";
import { badRequest, ok, readJson } from "@/lib/api/response";
import { DECISION_RATIONALE_MIN_LENGTH, type ReviewDecision } from "@/lib/types/workspace";
import { simulateAlternative } from "@/services/agent-orchestrator";
import { clampStepIndex, currentStage } from "@/services/bpm-engine";
import { decisionToAction, summarizeGap } from "@/services/rolling-plan";

interface DecisionRequest {
  alternativeId: string;
  leverValue: number;
  rationale: string;
}

/**
 * 승인 요청 검증.
 *
 * **사유 검사를 여기서 한 번 더 한다.** UI의 버튼 비활성은 편의일 뿐 강제가 아니다 —
 * API를 직접 호출하면 우회된다. 최종 판단의 책임이 사람에게 있다는 원칙(CLAUDE.md 1장)을
 * 실제로 지키려면 경계에서 막아야 한다.
 */
function parse(body: unknown): { ok: true; value: DecisionRequest } | { ok: false; message: string; detail?: unknown } {
  if (typeof body !== "object" || body === null) {
    return { ok: false, message: "본문은 객체여야 한다" };
  }
  const { alternativeId, leverValue, rationale } = body as Record<string, unknown>;

  if (typeof alternativeId !== "string") {
    return { ok: false, message: "alternativeId는 문자열이어야 한다" };
  }

  const alternative = reviewCase.alternatives.find((a) => a.id === alternativeId);
  if (!alternative) {
    return {
      ok: false,
      message: `알 수 없는 대안: ${alternativeId}`,
      detail: { available: reviewCase.alternatives.map((a) => a.id) },
    };
  }

  if (typeof leverValue !== "number" || Number.isNaN(leverValue)) {
    return { ok: false, message: "leverValue는 숫자여야 한다" };
  }
  const { lever } = alternative;
  if (leverValue < lever.min || leverValue > lever.max) {
    return {
      ok: false,
      message: `leverValue는 ${lever.min} 이상 ${lever.max} 이하여야 한다`,
      detail: { lever: lever.label, unit: lever.unit, received: leverValue },
    };
  }

  if (typeof rationale !== "string" || rationale.trim().length < DECISION_RATIONALE_MIN_LENGTH) {
    return {
      ok: false,
      message: `결정 사유는 ${DECISION_RATIONALE_MIN_LENGTH}자 이상이어야 한다`,
      detail: { received: typeof rationale === "string" ? rationale.trim().length : 0 },
    };
  }

  return { ok: true, value: { alternativeId, leverValue, rationale: rationale.trim() } };
}

/** 결정 시각. 서버 시각이며 SSR 하이드레이션과 무관하다. */
function stampNow(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/**
 * POST /api/bpm/decision — Management Review 승인.
 *
 * 승인의 결과를 한 번에 돌려준다: 기록된 결정, 그로부터 만들어진 실행 과제,
 * 프로세스가 이동할 지점, 그리고 Gap이 어떻게 달라지는지.
 *
 * Gap 계산은 `summarizeGap`을 그대로 쓰므로 **이중 계상 규칙(CLAUDE.md "화면 간 수치·상태 연동")이 여기서도
 * 지켜진다** — 신규 과제는 미반영으로 잡히고 현재 Forecast를 바꾸지 않는다.
 */
export async function POST(request: Request) {
  const body = await readJson(request);
  if (!body.ok) return badRequest(body.message);

  const parsed = parse(body.data);
  if (!parsed.ok) return badRequest(parsed.message, parsed.detail ?? body.data);

  const alternative = reviewCase.alternatives.find((a) => a.id === parsed.value.alternativeId)!;
  const result = simulateAlternative(alternative, parsed.value.leverValue);

  const decision: ReviewDecision = {
    alternativeId: alternative.id,
    leverValue: parsed.value.leverValue,
    profitImpact: result.profitImpact,
    rationale: parsed.value.rationale,
    decidedAt: stampNow(),
  };

  const action = decisionToAction(decision, alternative, reviewCase.riskId);
  const step = clampStepIndex(bpmProcess, bpmProcess.sequence.indexOf("action"));

  const before = summarizeGap(rollingPlan, rollingPlan.actions);
  const after = summarizeGap(rollingPlan, [action, ...rollingPlan.actions]);

  return ok(
    {
      decision,
      simulation: result,
      action,
      process: {
        processId: bpmProcess.id,
        step,
        stage: currentStage(bpmProcess, step),
      },
      gap: {
        before: { forecast: before.forecast, gap: before.gap },
        after: {
          // 신규 과제는 아직 미반영이므로 현재 Forecast는 그대로다.
          forecast: after.forecast,
          gap: after.gap,
          pendingRecovery: after.pendingRecovery,
          projectedForecast: after.projectedForecast,
          projectedGap: after.projectedGap,
        },
      },
    },
    { status: 201 },
  );
}
