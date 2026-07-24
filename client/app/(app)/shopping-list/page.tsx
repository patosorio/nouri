"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { PageHeader } from "@/components/shared/PageHeader";
import { PageShell } from "@/components/shared/PageShell";
import { Skeleton } from "@/components/ui/skeleton";
import { usePlans } from "@/hooks";

export default function ShoppingListPage() {
  const router = useRouter();
  const { data, isLoading } = usePlans({ limit: 1, status: "approved" });

  useEffect(() => {
    const id = data?.data[0]?.id;
    if (id) router.replace(`/shopping-list/${id}`);
  }, [data, router]);

  if (isLoading || data?.data[0]) {
    return (
      <PageShell>
        <Skeleton className="h-10 w-64" />
      </PageShell>
    );
  }

  return (
    <PageShell>
      <PageHeader
        eyebrow="Shopping"
        title="Shopping List"
        description="Generate and approve a meal plan to build a shopping list."
      />
    </PageShell>
  );
}
