/** Types aligned with docs/4_API_DESIGN.yaml component schemas. */

export type DietType =
  | "vegan"
  | "plant_based"
  | "wfpb"
  | "pescatarian"
  | "flexitarian"
  | "omnivore"
  | "no_pork";

export type CookingType =
  | "raw_100"
  | "raw_80_cooked_20"
  | "raw_70_cooked_30"
  | "raw_50_cooked_50"
  | "cooked_100";

export type DietSubtype =
  | "keto"
  | "high_iron"
  | "high_protein"
  | "low_carb"
  | "low_fodmap"
  | "anti_inflammatory"
  | "alkaline"
  | "low_sodium"
  | "detox"
  | "high_fiber";

export type Cuisine =
  | "mediterranean"
  | "italian"
  | "asian"
  | "indian"
  | "middle_eastern"
  | "mexican"
  | "japanese"
  | "thai"
  | "western"
  | "latin_american";

export type RecipeType = "meal" | "juice" | "smoothie";

export type JuiceSize =
  | "shot_ml125"
  | "oz8_ml250"
  | "oz16_ml500"
  | "oz24_ml750"
  | "oz32_ml1000";

export type JuiceTime =
  | "morning"
  | "pre_lunch"
  | "lunch"
  | "afternoon"
  | "evening"
  | "dinner"
  | "after_dinner";

export type JuiceColor =
  | "purple"
  | "green"
  | "yellow"
  | "orange"
  | "red"
  | "pink"
  | "blue";

export type PrepMethod =
  | "raw"
  | "juiced"
  | "blended"
  | "dehydrated"
  | "sprouted"
  | "fermented"
  | "steamed"
  | "baked"
  | "fried"
  | "boiled"
  | "pressure_cooked";

export type RecipeUsagePolicy = "prefer_saved" | "balanced" | "prefer_new";

export type PlanStatus = "draft" | "reviewing" | "approved";

export type JobStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type PlanSlot =
  | "breakfast"
  | "lunch"
  | "dinner"
  | "snack"
  | "juice"
  | "extra_morning"
  | "extra_afternoon"
  | "extra_evening";

export type PlanItemSource = "ai_generated" | "saved_recipe" | "shared_corpus";

export type RecipeSource =
  | "ai_generated"
  | "imported_image"
  | "imported_text"
  | "manual";

export type SourceBadgeValue = PlanItemSource | RecipeSource;

export type UserTier = "free" | "pro";

export type NotificationType = "plan_ready" | "plan_failed" | "system";

export interface PaginationMeta {
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: PaginationMeta;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    trace_id: string;
  };
}

export interface UserProfile {
  id: string;
  email: string;
  display_name: string | null;
  tier: UserTier;
  diet_type: DietType;
  diet_subtypes: string[];
  cooking_type: CookingType;
  cuisine_prefs: string[];
  calorie_target: number | null;
  protein_g_target: number | null;
  carbs_g_target: number | null;
  fat_g_target: number | null;
  fiber_g_target: number | null;
  recipe_usage_policy: RecipeUsagePolicy;
  juicing_enabled: boolean;
  generation_credits_remaining: number;
  free_text_preferences: string | null;
  timezone: string;
  created_at: string;
  updated_at: string;
}

export interface ProfileUpdatePayload {
  display_name?: string;
  diet_type?: DietType;
  diet_subtypes?: string[];
  cooking_type?: CookingType;
  cuisine_prefs?: string[];
  calorie_target?: number | null;
  protein_g_target?: number | null;
  carbs_g_target?: number | null;
  fat_g_target?: number | null;
  fiber_g_target?: number | null;
  recipe_usage_policy?: RecipeUsagePolicy;
  juicing_enabled?: boolean;
  timezone?: string;
  free_text_preferences?: string | null;
}

export interface OnboardingPayload extends ProfileUpdatePayload {
  diet_type: DietType;
  cooking_type: CookingType;
  exclusion_names?: string[];
}

export interface UserExclusion {
  id: string;
  user_id: string;
  ingredient_id: string | null;
  ingredient_name_raw: string;
  created_at: string;
}

export interface ExclusionPayload {
  ingredient_name_raw: string;
}

export interface MealPlanSummary {
  id: string;
  title: string | null;
  status: PlanStatus;
  num_days: number;
  week_start_date: string;
  scheduled_date: string | null;
  created_at: string;
}

export interface PlanGenerationParams {
  num_days: number;
  diet_type: DietType;
  cooking_type?: CookingType | null;
  calorie_target?: number | null;
  recipe_usage_policy?: RecipeUsagePolicy;
  include_juicing?: boolean;
  notes?: string | null;
  cloned_from_plan_id?: string | null;
}

export interface NutritionSummary {
  avg_daily_calories?: number;
  avg_daily_protein_g?: number;
  avg_daily_fat_g?: number;
  avg_daily_carbs_g?: number;
  avg_daily_fiber_g?: number;
  validation_passed?: boolean;
  validation_notes?: string[];
}

export interface PlanItem {
  id: string;
  plan_id?: string;
  day_number: number;
  slot: PlanSlot;
  recipe_id: string | null;
  name: string;
  description: string | null;
  recipe_type: RecipeType;
  item_source: PlanItemSource;
  prep_method: PrepMethod | null;
  color: string | null;
  prep_minutes: number | null;
  slot_order?: number;
  juice_time: string | null;
  calories: number | null;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
  fiber_g: number | null;
}

export interface PlanDay {
  id?: string;
  day_number: number;
  date: string | null;
  calories_actual: number | null;
  protein_g_actual: number | null;
  carbs_g_actual: number | null;
  fat_g_actual: number | null;
  fiber_g_actual: number | null;
  calories_target: number | null;
  protein_g_target: number | null;
  carbs_g_target: number | null;
  fat_g_target: number | null;
  fiber_g_target: number | null;
  items: PlanItem[];
}

export interface MealPlan {
  id: string;
  user_id: string;
  title: string | null;
  status: PlanStatus;
  num_days: number;
  week_start_date: string;
  scheduled_date: string | null;
  recipe_usage_policy?: RecipeUsagePolicy;
  generation_params: PlanGenerationParams | null;
  nutrition_summary: NutritionSummary | null;
  days: PlanDay[];
  cloned_from_plan_id: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface SwapPayload {
  recipe_id?: string | null;
  reason?: string | null;
}

export interface RecipeListItem {
  id: string;
  name: string;
  description: string | null;
  recipe_type: RecipeType;
  diet_subtypes: string[];
  cooking_type: CookingType;
  cuisine: string[];
  prep_method: PrepMethod | null;
  color: string | null;
  servings: number;
  prep_minutes: number | null;
  cook_minutes: number | null;
  calories_per_serving: number | null;
  source: RecipeSource;
  created_at: string;
}

export interface RecipeIngredient {
  id?: string;
  ingredient_id: string;
  ingredient_name?: string;
  amount: number;
  unit: string;
  notes?: string | null;
  is_optional?: boolean;
  sort_order?: number;
}

export interface RecipeStep {
  step_number: number;
  instruction: string;
  duration_minutes?: number | null;
  tips?: string | null;
}

export interface NutritionalHighlight {
  nutrient: string;
  note: string;
}

export interface RecipeNutrition {
  calories_per_serving: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  fiber_g: number;
  sat_fat_g?: number | null;
  sugar_g?: number | null;
  nutritional_highlights?: NutritionalHighlight[];
  food_advisor_notes?: string | null;
}

export interface Recipe {
  id: string;
  user_id: string | null;
  name: string;
  description: string | null;
  servings: number;
  prep_minutes: number | null;
  cook_minutes: number | null;
  recipe_type: RecipeType;
  diet_types: DietType[];
  diet_subtypes: string[];
  cooking_type: CookingType;
  cuisine: string[];
  tags: string[];
  prep_method: PrepMethod | null;
  color: string | null;
  source: RecipeSource;
  ingredients: RecipeIngredient[];
  steps: RecipeStep[];
  nutrition: RecipeNutrition | null;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RecipeFilters {
  q?: string;
  diet_type?: DietType;
  cooking_type?: CookingType;
  cuisine?: string[];
  recipe_type?: RecipeType;
  prep_method?: PrepMethod;
  color?: string;
  max_calories?: number;
  max_prep_minutes?: number;
  offset?: number;
  limit?: number;
}

export interface NutritionalProfile {
  recipe_id: string;
  per_serving: RecipeNutrition;
  estimated_at: string;
  disclaimer: string;
}

export interface ShoppingListItem {
  id: string;
  ingredient_id: string | null;
  ingredient_name_display: string;
  quantity_total: number;
  unit: string;
  category: string | null;
  is_checked: boolean;
}

export interface ShoppingList {
  plan_id: string;
  items: ShoppingListItem[];
  pantry_deducted?: boolean;
  generated_at: string;
}

export interface PantryItem {
  id: string;
  user_id: string;
  ingredient_id: string | null;
  ingredient_name_raw: string;
  quantity: number | null;
  unit: string | null;
  notes: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PantryItemPayload {
  ingredient_name_raw: string;
  quantity?: number | null;
  unit?: string | null;
  notes?: string | null;
  expires_at?: string | null;
}

export interface Notification {
  id: string;
  user_id: string;
  type: NotificationType;
  title: string;
  body: string | null;
  data: Record<string, unknown>;
  is_read: boolean;
  created_at: string;
}

export interface Job {
  id: string;
  job_type: "generate_plan" | "generate_recipe";
  status: JobStatus;
  plan_id: string | null;
  payload: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error_message: string | null;
  attempts: number;
  claimed_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface CalendarWeek {
  week_start_date: string;
  plan_id: string | null;
  days: PlanDay[];
}

export interface ConversationSummary {
  id: string;
  plan_id: string | null;
  message_count: number;
  model_version?: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface Conversation {
  id: string;
  plan_id: string | null;
  messages: ChatMessage[];
  model_version?: string;
  created_at: string;
  updated_at: string;
}

export interface ChatRequest {
  message: string;
  conversation_id?: string | null;
  context?: Record<string, unknown> | null;
}
