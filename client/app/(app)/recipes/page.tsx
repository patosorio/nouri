"use client";

import { useEffect, useMemo, useState } from "react";
import { FilterPanel } from "@/components/recipes/FilterPanel";
import { RecipeCard } from "@/components/recipes/RecipeCard";
import { RecipeLibraryActions } from "@/components/recipes/RecipeLibraryActions";
import { RecipeSearchInput } from "@/components/recipes/RecipeSearchInput";
import { PageHeader } from "@/components/shared/PageHeader";
import { PageShell } from "@/components/shared/PageShell";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import { useRecipes } from "@/hooks";
import type { RecipeFilters, RecipeListItem, RecipeType } from "@/lib/types";
import { cn } from "@/lib/utils";

const TYPE_TABS: Array<{ label: string; value: RecipeType | "all" }> = [
  { label: "All", value: "all" },
  { label: "Meal", value: "meal" },
  { label: "Juice", value: "juice" },
  { label: "Smoothie", value: "smoothie" },
];

export default function RecipesPage() {
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filters, setFilters] = useState<RecipeFilters>({
    limit: 30,
    offset: 0,
  });
  const [typeTab, setTypeTab] = useState<RecipeType | "all">("all");
  const [search, setSearch] = useState("");
  const [accumulated, setAccumulated] = useState<RecipeListItem[]>([]);

  const queryFilters = useMemo<RecipeFilters>(
    () => ({
      ...filters,
      q: search.trim() || undefined,
      recipe_type: typeTab === "all" ? undefined : typeTab,
    }),
    [filters, search, typeTab],
  );

  const { data, isLoading, isError, isFetching } = useRecipes(queryFilters);

  useEffect(() => {
    if (!data) return;
    setAccumulated((prev) => {
      if ((queryFilters.offset ?? 0) === 0) return data.data;
      const seen = new Set(prev.map((r) => r.id));
      return [...prev, ...data.data.filter((r) => !seen.has(r.id))];
    });
  }, [data, queryFilters.offset]);

  function resetFilters(next: Partial<RecipeFilters> = {}) {
    setFilters((prev) => ({ ...prev, ...next, offset: 0 }));
  }

  function loadMore() {
    if (!data?.pagination.has_more) return;
    setFilters((prev) => ({
      ...prev,
      offset: (prev.offset ?? 0) + (prev.limit ?? 30),
    }));
  }

  const count = data?.pagination.total;
  const description =
    count != null
      ? `${count} saved recipe${count === 1 ? "" : "s"}`
      : "Your saved recipes";

  return (
    <PageShell>
      <PageHeader
        eyebrow="Library"
        title="Recipes"
        description={description}
        actions={<RecipeLibraryActions />}
      />

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <RecipeSearchInput
          value={search}
          onChange={(value) => {
            setSearch(value);
            resetFilters();
          }}
          className="max-w-[400px] flex-1"
        />
        <Collapsible open={filtersOpen} onOpenChange={setFiltersOpen}>
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className={cn(
                "inline-flex items-center gap-2 rounded-pill border px-[18px] py-2.5 font-mono text-xs tracking-[0.04em]",
                filtersOpen
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border bg-surface text-text",
              )}
            >
              Filters {filtersOpen ? "▴" : "▾"}
            </button>
          </CollapsibleTrigger>
        </Collapsible>
      </div>

      <div className="mb-5 flex w-fit flex-wrap gap-1.5 rounded-pill bg-surface p-1.5">
        {TYPE_TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            className={cn(
              "rounded-pill px-[18px] py-2 font-mono text-[11px] uppercase tracking-[0.1em]",
              typeTab === tab.value
                ? "bg-primary text-white"
                : "bg-transparent text-text-muted hover:text-text",
            )}
            onClick={() => {
              setTypeTab(tab.value);
              resetFilters();
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <Collapsible open={filtersOpen} onOpenChange={setFiltersOpen}>
        <CollapsibleContent className="mb-6">
          <FilterPanel
            filters={filters}
            onFiltersChange={(next) => {
              setFilters({ ...next, offset: 0 });
            }}
          />
        </CollapsibleContent>
      </Collapsible>

      {isLoading && (queryFilters.offset ?? 0) === 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-72" />
          ))}
        </div>
      ) : null}

      {isError ? (
        <p className="font-sans text-body text-accent-cta">
          Could not load recipes.
        </p>
      ) : null}

      {!isLoading || accumulated.length > 0 ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {accumulated.map((recipe) => (
              <RecipeCard key={recipe.id} recipe={recipe} />
            ))}
          </div>
          {accumulated.length === 0 && !isLoading ? (
            <p className="mt-6 font-sans text-body-sm italic text-text-muted">
              No recipes match these filters.
            </p>
          ) : null}
          {data?.pagination.has_more ? (
            <div className="mt-8 flex justify-center">
              <Button
                type="button"
                variant="outline"
                onClick={loadMore}
                disabled={isFetching}
              >
                {isFetching ? "Loading…" : "Load more"}
              </Button>
            </div>
          ) : null}
        </>
      ) : null}
    </PageShell>
  );
}
