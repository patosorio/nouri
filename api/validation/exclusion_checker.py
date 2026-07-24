"""ExclusionChecker — mitigates RISK-05 (alias mismatch) / exclusion safety."""

from __future__ import annotations

from uuid import UUID

from validation.types import ExclusionView, RecipeView


class ExclusionChecker:
    def format_constraint_string(
        self,
        user_exclusions: list[ExclusionView] | tuple[ExclusionView, ...],
    ) -> str:
        """Build exclusion constraint text for recipe-generation prompts (§5.5)."""
        if not user_exclusions:
            return "No ingredient exclusions."
        names: list[str] = []
        for excl in user_exclusions:
            label = excl.raw_name.strip()
            if excl.aliases:
                alias_part = ", ".join(a.strip() for a in excl.aliases if a.strip())
                if alias_part:
                    label = f"{label} (also: {alias_part})"
            names.append(label)
        return (
            "The recipe MUST NOT contain any of the following ingredients "
            f"or their aliases: {'; '.join(names)}."
        )

    def check_recipe(
        self,
        recipe: RecipeView,
        user_exclusions: list[ExclusionView] | tuple[ExclusionView, ...],
    ) -> bool:
        """Return True if recipe is clean (no excluded ingredients)."""
        if not user_exclusions:
            return True
        for ingredient in recipe.ingredients:
            if self._ingredient_excluded(ingredient.ingredient_id, ingredient.name, ingredient.aliases, user_exclusions):
                return False
        return True

    def filter_candidates(
        self,
        candidates: list[RecipeView] | tuple[RecipeView, ...],
        user_exclusions: list[ExclusionView] | tuple[ExclusionView, ...],
    ) -> list[RecipeView]:
        return [r for r in candidates if self.check_recipe(r, user_exclusions)]

    def filter_candidate_ids(
        self,
        candidates: list[RecipeView] | tuple[RecipeView, ...],
        user_exclusions: list[ExclusionView] | tuple[ExclusionView, ...],
    ) -> list[UUID]:
        return [r.id for r in self.filter_candidates(candidates, user_exclusions)]

    def _ingredient_excluded(
        self,
        ingredient_id: UUID | None,
        name: str,
        aliases: tuple[str, ...],
        exclusions: list[ExclusionView] | tuple[ExclusionView, ...],
    ) -> bool:
        name_norm = name.strip().lower()
        alias_norms = {a.strip().lower() for a in aliases}

        for exclusion in exclusions:
            if (
                ingredient_id is not None
                and exclusion.ingredient_id is not None
                and ingredient_id == exclusion.ingredient_id
            ):
                return True

            excl_raw = exclusion.raw_name.strip().lower()
            excl_aliases = {a.strip().lower() for a in exclusion.aliases}

            # Unresolved ingredient: case-insensitive name match (tech spec §6.2)
            if ingredient_id is None and name_norm == excl_raw:
                return True

            # Alias cross-match (RISK-05): recipe name/aliases vs exclusion name/aliases
            recipe_names = {name_norm} | alias_norms
            exclusion_names = {excl_raw} | excl_aliases
            if recipe_names & exclusion_names:
                return True

        return False
