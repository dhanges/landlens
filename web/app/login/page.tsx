import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthForm } from "@/components/auth-form";
import { Footer, Header } from "@/components/header";

export const metadata: Metadata = { title: "Sign in" };

export default function Page() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="flex flex-1 items-start justify-center px-4 py-16">
        <Suspense>
          <AuthForm kind="login" />
        </Suspense>
      </main>
      <Footer />
    </div>
  );
}
