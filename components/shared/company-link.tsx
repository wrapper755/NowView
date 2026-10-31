"use client";

import Link from "next/link";
import type { ComponentProps } from "react";

import { companyPath } from "@/lib/companies";
import { useCompanyId } from "@/lib/company-nav";

/** 장면 경로(`/sc01/plans`)를 받는 링크 — 지금 회사의 실제 주소(`/c/{회사}/sc01/plans`)로 간다(`lib/company-nav.ts`). */
export function CompanyLink({ href, ...rest }: ComponentProps<typeof Link>) {
  const company = useCompanyId();
  const target = company && typeof href === "string" && href.startsWith("/") ? companyPath(company, href) : href;
  return <Link href={target} {...rest} />;
}
