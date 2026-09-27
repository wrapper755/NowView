"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";

/**
 * 화면 안 섹션 이동 (앵커 네비게이션) — GNB 바로 아래 한 줄.
 *
 * **왼쪽 레일로 먼저 만들었다가 걷어냈다.** 화면 위(GNB)와 왼쪽(목차)으로 시선 축이
 * 둘로 갈려 오히려 찾기 어려웠고, 펼치면 본문을 밀어내 레이아웃까지 움직였다. 같은
 * 기능을 헤더 안에 한 줄로 넣으면 축이 하나로 모이고 본문은 그대로 있는다.
 *
 * **항목은 선언하지 않고 지금 그려진 DOM에서 파생한다.** 화면별 섹션 목록을 손으로
 * 적어 두면 조건부 섹션(미답 질문, 엔진 패널, 승인 후 나타나는 것들)과 데이터가 들어간
 * 제목("실행 과제 3건")이 곧 어긋난다 — `docs/scene-design.md`를 손으로 쓰지 않는 것과
 * 같은 이유다(CLAUDE.md 4.14). 목차에서 빼려면 해당 카드에 `data-index-skip`을 단다.
 */

/** 헤더를 못 읽었을 때 쓸 값. 평소에는 실제 헤더 높이를 잰다. */
const FALLBACK_HEADER_OFFSET = 88;

type IndexItem = { id: string; label: string };

function headerOffset(): number {
  const header = document.querySelector("header");
  return header ? header.getBoundingClientRect().height + 12 : FALLBACK_HEADER_OFFSET;
}

/**
 * 제목 텍스트를 앵커 id로 바꾼다.
 *
 * 숫자를 지우는 것은 "실행 과제 3건"처럼 건수가 제목에 들어간 섹션 때문이다 — 승인으로
 * 4건이 되면 id가 달라져 링크가 아니라 일회용 좌표가 된다.
 */
function slugify(label: string): string {
  return label
    .toLowerCase()
    .replace(/[0-9]+/g, "")
    .replace(/[^0-9a-z가-힣]+/gi, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * 한 줄에 늘어놓을 짧은 라벨.
 *
 * 카드 제목은 "경영 수행 성과 — 속도 · 정확성 · 실행력"처럼 뒤에 부연이 붙는다.
 * 그 부연은 카드에 가면 바로 보이므로 탭에서는 앞머리만 쓴다. 건수도 뗀다 —
 * 값이 바뀔 때마다 탭 폭이 흔들린다.
 */
function shortLabel(label: string): string {
  const head = label.split(/\s[—–]\s/)[0];
  return head.replace(/\s\d+건$/, "").trim() || label;
}

function collect(): IndexItem[] {
  const main = document.querySelector("main");
  if (!main) return [];

  const items: IndexItem[] = [];
  const used = new Set<string>();

  const push = (el: Element, label: string) => {
    const base = slugify(label) || "section";
    let id = base;
    for (let n = 2; used.has(id); n += 1) id = `${base}-${n}`;
    used.add(id);
    if (el.id !== id) el.id = id;
    // scroll-margin-top을 globals.css가 이 속성으로 건다. React가 관리하지 않는
    // 속성이라 재렌더에 지워지지 않는다(style을 직접 쓰면 덮일 수 있다).
    el.setAttribute("data-index-target", "");
    items.push({ id, label });
  };

  const h1 = main.querySelector("h1");
  // 화면 이름은 GNB가 이미 말하고 있다. 여기서는 "맨 위로"의 뜻만 있으면 된다.
  if (h1) push(h1.closest("header") ?? h1, "맨 위");

  // h2는 카드가 아닌 섹션(예: 사업부 듀얼 매트릭스), card-title은 카드 섹션.
  const headings = main.querySelectorAll<HTMLElement>('h2, [data-slot="card-title"]');
  for (const heading of headings) {
    if (heading.closest("[data-index-skip]")) continue;
    const target = heading.closest('[data-slot="card"], section') ?? heading;
    const label = (heading.textContent ?? "").trim().replace(/\s+/g, " ");
    if (!label) continue;
    push(target, shortLabel(label));
  }

  return items;
}

/** 같은 목록이면 상태를 갈지 않는다 — MutationObserver가 자주 울리므로 리렌더가 샌다. */
function same(a: IndexItem[], b: IndexItem[]): boolean {
  return (
    a.length === b.length && a.every((x, i) => x.id === b[i].id && x.label === b[i].label)
  );
}

export function SectionNav() {
  const pathname = usePathname();
  const [items, setItems] = useState<IndexItem[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const itemsRef = useRef<IndexItem[]>([]);

  // 목차 수집. setState는 전부 타이머·Observer 콜백 안에서 일어난다 — effect 본문에서
  // 상태를 바꾸면 react-hooks/set-state-in-effect에 걸린다(CLAUDE.md 4.1과 같은 제약).
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;

    const rescan = () => {
      clearTimeout(timer);
      // requestAnimationFrame을 쓰면 안 된다 — 탭이 보이지 않는 동안 콜백이 아예
      // 발화하지 않아 목차가 영영 비어 있다(CLAUDE.md의 React Flow 함정과 같은 원인).
      timer = setTimeout(() => {
        const next = collect();
        if (same(itemsRef.current, next)) return;
        itemsRef.current = next;
        setItems(next);
      }, 50);
    };

    rescan();
    // 엔진 스냅샷·승인·해설 토글로 섹션이 생기고 사라진다. 목차가 그것을 따라가야 한다.
    const observer = new MutationObserver(rescan);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      clearTimeout(timer);
      observer.disconnect();
    };
  }, [pathname]);

  // 스크롤 위치로 현재 섹션을 정한다. IntersectionObserver보다 규칙이 단순하다 —
  // "헤더 아래로 지나간 것 중 마지막"이고, 바닥에 닿으면 마지막 항목이다.
  useEffect(() => {
    let queued = false;

    const compute = () => {
      queued = false;
      const list = itemsRef.current;
      if (list.length === 0) return;

      // 바닥에서는 마지막 섹션이 화면 위쪽까지 올라오지 못한다 — 아래 규칙만으로는
      // 끝까지 내려도 중간 항목이 켜진 채로 남는다.
      if (window.innerHeight + window.scrollY >= document.body.scrollHeight - 4) {
        setActiveId(list[list.length - 1].id);
        return;
      }

      const limit = headerOffset() + 8;
      let current = list[0].id;
      for (const item of list) {
        const el = document.getElementById(item.id);
        if (!el) continue;
        if (el.getBoundingClientRect().top <= limit) current = item.id;
        else break;
      }
      setActiveId(current);
    };

    const update = () => {
      if (queued) return;
      queued = true;
      setTimeout(compute, 100);
    };

    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update, { passive: true });
    return () => {
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, [items]);

  const jump = useCallback((event: React.MouseEvent<HTMLAnchorElement>, id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    event.preventDefault();
    window.scrollTo({
      top: window.scrollY + el.getBoundingClientRect().top - headerOffset(),
      behavior: "smooth",
    });
    // 스크롤을 직접 하므로 hash는 기록만 한다 — pushState면 뒤로가기가 목차 이동으로 찬다.
    history.replaceState(null, "", `#${id}`);
  }, []);

  if (items.length < 2) return null;

  return (
    <nav
      aria-label="이 화면의 섹션"
      className="border-t border-foreground/5 bg-background/60"
    >
      <ul className="mx-auto flex w-full max-w-7xl items-center gap-1 overflow-x-auto px-4 sm:px-6 lg:px-8">
        {items.map((item) => {
          const active = item.id === activeId;
          return (
            <li key={item.id} className="shrink-0">
              <a
                href={`#${item.id}`}
                onClick={(event) => jump(event, item.id)}
                aria-current={active ? "location" : undefined}
                className={
                  active
                    ? "-mb-px inline-block border-b-2 border-foreground px-1.5 py-1.5 text-[11px] font-medium text-foreground"
                    : "-mb-px inline-block border-b-2 border-transparent px-1.5 py-1.5 text-[11px] text-muted-foreground hover:text-foreground"
                }
              >
                {item.label}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
