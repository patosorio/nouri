"""ExclusionChecker — mitigates RISK-05 (alias mismatch) / exclusion safety."""

from __future__ import annotations

from uuid import UUID

from validation.text_match import contains
from validation.types import ExclusionView, RecipeIngredientView, RecipeView


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

    def first_violation(
        self,
        recipe: RecipeView,
        user_exclusions: list[ExclusionView] | tuple[ExclusionView, ...],
    ) -> tuple[str, str] | None:
        """Return (ingredient name, exclusion name) for the first hit."""
        for ingredient in recipe.ingredients:
            for exclusion in user_exclusions:
                if self._ingredient_matches(ingredient, exclusion):
                    return ingredient.name, exclusion.raw_name
        return None

    def _ingredient_excluded(
        self,
        ingredient_id: UUID | None,
        name: str,
        aliases: tuple[str, ...],
        exclusions: list[ExclusionView] | tuple[ExclusionView, ...],
    ) -> bool:
        ingredient = RecipeIngredientView(
            name=name, ingredient_id=ingredient_id, aliases=aliases
        )
        return any(self._ingredient_matches(ingredient, exclusion) for exclusion in exclusions)

    def _ingredient_matches(
        self, ingredient: RecipeIngredientView, exclusion: ExclusionView
    ) -> bool:
        if (
            ingredient.ingredient_id is not None
            and exclusion.ingredient_id is not None
            and ingredient.ingredient_id == exclusion.ingredient_id
        ):
            return True

        # Token containment runs even when ids differ. Alias cross-match uses
        # the same rule: an exclusion token run inside a recipe name or alias.
        ingredient_labels = (ingredient.name, *ingredient.aliases)
        exclusion_labels = (exclusion.raw_name, *exclusion.aliases)
        for ingredient_label in ingredient_labels:
            for exclusion_label in exclusion_labels:
                if exclusion_label.strip() and contains(ingredient_label, exclusion_label):
                    return True
        return False
