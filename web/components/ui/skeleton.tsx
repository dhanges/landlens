import { cn } from "@/lib/utils";

/** Loading block: a surface-toned shape with a subtle pulse (web/DESIGN.md "States"). */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden="true" className={cn("animate-pulse rounded-md bg-border/60", className)} {...props} />;
}
