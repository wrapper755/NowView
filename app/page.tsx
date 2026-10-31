import Link from "next/link";

import { BrandHero } from "@/components/shared/brand-hero";
import { TopBar } from "@/components/shared/top-bar";
import { WorkerBadge } from "@/components/shared/worker-status";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { COMPANIES, migrated } from "@/lib/companies";

/**
 * 회사 목록 — NowView가 운영 현황을 보여 주는 회사들. 회사마다 BPM 프로세스(장면)가 Center에 회사 이름으로 올라가 있고, NowView
 * 일꾼이 그 일감을 수행한다. 회사를 고르면 그 회사의 운영 현황(`/c/{회사}`)으로 간다.
 */
export default function CompaniesPage() {
  return (
    <>
      <TopBar />
      <BrandHero />
      <main className="mx-auto w-full max-w-5xl space-y-5 px-4 py-6 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xl font-semibold">회사</h2>
          <Link href="/worker">
            <WorkerBadge />
          </Link>
        </div>
        <ul className="grid gap-4 md:grid-cols-2">
          {COMPANIES.map((c) => {
            const done = c.scenes.filter(migrated).length;
            return (
              <li key={c.id}>
                <Link href={`/c/${c.id}`} className="block h-full">
                  <Card className="h-full transition-colors hover:border-brand/60">
                    <CardHeader>
                      <CardTitle>{c.name}</CardTitle>
                      <CardDescription>{c.description}</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-2 text-sm">
                      <p className="text-muted-foreground">
                        BPM 프로세스 {c.scenes.length}개 · 회사 이름으로 등록 {done}개
                      </p>
                      <ol className="flex flex-wrap gap-1.5">
                        {c.scenes.map((s) => (
                          <li key={s.no}>
                            <Badge variant={migrated(s) ? "default" : "outline"}>
                              {s.no}. {s.work}
                            </Badge>
                          </li>
                        ))}
                      </ol>
                    </CardContent>
                  </Card>
                </Link>
              </li>
            );
          })}
        </ul>
      </main>
    </>
  );
}
