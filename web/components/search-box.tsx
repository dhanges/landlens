"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { area, clean, LAND_TYPE_LABEL, survey } from "@/lib/format";
import { useSearch } from "@/lib/queries";
import { cn } from "@/lib/utils";

type Option =
  | { kind: "village"; id: number; label: string; sub: string; lat: number; lon: number }
  | { kind: "parcel"; id: number; label: string; sub: string; lat: number; lon: number };

/**
 * Header search (FR-2): fuzzy village names (Hanmakonda finds Hanamkonda) and survey numbers. Picking a result
 * moves the map through the URL (/map?village=ID or ?parcel=ID with lat/lon), which the map page reacts to.
 */
export function SearchBox() {
  const router = useRouter();
  const id = useId();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 200);
    return () => clearTimeout(t);
  }, [q]);

  const res = useSearch(debounced);
  const options: Option[] = [
    ...(res.data?.villages ?? []).map((v) => ({
      kind: "village" as const,
      id: v.village_id,
      label: clean(v.name),
      sub: `Village · ${v.mandal}`,
      lat: v.lat,
      lon: v.lon,
    })),
    ...(res.data?.parcels ?? []).map((p) => ({
      kind: "parcel" as const,
      id: p.parcel_id,
      label: `Survey ${survey(p)}, ${clean(p.village)}`,
      sub: `${LAND_TYPE_LABEL[p.land_type]} · ${area(p.area_sqm)}`,
      lat: p.lat,
      lon: p.lon,
    })),
  ];

  useEffect(() => setActive(0), [debounced]);
  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  function pick(o: Option) {
    setOpen(false);
    setQ(o.label);
    const p = new URLSearchParams({ lat: String(o.lat), lon: String(o.lon), [o.kind]: String(o.id) });
    router.push(`/map?${p.toString()}`);
  }

  const showList = open && debounced.length >= 2;
  return (
    <div ref={box} className="relative max-w-[420px] flex-[1_1_280px]">
      <label className="flex h-10 items-center gap-2 rounded-lg border border-border bg-bg px-3 focus-within:border-primary">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-muted" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="M20 20l-3.5-3.5" />
        </svg>
        <span className="sr-only-label">Search</span>
        <input
          role="combobox"
          aria-expanded={showList}
          aria-controls={`${id}-list`}
          aria-activedescendant={showList && options[active] ? `${id}-${active}` : undefined}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, options.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === "Enter" && options[active]) {
              e.preventDefault();
              pick(options[active]);
            } else if (e.key === "Escape") setOpen(false);
          }}
          placeholder="Village or survey number, e.g. Hanamkonda"
          className="min-w-0 flex-1 border-0 bg-transparent text-[15px] text-text outline-none placeholder:text-muted"
        />
      </label>
      {showList && (
        <ul
          id={`${id}-list`}
          role="listbox"
          className="tile absolute left-0 right-0 top-[44px] z-40 max-h-80 overflow-auto py-1 text-[14px]"
        >
          {res.isError ? (
            <li className="px-3 py-2 text-muted">Search is unavailable right now. Try again in a moment.</li>
          ) : res.isPending || (res.isFetching && options.length === 0) ? (
            <li className="px-3 py-2 text-muted">Searching…</li>
          ) : options.length === 0 ? (
            <li className="px-3 py-2 text-muted">No village or survey number matches “{debounced}”.</li>
          ) : (
            options.map((o, i) => (
              <li
                key={`${o.kind}-${o.id}`}
                id={`${id}-${i}`}
                role="option"
                aria-selected={i === active}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => {
                  e.preventDefault();
                  pick(o);
                }}
                className={cn("cursor-pointer px-3 py-2", i === active && "bg-tint text-tint-text")}
              >
                <div className="font-medium">{o.label}</div>
                <div className={cn("text-[12px]", i === active ? "text-tint-text" : "text-muted")}>{o.sub}</div>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
