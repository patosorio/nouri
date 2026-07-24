"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { AuthSplitShell } from "@/components/shared/AuthSplitShell";
import { createBrowserSupabaseClient } from "@/lib/supabase";

const loginSchema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
});

type LoginForm = z.infer<typeof loginSchema>;

const AUTH_ERROR_COPY = "Invalid email or password. Please try again.";

export default function LoginPage() {
  const router = useRouter();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    const supabase = createBrowserSupabaseClient();
    const { error } = await supabase.auth.signInWithPassword({
      email: values.email,
      password: values.password,
    });

    if (error) {
      setFormError(AUTH_ERROR_COPY);
      return;
    }

    router.replace("/chat");
    router.refresh();
  });

  async function handleGoogle() {
    setFormError(null);
    const supabase = createBrowserSupabaseClient();
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/api/auth/callback`,
      },
    });
    if (error) {
      setFormError(AUTH_ERROR_COPY);
    }
  }

  return (
    <AuthSplitShell
      editorialTitle={
        <>
          Eat <em>well.</em>
        </>
      }
      editorialSubtitle="A conversational food advisor and chef, built for people who eat with intention — plant-based, raw-forward, and grounded in real nutrition data."
      tagType="raw"
    >
      <h2 className="font-sans text-heading font-medium text-text">
        Welcome back
      </h2>
      <p className="mb-8 mt-2 font-sans text-body italic text-text-muted">
        Your plant-based advisor is ready.
      </p>

      <form onSubmit={onSubmit} className="flex flex-col">
        <label className="mb-2 font-mono text-eyebrow-sm uppercase tracking-[0.12em] text-text-muted">
          Email
        </label>
        <input
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          className="mb-[18px] w-full rounded-input border border-border bg-surface px-3.5 py-3 font-sans text-body text-text outline-none focus:border-primary"
          {...register("email")}
        />
        {errors.email ? (
          <span className="-mt-3 mb-3 font-sans text-body-sm text-cta">
            {errors.email.message}
          </span>
        ) : null}

        <label className="mb-2 font-mono text-eyebrow-sm uppercase tracking-[0.12em] text-text-muted">
          Password
        </label>
        <input
          type="password"
          autoComplete="current-password"
          placeholder="••••••••"
          className="mb-[18px] w-full rounded-input border border-border bg-surface px-3.5 py-3 font-sans text-body text-text outline-none focus:border-primary"
          {...register("password")}
        />
        {errors.password ? (
          <span className="-mt-3 mb-3 font-sans text-body-sm text-cta">
            {errors.password.message}
          </span>
        ) : null}

        {formError ? (
          <p className="mb-3 font-sans text-body-sm text-cta">{formError}</p>
        ) : null}

        <button
          type="submit"
          disabled={isSubmitting}
          className="btn-primary mt-2 w-full"
        >
          {isSubmitting ? "Signing in…" : "Sign In"}
        </button>
      </form>

      <div className="my-[22px] flex items-center gap-3 font-mono text-eyebrow text-text-muted">
        <span className="h-px flex-1 bg-border" />
        or
        <span className="h-px flex-1 bg-border" />
      </div>

      <button
        type="button"
        onClick={() => void handleGoogle()}
        className="btn-ghost w-full border-border text-text hover:bg-primary/5"
      >
        Continue with Google
      </button>

      <p className="mt-7 font-sans text-body-sm text-text-muted">
        Don&apos;t have an account?{" "}
        <Link href="/signup" className="text-primary no-underline hover:underline">
          Sign up →
        </Link>
      </p>
    </AuthSplitShell>
  );
}
