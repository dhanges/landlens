import type { Metadata } from "next";
import { Suspense } from "react";

import { Footer, Header } from "@/components/header";
import { TrendsView } from "@/components/pages/trends-view";

export const metadata: Metadata = { title: "Locality trends" };

export default function Page() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="flex-1">
        <Suspense>
          <TrendsView />
        </Suspense>
      </main>
      <Footer />
    </div>
  );
}
