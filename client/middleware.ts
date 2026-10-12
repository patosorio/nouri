import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import {
  hasSupabaseAuthCookie,
  readPublicSupabaseEnv,
} from "@/lib/supabase-public-env";

const PROTECTED_PREFIXES = [
  "/chat",
  "/plans",
  "/recipes",
  "/calendar",
  "/shopping-list",
  "/pantry",
  "/profile",
  "/onboarding",
];

function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

function redirectToLogin(request: NextRequest, pathname: string): NextResponse {
  const loginUrl = request.nextUrl.clone();
  loginUrl.pathname = "/login";
  loginUrl.searchParams.set("next", pathname);
  return NextResponse.redirect(loginUrl);
}

export async function middleware(request: NextRequest): Promise<NextResponse> {
  let response = NextResponse.next({
    request: {
      headers: request.headers,
    },
  });

  const env = readPublicSupabaseEnv();
  if (env === null) {
    return response;
  }

  const { pathname } = request.nextUrl;
  const sessionCookie = hasSupabaseAuthCookie(request.cookies.getAll());

  // Public routes must not wait on hosted Auth. Leftover sb-* cookies plus a
  // paused/unreachable project made every / and /login hit hang on getUser().
  if (!isProtectedPath(pathname)) {
    return response;
  }

  if (!sessionCookie) {
    return redirectToLogin(request, pathname);
  }

  const supabase = createServerClient(env.url, env.anonKey, {
    global: {
      fetch: (input, init) =>
        fetch(input, {
          ...init,
          signal: AbortSignal.timeout(2_500),
        }),
    },
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value }) => {
          request.cookies.set(name, value);
        });
        response = NextResponse.next({
          request: {
            headers: request.headers,
          },
        });
        cookiesToSet.forEach(({ name, value, options }) => {
          response.cookies.set(name, value, options);
        });
      },
    },
  });

  let user: { id: string } | null = null;
  try {
    const { data, error } = await supabase.auth.getUser();
    if (error === null) {
      user = data.user;
    }
  } catch {
    user = null;
  }

  if (!user) {
    return redirectToLogin(request, pathname);
  }

  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
