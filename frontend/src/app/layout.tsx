import type { Metadata } from "next";
import localFont from "next/font/local";
import type { ReactNode } from "react";

import { AuthProvider } from "@/providers/auth-provider";
import { QueryProvider } from "@/providers/query-provider";

import "./globals.css";

// IBM Plex Sans = every sentence a human wrote; IBM Plex Mono = every measured
// value or machine token (§3.1). Self-hosted via next/font/local (bundled
// woff2 in ./fonts) so the build never fetches Google Fonts CSS. Exposed as
// CSS vars the Tailwind theme reads.
const plexSans = localFont({
  src: [
    { path: "./fonts/IBMPlexSans-Regular.woff2", weight: "400", style: "normal" },
    { path: "./fonts/IBMPlexSans-Medium.woff2", weight: "500", style: "normal" },
  ],
  variable: "--font-plex-sans",
  display: "swap",
});

const plexMono = localFont({
  src: [
    { path: "./fonts/IBMPlexMono-Regular.woff2", weight: "400", style: "normal" },
    { path: "./fonts/IBMPlexMono-Medium.woff2", weight: "500", style: "normal" },
  ],
  variable: "--font-plex-mono",
  display: "swap",
});

// Absolute origin for og:image — Open Graph consumers (X, Slack, Discord, iMessage)
// do not resolve relative URLs, so without metadataBase the card silently fails to
// unfurl in exactly the places a share link matters. Vercel injects VERCEL_URL per
// deployment, but it is the *generated* hostname, so the stable public origin wins
// when set.
const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL ??
  (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : "http://localhost:3000");

const description =
  "Autonomous research agents that have to show their work: deterministic instruments, " +
  "append-only provenance, and a research ledger that cannot be rewritten.";

const ogImage = {
  url: "/og.jpg",
  width: 1280,
  height: 640,
  alt: "OpenTheory — autonomous research agents that have to show their work.",
};

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: { default: "OpenTheory", template: "%s · OpenTheory" },
  description,
  openGraph: {
    type: "website",
    siteName: "OpenTheory",
    title: "OpenTheory",
    description,
    url: siteUrl,
    images: [ogImage],
  },
  twitter: {
    card: "summary_large_image",
    title: "OpenTheory",
    description,
    images: [ogImage],
  },
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
