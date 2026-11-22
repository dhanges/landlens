import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthForm } from "@/components/auth-form";
import { Footer, Header } from "@/components/header";

export const metadata: Metadata = { title: "Create account" };

export default function Page() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="flex flex-1 items-start justify-center px-4 py-16">
        <Suspense>
          <AuthForm kind="signup" />
        </Suspense>
      </main>
      <Footer />
    </div>
  );
}
