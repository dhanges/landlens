import Link from "next/link";

import { Footer, Header } from "@/components/header";
import { EmptyState } from "@/components/states";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="flex-1">
        <EmptyState
          title="This page does not exist"
          hint="The link may be old or mistyped. The map is a good place to start."
          action={
            <Button asChild variant="primary">
              <Link href="/map">Open the map</Link>
            </Button>
          }
          className="py-24"
        />
      </main>
      <Footer />
    </div>
  );
}
