import { createBrowserSupabaseClient } from "@/lib/supabase";
import type {
  ApiErrorBody,
  CalendarWeek,
  ChatRequest,
  Conversation,
  ConversationSummary,
  ExclusionPayload,
  Job,
  MealPlan,
  MealPlanSummary,
  Notification,
  NutritionalProfile,
  OnboardingPayload,
  PaginatedResponse,
  PantryItem,
  PantryItemPayload,
  PlanGenerationParams,
  PlanItem,
  PlanStatus,
  ProfileUpdatePayload,
  Recipe,
  RecipeFilters,
  RecipeListItem,
  ShoppingList,
  SwapPayload,
  UserExclusion,
  UserProfile,
} from "@/lib/types";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly traceId: string;

  constructor(
    code: string,
    message: string,
    status: number,
    traceId: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.traceId = traceId;
  }
}

function apiBaseUrl(): string {
  // Static access required for Next.js client-bundle inlining.
  const base = process.env.NEXT_PUBLIC_API_URL;
  if (!base) {
    throw new Error("Missing NEXT_PUBLIC_API_URL");
  }
  // Routers mount at /api/v1 (api/main.py). Accept either
  // http://localhost:8000 or http://localhost:8000/api/v1.
  const trimmed = base.replace(/\/$/, "");
  return trimmed.endsWith("/api/v1") ? trimmed : `${trimmed}/api/v1`;
}

async function authHeaders(): Promise<HeadersInit> {
  const supabase = createBrowserSupabaseClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const headers: Record<string, string> = {
    Accept: "application/json",
  };

  if (session?.access_token) {
    headers.Authorization = `Bearer ${session.access_token}`;
  }

  return headers;
}

function toQuery(params: Record<string, unknown> | undefined): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    if (Array.isArray(value)) {
      for (const item of value) {
        search.append(key, String(item));
      }
    } else {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

async function parseError(response: Response): Promise<ApiError> {
  let code = "UNKNOWN_ERROR";
  let message = response.statusText || "Request failed";
  let traceId = "";

  try {
    const body = (await response.json()) as ApiErrorBody;
    if (body.error) {
      code = body.error.code;
      message = body.error.message;
      traceId = body.error.trace_id;
    }
  } catch {
    // Non-JSON error body — keep defaults.
  }

  return new ApiError(code, message, response.status, traceId);
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(await authHeaders());
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${apiBaseUrl()}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    throw await parseError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const apiClient = {
  // Profile
  getProfile: () => request<UserProfile>("/profile"),

  updateProfile: (body: ProfileUpdatePayload) =>
    request<UserProfile>("/profile", {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  completeOnboarding: (body: OnboardingPayload) =>
    request<UserProfile>("/profile/onboarding", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listExclusions: () =>
    request<PaginatedResponse<UserExclusion>>("/profile/exclusions"),

  addExclusion: (body: ExclusionPayload) =>
    request<UserExclusion>("/profile/exclusions", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteExclusion: (itemId: string) =>
    request<void>(`/profile/exclusions/${itemId}`, { method: "DELETE" }),

  // Plans
  listPlans: (params?: { offset?: number; limit?: number; status?: PlanStatus }) =>
    request<PaginatedResponse<MealPlanSummary>>(`/plans${toQuery(params)}`),

  generatePlan: (body: PlanGenerationParams) =>
    request<Job>("/plans", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getPlan: (planId: string) => request<MealPlan>(`/plans/${planId}`),

  updatePlanStatus: (planId: string, status: PlanStatus) =>
    request<MealPlan>(`/plans/${planId}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),

  deletePlan: (planId: string) =>
    request<void>(`/plans/${planId}`, { method: "DELETE" }),

  clonePlan: (planId: string) =>
    request<Job>(`/plans/${planId}/clone`, { method: "POST" }),

  swapPlanItem: (planId: string, itemId: string, body: SwapPayload) =>
    request<PlanItem | Job>(`/plans/${planId}/items/${itemId}/swap`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  regeneratePlanDay: (planId: string, dayNumber: number) =>
    request<Job>(`/plans/${planId}/days/${dayNumber}/regenerate`, {
      method: "POST",
    }),

  getShoppingList: (planId: string) =>
    request<ShoppingList>(`/plans/${planId}/shopping-list`),

  /** GET /plans/{id}/export — PDF binary (pro tier). */
  exportPlanPdf: async (planId: string): Promise<Blob> => {
    const headers = new Headers(await authHeaders());
    headers.set("Accept", "application/pdf");
    const response = await fetch(`${apiBaseUrl()}/plans/${planId}/export`, {
      headers,
    });
    if (!response.ok) {
      throw await parseError(response);
    }
    return response.blob();
  },

  // Recipes
  listRecipes: (filters?: RecipeFilters) =>
    request<PaginatedResponse<RecipeListItem>>(
      `/recipes${toQuery(filters as Record<string, unknown> | undefined)}`,
    ),

  searchRecipes: (filters?: RecipeFilters) =>
    request<PaginatedResponse<RecipeListItem>>(
      `/recipes/search${toQuery(filters as Record<string, unknown> | undefined)}`,
    ),

  getRecipe: (recipeId: string) => request<Recipe>(`/recipes/${recipeId}`),

  deleteRecipe: (recipeId: string) =>
    request<void>(`/recipes/${recipeId}`, { method: "DELETE" }),

  /** POST /recipes/import — returns a draft (not yet saved). */
  importRecipe: async (body: {
    text?: string;
    file?: File;
  }): Promise<Record<string, unknown>> => {
    const headers = new Headers(await authHeaders());
    const form = new FormData();
    if (body.text) form.set("text", body.text);
    if (body.file) form.set("file", body.file);
    const response = await fetch(`${apiBaseUrl()}/recipes/import`, {
      method: "POST",
      headers,
      body: form,
    });
    if (!response.ok) {
      throw await parseError(response);
    }
    return (await response.json()) as Record<string, unknown>;
  },

  /** POST /recipes — persist a RecipeDraft. */
  saveRecipe: (body: { draft: Record<string, unknown> }) =>
    request<Recipe>("/recipes", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getRecipeNutritionProfile: (recipeId: string) =>
    request<NutritionalProfile>(`/recipes/${recipeId}/nutrition-profile`),

  // Chat / conversations
  listConversations: (params?: { offset?: number; limit?: number }) =>
    request<PaginatedResponse<ConversationSummary>>(
      `/conversations${toQuery(params)}`,
    ),

  getConversation: (conversationId: string) =>
    request<Conversation>(`/conversations/${conversationId}`),

  deleteConversation: (conversationId: string) =>
    request<void>(`/conversations/${conversationId}`, { method: "DELETE" }),

  /** Returns the raw Response for SSE streaming (Phase 9A). */
  chatStream: async (body: ChatRequest): Promise<Response> => {
    const headers = new Headers(await authHeaders());
    headers.set("Content-Type", "application/json");
    headers.set("Accept", "text/event-stream");

    const response = await fetch(`${apiBaseUrl()}/chat`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      throw await parseError(response);
    }

    return response;
  },

  // Pantry
  listPantryItems: (params?: { offset?: number; limit?: number }) =>
    request<PaginatedResponse<PantryItem>>(`/pantry${toQuery(params)}`),

  addPantryItem: (body: PantryItemPayload) =>
    request<PantryItem>("/pantry/items", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updatePantryItem: (itemId: string, body: PantryItemPayload) =>
    request<PantryItem>(`/pantry/items/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deletePantryItem: (itemId: string) =>
    request<void>(`/pantry/items/${itemId}`, { method: "DELETE" }),

  // Calendar
  listCalendarWeeks: (params?: { from?: string; to?: string }) =>
    request<{ data: CalendarWeek[] }>(`/calendar${toQuery(params)}`),

  getCalendarWeek: (weekStartDate: string) =>
    request<CalendarWeek>(`/calendar/${weekStartDate}`),

  assignPlanToWeek: (weekStartDate: string, planId: string) =>
    request<CalendarWeek>(`/calendar/${weekStartDate}`, {
      method: "PUT",
      body: JSON.stringify({ plan_id: planId }),
    }),

  // Notifications
  listNotifications: (params?: {
    offset?: number;
    limit?: number;
    unread_only?: boolean;
  }) =>
    request<PaginatedResponse<Notification>>(
      `/notifications${toQuery(params)}`,
    ),

  markNotificationRead: (notificationId: string) =>
    request<void>(`/notifications/${notificationId}/read`, { method: "POST" }),

  markAllNotificationsRead: () =>
    request<void>("/notifications/read-all", { method: "POST" }),

  // Jobs
  getJob: (jobId: string) => request<Job>(`/jobs/${jobId}`),
};
