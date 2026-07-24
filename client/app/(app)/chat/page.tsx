"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChatInputBar } from "@/components/chat/ChatInputBar";
import { ChatMessage } from "@/components/chat/ChatMessage";
import { SuggestedPromptChip } from "@/components/chat/SuggestedPromptChip";
import { TodayMealsPanel } from "@/components/chat/TodayMealsPanel";
import { useRightPanel } from "@/components/shared/right-panel-context";
import { Skeleton } from "@/components/ui/skeleton";
import { usePlans, usePlan, useProfile } from "@/hooks";
import { apiClient } from "@/lib/api-client";
import { readSseStream } from "@/lib/sse";
import type { PlanItem } from "@/lib/types";

interface ThreadMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

const SUGGESTED_PROMPTS = [
  "Swap dinner",
  "What's for Thursday?",
  "Generate a new plan",
] as const;

const PRO_ONLY_PROMPTS = ["Build a juice protocol for the week"] as const;

function todayItemsFromPlan(
  days: { date: string | null; day_number: number; items: PlanItem[] }[] | undefined,
): PlanItem[] {
  if (!days?.length) return [];
  const today = new Date().toISOString().slice(0, 10);
  const match = days.find((d) => d.date === today) ?? days[0];
  return match?.items ?? [];
}

function avgNutrition(
  days:
    | {
        calories_actual?: number | null;
        protein_g_actual?: number | null;
        carbs_g_actual?: number | null;
        fat_g_actual?: number | null;
        calories_target?: number | null;
        protein_g_target?: number | null;
        carbs_g_target?: number | null;
        fat_g_target?: number | null;
      }[]
    | undefined,
) {
  if (!days?.length) return null;
  const n = days.length;
  const sum = days.reduce(
    (acc, d) => ({
      calories: acc.calories + (d.calories_actual ?? d.calories_target ?? 0),
      protein: acc.protein + (d.protein_g_actual ?? d.protein_g_target ?? 0),
      carbs: acc.carbs + (d.carbs_g_actual ?? d.carbs_g_target ?? 0),
      fat: acc.fat + (d.fat_g_actual ?? d.fat_g_target ?? 0),
    }),
    { calories: 0, protein: 0, carbs: 0, fat: 0 },
  );
  return {
    calories: Math.round(sum.calories / n),
    protein: Math.round(sum.protein / n),
    carbs: Math.round(sum.carbs / n),
    fat: Math.round(sum.fat / n),
  };
}

export default function ChatPage() {
  const { setRightPanel } = useRightPanel();
  const { data: profile } = useProfile();
  const { data: plansData } = usePlans({ limit: 1, status: "approved" });
  const activePlanId = plansData?.data[0]?.id;
  const { data: activePlan } = usePlan(activePlanId);

  const [messages, setMessages] = useState<ThreadMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hi — I'm Nouri, your food advisor. Ask about today's meals, swap a recipe, or generate a new plan.",
    },
  ]);
  const [draft, setDraft] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const todayItems = useMemo(
    () => todayItemsFromPlan(activePlan?.days),
    [activePlan?.days],
  );
  const weekAvg = useMemo(() => avgNutrition(activePlan?.days), [activePlan?.days]);

  useEffect(() => {
    setRightPanel(
      <TodayMealsPanel
        items={todayItems}
        planId={activePlanId ?? null}
        weekTitle={
          activePlan
            ? `${activePlan.title ?? "This week"} · ${activePlan.week_start_date}`
            : null
        }
        weekCalories={weekAvg?.calories ?? null}
        weekProteinG={weekAvg?.protein ?? null}
        weekCarbsG={weekAvg?.carbs ?? null}
        weekFatG={weekAvg?.fat ?? null}
      />,
    );
    return () => setRightPanel(null);
  }, [setRightPanel, todayItems, activePlanId, activePlan, weekAvg]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    const pending = sessionStorage.getItem("nouri.chat.draft");
    if (!pending) return;
    sessionStorage.removeItem("nouri.chat.draft");
    setDraft(pending);
  }, []);

  async function sendMessage(text: string) {
    if (sending) return;

    const userMessage: ThreadMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
    };
    const assistantId = `assistant-${Date.now()}`;
    const assistantMessage: ThreadMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      streaming: true,
    };

    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setSending(true);

    try {
      const response = await apiClient.chatStream({
        message: text,
        conversation_id: conversationId,
        context: activePlanId
          ? { current_plan_id: activePlanId }
          : undefined,
      });

      const headerConversationId = response.headers.get("X-Conversation-Id");
      if (headerConversationId) {
        setConversationId(headerConversationId);
      }

      await readSseStream(response, (event) => {
        if (event.type === "text_delta" && event.text) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + event.text }
                : m,
            ),
          );
        }
        if (event.type === "done") {
          if (event.conversation_id) {
            setConversationId(event.conversation_id);
          }
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, streaming: false } : m,
            ),
          );
        }
        if (event.type === "error") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    streaming: false,
                    content:
                      m.content ||
                      event.message ||
                      event.error ||
                      "Something went wrong. Please try again.",
                  }
                : m,
            ),
          );
        }
      });
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                streaming: false,
                content:
                  m.content ||
                  "I couldn't reach the food advisor just now. Please try again.",
              }
            : m,
        ),
      );
    } finally {
      setSending(false);
    }
  }

  const prompts = [
    ...SUGGESTED_PROMPTS,
    ...(profile?.tier === "pro" ? PRO_ONLY_PROMPTS : []),
  ];

  return (
    <div className="flex h-screen min-h-0 flex-1 flex-col bg-bg">
      <header className="flex items-center justify-between border-b border-border bg-surface px-8 py-5">
        <div>
          <p className="font-sans text-title font-semibold text-text">Nouri</p>
          <span className="font-mono text-eyebrow-sm uppercase tracking-[0.12em] text-primary">
            Your food advisor
          </span>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="flex flex-col gap-5 px-8 py-8">
          {messages.map((message) => (
            <ChatMessage
              key={message.id}
              role={message.role}
              content={
                message.streaming && !message.content ? (
                  <Skeleton className="h-4 w-40" />
                ) : (
                  message.content
                )
              }
            />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="border-t border-border bg-surface px-8 pb-7 pt-5">
        <div className="mb-3 flex flex-wrap gap-2.5">
          {prompts.map((label) => (
            <SuggestedPromptChip
              key={label}
              label={label}
              onClick={() => {
                setDraft(label);
              }}
            />
          ))}
        </div>
        <ChatInputBar
          value={draft}
          onChange={setDraft}
          onSend={sendMessage}
          disabled={sending}
        />
      </div>
    </div>
  );
}
