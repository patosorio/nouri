"use client";

import { useId, useState } from "react";
import { useRouter } from "next/navigation";
import { AddJuiceSlotLink } from "@/components/plans/AddJuiceSlotLink";
import {
  JuiceSlotConfigRow,
  type JuiceSlotDraft,
} from "@/components/plans/JuiceSlotConfigRow";
import { MealTogglePill } from "@/components/plans/MealTogglePill";
import { CookingTypeOption, COOKING_TYPE_VALUES } from "@/components/profile/CookingTypeOption";
import { CuisineChip } from "@/components/profile/CuisineChip";
import { DietSubtypeChip } from "@/components/profile/DietSubtypeChip";
import { DietTypeCard } from "@/components/profile/DietTypeCard";
import { ExclusionTag } from "@/components/profile/ExclusionTag";
import { EyebrowLabel } from "@/components/shared/EyebrowLabel";
import { OnboardingShell } from "@/components/shared/OnboardingShell";
import { ProgressBarStep } from "@/components/shared/ProgressBarStep";
import { SkipLink } from "@/components/shared/SkipLink";
import { ToggleSwitch } from "@/components/shared/ToggleSwitch";
import { apiClient } from "@/lib/api-client";
import type {
  CookingType,
  Cuisine,
  DietSubtype,
  DietType,
  OnboardingPayload,
} from "@/lib/types";

const TOTAL_STEPS = 5;

const DIET_TYPES: DietType[] = [
  "vegan",
  "plant_based",
  "wfpb",
  "pescatarian",
  "flexitarian",
  "omnivore",
  "no_pork",
];

const DIET_SUBTYPES: { value: DietSubtype; label: string }[] = [
  { value: "keto", label: "Keto" },
  { value: "high_iron", label: "High Iron" },
  { value: "high_protein", label: "High Protein" },
  { value: "low_carb", label: "Low Carb" },
  { value: "low_fodmap", label: "Low FODMAP" },
  { value: "anti_inflammatory", label: "Anti-Inflammatory" },
  { value: "alkaline", label: "Alkaline" },
  { value: "low_sodium", label: "Low Sodium" },
  { value: "detox", label: "Detox" },
  { value: "high_fiber", label: "High Fiber" },
];

const CUISINES: { value: Cuisine; label: string }[] = [
  { value: "mediterranean", label: "Mediterranean" },
  { value: "italian", label: "Italian" },
  { value: "asian", label: "Asian" },
  { value: "indian", label: "Indian" },
  { value: "middle_eastern", label: "Middle Eastern" },
  { value: "mexican", label: "Mexican" },
  { value: "japanese", label: "Japanese" },
  { value: "thai", label: "Thai" },
  { value: "western", label: "Western" },
  { value: "latin_american", label: "Latin American" },
];

const GOAL_OPTIONS = [
  "Weight Management",
  "Athletic Performance",
  "Energy & Vitality",
  "Gut Health",
  "Anti-Aging",
  "Hormone Balance",
  "Detox & Cleanse",
  "Iron Levels",
  "Mental Clarity",
  "General Wellness",
] as const;

type GoalOption = (typeof GOAL_OPTIONS)[number];

const STEP_COPY = [
  {
    eyebrow: "Step 1 of 5",
    title: (
      <>
        What&apos;s your <em>eating style?</em>
      </>
    ),
    subtitle:
      "We'll use this as the foundation for every plan and recipe we build for you.",
  },
  {
    eyebrow: "Step 2 of 5",
    title: (
      <>
        How do you <em>prepare</em> your food?
      </>
    ),
    subtitle:
      "This controls how raw vs. cooked your meals will be — independent of your diet type.",
  },
  {
    eyebrow: "Step 3 of 5",
    title: (
      <>
        Any <em>cuisine</em> you love?
      </>
    ),
    subtitle:
      "We'll lean into these when building recipes. You can always add more later.",
  },
  {
    eyebrow: "Step 4 of 5",
    title: (
      <>
        Tell us about <em>your goals.</em>
      </>
    ),
    subtitle: null,
  },
  {
    eyebrow: "Step 5 of 5",
    title: (
      <>
        Do you juice <em>regularly?</em>
      </>
    ),
    subtitle:
      "Juicing Mode adds structured juice slots to your daily plan alongside your meals.",
  },
] as const;

const SKIP_DEFAULTS: OnboardingPayload = {
  diet_type: "plant_based",
  cooking_type: "raw_80_cooked_20",
  diet_subtypes: [],
  cuisine_prefs: [],
  juicing_enabled: true,
  calorie_target: null,
  exclusion_names: [],
};

function defaultJuiceSlots(idPrefix: string): JuiceSlotDraft[] {
  return [
    {
      id: `${idPrefix}-morning`,
      time: "morning",
      color: "green",
      size: "oz16_ml500",
    },
    {
      id: `${idPrefix}-pre-lunch`,
      time: "pre_lunch",
      color: "purple",
      size: "oz8_ml250",
    },
  ];
}

function buildFreeTextPreferences(
  goals: GoalOption[],
  softPreferences: string,
): string | null {
  const soft = softPreferences.trim();
  const parts: string[] = [];
  if (goals.length > 0) {
    parts.push(`Goals: ${goals.join("; ")}`);
  }
  if (soft) {
    parts.push(soft);
  }
  return parts.length > 0 ? parts.join("\n\n") : null;
}

export default function OnboardingPage() {
  const router = useRouter();
  const idPrefix = useId();
  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [dietType, setDietType] = useState<DietType>("plant_based");
  const [cookingType, setCookingType] =
    useState<CookingType>("raw_80_cooked_20");
  const [subtypes, setSubtypes] = useState<DietSubtype[]>([]);
  const [cuisines, setCuisines] = useState<Cuisine[]>([]);
  const [goals, setGoals] = useState<GoalOption[]>([]);
  const [exclusions, setExclusions] = useState<string[]>([]);
  const [exclusionDraft, setExclusionDraft] = useState("");
  const [softPreferences, setSoftPreferences] = useState("");
  const [juicing, setJuicing] = useState(true);
  const [activeMeals, setActiveMeals] = useState({
    breakfast: false,
    lunch: true,
    dinner: true,
  });
  const [juiceSlots, setJuiceSlots] = useState<JuiceSlotDraft[]>(() =>
    defaultJuiceSlots(idPrefix),
  );

  const copy = STEP_COPY[step];

  async function submit(payload: OnboardingPayload) {
    setSubmitting(true);
    setError(null);
    try {
      await apiClient.completeOnboarding(payload);
      router.replace("/chat");
      router.refresh();
    } catch {
      setError("Could not save onboarding. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  function finishWithSelections() {
    void submit({
      diet_type: dietType,
      cooking_type: cookingType,
      diet_subtypes: subtypes,
      cuisine_prefs: cuisines,
      juicing_enabled: juicing,
      free_text_preferences: buildFreeTextPreferences(goals, softPreferences),
      exclusion_names: exclusions,
      calorie_target: null,
    });
  }

  function skipWithDefaults() {
    void submit(SKIP_DEFAULTS);
  }

  function continueOrFinish() {
    if (step < TOTAL_STEPS - 1) {
      setStep((s) => s + 1);
      return;
    }
    finishWithSelections();
  }

  function toggleJuicing(next: boolean) {
    setJuicing(next);
    if (next && juiceSlots.length === 0) {
      setJuiceSlots(defaultJuiceSlots(idPrefix));
      setActiveMeals({ breakfast: false, lunch: true, dinner: true });
    }
  }

  function addExclusion(name: string) {
    const trimmed = name.trim();
    if (!trimmed) return;
    setExclusions((prev) =>
      prev.includes(trimmed) ? prev : [...prev, trimmed],
    );
    setExclusionDraft("");
  }

  const skipLabel =
    step === 2
      ? "Maybe later"
      : step === TOTAL_STEPS - 1
        ? "Skip for now"
        : "I'll set this later";

  const primaryLabel =
    step === TOTAL_STEPS - 1
      ? submitting
        ? "Saving…"
        : "Finish Setup →"
      : "Continue →";

  return (
    <OnboardingShell className={step === 0 ? "max-w-[680px]" : undefined}>
      <ProgressBarStep currentStep={step} totalSteps={TOTAL_STEPS} />

      <EyebrowLabel>{copy.eyebrow}</EyebrowLabel>
      <h1 className="mt-1.5 mb-2.5 font-sans text-heading font-medium text-text [&_em]:italic [&_em]:text-cta">
        {copy.title}
      </h1>
      {copy.subtitle ? (
        <p className="mb-9 font-sans italic text-text-muted">{copy.subtitle}</p>
      ) : (
        <div className="mb-7" />
      )}

      {step === 0 ? (
        <div className="mb-9 grid grid-cols-1 gap-3.5 sm:grid-cols-2">
          {DIET_TYPES.map((value) => (
            <DietTypeCard
              key={value}
              value={value}
              selected={dietType === value}
              onSelect={() => setDietType(value)}
              className={value === "no_pork" ? "sm:col-span-2" : undefined}
            />
          ))}
        </div>
      ) : null}

      {step === 1 ? (
        <div>
          <p className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-text-muted">
            Cooking Type
          </p>
          <div className="mb-10 flex flex-col gap-3">
            {COOKING_TYPE_VALUES.map((value) => (
              <CookingTypeOption
                key={value}
                value={value}
                selected={cookingType === value}
                onSelect={() => setCookingType(value)}
              />
            ))}
          </div>
          <p className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-text-muted">
            Diet Modifiers
          </p>
          <p className="mb-4 font-sans text-[0.92rem] italic text-text-muted">
            Optional — select any that apply to your approach.
          </p>
          <div className="mb-10 flex flex-wrap gap-2.5">
            {DIET_SUBTYPES.map(({ value, label }) => (
              <DietSubtypeChip
                key={value}
                label={label}
                selected={subtypes.includes(value)}
                onToggle={() =>
                  setSubtypes((prev) =>
                    prev.includes(value)
                      ? prev.filter((s) => s !== value)
                      : [...prev, value],
                  )
                }
              />
            ))}
          </div>
        </div>
      ) : null}

      {step === 2 ? (
        <div>
          <div className="mb-4 flex flex-wrap gap-2.5">
            {CUISINES.map(({ value, label }) => (
              <CuisineChip
                key={value}
                label={label}
                selected={cuisines.includes(value)}
                onToggle={() =>
                  setCuisines((prev) =>
                    prev.includes(value)
                      ? prev.filter((c) => c !== value)
                      : [...prev, value],
                  )
                }
              />
            ))}
          </div>
          <p className="mb-10 font-sans text-body-sm italic text-text-muted">
            Skip this if you&apos;re open to anything.
          </p>
        </div>
      ) : null}

      {step === 3 ? (
        <div>
          <div className="mb-9">
            <p className="mb-4 font-sans text-body-sm italic text-text-muted">
              What are you optimizing for? (Select all that apply)
            </p>
            <div className="flex flex-wrap gap-2">
              {GOAL_OPTIONS.map((label) => (
                <DietSubtypeChip
                  key={label}
                  label={label}
                  selected={goals.includes(label)}
                  onToggle={() =>
                    setGoals((prev) =>
                      prev.includes(label)
                        ? prev.filter((g) => g !== label)
                        : [...prev, label],
                    )
                  }
                />
              ))}
            </div>
          </div>

          <div className="mb-9">
            <p className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-text-muted">
              Ingredients to Never Use
            </p>
            <p className="mb-4 font-sans text-body-sm italic text-text-muted">
              These are hard constraints — they&apos;ll never appear in any
              recipe or plan.
            </p>
            {exclusions.length > 0 ? (
              <div className="mb-3 flex flex-wrap gap-2">
                {exclusions.map((name) => (
                  <ExclusionTag
                    key={name}
                    name={name}
                    onRemove={() =>
                      setExclusions((prev) => prev.filter((e) => e !== name))
                    }
                  />
                ))}
              </div>
            ) : null}
            <input
              type="text"
              value={exclusionDraft}
              placeholder="e.g. peanuts, gluten, nightshades…"
              onChange={(e) => setExclusionDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addExclusion(exclusionDraft);
                }
              }}
              className="w-full rounded-input border border-border bg-surface px-3.5 py-2.5 font-sans text-body text-text outline-none placeholder:text-text-muted/70 focus:border-primary"
            />
          </div>

          <div className="mb-9">
            <p className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-text-muted">
              Soft Preferences
            </p>
            <p className="mb-4 font-sans text-body-sm italic text-text-muted">
              Anything else we should know? (Not enforced as a hard rule)
            </p>
            <textarea
              value={softPreferences}
              onChange={(e) => setSoftPreferences(e.target.value)}
              placeholder="e.g. I prefer meals I can prep in under 20 minutes…"
              rows={4}
              className="min-h-[88px] w-full resize-y rounded-input border border-border bg-surface px-3.5 py-2.5 font-sans text-body text-text outline-none placeholder:text-text-muted/70 focus:border-primary"
            />
          </div>
        </div>
      ) : null}

      {step === 4 ? (
        <div>
          <div className="mb-6 flex items-center justify-between rounded-card border border-border bg-surface px-[22px] py-[18px]">
            <span className="font-sans text-body font-medium text-text">
              Enable Juicing Mode
            </span>
            <ToggleSwitch
              checked={juicing}
              onChange={toggleJuicing}
              aria-label="Enable Juicing Mode"
            />
          </div>

          {juicing ? (
            <div className="mb-8 flex flex-col gap-[22px] rounded-card border border-border bg-surface p-[22px]">
              <div>
                <p className="mb-2.5 font-mono text-[11px] uppercase tracking-[0.14em] text-text-muted">
                  Active Solid Meals
                </p>
                <div className="flex gap-2.5">
                  {(
                    [
                      "breakfast",
                      "lunch",
                      "dinner",
                    ] as const
                  ).map((slot) => (
                    <MealTogglePill
                      key={slot}
                      slot={slot}
                      active={activeMeals[slot]}
                      onToggle={() =>
                        setActiveMeals((prev) => ({
                          ...prev,
                          [slot]: !prev[slot],
                        }))
                      }
                    />
                  ))}
                </div>
              </div>

              <div>
                <p className="mb-2.5 font-mono text-[11px] uppercase tracking-[0.14em] text-text-muted">
                  Juice Slots
                </p>
                <div className="flex flex-col gap-2">
                  {juiceSlots.map((slot) => (
                    <JuiceSlotConfigRow
                      key={slot.id}
                      slot={slot}
                      onChange={(next) =>
                        setJuiceSlots((prev) =>
                          prev.map((s) => (s.id === next.id ? next : s)),
                        )
                      }
                      onRemove={() =>
                        setJuiceSlots((prev) =>
                          prev.filter((s) => s.id !== slot.id),
                        )
                      }
                    />
                  ))}
                </div>
                <AddJuiceSlotLink
                  disabled={juiceSlots.length >= 4}
                  onClick={() =>
                    setJuiceSlots((prev) => {
                      if (prev.length >= 4) return prev;
                      return [
                        ...prev,
                        {
                          id: `${idPrefix}-${prev.length + 1}`,
                          time: "afternoon",
                          color: "green",
                          size: "oz16_ml500",
                        },
                      ];
                    })
                  }
                />
              </div>
            </div>
          ) : (
            <div className="mb-8" />
          )}
        </div>
      ) : null}

      {error ? <p className="mb-4 text-body-sm text-cta">{error}</p> : null}

      <div
        className={
          step === 3
            ? "flex items-center justify-end"
            : "flex items-center justify-between"
        }
      >
        {step !== 3 ? (
          <SkipLink
            label={skipLabel}
            onClick={skipWithDefaults}
          />
        ) : null}
        <button
          type="button"
          onClick={continueOrFinish}
          disabled={submitting}
          className="btn-primary"
        >
          {primaryLabel}
        </button>
      </div>
    </OnboardingShell>
  );
}
