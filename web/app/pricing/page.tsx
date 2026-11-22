import type { Metadata } from "next";
import { Suspense } from "react";

import { Footer, Header } from "@/components/header";
import { PricingView } from "@/components/pages/pricing-view";

export const metadata: Metadata = { title: "Pricing" };

export default function Page() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="flex-1">
        <Suspense>
          <PricingView />
        </Suspense>
      </main>
      <Footer />
    </div>
  );
}
