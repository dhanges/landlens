import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LandLens",
  description: "Spatial land intelligence for the KUDA region.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background text-foreground antialiased">
        {children}
      </body>
    </html>
  );
}
