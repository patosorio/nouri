"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { AuthSplitShell } from "@/components/shared/AuthSplitShell";
import { createBrowserSupabaseClient } from "@/lib/supabase";

const signupSchema = z
  .object({
    displayName: z.string().min(1, "Display name is required"),
    email: z.string().email("Enter a valid email"),
    password: z.string().min(8, "Password must be at least 8 characters"),
    confirmPassword: z.string().min(1, "Confirm your password"),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

type SignupForm = z.infer<typeof signupSchema>;

const AUTH_ERROR_COPY = "Unable to create account. Please try again.";

export default function SignupPage() {
  const router = useRouter();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SignupForm>({
    resolver: zodResolver(signupSchema),
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    const supabase = createBrowserSupabaseClient();
    const { error } = await supabase.auth.signUp({
      email: values.email,
      password: values.password,
      options: {
        data: {
          display_name: values.displayName,
        },
      },
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

  const fieldClass =
    "mb-[18px] w-full rounded-input border border-border bg-surface px-3.5 py-3 font-sans text-body text-text outline-none focus:border-primary";
  const labelClass =
    "mb-2 font-mono text-eyebrow-sm uppercase tracking-[0.12em] text-text-muted";

  return (
    <AuthSplitShell
      editorialTitle={
        <>
          Nourish <em>yourself.</em>
        </>
      }
      editorialSubtitle="Your plant-based chef and advisor — it plans your week, writes your recipes, and explains the nutrition behind every bite."
      tagType="cooked"
    >
      <h2 className="font-sans text-heading font-medium text-text">
        Create your account
      </h2>
      <p className="mb-7 mt-2 font-sans text-body italic text-text-muted">
        Then we&apos;ll learn how you eat.
      </p>

      <form onSubmit={onSubmit} className="flex flex-col">
        <label className={labelClass}>Display Name</label>
        <input
          type="text"
          autoComplete="name"
          placeholder="Maya"
          className={fieldClass}
          {...register("displayName")}
        />
        {errors.displayName ? (
          <span className="-mt-3 mb-3 font-sans text-body-sm text-cta">
            {errors.displayName.message}
          </span>
        ) : null}

        <label className={labelClass}>Email</label>
        <input
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          className={fieldClass}
          {...register("email")}
        />
        {errors.email ? (
          <span className="-mt-3 mb-3 font-sans text-body-sm text-cta">
            {errors.email.message}
          </span>
        ) : null}

        <label className={labelClass}>Password</label>
        <input
          type="password"
          autoComplete="new-password"
          placeholder="••••••••"
          className={fieldClass}
          {...register("password")}
        />
        {errors.password ? (
          <span className="-mt-3 mb-3 font-sans text-body-sm text-cta">
            {errors.password.message}
          </span>
        ) : null}

        <label className={labelClass}>Confirm Password</label>
        <input
          type="password"
          autoComplete="new-password"
          placeholder="••••••••"
          className={fieldClass}
          {...register("confirmPassword")}
        />
        {errors.confirmPassword ? (
          <span className="-mt-3 mb-3 font-sans text-body-sm text-cta">
            {errors.confirmPassword.message}
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
          {isSubmitting ? "Creating…" : "Create Account"}
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

      <p className="mt-6 font-sans text-body-sm text-text-muted">
        Already have an account?{" "}
        <Link href="/login" className="text-primary no-underline hover:underline">
          Sign in →
        </Link>
      </p>

      <p className="mt-4 font-mono text-[10.5px] leading-relaxed text-text-muted">
        For educational purposes only. Not medical advice. Nutritional values
        are AI-estimated and clearly labeled throughout the product.
      </p>
    </AuthSplitShell>
  );
}
