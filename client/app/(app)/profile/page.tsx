"use client";

import { useEffect, useState } from "react";
import { EyebrowLabel } from "@/components/shared/EyebrowLabel";
import { Skeleton } from "@/components/ui/skeleton";
import { useProfile, useUpdateProfile } from "@/hooks";

export default function ProfileMainPage() {
  const { data: profile, isLoading } = useProfile();
  const update = useUpdateProfile();
  const [displayName, setDisplayName] = useState("");
  const [timezone, setTimezone] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!profile) return;
    setDisplayName(profile.display_name ?? "");
    setTimezone(profile.timezone);
  }, [profile]);

  if (isLoading || !profile) {
    return <Skeleton className="h-64 w-full max-w-md" />;
  }

  const initial = (profile.display_name ?? profile.email)
    .charAt(0)
    .toUpperCase();

  async function handleSave() {
    await update.mutateAsync({
      display_name: displayName.trim() || undefined,
      timezone,
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <section>
      <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-full bg-primary-dark font-sans text-heading font-medium text-white">
        {initial}
      </div>
      <EyebrowLabel>Profile</EyebrowLabel>
      <h2 className="mt-2 mb-6 font-sans text-title font-semibold text-text">
        Basic information
      </h2>

      <div className="mb-6 max-w-[420px]">
        <label className="mb-2 block font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
          Display Name
        </label>
        <input
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          className="w-full rounded-input border border-border bg-surface px-3.5 py-2.5 font-sans text-body text-text outline-none focus:border-primary"
        />
      </div>

      <div className="mb-6 max-w-[420px]">
        <label className="mb-2 block font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
          Email
        </label>
        <input
          value={profile.email}
          disabled
          className="w-full rounded-input border border-border bg-surface px-3.5 py-2.5 font-sans text-body text-text-muted opacity-70"
        />
      </div>

      <div className="mb-6 max-w-[420px]">
        <label className="mb-2 block font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
          Timezone
        </label>
        <input
          value={timezone}
          onChange={(e) => setTimezone(e.target.value)}
          className="w-full rounded-input border border-border bg-surface px-3.5 py-2.5 font-sans text-body text-text outline-none focus:border-primary"
        />
      </div>

      <button
        type="button"
        onClick={() => void handleSave()}
        disabled={update.isPending}
        className="btn-primary disabled:opacity-50"
      >
        {update.isPending ? "Saving…" : saved ? "Saved" : "Save Changes"}
      </button>
    </section>
  );
}
