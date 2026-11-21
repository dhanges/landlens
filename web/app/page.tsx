import { MapPin } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Placeholder home page for the M0 scaffold. Real features (map, search,
 * reports) arrive in later milestones; the data for them will flow through
 * the typed client in web/lib/api.ts (ADR-003).
 */
export default function Home() {
  return (
    <main className="container flex min-h-screen flex-col items-center justify-center gap-4 text-center">
      <div
        className={cn(
          "flex items-center gap-2 rounded-full border px-4 py-1.5",
          "text-sm text-muted-foreground",
        )}
      >
        <MapPin className="h-4 w-4" />
        KUDA region
      </div>
      <h1 className="text-4xl font-semibold tracking-tight">LandLens</h1>
      <p className="max-w-md text-muted-foreground">
        Spatial land intelligence. The application scaffold is in place; features
        land in upcoming milestones.
      </p>
    </main>
  );
}
