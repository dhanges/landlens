import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Empty state: serif headline, one-line suggestion, one action (web/DESIGN.md "States"). */
export function EmptyState({
  title,
  hint,
  action,
  className,
}: {
  title: string;
  hint?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 px-6 py-10 text-center", className)}>
      <h3 className="text-[22px]">{title}</h3>
      {hint && <p className="max-w-md text-[15px] text-muted">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

/** Error state: what happened, plus retry. */
export function ErrorState({
  error,
  title = "Something went wrong",
  onRetry,
  className,
}: {
  error: unknown;
  title?: string;
  onRetry?: () => void;
  className?: string;
}) {
  const e = error as Partial<ApiError> | null;
  const msg = e?.message ?? "The request failed.";
  const wait = e?.retryAfter ? ` Try again in ${e.retryAfter} s.` : "";
  return (
    <div role="alert" className={cn("flex flex-col items-center gap-2 px-6 py-8 text-center", className)}>
      <h3 className="text-[20px]">{title}</h3>
      <p className="max-w-md text-[14px] text-muted">
        {msg}
        {wait}
        {e?.code && <span className="num ml-1 text-[12px]">({e.code})</span>}
      </p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry} className="mt-1">
          Try again
        </Button>
      )}
    </div>
  );
}

/** Rows of skeleton lines for tables and lists. */
export function SkeletonRows({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-3 p-4", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-5" style={{ width: `${92 - ((i * 13) % 30)}%` }} />
      ))}
    </div>
  );
}
