import { WorkspaceShell } from "@/components/workspace/workspace-shell";

export const metadata = {
  title: "NowView — Human-Agent Collaboration Station",
};

export default function WorkspacePage() {
  return (
    <main className="mx-auto w-full max-w-7xl space-y-5 px-4 py-6 sm:px-6 lg:px-8">
      <WorkspaceShell />

      <p className="pb-2 text-xs text-muted-foreground">
        본 화면의 보고서·대안·시뮬레이션 결과는 Mock 데이터다. 시뮬레이션 응답 모델은 선형
        근사이며 실제 추정 엔진이 아니다.
      </p>
    </main>
  );
}
