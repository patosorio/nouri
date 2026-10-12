import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import type { SupabaseClient } from "@supabase/supabase-js";
import { readPublicSupabaseEnv } from "@/lib/supabase-public-env";

/** Server Supabase client for Route Handlers and Server Components. */
export async function createServerSupabaseClient(): Promise<SupabaseClient> {
  const env = readPublicSupabaseEnv();
  if (env === null) {
    throw new Error(
      "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY",
    );
  }

  const cookieStore = await cookies();

  return createServerClient(env.url, env.anonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => {
            cookieStore.set(name, value, options);
          });
        } catch {
          // Called from a Server Component; middleware handles session refresh.
        }
      },
    },
  });
}
