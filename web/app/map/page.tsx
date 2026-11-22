import type { Metadata } from "next";
import { Suspense } from "react";

import { Header } from "@/components/header";
import { MapScreener } from "@/components/map/map-screener";

export const metadata: Metadata = { title: "Map and screener" };

export default function MapPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header wide search />
      <Suspense>
        <MapScreener />
      </Suspense>
    </div>
  );
}
