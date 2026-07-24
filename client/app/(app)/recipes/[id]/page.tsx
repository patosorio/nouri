import { RecipeDetailView } from "@/components/recipes/RecipeDetailView";

export default async function RecipeDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <RecipeDetailView recipeId={id} />;
}
