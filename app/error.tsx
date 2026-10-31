"use client";

/**
 * 라우트 단위 오류 경계.
 *
 * **지금까지 이런 것이 없었다** — 데이터가 전부 Mock 코드라 "항상 있다"고 가정했기
 * 때문이다. 엔진이 붙으면 그 가정이 깨진다: `buildEngineSpec`이 명세 문제로 throw하거나
 * (게이트웨이에 분기 규칙이 없는 경우) 파생 함수가 Mock 불일치에 throw할 수 있다
 * (`buildChains`, `assertQuartersBalance`는 의도적으로 throw한다).
 *
 * 그 예외들은 **조용히 넘기면 안 되는 종류**이므로 throw를 유지하고, 대신 여기서
 * 사람이 읽을 수 있게 받는다.
 */

import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // 프로덕션 빌드는 메시지를 지우고 digest만 남긴다 — 콘솔에라도 남겨 둔다.
    console.error("화면 렌더 중 오류", error);
  }, [error]);

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-16 sm:px-6 lg:px-8">
      <div
        className="flex items-start gap-3 rounded-lg border p-4"
        style={{ borderColor: "var(--viz-status-serious)" }}
      >
        <AlertTriangle
          aria-hidden
          className="mt-0.5 size-5 shrink-0"
          style={{ color: "var(--viz-status-serious)" }}
        />
        <div className="min-w-0 space-y-2">
          <h1 className="text-base font-semibold">이 화면을 그리지 못했다</h1>
          <p className="text-sm text-muted-foreground">
            데이터가 서로 어긋났거나 엔진 응답이 예상과 다르다. 화면을 억지로 그리면
            잘못된 숫자가 나가므로 여기서 멈춘다.
          </p>
          {error.message ? (
            <p className="break-words rounded bg-muted p-2 font-mono text-xs">{error.message}</p>
          ) : null}
          {error.digest ? (
            <p className="text-xs text-muted-foreground">
              digest <span className="font-mono">{error.digest}</span>
            </p>
          ) : null}
          <div className="flex gap-2 pt-1">
            <Button size="sm" onClick={reset}>
              <RotateCcw aria-hidden className="size-3.5" />
              다시 시도
            </Button>
            <Button size="sm" variant="outline" asChild>
              <Link href="/">회사 목록으로</Link>
            </Button>
          </div>
        </div>
      </div>
    </main>
  );
}
