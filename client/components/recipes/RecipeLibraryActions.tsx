"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  Sheet,
  SheetContent,
  SheetTitle,
} from "@/components/ui/sheet";
import { ApiError, apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";

interface RecipeLibraryActionsProps {
  className?: string;
}

export function RecipeLibraryActions({ className }: RecipeLibraryActionsProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [importOpen, setImportOpen] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [generateTitle, setGenerateTitle] = useState("");
  const [generateNotes, setGenerateNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleImport() {
    const text = importText.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    try {
      const draft = await apiClient.importRecipe({ text });
      await apiClient.saveRecipe({ draft });
      await queryClient.invalidateQueries({ queryKey: ["recipes"] });
      setImportText("");
      setImportOpen(false);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not import recipe. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  function handleGenerate() {
    const title = generateTitle.trim();
    const notes = generateNotes.trim();
    if (!title && !notes) return;
    const prompt = [
      "Generate a recipe for me.",
      title ? `Title: ${title}` : null,
      notes ? `Details: ${notes}` : null,
      "Save it to my recipe library when it's ready.",
    ]
      .filter(Boolean)
      .join("\n");
    sessionStorage.setItem("nouri.chat.draft", prompt);
    setGenerateOpen(false);
    setGenerateTitle("");
    setGenerateNotes("");
    router.push("/chat");
  }

  return (
    <>
      <div className={cn("flex flex-wrap gap-3", className)}>
        <button
          type="button"
          className="btn-ghost"
          onClick={() => {
            setError(null);
            setImportOpen(true);
          }}
        >
          Import Recipe
        </button>
        <button
          type="button"
          className="btn-primary"
          onClick={() => {
            setError(null);
            setGenerateOpen(true);
          }}
        >
          Generate Recipe
        </button>
      </div>

      <Sheet open={importOpen} onOpenChange={setImportOpen}>
        <SheetContent side="right" className="gap-0 overflow-y-auto p-0 sm:max-w-[400px]">
          <div className="border-b border-border px-6 py-5">
            <SheetTitle className="font-sans text-title font-semibold text-text">
              Import Recipe
            </SheetTitle>
            <p className="mt-1 font-sans text-body-sm italic text-text-muted">
              Paste a recipe — we&apos;ll structure it and save it to your library.
            </p>
          </div>
          <div className="flex flex-col gap-4 px-6 py-5">
            <label className="block">
              <span className="font-mono text-eyebrow-sm uppercase tracking-[0.12em] text-text-muted">
                Recipe text
              </span>
              <textarea
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
                rows={12}
                placeholder="Paste ingredients and steps…"
                className="mt-2 w-full rounded-input border border-border bg-surface px-3.5 py-2.5 font-sans text-body text-text outline-none placeholder:italic placeholder:text-text-muted focus:border-primary"
              />
            </label>
            {error ? (
              <p className="font-sans text-body-sm text-cta">{error}</p>
            ) : null}
            <button
              type="button"
              className="btn-primary w-full"
              disabled={busy || !importText.trim()}
              onClick={() => void handleImport()}
            >
              {busy ? "Importing…" : "Import & Save"}
            </button>
          </div>
        </SheetContent>
      </Sheet>

      <Sheet open={generateOpen} onOpenChange={setGenerateOpen}>
        <SheetContent side="right" className="gap-0 overflow-y-auto p-0 sm:max-w-[400px]">
          <div className="border-b border-border px-6 py-5">
            <SheetTitle className="font-sans text-title font-semibold text-text">
              Generate Recipe
            </SheetTitle>
            <p className="mt-1 font-sans text-body-sm italic text-text-muted">
              Tell Nouri what you want — generation continues in chat.
            </p>
          </div>
          <div className="flex flex-col gap-4 px-6 py-5">
            <label className="block">
              <span className="font-mono text-eyebrow-sm uppercase tracking-[0.12em] text-text-muted">
                Working title
              </span>
              <input
                value={generateTitle}
                onChange={(e) => setGenerateTitle(e.target.value)}
                placeholder="e.g. High-protein raw lunch bowl"
                className="mt-2 w-full rounded-input border border-border bg-surface px-3.5 py-2.5 font-sans text-body text-text outline-none placeholder:italic placeholder:text-text-muted focus:border-primary"
              />
            </label>
            <label className="block">
              <span className="font-mono text-eyebrow-sm uppercase tracking-[0.12em] text-text-muted">
                Notes
              </span>
              <textarea
                value={generateNotes}
                onChange={(e) => setGenerateNotes(e.target.value)}
                rows={5}
                placeholder="Diet, prep time, ingredients to use or avoid…"
                className="mt-2 w-full rounded-input border border-border bg-surface px-3.5 py-2.5 font-sans text-body text-text outline-none placeholder:italic placeholder:text-text-muted focus:border-primary"
              />
            </label>
            <button
              type="button"
              className="btn-primary w-full"
              disabled={!generateTitle.trim() && !generateNotes.trim()}
              onClick={handleGenerate}
            >
              Continue in Chat
            </button>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
