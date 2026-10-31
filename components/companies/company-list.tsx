"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { SCENES, useCompanies } from "@/lib/companies";

/** 회사 목록 — 엔진 설정의 공개 목록(이름·설명·업무). 회사는 설정이라 빌드 때 모른다. */
export function CompanyList() {
  const { companies, error } = useCompanies();
  if (error) return <p className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">{error}</p>;
  if (!companies) return <p className="text-sm text-muted-foreground">회사 목록을 읽는 중…</p>;
  if (companies.length === 0) return <p className="text-sm text-muted-foreground">등록된 회사가 없다.</p>;
  return (
    <ul className="grid gap-4 md:grid-cols-2">
      {companies.map((c) => (
        <li key={c.id}>
          <Link href={`/c/${c.id}`} className="block h-full">
            <Card className="h-full transition-colors hover:border-brand/60">
              <CardHeader>
                <CardTitle>{c.name}</CardTitle>
                <CardDescription>{c.description}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <p className="text-muted-foreground">업무 {c.scenes.length}개</p>
                <ol className="flex flex-wrap gap-1.5">
                  {SCENES.filter((s) => c.scenes.includes(s.no)).map((s) => (
                    <li key={s.no}>
                      <Badge variant="outline">
                        {s.no}. {s.work}
                      </Badge>
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          </Link>
        </li>
      ))}
    </ul>
  );
}

/** 회사 운영 현황 — 그 회사가 쓰는 업무. 업무를 고르면 그 화면으로 간다. 없는 회사면 그렇게 말한다(Q6). */
export function CompanyOverview({ companyId }: { companyId: string }) {
  const { companies, error } = useCompanies();
  if (error) return <p className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">{error}</p>;
  if (!companies) return <p className="text-sm text-muted-foreground">읽는 중…</p>;
  const company = companies.find((c) => c.id === companyId);
  if (!company) {
    return (
      <p className="text-sm">
        없는 회사다: <span className="font-mono">{companyId}</span> —{" "}
        <Link href="/" className="underline">
          회사 목록
        </Link>
      </p>
    );
  }
  return (
    <>
      <div>
        <h1 className="text-xl font-semibold">{company.name}</h1>
        <p className="text-sm text-muted-foreground">{company.description}</p>
      </div>
      <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {SCENES.filter((s) => company.scenes.includes(s.no)).map((s) => (
          <li key={s.no}>
            <Link href={`/c/${company.id}/sc0${s.no}`} className="block h-full">
              <Card className="h-full transition-colors hover:border-brand/60">
                <CardHeader>
                  <CardTitle>
                    {s.no}. {s.work}
                  </CardTitle>
                  <CardDescription>{s.detail}</CardDescription>
                </CardHeader>
              </Card>
            </Link>
          </li>
        ))}
      </ol>
    </>
  );
}
