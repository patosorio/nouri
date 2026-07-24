"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Session, User } from "@supabase/supabase-js";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { createBrowserSupabaseClient } from "@/lib/supabase";
import type { UserTier } from "@/lib/types";

interface AuthContextValue {
  session: Session | null;
  user: User | null;
  tier: UserTier | null;
  isLoading: boolean;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [session, setSession] = useState<Session | null>(null);
  const [sessionLoading, setSessionLoading] = useState(true);

  useEffect(() => {
    const supabase = createBrowserSupabaseClient();

    void supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setSessionLoading(false);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setSessionLoading(false);
    });

    return () => {
      subscription.unsubscribe();
    };
  }, []);

  const profileQuery = useQuery({
    queryKey: ["profile"],
    queryFn: () => apiClient.getProfile(),
    enabled: Boolean(session?.access_token),
    staleTime: 60_000,
  });

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      user: session?.user ?? null,
      tier: profileQuery.data?.tier ?? null,
      isLoading: sessionLoading || (Boolean(session) && profileQuery.isLoading),
      signOut: async () => {
        const supabase = createBrowserSupabaseClient();
        await supabase.auth.signOut();
      },
    }),
    [session, sessionLoading, profileQuery.data?.tier, profileQuery.isLoading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
