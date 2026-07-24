"use client";

import { useState } from "react";
import { NotificationToggleRow } from "@/components/profile/NotificationToggleRow";
import { EyebrowLabel } from "@/components/shared/EyebrowLabel";

export default function ProfileNotificationsPage() {
  const [prefs, setPrefs] = useState({
    planReady: true,
    planFailed: true,
    system: false,
  });

  return (
    <section>
      <EyebrowLabel>Notifications</EyebrowLabel>
      <h2 className="mt-2 mb-6 font-sans text-title font-semibold text-text">
        What we tell you
      </h2>

      <div className="max-w-lg">
        <NotificationToggleRow
          label="Plan ready"
          description="When a generated meal plan finishes successfully."
          enabled={prefs.planReady}
          onToggle={(enabled) =>
            setPrefs((p) => ({ ...p, planReady: enabled }))
          }
        />
        <NotificationToggleRow
          label="Plan failed"
          description="If generation fails or needs your attention."
          enabled={prefs.planFailed}
          onToggle={(enabled) =>
            setPrefs((p) => ({ ...p, planFailed: enabled }))
          }
        />
        <NotificationToggleRow
          label="Product updates"
          description="Occasional product and feature notes."
          enabled={prefs.system}
          onToggle={(enabled) => setPrefs((p) => ({ ...p, system: enabled }))}
        />
      </div>

      <p className="mt-6 font-mono text-[10px] text-text-muted">
        Preferences are stored locally until notification APIs are wired.
      </p>
    </section>
  );
}
