import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, Inter } from "next/font/google";

import { SiteHeader } from "@/components/shell/SiteHeader";

import "./globals.css";

/**
 * Two typefaces, two jobs. Inter carries prose and labels; IBM Plex Mono
 * carries every measured value, because a column of readings that does not
 * align on the digit is not an instrument.
 */
const display = Inter({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

const readout = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-readout",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Atmos — AI engineering observatory",
    template: "%s — Atmos",
  },
  description:
    "Continuous observation of the AI engineering ecosystem: what is changing, how "
    + "significant it is, why it might be happening, and the evidence behind it.",
  applicationName: "Atmos",
};

export const viewport: Viewport = {
  themeColor: "#05070b",
  colorScheme: "dark",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${readout.variable}`}>
      <body className="min-h-dvh font-sans text-ink antialiased">
        <SiteHeader />
        <main className="mx-auto max-w-[1400px] px-4 py-5 sm:px-5 sm:py-6">{children}</main>
        <footer className="mx-auto max-w-[1400px] px-4 pt-4 pb-10 sm:px-5">
          <div className="border-t border-edge/70 pt-4">
            <p className="font-mono text-[9px] leading-relaxed uppercase tracking-[0.14em] text-ghost">
              Atmos watches open-source AI engineering activity and identifies
              technologies whose momentum is changing.
            </p>
            <p className="mt-1 font-mono text-[9px] leading-relaxed uppercase tracking-[0.14em] text-ghost">
              Signals derived from public GitHub activity · every claim is labelled
              observation, inference, hypothesis or unknown
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
