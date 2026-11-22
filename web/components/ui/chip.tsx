import * as React from "react";

import { cn } from "@/lib/utils";

/** Small label: tint (land type), outline (facts), or muted outline ("Sample data", "Synthetic"). */
export function Chip({
  tone = "outline",
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: "tint" | "outline" | "muted" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center whitespace-nowrap rounded-md px-2.5 py-[3px] text-[13px] leading-snug",
        tone === "tint" && "bg-tint text-tint-text",
        tone === "outline" && "border border-border text-text",
        tone === "muted" && "border border-border text-muted",
        className,
      )}
      {...props}
    />
  );
}

/** "Sample data" / "Synthetic" badge wherever synthetic values appear (FR-12). */
export function SyntheticBadge({ label = "Synthetic", className }: { label?: string; className?: string }) {
  return (
    <Chip tone="muted" className={cn("px-2 py-0.5 text-[12px]", className)} title="Generated data, not real records">
      {label}
    </Chip>
  );
}

/** Toggle chip for filters: selected = tint + sage border (Map mockup). */
export function ToggleChip({
  selected,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { selected: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      className={cn(
        "rounded-md border px-2.5 py-1.5 text-[13px]",
        selected ? "border-primary bg-tint text-tint-text" : "border-border bg-surface text-text hover:bg-bg",
        className,
      )}
      {...props}
    />
  );
}
