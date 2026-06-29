import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import type { ReactNode } from "react";

import { AuthProvider } from "@/providers/auth-provider";
import { QueryProvider } from "@/providers/query-provider";

import "./globals.css";

// IBM Plex Sans = every sentence a human wrote; IBM Plex Mono = every measured
// value or machine token (§3.1). Self-hosted by next/font (no FOUT, size-adjust
// fallback minimises layout shift); exposed as CSS vars the Tailwind theme reads.
const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-sans",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "OpenTheory",
  description: "Continuous, agent-driven research projects with transparent provenance.",
};

type RootLayoutProps = {
  children: ReactNode;
};

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable}`}>
      <body>
        <QueryProvider>
          <AuthProvider>{children}</AuthProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
