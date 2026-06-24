import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

// Supabase Auth is the IdP (Decision #2): it issues the session JWT the backend verifies.
// These are public, client-safe values (the anon key is meant to ship to the browser).
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

// Whether real auth is wired. When false, the app still builds and runs in dev mode
// (NEXT_PUBLIC_AUTH_DEV) against the backend's X-Dev-Actor-Id path.
export const isSupabaseConfigured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

let browserClient: SupabaseClient | null = null;

/** The singleton browser Supabase client, or null when auth is not configured. */
export function getSupabaseBrowserClient(): SupabaseClient | null {
  if (!isSupabaseConfigured) return null;
  if (browserClient === null) {
    browserClient = createBrowserClient(SUPABASE_URL as string, SUPABASE_ANON_KEY as string);
  }
  return browserClient;
}
