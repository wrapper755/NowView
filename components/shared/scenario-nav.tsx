"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BadgeCheck,
  CalendarCheck,
  ChartLine,
  Calculator,
  ClipboardList,
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

import { cn } from "@/lib/utils";

/**
 * GNB — 장면 선택 + 그 장면의 화면(시연 순서대로). 장면 1은 UI01~UI06, 장면 2는 U21~U27, 장면 3은 U31~U37, 장면 4는
 * U401~U408, 장면 5는 U501~U508이다. 화면 경로로 장면을 가른다(`/sc02/*` = 장면 2 …) — 장면을 상태로 따로 들고 있으면 GNB·플레이어·링크가 갈라진다.
 */
const SC01_ITEMS: Array<{ label: string; icon: LucideIcon; href: string }> = [
  { label: "경영 현황", icon: GaugeCircle, href: "/" },
  { label: "고객계획", icon: FileInput, href: "/plans" },
  { label: "위험 검토", icon: TriangleAlert, href: "/risk" },
  { label: "업무", icon: ClipboardList, href: "/tasks" },
  { label: "이슈·인계", icon: Handshake, href: "/handoff" },
  { label: "BPM 흐름", icon: GitBranch, href: "/process" },
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

/** 경로 → 장면 번호. */
export function sceneOf(pathname: string): 1 | 2 | 3 | 4 | 5 {
  if (pathname === "/sc05" || pathname.startsWith("/sc05/")) return 5;
  if (pathname === "/sc04" || pathname.startsWith("/sc04/")) return 4;
  if (pathname === "/sc03" || pathname.startsWith("/sc03/")) return 3;
  if (pathname === "/sc02" || pathname.startsWith("/sc02/")) return 2;
  return 1;
}

export function ScenarioNav() {
  const pathname = usePathname();
  const scene = sceneOf(pathname);
  const items = scene === 5 ? SC05_ITEMS : scene === 4 ? SC04_ITEMS : scene === 3 ? SC03_ITEMS : scene === 2 ? SC02_ITEMS : SC01_ITEMS;
  return (
    <nav aria-label="주요 화면" className="flex min-w-[5.75rem] flex-1 items-center gap-1 sm:gap-2">
      <div role="group" aria-label="장면" className="flex shrink-0 rounded-md border p-0 text-[11px] sm:p-0.5">
        {[
          { n: "1", href: "/", on: scene === 1 },
          { n: "2", href: "/sc02", on: scene === 2 },
          { n: "3", href: "/sc03", on: scene === 3 },
          { n: "4", href: "/sc04", on: scene === 4 },
          { n: "5", href: "/sc05", on: scene === 5 },
        ].map((s) => (
          <Link
            key={s.n}
            href={s.href}
            aria-current={s.on ? "page" : undefined}
            className={cn("rounded px-px py-0.5 font-medium sm:px-1.5", s.on ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground")}
          >
            {/* 좁은 화면에서는 숫자만 — 「장면」 두 번이 화면 메뉴 자리를 0px로 눌렀다(375px 실측). 장면 3을 더하자
                칩 묶음(62px)+메뉴 최소 폭이 nav 최소 폭(88px)을 넘어 메뉴가 역할 선택 위로 겹쳤다 — 칩 여백·간격과 메뉴 최소 폭을
                줄이고 nav 최소 폭을 6rem으로 맞췄다(375px에서 테마 버튼까지 들어간다). 장면 4 칩을 더하자 칩 묶음이 65px가 되어
                메뉴가 역할 선택에 다시 닿았다 — nav 최소 폭을 올리면 테마 버튼이 화면 밖(386px)으로 밀려서, 좁을 때 칩 여백을
                px-0.5로 줄였다. 장면 5 칩을 더하자 칩 묶음(59px)+메뉴 최소 폭이 nav를 8px 넘고 헤더 전체가 오른쪽 여백을 침범했다
                (테마 버튼 오른쪽 끝 370px, 375px 실측) — 좁을 때 칩 여백을 1px·묶음 안쪽 여백을 0으로, nav 최소 폭을 5.75rem으로,
                역할 선택을 5rem으로 줄였다. */}
            <span className="sr-only sm:not-sr-only">장면 </span>
            {s.n}
          </Link>
        ))}
      </div>
      <ul className="flex min-w-[2.5rem] flex-1 items-center gap-1 overflow-x-auto">
        {items.map(({ label, icon: Icon, href }) => (
          <li key={label} className="shrink-0">
            <Link
              href={href}
              aria-current={pathname === href ? "page" : undefined}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-muted",
                pathname === href && "bg-muted",
              )}
            >
              <Icon aria-hidden className="size-3.5" />
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
