import { cn } from "@/lib/utils";

export const PACKS = [
  { pack: "5" as const, credits: 5, price: 1999, blurb: "Full parcel reports with valuation, comparables, zoning and environment. Credits never expire." },
  { pack: "20" as const, credits: 20, price: 6999, blurb: "For agents, NRIs comparing several parcels, and small developers." },
  { pack: "50" as const, credits: 50, price: 14999, blurb: "For brokers screening whole corridors." },
];
export const rupees = (n: number) => `₹${new Intl.NumberFormat("en-IN").format(n)}`;

/** Pricing card (Main mockup): the highlighted pack gets a 2px sage border. */
export function PriceCard({
  title,
  price,
  blurb,
  highlight = false,
  children,
}: {
  title: string;
  price: string;
  blurb: string;
  highlight?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className={cn("flex flex-col rounded-card bg-surface p-6 shadow-card", highlight ? "border-2 border-primary" : "border border-border")}>
      <div className="mb-1 font-medium">{title}</div>
      <div className="num mb-3 text-[28px]">{price}</div>
      <p className="text-[15px] text-muted">{blurb}</p>
      {children && <div className="mt-auto pt-5">{children}</div>}
    </div>
  );
}
