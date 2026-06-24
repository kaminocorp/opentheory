import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";

type CookieToSet = { name: string; value: string; options: CookieOptions };

// Only a same-origin, single-leading-slash path is an acceptable post-login destination. This
// rejects open-redirect payloads (CWE-601) that would otherwise escape our origin once
// concatenated as `${origin}${next}`: `//evil.com`, `/\evil.com`, and non-slash values like
// `@evil.com` / `.evil.com` / `https://evil.com` (which would re-home the URL's authority).
function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/\\")) {
    return "/";
  }
  return raw;
}

// OAuth / magic-link callback (0.6.2): Supabase redirects here with a `code`, which we
// exchange for a session and persist in cookies, then bounce to the originating page.
export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = safeNext(searchParams.get("next"));

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (code && url && key) {
    const cookieStore = await cookies();
    const supabase = createServerClient(url, key, {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet: CookieToSet[]) {
          cookiesToSet.forEach(({ name, value, options }) => {
            cookieStore.set(name, value, options);
          });
        },
      },
    });
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (error) {
      // Don't bounce the user onto a page that thinks they're signed in — surface the failure.
      return NextResponse.redirect(`${origin}/?auth_error=${encodeURIComponent(error.message)}`);
    }
  }

  return NextResponse.redirect(`${origin}${next}`);
}
