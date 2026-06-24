import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AuthProvider } from "@/providers/auth-provider";
import { DevActorProvider } from "@/providers/dev-actor-provider";
import { QueryProvider } from "@/providers/query-provider";

import "./globals.css";

export const metadata: Metadata = {
  title: "OpenTheory",
  description: "Continuous, agent-driven research projects with transparent provenance.",
};

type RootLayoutProps = {
  children: ReactNode;
};

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en">
      <body>
        <QueryProvider>
          <AuthProvider>
            <DevActorProvider>{children}</DevActorProvider>
          </AuthProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
