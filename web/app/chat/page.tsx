import type { Metadata } from "next";

import { ChatPanel } from "@/components/chat/chat-panel";
import { Footer, Header } from "@/components/header";

export const metadata: Metadata = { title: "Ask the documents" };

const EXAMPLES = [
  "Who can declare an area a development area?",
  "What happens if I develop land without permission?",
  "What is an unapproved layout?",
  "How is agricultural land converted to non-agricultural use?",
];

/** Chat page (J3): the same panel as the report card, full width, with the corpus listed. */
export default function ChatPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="mx-auto w-full max-w-page flex-1 px-8 pb-14 pt-10">
        <div className="flex flex-wrap items-start gap-8">
          <div className="min-w-0 flex-[999_1_560px]">
            <h1 className="mb-1 text-[44px] leading-tight tracking-display">Ask the documents</h1>
            <p className="mb-6 max-w-[640px] text-muted">
              Answers come only from the government documents loaded into LandLens, with the page for every statement.
              If the documents do not say, you get &ldquo;not found in the documents&rdquo; rather than a guess.
            </p>
            <section className="card p-6">
              <ChatPanel placeholder="Ask about development permission, layouts, land records or conversion" />
            </section>
          </div>
          <aside className="flex min-w-0 flex-[1_1_300px] flex-col gap-6">
            <section className="card p-5">
              <h2 className="mb-2 text-[22px]">Try asking</h2>
              <ul className="flex flex-col gap-2 text-[14px] text-muted">
                {EXAMPLES.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </section>
            <section className="card p-5 text-[14px]">
              <h2 className="mb-2 text-[22px]">Documents</h2>
              <ul className="flex flex-col gap-1.5 text-muted">
                <li>Telangana Urban Areas (Development) Act, 1975</li>
                <li>Telangana Bhu Bharati (Record of Rights in Land) Act, 2025</li>
                <li>AP Agricultural Land (Conversion for Non-Agricultural Purposes) Act, 2006 (scanned amendment pages are not searchable)</li>
                <li>Layout Regularization Scheme 2020: FAQs</li>
              </ul>
              <p className="mt-3 text-[13px] text-muted">
                The KUDA Master Plan 2041 report and its zoning regulations are not public, so zone-specific rules such as
                setbacks are usually not found. Not legal advice.
              </p>
            </section>
          </aside>
        </div>
      </main>
      <Footer />
    </div>
  );
}
