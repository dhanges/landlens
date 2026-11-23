"use client";

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment, useState } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import * as api from "@/lib/api";
import { useMe } from "@/lib/queries";
import { cn } from "@/lib/utils";

type Turn = { q: string; res?: api.ChatResponse; err?: api.ApiError };

const pages = (c: api.ChatCitation) => (c.page_start === c.page_end ? `p. ${c.page_start}` : `pp. ${c.page_start}–${c.page_end}`);

/** "[2]" in the answer becomes a walnut mono link to that citation's page in the PDF. */
function AnswerText({ text, citations }: { text: string; citations: api.ChatCitation[] }) {
  const byN = new Map(citations.map((c) => [c.n, c]));
  const parts = text.split(/(\[\d{1,2}\])/g);
  return (
    <p className="whitespace-pre-line">
      {parts.map((p, i) => {
        const m = /^\[(\d{1,2})\]$/.exec(p);
        const c = m ? byN.get(Number(m[1])) : undefined;
        return c ? (
          <a
            key={i}
            href={api.documentUrl(c.document_id, c.page_start)}
            target="_blank"
            rel="noreferrer"
            title={`${c.title}, ${pages(c)}`}
            className="num text-[0.92em] no-underline"
          >
            [{c.n}]
          </a>
        ) : (
          <Fragment key={i}>{p}</Fragment>
        );
      })}
    </p>
  );
}

function Citations({ citations }: { citations: api.ChatCitation[] }) {
  return (
    <ol className="mt-3 flex flex-col gap-2" data-testid="citations">
      {citations.map((c) => (
        <li key={c.n} className="text-[13px]">
          <a
            href={api.documentUrl(c.document_id, c.page_start)}
            target="_blank"
            rel="noreferrer"
            className="num no-underline"
            data-testid="citation-link"
          >
            [{c.n}] {c.title}, {pages(c)}
          </a>
          <div className="mt-0.5 text-muted">“{c.snippet}”</div>
        </li>
      ))}
    </ol>
  );
}

function Reply({ t }: { t: Turn }) {
  if (t.err) {
    const e = t.err;
    return (
      <p role="alert" className="text-[14px] text-down">
        {e.code === "rate_limited"
          ? `Too many questions in a minute. Try again in ${e.retryAfter ?? 60} s.`
          : e.code === "auth_required"
            ? "Your session ended. Sign in again to ask."
            : e.message}
      </p>
    );
  }
  if (!t.res)
    return (
      <div className="flex flex-col gap-2" aria-busy="true" aria-label="Searching the documents">
        <Skeleton className="h-4 w-11/12" />
        <Skeleton className="h-4 w-9/12" />
        <Skeleton className="h-4 w-10/12" />
      </div>
    );
  const r = t.res;
  return (
    <div className="text-[14px]" data-testid="chat-reply">
      {r.degraded && (
        <span className="mb-2 inline-block rounded-md border border-border px-2 py-0.5 text-[12px] text-muted">
          Keyword search only
        </span>
      )}
      {!r.found ? (
        <p>
          <span className="font-medium">Not found in the documents.</span>{" "}
          <span className="text-muted">
            {r.note ?? "The loaded documents do not cover this. Try other words, or check with KUDA directly."}
          </span>
        </p>
      ) : (
        <>
          {r.answer ? <AnswerText text={r.answer} citations={r.citations} /> : r.note && <p className="text-muted">{r.note}</p>}
          <Citations citations={r.citations} />
        </>
      )}
    </div>
  );
}

/**
 * Document Q&A (J3, FR-8): answers only from the ingested documents, with numbered citations that open the
 * PDF at the page. `parcelId` sends the parcel's zone and land type as context. Compact = the report card.
 */
export function ChatPanel({ parcelId, compact = false, placeholder }: { parcelId?: number; compact?: boolean; placeholder?: string }) {
  const me = useMe();
  const path = usePathname();
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const ask = useMutation({
    mutationFn: (question: string) => api.chat(question, parcelId),
    onMutate: (question) => setTurns((ts) => [...ts, { q: question }]),
    onSuccess: (res) => setTurns((ts) => ts.map((t, i) => (i === ts.length - 1 ? { ...t, res } : t))),
    onError: (err) =>
      setTurns((ts) => ts.map((t, i) => (i === ts.length - 1 ? { ...t, err: err as api.ApiError } : t))),
  });
  const submit = () => {
    const question = q.trim();
    if (question.length < 3 || ask.isPending) return;
    setQ("");
    ask.mutate(question);
  };
  const shown = compact ? turns.slice(-2) : turns;

  return (
    <div className="flex flex-col gap-3">
      {shown.length === 0 && compact && (
        <>
          <div className="rounded-lg bg-bg px-3 py-2.5 text-[14px] text-muted">Can I build a warehouse on this parcel?</div>
          <p className="text-[14px]">
            Answers appear here with numbered citations, such as <span className="num text-accent">[1] Act, p. 12</span>, each
            opening the document at that page.
          </p>
        </>
      )}
      {shown.map((t, i) => (
        <div key={i} className="flex flex-col gap-2.5">
          <div className="self-end rounded-lg bg-bg px-3 py-2.5 text-[14px]">{t.q}</div>
          <Reply t={t} />
        </div>
      ))}
      {me.isPending ? null : !me.data ? (
        <p className="text-[14px] text-muted">
          <Link href={`/login?next=${encodeURIComponent(path || "/chat")}`}>Sign in</Link> to ask the documents. It is free.
        </p>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
          className={cn("flex items-center gap-2 rounded-lg border border-border py-1.5 pl-3 pr-1.5 focus-within:border-primary", compact ? "" : "bg-surface")}
        >
          <label htmlFor={compact ? "ask-card" : "ask-page"} className="sr-only-label">
            Question
          </label>
          <input
            id={compact ? "ask-card" : "ask-page"}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            maxLength={500}
            placeholder={placeholder ?? "What setbacks apply to a residential plot?"}
            className="min-w-0 flex-1 border-0 bg-transparent text-[14px] text-text outline-none placeholder:text-muted"
            data-testid="ask-input"
          />
          <Button type="submit" variant="primary" size="sm" disabled={ask.isPending || q.trim().length < 3} data-testid="ask-button">
            {ask.isPending ? "Asking…" : "Ask"}
          </Button>
        </form>
      )}
    </div>
  );
}
