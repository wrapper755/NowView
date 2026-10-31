/* eslint-disable @next/next/no-img-element -- 고정 크기 PNG 두 장을 테마로 바꿔 보일 뿐이다(최적화할 것이 없다). */

/**
 * 첫 화면 머리 — Chaeksas Center 로그인 상단과 같은 모양(INNONOW 로고 · 문구, Center ADR-0116).
 * 로고는 Center 콘솔 `public/brand/`에서 그대로 들여왔다. Center는 `prefers-color-scheme`로 고르지만 NowView는 테마가
 * `.dark` 클래스라(next-themes) 두 장을 모두 두고 `dark:` 변형으로 하나만 보인다 — 마크업이 양쪽 테마에서 같다.
 */
export function BrandHero() {
  return (
    <header className="border-b border-border bg-card">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 py-10 sm:px-6">
        <img
          src="/brand/logo-innonow-navy.png"
          alt="INNONOW"
          width={717}
          height={120}
          className="h-7 w-auto self-start dark:hidden"
        />
        <img
          src="/brand/logo-innonow-ivory.png"
          alt="INNONOW"
          width={717}
          height={120}
          className="hidden h-7 w-auto self-start dark:block"
        />
        <h1 className="text-[30px] leading-normal font-bold break-keep text-card-foreground">AI와 함께, 경영을 실행합니다.</h1>
        <p className="text-base text-muted-foreground">Management Transformation in Action.</p>
      </div>
    </header>
  );
}
