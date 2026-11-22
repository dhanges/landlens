"use client";

import { Footer, Header } from "@/components/header";
import { ErrorState } from "@/components/states";

/** Route error boundary: an unexpected render error shows what happened and a retry, not a blank page. */
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="flex-1">
        <ErrorState
          error={{ message: "This page hit an unexpected error. Your credits and reports are safe.", code: error.digest }}
          title="Something went wrong on this page"
          onRetry={reset}
          className="py-24"
        />
      </main>
      <Footer />
    </div>
  );
}
