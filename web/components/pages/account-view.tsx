"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { EmptyState, ErrorState, SkeletonRows } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { dateTime, int } from "@/lib/format";
import { useLedger, useLogout, useMe } from "@/lib/queries";
import { cn } from "@/lib/utils";

const REASON: Record<string, string> = {
  signup_bonus: "Signup bonus",
  top_up: "Credit pack (mock payment)",
  report_unlock: "Report unlocked",
  refund: "Refund",
};

/** Account (J5 step 2, FR-10): balance and the credit ledger, newest first, keyset "Load more". */
export function AccountView() {
  const router = useRouter();
  const me = useMe();
  const ledger = useLedger(!!me.data);
  const logout = useLogout();

  if (me.isPending)
    return (
      <div className="mx-auto max-w-page px-8 py-14">
        <Skeleton className="mb-6 h-12 w-64" />
        <SkeletonRows rows={6} className="card" />
      </div>
    );
  if (me.isError) return <ErrorState error={me.error} title="Your account could not load" onRetry={() => me.refetch()} className="py-24" />;
  if (!me.data)
    return (
      <EmptyState
        title="Sign in to see your account"
        hint="Your credit balance, unlocked reports and ledger live here."
        action={
          <Button asChild variant="primary">
            <Link href="/login?next=/account">Sign in</Link>
          </Button>
        }
        className="py-24"
      />
    );

  const u = me.data;
  const items = ledger.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className="mx-auto max-w-page px-8 pb-14 pt-10">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[44px] leading-tight tracking-display">Account</h1>
          <p className="text-muted">{u.email}</p>
        </div>
        <Button variant="outline" onClick={() => logout.mutate(undefined, { onSettled: () => router.push("/") })} disabled={logout.isPending}>
          {logout.isPending ? "Signing out…" : "Sign out"}
        </Button>
      </div>

      <div className="mb-8 grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
        <div className="tile p-4">
          <div className="text-[13px] text-muted">Credit balance</div>
          <div className="num text-[28px] font-medium" data-testid="account-balance">
            {u.credit_balance}
          </div>
          <div className="text-[13px] text-muted">1 credit unlocks one parcel report</div>
        </div>
        <div className="tile flex flex-col justify-between gap-3 p-4">
          <div className="text-[13px] text-muted">Need more?</div>
          <Button asChild variant="primary">
            <Link href="/pricing">Buy credits</Link>
          </Button>
        </div>
      </div>

      <h2 className="mb-3 text-[26px]">Ledger</h2>
      <div className="tile overflow-x-auto">
        {ledger.isPending ? (
          <SkeletonRows rows={5} />
        ) : ledger.isError ? (
          <ErrorState error={ledger.error} title="The ledger could not load" onRetry={() => ledger.refetch()} />
        ) : items.length === 0 ? (
          <EmptyState title="No entries yet" hint="Your signup bonus, packs and unlocks will appear here." />
        ) : (
          <table className="w-full min-w-[560px] border-collapse text-[14px]" data-testid="ledger">
            <thead>
              <tr className="text-left text-[12px] text-muted">
                <th className="border-b border-border px-[14px] py-2.5 font-medium">When</th>
                <th className="border-b border-border px-[14px] py-2.5 font-medium">What</th>
                <th className="border-b border-border px-[14px] py-2.5 font-medium">Parcel</th>
                <th className="border-b border-border px-[14px] py-2.5 text-right font-medium">Credits</th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.entry_id}>
                  <td className="num border-b border-border px-[14px] py-2.5 text-muted">{dateTime(e.created_at)}</td>
                  <td className="border-b border-border px-[14px] py-2.5">{REASON[e.reason] ?? e.reason}</td>
                  <td className="border-b border-border px-[14px] py-2.5">
                    {e.parcel_id ? <Link href={`/parcels/${e.parcel_id}`}>Parcel {e.parcel_id}</Link> : <span className="text-muted">{"—"}</span>}
                  </td>
                  <td className={cn("num border-b border-border px-[14px] py-2.5 text-right", e.delta > 0 ? "text-up" : "text-down")}>
                    {e.delta > 0 ? `+${int(e.delta)}` : int(e.delta)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {ledger.hasNextPage && (
        <div className="mt-4 text-center">
          <Button variant="outline" onClick={() => ledger.fetchNextPage()} disabled={ledger.isFetchingNextPage}>
            {ledger.isFetchingNextPage ? "Loading…" : "Load more"}
          </Button>
        </div>
      )}
    </div>
  );
}
