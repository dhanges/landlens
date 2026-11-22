import Link from "next/link";

import { cn } from "@/lib/utils";

/** Sage magnifying glass with a rising trend line in the lens (web/DESIGN.md "Logo"). */
export function LogoMark({ size = 24, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      aria-hidden="true"
      className={cn("text-primary", className)}
    >
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="M15.5 15.5L21 21" />
      <path d="M7.5 12.5l2-2.5 1.5 1.5 2-3" />
    </svg>
  );
}

export function Logo({ large = false }: { large?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-2 text-text no-underline hover:text-text">
      <LogoMark size={large ? 26 : 24} />
      <span className={cn("font-serif font-medium tracking-[-0.01em]", large ? "text-[24px]" : "text-[22px]")}>
        LandLens
      </span>
    </Link>
  );
}
