"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Logo } from "@/components/logo";
import { SearchBox } from "@/components/search-box";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/lib/queries";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/map", label: "Map" },
  { href: "/trends", label: "Trends" },
  { href: "/pricing", label: "Pricing" },
];

/**
 * Header on every page (web/DESIGN.md): logo, nav with the active item in sage, the search box on the map page,
 * the credit balance in mono, the theme toggle, and sign in or the page's call to action.
 * `wide` = full-width map layout; otherwise the 1240px column. `landing` = the landing variant (larger logo,
 * Screener link, primary "Open the map").
 */
export function Header({ wide = false, search = false, landing = false }: { wide?: boolean; search?: boolean; landing?: boolean }) {
  const path = usePathname();
  const me = useMe();
  const user = me.data;
  const nav = landing ? [NAV[0], { href: "/map#screener", label: "Screener" }, NAV[1], { href: "#pricing", label: "Pricing" }] : NAV;
  const next = encodeURIComponent(path || "/");

  return (
    <header className="no-print border-b border-border bg-surface">
      <div
        className={cn(
          "flex flex-wrap items-center gap-6",
          wide ? "px-6 py-3" : "mx-auto max-w-page px-8",
          !wide && (landing ? "py-3.5" : "py-3"),
        )}
      >
        <Logo large={landing} />
        {search && <SearchBox />}
        <nav aria-label="Main" className={cn("flex flex-wrap text-[15px]", landing ? "gap-5" : "gap-[18px]")}>
          {nav.map((n) => {
            const active = !landing && path?.startsWith(n.href);
            return (
              <Link
                key={n.label}
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={cn("no-underline", active ? "font-medium text-primary hover:text-primary" : "text-text hover:text-accent")}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          {me.isPending ? (
            <Skeleton className="h-4 w-20" />
          ) : user ? (
            <>
              <Link
                href="/account"
                className="num text-[13px] text-muted no-underline hover:text-accent"
                title={`${user.email}: account and ledger`}
                data-testid="credit-balance"
              >
                {user.credit_balance} {user.credit_balance === 1 ? "credit" : "credits"}
              </Link>
              <ThemeToggle large={landing} />
              <Link
                href="/account"
                className={cn("text-[15px] no-underline", path === "/account" ? "font-medium text-primary" : "text-text hover:text-accent")}
              >
                Account
              </Link>
            </>
          ) : (
            <>
              <ThemeToggle large={landing} />
              <Link href={`/login?next=${next}`} className="text-[15px] text-text no-underline hover:text-accent">
                Sign in
              </Link>
              {landing ? (
                <Button asChild variant="primary">
                  <Link href="/map">Open the map</Link>
                </Button>
              ) : (
                path !== "/signup" && (
                  <Button asChild variant="outline">
                    <Link href={`/signup?next=${next}`}>Sign up</Link>
                  </Button>
                )
              )}
            </>
          )}
        </div>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="no-print border-t border-border">
      <div className="mx-auto flex max-w-page flex-wrap justify-between gap-4 px-8 py-6 text-[13px] text-muted">
        <span>LandLens · Kakatiya (Warangal) Development Area</span>
        <span>Not legal or financial advice. This demo uses synthetic parcel and price data.</span>
      </div>
    </footer>
  );
}
