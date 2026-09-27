import { WorkspaceShell } from "@/components/workspace/workspace-shell";
import { Commentary } from "@/components/shared/commentary";

export const metadata = {
  title: "NowView — Human-Agent Collaboration Station",
};

export default function WorkspacePage() {
  return (
    <main className="mx-auto w-full max-w-7xl space-y-5 px-4 py-6 sm:px-6 lg:px-8">
      <WorkspaceShell />

      <Commentary block>
        <p className="pb-2 text-xs text-muted-foreground">
          시뮬레이션 응답 모델은 선형 근사이며 실제 추정 엔진이 아니다. 엔진 모드에서는
          승인이 멈춰 있는 워크플로를 실제로 재개하고, 사유가 짧으면 엔진이 반려해 같은
          지점에 다시 멈춘다 — 금액은 화면이 계산한다(엔진은 무엇을 골랐는지만 돌려준다).
        </p>
      </Commentary>
    </main>
  );
}
