import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ActorSwitcher } from "@/components/sc01/actor-switcher";
import { Sc01SessionSync } from "@/components/sc01/session-sync";
import { CommentaryToggle } from "@/components/shared/commentary-toggle";
import { DemoPlayerSwitch } from "@/components/shared/demo-player-switch";
import { ScreenNav, WorkHeading, WorkSidebar } from "@/components/shared/scenario-nav";
import { SectionNav } from "@/components/shared/section-nav";
import { TopBar } from "@/components/shared/top-bar";
import { COMPANIES, findCompany } from "@/lib/companies";

/** 회사는 등록부(`lib/companies.ts`)에 있는 것뿐이다 — 빌드 때 회사마다 정적 경로를 만든다(페이지는 정적 프리렌더, 4.3). */
export const dynamicParams = false;

export function generateStaticParams() {
  return COMPANIES.map((c) => ({ company: c.id }));
}

export async function generateMetadata({ params }: LayoutProps<"/c/[company]">): Promise<Metadata> {
  const { company } = await params;
  return { title: `NowView — ${findCompany(company)?.name ?? company}` };
}

/**
 * 회사 화면 — 공통 줄 아래 세 단이다: 왼쪽 업무(그 회사의 BPM 프로세스, 사이드바 `lg:pl-56`), 가운데 머리·본문, 오른쪽 데모
 * 플레이어(xl, 여백은 globals.css의 `[data-demo-player]`). 좁으면 업무는 가운데 머리의 선택, 플레이어는 하단 바다.
 * 사이드바·플레이어·가운데 머리가 `top-12`에 맞물리므로 공통 줄 높이를 바꾸면 함께 본다.
 */
export default async function CompanyLayout({ children, params }: LayoutProps<"/c/[company]">) {
  const { company: id } = await params;
  const company = findCompany(id);
  if (!company) notFound();
  return (
    <div className="flex flex-1 flex-col lg:pl-56">
      <TopBar company={company}>
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

      {/* 하단 여백은 데모 플레이어 높이만큼 CSS가 준다(globals.css의 `[data-demo-player]`). */}
      <div className="flex-1">{children}</div>

      {/* 데모 실행을 여기서만 받는다(SSE, 폴백은 폴링) — 화면마다 받으면 같은 화면의 두 패널이 서로 다른 순간을 보고,
          요청이 패널 수만큼 배로 늘어난다. */}
      <Sc01SessionSync />
      <DemoPlayerSwitch />
    </div>
  );
}
