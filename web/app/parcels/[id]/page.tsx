import type { Metadata } from "next";

import { Footer, Header } from "@/components/header";
import { ReportView } from "@/components/report/report-view";
import { EmptyState } from "@/components/states";

export const metadata: Metadata = { title: "Parcel report" };

export default async function ParcelPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const n = Number(id);
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="flex-1">
        {Number.isInteger(n) && n > 0 ? (
          <ReportView id={n} />
        ) : (
          <EmptyState title="No parcel with this number" hint="Parcel links look like /parcels/1234." className="py-24" />
        )}
      </main>
      <Footer />
    </div>
  );
}
