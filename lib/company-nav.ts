"use client";

import { useParams, usePathname, useRouter } from "next/navigation";
import { useMemo } from "react";

import { companyPath } from "@/lib/companies";

/**
 * 회사 안 화면의 길찾기. 장면 화면·플레이어는 회사를 모른 채 `/sc02/request`처럼 **장면 경로**로 말하고, 여기서 실제 주소
 * `/c/{회사}/sc02/request`로 바꾼다 — 회사가 늘어도 장면 코드가 회사를 들고 다니지 않는다. `next/navigation`의
 * `usePathname`·`useRouter`와 같은 모양이라 장면 코드는 import만 바꾼다.
 */

export function useCompanyId(): string {
  const params = useParams<{ company?: string }>();
  return params?.company ?? "";
}

/** 지금 주소에서 회사를 뗀 장면 경로 — 회사 첫 화면(`/c/{회사}`)은 `/`다. */
export function useScenePath(): string {
  const pathname = usePathname();
  const company = useCompanyId();
  const prefix = `/c/${company}`;
  if (!company || !pathname.startsWith(prefix)) return pathname;
  return pathname.slice(prefix.length) || "/";
}

/** 장면 경로를 받는 라우터 — `/`로 시작하는 경로에 회사를 붙인다. */
export function useCompanyRouter() {
  const router = useRouter();
  const company = useCompanyId();
  return useMemo(() => {
    const to = (href: string) => (company && href.startsWith("/") ? companyPath(company, href) : href);
    return {
      ...router,
      push: (href: string, options?: Parameters<typeof router.push>[1]) => router.push(to(href), options),
      replace: (href: string, options?: Parameters<typeof router.replace>[1]) => router.replace(to(href), options),
      prefetch: (href: string) => router.prefetch(to(href)),
    };
  }, [router, company]);
}
