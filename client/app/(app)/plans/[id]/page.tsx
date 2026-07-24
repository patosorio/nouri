import { PlanDetailView } from "@/components/plans/PlanDetailView";

export default async function PlanDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <PlanDetailView planId={id} />;
}
