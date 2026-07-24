"use client";

import { useState } from "react";
import { EyebrowLabel } from "@/components/shared/EyebrowLabel";
import { createBrowserSupabaseClient } from "@/lib/supabase";
import { useProfile } from "@/hooks";
import { Skeleton } from "@/components/ui/skeleton";

export default function ProfileAccountPage() {
  const { data: profile, isLoading } = useProfile();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (isLoading || !profile) {
    return <Skeleton className="h-48 w-full max-w-md" />;
  }

  async function handlePassword() {
    setMessage(null);
    setError(null);
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setSaving(true);
    const supabase = createBrowserSupabaseClient();
    const { error: updateError } = await supabase.auth.updateUser({
      password,
    });
    setSaving(false);
    if (updateError) {
      setError("Could not update password.");
      return;
    }
    setPassword("");
    setConfirm("");
    setMessage("Password updated.");
  }

  return (
    <section>
      <EyebrowLabel>Account</EyebrowLabel>
      <h2 className="mt-2 mb-6 font-sans text-title font-semibold text-text">
        Sign-in details
      </h2>

      <div className="mb-6 max-w-[420px]">
        <label className="mb-2 block font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
          Email
        </label>
        <input
          value={profile.email}
          disabled
          className="w-full rounded-input border border-border bg-surface px-3.5 py-2.5 text-text-muted opacity-70"
        />
      </div>

      <div className="mb-4 max-w-[420px]">
        <label className="mb-2 block font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
          New Password
        </label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-input border border-border bg-surface px-3.5 py-2.5 outline-none focus:border-primary"
        />
      </div>

      <div className="mb-6 max-w-[420px]">
        <label className="mb-2 block font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
          Confirm Password
        </label>
        <input
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          className="w-full rounded-input border border-border bg-surface px-3.5 py-2.5 outline-none focus:border-primary"
        />
      </div>

      {error ? <p className="mb-3 text-body-sm text-cta">{error}</p> : null}
      {message ? (
        <p className="mb-3 text-body-sm text-primary">{message}</p>
      ) : null}

      <button
        type="button"
        onClick={() => void handlePassword()}
        disabled={saving}
        className="btn-primary"
      >
        {saving ? "Updating…" : "Update Password"}
      </button>
    </section>
  );
}
