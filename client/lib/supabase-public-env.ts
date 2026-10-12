/** Shared env/cookie helpers — safe to import from Edge middleware. */

export function readPublicSupabaseEnv(): { url: string; anonKey: string } | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim().replace(/\/$/, "");
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
  if (!url || !anonKey) {
    return null;
  }
  if (!url.startsWith("http://") && !url.startsWith("https://")) {
    return null;
  }
  return { url, anonKey };
}

export function hasSupabaseAuthCookie(
  cookies: readonly { name: string }[],
): boolean {
  return cookies.some((cookie) => {
    const { name } = cookie;
    if (!name.startsWith("sb-")) {
      return false;
    }
    return name.endsWith("-auth-token") || name.includes("-auth-token.");
  });
}
