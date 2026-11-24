import Link from "next/link";

import { Footer, Header } from "@/components/header";
import { PACKS, PriceCard, rupees } from "@/components/pages/pricing-cards";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";

const FEATURES = [
  ["Screener", "Filter parcels by zone, distance to new projects, price against the village median and growth. Like a stock screener, for land."],
  ["Parcel report", "A fair value range from comparable sales, with every driver spelled out, so you walk into the negotiation with numbers."],
  ["Ask the master plan", "Ask what you can build and get the answer with the exact clause and page from the government documents."],
  ["Locality trends", "Village price history, year on year, and the gap between guideline rates and what land actually sells for."],
];

function Metric({ label, value, sub, className }: { label: string; value: string; sub: string; className?: string }) {
  return (
    <div className="rounded-lg bg-bg px-[14px] py-3">
      <div className="text-[12px] text-muted">{label}</div>
      <div className={className ?? "num text-[17px] font-medium"}>{value}</div>
      <div className="text-[12px] text-muted">{sub}</div>
    </div>
  );
}

/** Landing (Main mockup, FR-11). */
export default function Home() {
  return (
    <div className="flex min-h-screen flex-col text-base">
      <Header landing />
      <main className="flex-1">
        <section className="mx-auto flex max-w-page flex-wrap items-center gap-14 px-8 pb-14 pt-[72px]">
          <div className="min-w-0 flex-[999_1_520px]">
            <p className="mb-4 text-[13px] uppercase tracking-[0.08em] text-accent">Land research for the Warangal region</p>
            <h1 className="mb-5 text-[56px] leading-[1.05] tracking-hero">Know what a parcel is worth before you negotiate.</h1>
            <p className="mb-8 max-w-[560px] text-[19px] text-muted">
              Zoning, development plans, soil and water, and price history for every parcel in the KUDA area. Independent
              research, not listings, so nobody is selling you anything.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button asChild variant="primary" size="lg">
                <Link href="/map">Screen parcels on the map</Link>
              </Button>
              <Button asChild variant="outline" size="lg">
                <Link href="/parcels/1">See a sample report</Link>
              </Button>
            </div>
          </div>
          <div className="card min-w-0 flex-[1_1_380px] p-6">
            <div className="mb-1 flex items-baseline justify-between gap-2">
              <span className="font-serif text-[22px] font-medium">Survey 214/3, Mamnoor</span>
              <Chip tone="tint" className="px-2 text-[12px]">Peri-urban</Chip>
            </div>
            <p className="mb-[18px] text-[14px] text-muted">1,850 sq m · 1.2 km from the airport site</p>
            <div className="grid grid-cols-2 gap-3">
              <Metric label="Fair value range" value={"₹16,900–19,800"} sub="per sq m" className="num whitespace-nowrap text-[17px] font-medium" />
              <Metric label="5-year growth" value="+12.4% a year" sub="village median" className="num text-[17px] font-medium text-up" />
              <Metric label="Master plan zone" value="Residential" sub="KUDA 2041" className="text-base font-medium" />
              <Metric label="Groundwater" value="Semi-critical" sub="mandal level" className="text-base font-medium" />
            </div>
            <p className="mt-4 text-[12px] text-muted">Sample data, not a real parcel</p>
          </div>
        </section>

        <section className="border-y border-border bg-surface">
          <div className="mx-auto grid max-w-page grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-8 px-8 py-14">
            {FEATURES.map(([h, p]) => (
              <div key={h}>
                <h3 className="mb-2 text-[22px]">{h}</h3>
                <p className="text-muted">{p}</p>
              </div>
            ))}
          </div>
        </section>

        <section id="pricing" className="mx-auto max-w-page px-8 py-16">
          <h2 className="mb-2 text-[36px]">Pay only when you&apos;re serious about a parcel</h2>
          <p className="mb-8 text-muted">
            Most people buy land once every few years. So there&apos;s no subscription: research for free, then unlock the
            reports you need.
          </p>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-5">
            <PriceCard title="Free" price={rupees(0)} blurb="Map, screener, locality trends, and a summary of any parcel." />
            {PACKS.slice(0, 2).map((p, i) => (
              <PriceCard key={p.pack} title={`${p.credits} report credits`} price={rupees(p.price)} blurb={p.blurb} highlight={i === 0} />
            ))}
          </div>
          <p className="mt-5 text-[14px]">
            <Link href="/pricing">All packs and the mock checkout</Link>
          </p>
        </section>
      </main>
      <Footer />
    </div>
  );
}
