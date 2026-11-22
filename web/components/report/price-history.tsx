"use client";

import { useEffect, useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { EmptyState } from "@/components/states";
import type { ProjectNearby, Sale, TrendPoint } from "@/lib/api";
import { clean, inr } from "@/lib/format";
import { cssVar, useTheme } from "@/lib/theme";

/** Token colours for Recharts (SVG attributes need concrete values), re-read on theme flips. */
export function useChartColours() {
  const { theme } = useTheme();
  const [c, setC] = useState({ primary: "", accent: "", border: "", muted: "", surface: "", text: "", up: "", down: "" });
  useEffect(() => {
    setC({
      primary: cssVar("--primary"),
      accent: cssVar("--accent"),
      border: cssVar("--border"),
      muted: cssVar("--muted"),
      surface: cssVar("--surface"),
      text: cssVar("--text"),
      up: cssVar("--up"),
      down: cssVar("--down"),
    });
  }, [theme]);
  return c;
}

const kfmt = (v: number) => (v >= 1000 ? `${Math.round(v / 100) / 10}k` : String(Math.round(v)));
const yearFrac = (iso: string) => {
  const [y, m, d] = iso.split("-").map(Number);
  return y + (m - 1) / 12 + (d - 1) / 365;
};

/** Price history (Report mockup): village median line in sage, project announcement dashed walnut, sales as open circles. */
export function PriceHistory({
  series,
  sales,
  project,
}: {
  series: TrendPoint[];
  sales: Sale[];
  project: ProjectNearby | null;
}) {
  const c = useChartColours();
  if (series.length === 0 && sales.length === 0) {
    return (
      <EmptyState
        title="No sales recorded here yet"
        hint="Neither this village nor this parcel has a registered sale for this land type."
        className="py-6"
      />
    );
  }
  const line = series.map((p) => ({ x: p.yr + 0.5, median: p.median_price_sqm, n: p.n_sales }));
  const dots = sales.map((s) => ({ x: yearFrac(s.registered_on), sale: s.price_sqm, date: s.registered_on }));
  const ann = project?.announced_on ? yearFrac(project.announced_on) : null;
  const xs = [...line.map((p) => p.x), ...dots.map((p) => p.x), ...(ann ? [ann] : [])];
  const x0 = Math.floor(Math.min(...xs));
  const x1 = Math.ceil(Math.max(...xs));
  const ticks = Array.from({ length: x1 - x0 + 1 }, (_, i) => x0 + i).filter((_, i, a) => a.length <= 8 || i % 2 === 0 || i === a.length - 1);
  if (!c.primary) return <div className="h-[240px]" />;

  return (
    <div className="mt-3 h-[260px]" role="img" aria-label="Village median price per sq m by year, with this parcel's sales">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart margin={{ top: 16, right: 12, bottom: 4, left: 4 }}>
          <CartesianGrid vertical={false} stroke={c.border} />
          <XAxis
            type="number"
            dataKey="x"
            domain={[x0, x1]}
            ticks={ticks}
            tickFormatter={(v: number) => String(Math.floor(v))}
            tick={{ fill: c.muted, fontSize: 11, fontFamily: "var(--font-plex-mono)" }}
            axisLine={{ stroke: c.border }}
            tickLine={false}
            allowDuplicatedCategory={false}
          />
          <YAxis
            type="number"
            tickFormatter={kfmt}
            tick={{ fill: c.muted, fontSize: 11, fontFamily: "var(--font-plex-mono)" }}
            axisLine={false}
            tickLine={false}
            width={44}
            domain={[0, "auto"]}
          />
          <Tooltip
            cursor={{ stroke: c.border }}
            contentStyle={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 8, fontSize: 13, color: c.text }}
            labelFormatter={(v) => String(Math.floor(Number(v)))}
            formatter={(value, name) => [inr(Number(value)), name === "median" ? "Village median" : "This parcel's sale"]}
          />
          {ann && (
            <ReferenceLine
              x={ann}
              stroke={c.accent}
              strokeDasharray="4 4"
              label={{
                value: `${clean(project!.name)} announced`,
                position: "insideTopLeft",
                fill: c.accent,
                fontSize: 12,
                fontFamily: "var(--font-schibsted)",
              }}
            />
          )}
          <Line data={line} dataKey="median" stroke={c.primary} strokeWidth={2.5} dot={false} isAnimationActive={false} name="median" />
          <Scatter
            data={dots}
            dataKey="sale"
            fill={c.surface}
            stroke={c.accent}
            strokeWidth={2}
            shape="circle"
            isAnimationActive={false}
            name="sale"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
