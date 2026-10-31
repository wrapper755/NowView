"use client";

import { CompanyLink as Link } from "@/components/shared/company-link";
import { useCompanyRouter as useRouter, useScenePath as usePathname } from "@/lib/company-nav";
import {
  BadgeCheck,
  ClipboardCheck,
  CalendarCheck,
  ChartLine,
  Calculator,
  ClipboardList,
  FileText,
  FileInput,
  FilePen,
  GaugeCircle,
  GitBranch,
  Handshake,
  Inbox,
  ListChecks,
  ListTodo,
  MessagesSquare,
  Presentation,
  Receipt,
  RefreshCcw,
  ShieldCheck,
  SquareKanban,
  Stamp,
  TriangleAlert,
  UsersRound,
  type LucideIcon,
} from "lucide-react";

import { SCENES } from "@/lib/companies";
import { cn } from "@/lib/utils";

/**
 * 업무(장면) 선택 + 그 업무의 화면(시연 순서대로). 업무는 왼쪽 사이드바, 화면은 머리 줄 아래 한 줄이다. 장면 1은 UI01~UI06, 장면 2는 U21~U27, 장면 3은 U31~U37, 장면 4는
 * U401~U408, 장면 5는 U501~U508, 장면 6은 U601·U602다. 화면 경로로 장면을 가른다(`/sc02/*` = 장면 2 …) — 장면을 상태로 따로 들고 있으면 GNB·플레이어·링크가 갈라진다.
 */
const SC01_ITEMS: Array<{ label: string; icon: LucideIcon; href: string }> = [
  { label: "경영 현황", icon: GaugeCircle, href: "/sc01" },
  { label: "고객계획", icon: FileInput, href: "/sc01/plans" },
  { label: "위험 검토", icon: TriangleAlert, href: "/sc01/risk" },
  { label: "업무", icon: ClipboardList, href: "/sc01/tasks" },
  { label: "이슈·인계", icon: Handshake, href: "/sc01/handoff" },
  { label: "BPM 흐름", icon: GitBranch, href: "/sc01/process" },
];

const SC02_ITEMS: Array<{ label: string; icon: LucideIcon; href: string }> = [
  { label: "현황", icon: GaugeCircle, href: "/sc02" },
  { label: "요청 접수", icon: Inbox, href: "/sc02/request" },
  { label: "영향분석", icon: Calculator, href: "/sc02/analysis" },
  { label: "협상", icon: MessagesSquare, href: "/sc02/negotiation" },
  { label: "기안", icon: FilePen, href: "/sc02/proposal" },
  { label: "승인", icon: BadgeCheck, href: "/sc02/approval" },
  { label: "원가", icon: Receipt, href: "/sc02/cost" },
  { label: "통합영향·인계", icon: Handshake, href: "/sc02/handoff" },
  { label: "BPM 흐름", icon: GitBranch, href: "/sc02/process" },
];

const SC03_ITEMS: Array<{ label: string; icon: LucideIcon; href: string }> = [
  { label: "업무함", icon: Inbox, href: "/sc03" },
  { label: "통합분석", icon: Calculator, href: "/sc03/analysis" },
  { label: "부서확인", icon: UsersRound, href: "/sc03/confirm" },
  { label: "수시회의", icon: Presentation, href: "/sc03/meeting" },
  { label: "분석과제", icon: ListChecks, href: "/sc03/tasks" },
  { label: "완료·인계", icon: Handshake, href: "/sc03/handoff" },
  { label: "BPM 흐름", icon: GitBranch, href: "/sc03/process" },
];

const SC04_ITEMS: Array<{ label: string; icon: LucideIcon; href: string }> = [
  { label: "결과 업무함", icon: Inbox, href: "/sc04" },
  { label: "효과 검증", icon: ShieldCheck, href: "/sc04/verify" },
  { label: "실행안 제안", icon: ListChecks, href: "/sc04/recommend" },
  { label: "회의 보고", icon: Presentation, href: "/sc04/report" },
  { label: "대표 질의", icon: MessagesSquare, href: "/sc04/meeting" },
  { label: "포괄 승인", icon: Stamp, href: "/sc04/approval" },
  { label: "책임 인수", icon: CalendarCheck, href: "/sc04/actions" },
  { label: "인계·종료", icon: Handshake, href: "/sc04/handoff" },
  { label: "BPM 흐름", icon: GitBranch, href: "/sc04/process" },
];

const SC05_ITEMS: Array<{ label: string; icon: LucideIcon; href: string }> = [
  { label: "과제 현황", icon: SquareKanban, href: "/sc05" },
  { label: "상세 계획", icon: ListTodo, href: "/sc05/plan" },
  { label: "조건·착수", icon: ShieldCheck, href: "/sc05/ready" },
  { label: "변경 대응", icon: RefreshCcw, href: "/sc05/changes" },
  { label: "초기 결과", icon: GaugeCircle, href: "/sc05/results" },
  { label: "운영계획", icon: CalendarCheck, href: "/sc05/operating" },
  { label: "공식 전망", icon: ChartLine, href: "/sc05/forecast" },
  { label: "후속·인계", icon: Handshake, href: "/sc05/handoff" },
  { label: "BPM 흐름", icon: GitBranch, href: "/sc05/process" },
];

/** 장면 6 — 확인 절차(BPM) 뒤 두 화면·세 동작의 조회. */
const SC06_ITEMS: Array<{ label: string; icon: LucideIcon; href: string }> = [
  { label: "완료·성과 검토", icon: ClipboardCheck, href: "/sc06" },
  { label: "확인 절차", icon: ShieldCheck, href: "/sc06/confirm" },
  { label: "보고 요약", icon: FileText, href: "/sc06/report" },
  { label: "BPM 흐름", icon: GitBranch, href: "/sc06/process" },
];

/** 경로 → 장면 번호. */
export function sceneOf(pathname: string): 1 | 2 | 3 | 4 | 5 | 6 {
  if (pathname === "/sc06" || pathname.startsWith("/sc06/")) return 6;
  if (pathname === "/sc05" || pathname.startsWith("/sc05/")) return 5;
  if (pathname === "/sc04" || pathname.startsWith("/sc04/")) return 4;
  if (pathname === "/sc03" || pathname.startsWith("/sc03/")) return 3;
  if (pathname === "/sc02" || pathname.startsWith("/sc02/")) return 2;
  return 1;
}

/**
 * 장면 = 그 장면이 수행하는 업무. 「장면 1~6」은 시연 순서일 뿐 업무가 무엇인지 말하지 않는다 — 사이드바·좁은 화면의
 * 업무 선택은 업무 이름으로 보이고, 순서는 작은 번호로만 남긴다. 업무는 NowView 코드의 목록(`lib/companies.ts`의 `SCENES`)이다.
 */
export const WORKS: Array<{ scene: 1 | 2 | 3 | 4 | 5 | 6; label: string; detail: string; href: string }> = SCENES.map((s) => ({
  scene: s.no,
  label: s.work,
  detail: s.detail,
  href: `/sc0${s.no}`,
}));

function itemsOf(scene: number) {
  return scene === 6 ? SC06_ITEMS : scene === 5 ? SC05_ITEMS : scene === 4 ? SC04_ITEMS : scene === 3 ? SC03_ITEMS : scene === 2 ? SC02_ITEMS : SC01_ITEMS;
}

/** 왼쪽 사이드바(넓은 화면) — 업무 목록. 로고는 그 위 공통 줄에 있다. */
export function WorkSidebar() {
  const path = usePathname();
  // 회사 첫 화면(`/`)은 어느 업무도 아니다 — 회사 운영 현황이다.
  const scene = path === "/" ? 0 : sceneOf(path);
  return (
    <aside className="chrome-ink fixed top-12 bottom-0 left-0 z-40 hidden w-56 flex-col border-r lg:flex">
      <nav aria-label="업무" className="flex-1 overflow-y-auto px-2 pt-2 pb-4">
        <p className="px-2 pt-2 pb-1.5 text-[11px] font-medium text-muted-foreground">업무</p>
        <ol className="flex flex-col gap-0.5">
          {WORKS.map((w) => {
            const on = w.scene === scene;
            return (
              <li key={w.scene}>
                <Link
                  href={w.href}
                  aria-current={on ? "page" : undefined}
                  className={cn("flex gap-2 rounded-md px-2 py-2", on ? "bg-brand text-brand-foreground" : "hover:bg-muted")}
                >
                  <span
                    aria-hidden
                    className={cn(
                      "mt-px flex size-4 shrink-0 items-center justify-center rounded-full border text-[10px] tabular-nums",
                      on ? "border-brand-foreground bg-brand-foreground text-brand" : "border-current text-muted-foreground",
                    )}
                  >
                    {w.scene}
                  </span>
                  <span className="min-w-0">
                    <span className={cn("block text-xs leading-snug", on ? "font-semibold" : "font-medium text-foreground/85")}>{w.label}</span>
                    <span className={cn("block text-[11px] leading-snug", on ? "opacity-80" : "text-muted-foreground")}>{w.detail}</span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ol>
      </nav>
    </aside>
  );
}

/** 머리 줄의 지금 업무 — 넓을 때는 이름, 좁을 때(사이드바가 없을 때)는 업무 선택이다. */
export function WorkHeading() {
  const router = useRouter();
  const path = usePathname();
  const scene = sceneOf(path);
  const work = WORKS.find((w) => w.scene === scene) ?? WORKS[0];
  if (path === "/") {
    return (
      <div className="min-w-0 flex-1">
        <p className="truncate text-base font-semibold">운영 현황</p>
      </div>
    );
  }
  return (
    <div className="min-w-0 flex-1">
      <p className="hidden min-w-0 items-baseline gap-2 lg:flex">
        <span className="shrink-0 self-center rounded bg-brand px-1.5 py-0.5 text-[11px] font-semibold text-brand-foreground tabular-nums">
          업무 {work.scene}
        </span>
        <span className="truncate text-base font-semibold">{work.label}</span>
        <span className="hidden truncate text-xs text-muted-foreground xl:inline">{work.detail}</span>
      </p>
      <label className="lg:hidden">
        <span className="sr-only">업무</span>
        <select
          value={work.href}
          onChange={(e) => router.push(e.target.value)}
          className="w-full max-w-[14rem] truncate rounded-md border bg-transparent px-1.5 py-1 text-xs font-medium"
        >
          {WORKS.map((w) => (
            <option key={w.scene} value={w.href}>
              {w.scene}. {w.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

/**
 * 지금 업무의 화면들(시연 순서) — 왼쪽에서 고른 업무의 하위 메뉴다. 업무 이름 바로 아래에 알약 탭으로 두어 섹션 탭(밑줄)과
 * 층을 가른다. 가로로만 넘친다 — `overflow-x-auto`는 세로도 auto로 만들어, 밑줄의 `-mb-px` 1px 때문에 세로 스크롤 화살표가
 * 생겼다(1280px 실측). 세로는 숨긴다.
 */
export function ScreenNav() {
  const pathname = usePathname();
  if (pathname === "/") return null;
  const items = itemsOf(sceneOf(pathname));
  return (
    <nav aria-label="업무 화면" className="border-t border-brand/15 bg-brand-soft/50">
      <ul className="mx-auto flex w-full max-w-7xl items-center gap-1 overflow-x-auto overflow-y-hidden px-4 py-2 sm:px-6 lg:px-8">
        {items.map(({ label, icon: Icon, href }) => {
          const on = pathname === href;
          return (
            <li key={label} className="shrink-0">
              <Link
                href={href}
                aria-current={on ? "page" : undefined}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors",
                  on ? "bg-brand text-brand-foreground shadow-sm" : "text-foreground/80 hover:bg-card hover:text-foreground",
                )}
              >
                <Icon aria-hidden className={cn("size-4", on ? "opacity-100" : "text-muted-foreground")} />
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
