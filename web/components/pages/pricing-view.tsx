"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useRef } from "react";

import { PACKS, PriceCard, rupees } from "@/components/pages/pricing-cards";
import { Button } from "@/components/ui/button";
import * as api from "@/lib/api";
import { keys, useMe } from "@/lib/queries";

/** Pricing with the mock top-up (J5, DEC-004 OQ-23): no money moves; a ledger row and the balance change. */
export function PricingView() {
  const qc = useQueryClient();
  const me = useMe();
  const params = useSearchParams();
  const nextRaw = params.get("next");
  const next = nextRaw && nextRaw.startsWith("/") && !nextRaw.startsWith("//") ? nextRaw : null;
  const keyRef = useRef<{ pack: api.Pack; key: string } | null>(null);
  const buy = useMutation({
    mutationFn: (pack: api.Pack) => {
      if (keyRef.current?.pack !== pack) keyRef.current = { pack, key: api.newIdempotencyKey() };
      return api.topUp(pack, keyRef.current.key);
    },
    onSuccess: (res) => {
      keyRef.current = null;
      qc.setQueryData<api.User | null>(keys.me, (u) => (u ? { ...u, credit_balance: res.credit_balance } : u));
      qc.invalidateQueries({ queryKey: keys.ledger });
    },
    onError: (e) => {
      if (e instanceof api.ApiError && e.status !== 503 && e.status !== 0) keyRef.current = null;
    },
  });
  const signedIn = !!me.data;
  const login = `/login?next=${encodeURIComponent(`/pricing${next ? `?next=${encodeURIComponent(next)}` : ""}`)}`;

  return (
    <div className="mx-auto max-w-page px-8 py-14">
      <h1 className="mb-2 text-[44px] leading-tight tracking-display">Pricing</h1>
      <p className="mb-8 max-w-[640px] text-muted">
        Research is free. Each report credit unlocks one parcel report for good. This is a demo: checkout is a mock
        payment and no money moves.
      </p>

      {buy.isSuccess && (
        <div role="status" className="tile mb-6 flex flex-wrap items-center justify-between gap-3 px-5 py-4" data-testid="topup-ok">
          <span>
            Added <span className="num">{buy.data.credits_added}</span> credits. Your balance is{" "}
            <span className="num font-medium">{buy.data.credit_balance}</span>. <span className="text-muted">({buy.data.note})</span>
          </span>
          <span className="flex gap-4 text-[14px]">
            <Link href="/account">See the ledger</Link>
            {next && <Link href={next}>Back to the report</Link>}
          </span>
        </div>
      )}
      {buy.isError && (
        <p role="alert" className="mb-6 text-[14px] text-down">
          {(buy.error as api.ApiError).message} {(buy.error as api.ApiError).status === 503 ? "Try again: you will not be charged twice." : ""}
        </p>
      )}

      <div className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-5">
        <PriceCard title="Free" price={rupees(0)} blurb="Map, screener, locality trends, and a summary of any parcel.">
          <Button asChild variant="outline" className="w-full">
            <Link href="/map">Open the map</Link>
          </Button>
        </PriceCard>
        {PACKS.map((p, i) => (
          <PriceCard key={p.pack} title={`${p.credits} report credits`} price={rupees(p.price)} blurb={p.blurb} highlight={i === 0}>
            {signedIn ? (
              <Button
                variant={i === 0 ? "primary" : "outline"}
                className="w-full"
                disabled={buy.isPending}
                onClick={() => buy.mutate(p.pack)}
                data-testid={`buy-${p.pack}`}
              >
                {buy.isPending && buy.variables === p.pack ? "Processing…" : `Buy ${p.credits} credits (mock)`}
              </Button>
            ) : (
              <Button asChild variant={i === 0 ? "primary" : "outline"} className="w-full">
                <Link href={login}>Sign in to buy</Link>
              </Button>
            )}
          </PriceCard>
        ))}
      </div>
      <p className="mt-6 text-[13px] text-muted">
        {rupees(1999)} for 5 is {rupees(400)} a report; 20 brings it to {rupees(350)}, 50 to {rupees(300)}.

      </p>
    </div>
  );
}
