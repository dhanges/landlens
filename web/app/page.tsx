import { Footer, Header } from "@/components/header";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header landing />
      <main className="mx-auto w-full max-w-page flex-1 px-8 py-16">
        <h1 className="text-[56px] leading-[1.05] tracking-hero">Know what a parcel is worth before you negotiate.</h1>
      </main>
      <Footer />
    </div>
  );
}
