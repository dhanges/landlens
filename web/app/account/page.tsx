import type { Metadata } from "next";

import { Footer, Header } from "@/components/header";
import { AccountView } from "@/components/pages/account-view";

export const metadata: Metadata = { title: "Account" };

export default function Page() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="flex-1">
        <AccountView />
      </main>
      <Footer />
    </div>
  );
}
