import type { Metadata } from "next";
import { IBM_Plex_Mono, Newsreader, Schibsted_Grotesk } from "next/font/google";

import { Providers } from "@/components/providers";
import { THEME_SCRIPT } from "@/lib/theme";

import "./globals.css";

// web/DESIGN.md typography: Newsreader for display, Schibsted Grotesk for UI, IBM Plex Mono for every number.
// next/font self-hosts the files (downloaded at build time), so the browser never calls Google.
const newsreader = Newsreader({
  subsets: ["latin"],
  axes: ["opsz"],
  style: ["normal"],
  variable: "--font-newsreader",
  display: "swap",
});
const schibsted = Schibsted_Grotesk({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-schibsted",
  display: "swap",
});
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "LandLens", template: "%s · LandLens" },
  description: "Independent land research for the Warangal region: zoning, projects, soil and water, prices.",
  icons: { icon: "/icon.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      data-theme="light"
      suppressHydrationWarning
      className={`${newsreader.variable} ${schibsted.variable} ${plexMono.variable}`}
    >
      <head>
        {/* Blocking: sets data-theme from localStorage or the system preference before first paint. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-screen">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
