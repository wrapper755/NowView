import { ActorSwitcher } from "@/components/sc01/actor-switcher";
import { Sc01SessionSync } from "@/components/sc01/session-sync";
import { Sc02SessionSync } from "@/components/sc02/session-sync";
import { Sc03SessionSync } from "@/components/sc03/session-sync";
import { Sc04SessionSync } from "@/components/sc04/session-sync";
import { Sc05SessionSync } from "@/components/sc05/session-sync";
import { Sc06SessionSync } from "@/components/sc06/session-sync";
import { Sc07SessionSync } from "@/components/sc07/session-sync";
import { CommentaryToggle } from "@/components/shared/commentary-toggle";
import { ScreenNav, WorkHeading, WorkSidebar } from "@/components/shared/scenario-nav";
import { SectionNav } from "@/components/shared/section-nav";
import { TopBar } from "@/components/shared/top-bar";

/**
 * 회사 화면 — 공통 줄 아래 두 단이다: 왼쪽 업무(그 회사의 BPM 프로세스, 사이드바 — 자리는 globals.css의 `.work-shell`, 첫 화면에는 없다)와
 * 가운데 머리·본문. 좁으면 업무는 가운데 머리의 선택이다. 사이드바·가운데 머리가 `top-12`에 맞물리므로 공통 줄 높이를 바꾸면 함께 본다.
 *
 * **화면은 읽기 전용이다**(2026-11-03, `docs/role-split.md` §5.5) — 결재 답·장면 열기·시계·초기화 같은 시연 조작은 회사 사이트가 한다.
 * 데모 플레이어는 걷었다. 보는 사람(역할 선택)은 남는다 — 장면 6·7 조회가 참여자만 받는다.
 */
export default async function CompanyLayout({ children, params }: LayoutProps<"/c/[company]">) {
  // 회사는 설정(엔진 DB)이라 빌드 때 모른다 — 서버에서 엔진을 묻지 않는다(엔진이 꺼져도 화면 틀은 뜬다, 4.3). 이름·없는
  // 회사 판정은 클라이언트가 공개 목록으로 한다.
  const { company: id } = await params;
  return (
    <div className="work-shell flex flex-1 flex-col">
      <TopBar companyId={id}>
        <ActorSwitcher />
        <CommentaryToggle />
      </TopBar>

      <WorkSidebar />
      <header className="sticky top-12 z-30 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        {/* 지금 업무 — 업무 목록은 왼쪽 사이드바에 있다(좁으면 여기서 고른다). */}
        <div className="mx-auto flex w-full max-w-7xl items-center gap-3 px-4 pt-3 pb-2.5 sm:px-6 lg:px-8">
          <WorkHeading />
        </div>

        {/* 업무에 따라 달라지는 화면 메뉴 — 업무 이름 아래 줄이다. */}
        <ScreenNav />

        {/* 화면 안 섹션 이동 — 화면 메뉴 아래 한 줄. */}
        <SectionNav />
      </header>

      <div className="flex-1">{children}</div>

      {/* 데모 실행을 여기서만 받는다(SSE, 폴백은 폴링) — 화면마다 받으면 같은 화면의 두 패널이 서로 다른 순간을 보고,
          요청이 패널 수만큼 배로 늘어난다. */}
      <Sc01SessionSync />
      {/* 장면 2~7 문서 수신 — 각자 그 장면 화면에서만 돈다. */}
      <Sc02SessionSync />
      <Sc03SessionSync />
      <Sc04SessionSync />
      <Sc05SessionSync />
      <Sc06SessionSync />
      <Sc07SessionSync />
    </div>
  );
}
