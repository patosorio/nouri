"use client";

import { useEffect, useMemo, useState } from "react";
import { CalendarDayCell } from "@/components/calendar/CalendarDayCell";
import { CalendarNav } from "@/components/calendar/CalendarNav";
import { CalendarWeekBand } from "@/components/calendar/CalendarWeekBand";
import { CalendarWeekPreview } from "@/components/calendar/CalendarWeekPreview";
import { WeekDetailsPanel } from "@/components/calendar/WeekDetailsPanel";
import { PageHeader } from "@/components/shared/PageHeader";
import { PageShell } from "@/components/shared/PageShell";
import { useRightPanel } from "@/components/shared/right-panel-context";
import { Skeleton } from "@/components/ui/skeleton";
import { useCalendarWeeks } from "@/hooks/use-calendar";
import { usePlan, usePlans } from "@/hooks";
import { cn } from "@/lib/utils";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function addMonths(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + n, 1);
}

function toIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function mondayOf(d: Date): Date {
  const copy = new Date(d);
  const day = (copy.getDay() + 6) % 7;
  copy.setDate(copy.getDate() - day);
  copy.setHours(12, 0, 0, 0);
  return copy;
}

function buildMonthGrid(month: Date): Date[][] {
  const first = startOfMonth(month);
  const gridStart = mondayOf(first);
  const weeks: Date[][] = [];
  const cursor = new Date(gridStart);
  for (let w = 0; w < 6; w += 1) {
    const week: Date[] = [];
    for (let d = 0; d < 7; d += 1) {
      week.push(new Date(cursor));
      cursor.setDate(cursor.getDate() + 1);
    }
    // Drop trailing weeks that are entirely next month
    if (
      w > 0 &&
      week.every((day) => day.getMonth() !== month.getMonth())
    ) {
      break;
    }
    weeks.push(week);
  }
  return weeks;
}

function formatRange(start: Date, end: Date): string {
  const opts: Intl.DateTimeFormatOptions = {
    month: "short",
    day: "numeric",
    year: "numeric",
  };
  return `${start.toLocaleDateString("en-US", opts)} – ${end.toLocaleDateString("en-US", opts)}`;
}

export default function CalendarPage() {
  const { setRightPanel } = useRightPanel();
  const [cursorMonth, setCursorMonth] = useState(() => startOfMonth(new Date()));
  const [selectedWeekStart, setSelectedWeekStart] = useState<string | null>(
    null,
  );

  // Calendar uses inline week-details panel (screen-12), not AppShell right rail
  useEffect(() => {
    setRightPanel(null);
    return () => setRightPanel(null);
  }, [setRightPanel]);

  const monthStart = startOfMonth(cursorMonth);
  const monthEnd = new Date(
    monthStart.getFullYear(),
    monthStart.getMonth() + 1,
    0,
  );
  const rangeFrom = toIsoDate(mondayOf(monthStart));
  const rangeTo = toIsoDate(
    (() => {
      const last = mondayOf(monthEnd);
      last.setDate(last.getDate() + 6);
      return last;
    })(),
  );

  const { data: calendarData, isLoading } = useCalendarWeeks({
    from: rangeFrom,
    to: rangeTo,
  });
  const { data: plansData } = usePlans({ limit: 50 });

  const weeks = useMemo(() => buildMonthGrid(cursorMonth), [cursorMonth]);
  const todayMonday = toIsoDate(mondayOf(new Date()));

  const assignmentByWeek = useMemo(() => {
    const map = new Map<string, { planId: string; title: string }>();
    const plans = plansData?.data ?? [];
    for (const week of calendarData?.data ?? []) {
      if (!week.plan_id) continue;
      const plan = plans.find((p) => p.id === week.plan_id);
      map.set(week.week_start_date, {
        planId: week.plan_id,
        title: plan?.title ?? "Assigned plan",
      });
    }
    for (const plan of plans) {
      const key = plan.scheduled_date ?? plan.week_start_date;
      if (key && !map.has(key)) {
        map.set(key, {
          planId: plan.id,
          title: plan.title ?? `${plan.num_days}-day plan`,
        });
      }
    }
    return map;
  }, [calendarData, plansData]);

  // Default-select current week if it has a plan
  useEffect(() => {
    if (selectedWeekStart) return;
    if (assignmentByWeek.has(todayMonday)) {
      setSelectedWeekStart(todayMonday);
    }
  }, [assignmentByWeek, selectedWeekStart, todayMonday]);

  const selectedAssignment = selectedWeekStart
    ? assignmentByWeek.get(selectedWeekStart)
    : null;
  const { data: selectedPlan } = usePlan(selectedAssignment?.planId);

  const monthLabel = cursorMonth.toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
  });

  const selectedRange =
    selectedWeekStart != null
      ? (() => {
          const start = new Date(`${selectedWeekStart}T12:00:00`);
          const end = new Date(start);
          end.setDate(start.getDate() + 6);
          return formatRange(start, end);
        })()
      : "";

  const previewItems =
    selectedPlan?.days.flatMap((d) => d.items).slice(0, 3) ?? [];

  const summary = selectedPlan?.nutrition_summary;
  const avgCalories =
    summary?.avg_daily_calories ??
    (selectedPlan?.days.length
      ? Math.round(
          selectedPlan.days.reduce(
            (s, d) => s + (d.calories_actual ?? d.calories_target ?? 0),
            0,
          ) / selectedPlan.days.length,
        )
      : null);
  const avgProtein =
    summary?.avg_daily_protein_g ??
    (selectedPlan?.days.length
      ? Math.round(
          selectedPlan.days.reduce(
            (s, d) => s + (d.protein_g_actual ?? d.protein_g_target ?? 0),
            0,
          ) / selectedPlan.days.length,
        )
      : null);

  return (
    <PageShell className="flex gap-10">
      <div className="min-w-0 flex-1">
        <PageHeader
          eyebrow="Calendar"
          title="Your Schedule"
          description="Plan your weeks ahead."
        />

        <CalendarNav
          monthLabel={monthLabel}
          onPrev={() => setCursorMonth((m) => addMonths(m, -1))}
          onNext={() => setCursorMonth((m) => addMonths(m, 1))}
        />

        {isLoading ? (
          <Skeleton className="h-80 w-full" />
        ) : (
          <>
            <div className="mb-2 grid grid-cols-7 gap-2">
              {WEEKDAYS.map((d) => (
                <div
                  key={d}
                  className="text-center font-mono text-[10px] uppercase tracking-[0.1em] text-text-muted"
                >
                  {d}
                </div>
              ))}
            </div>

            {weeks.map((week) => {
              const weekStart = toIsoDate(week[0]);
              const assignment = assignmentByWeek.get(weekStart);
              const isSelected = selectedWeekStart === weekStart;
              const isPast = weekStart < todayMonday;
              const showPreview =
                isSelected && previewItems.length > 0;

              return (
                <div key={weekStart}>
                  <button
                    type="button"
                    onClick={() =>
                      setSelectedWeekStart(isSelected ? null : weekStart)
                    }
                    className={cn(
                      "relative mb-2 grid w-full grid-cols-7 gap-2 rounded-[10px] p-0.5 text-left",
                      isSelected &&
                        "outline outline-[1.5px] outline-offset-2 outline-primary",
                    )}
                  >
                    {week.map((day) => (
                      <CalendarDayCell
                        key={toIsoDate(day)}
                        dayNumber={day.getDate()}
                        isOutsideMonth={
                          day.getMonth() !== cursorMonth.getMonth()
                        }
                        isPastWeek={isPast && !isSelected}
                      />
                    ))}
                    {assignment ? (
                      <CalendarWeekBand planTitle={assignment.title} />
                    ) : null}
                  </button>

                  {showPreview ? (
                    <CalendarWeekPreview items={previewItems} />
                  ) : null}
                </div>
              );
            })}
          </>
        )}
      </div>

      <WeekDetailsPanel
        className="hidden lg:block"
        empty={!selectedAssignment}
        planName={selectedAssignment?.title ?? ""}
        dateRange={selectedRange}
        planId={selectedAssignment?.planId ?? null}
        avgCalories={avgCalories}
        avgProteinG={avgProtein}
      />
    </PageShell>
  );
}
