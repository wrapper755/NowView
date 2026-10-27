import { Clock } from "lucide-react";

/**
 * 데모 플레이어의 단계 설명. 각본 글은 「시점. 문장. 문장 — 부연.」 꼴의 한 문단이라 오른쪽 단(xl)에서 통으로 보이면
 * 읽히지 않았다 — 시점은 칩으로, 문장은 하나씩 점 목록으로, 「 — 」 뒤의 부연은 작은 글로 나눠 보인다. 글은 고치지 않고
 * 모양만 나눈다(각본의 원문이 한 곳에 남는다). 좁은 하단 바에서는 예전처럼 한두 줄로 접는다.
 */
export function Narration({ text }: { text: string }) {
  const { when, points } = splitNarration(text);
  return (
    <>
      <p className="line-clamp-1 text-xs leading-relaxed text-muted-foreground sm:line-clamp-2 xl:hidden">{text}</p>
      <div className="mt-2 hidden space-y-2 xl:block">
        {when ? (
          <p className="inline-flex items-center gap-1 rounded bg-brand-soft px-1.5 py-0.5 text-[11px] font-medium text-brand">
            <Clock aria-hidden className="size-3" />
            {when}
          </p>
        ) : null}
        <ul className="space-y-1.5">
          {points.map((p, i) => (
            <li key={i} className="flex gap-2 text-[13px] leading-snug text-foreground/90">
              <span aria-hidden className="mt-[0.45rem] size-1.5 shrink-0 rounded-full bg-brand" />
              <span>
                {p.head}
                {p.tail ? <span className="mt-0.5 block text-xs leading-snug text-muted-foreground">{p.tail}</span> : null}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}

/** 맨 앞의 짧은 시점 조각(「6/17 아침.」·「7/1 08:59.」 — 「…다」로 끝나지 않는다)과 「…다.」 문장들로 나눈다. */
export function splitNarration(text: string): { when: string | null; points: Array<{ head: string; tail: string | null }> } {
  let rest = text.trim();
  let when: string | null = null;
  const lead = /^([^.]{1,30})\.\s+/.exec(rest);
  if (lead && !lead[1].trim().endsWith("다")) {
    when = lead[1].trim();
    rest = rest.slice(lead[0].length);
  }
  const sentences = rest
    .split(/(?<=다\.)\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const points = sentences.map((s) => {
    const at = s.indexOf(" — ");
    return at > 0 ? { head: s.slice(0, at), tail: s.slice(at + 3) } : { head: s, tail: null };
  });
  return { when, points };
}
