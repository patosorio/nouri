from enum import StrEnum
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentTask(StrEnum):
    """Model routing keys — docs/2_SAD.md §6.1 / docs/7_TECH_SPEC.md §14."""

    CONVERSATION = "conversation"
    PLAN_GENERATION = "plan_generation"
    RECIPE_GENERATION = "recipe_generation"
    RECIPE_IMPORT_IMAGE = "recipe_import_image"
    RECIPE_IMPORT_TEXT = "recipe_import_text"
    RECIPE_EXPAND = "recipe_expand"
    PLAN_EXPLANATION = "plan_explanation"
    CONVERSATION_SUMMARY = "conversation_summary"
    NUTRITIONAL_PROFILE = "nutritional_profile"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    # Supabase
    supabase_url: str
    supabase_service_role_key: str
    supabase_jwt_issuer: str
    supabase_jwt_public_key: str

    # Anthropic
    anthropic_api_key: str
    anthropic_model_agent: str = "claude-sonnet-4-6"
    anthropic_model_fast: str = "claude-haiku-5-5"

    # Voyage AI — schema is VECTOR(1024) (docs/3_ERD.md). voyage-3-lite is 512-dim
    # only; use voyage-3 (native 1024) or voyage-3.5-lite with output_dimension=1024.
    voyage_api_key: str
    voyage_model: str = "voyage-3"
    voyage_embedding_dim: int = 1024

    # Field encryption
    field_encryption_key: bytes

    # Stripe
    stripe_webhook_secret: str

    # Database
    database_url: str

    # App
    environment: str = "production"
    cors_origins: list[str] = ["https://nouri.app"]
    rate_limit_chat_per_hour: int = 60
    plan_generation_free_tier_monthly_limit: int = 2
    agent_max_tool_iterations: int = 10
    plan_max_repair_iterations: int = 3
    # docs/6_DATA_INTEGRITY.md DI-3 — cosine similarity floor for saved-recipe candidates
    recipe_similarity_threshold: float = 0.82
    # NFR-5.3 — log when a single Anthropic call exceeds this token total
    anthropic_token_alert_threshold: int = 20000
    # Per-attempt HTTP timeout for Anthropic. Plan calls are also capped by the job deadline.
    anthropic_http_timeout_seconds: float = 420.0
    # Plan model calls must finish this long before the worker's hard job limit.
    plan_job_deadline_margin_seconds: float = 60.0
    # When set, refuse Anthropic calls once today's llm_calls spend reaches this USD total.
    # None disables the breaker. No per-user or per-tier limit.
    llm_daily_spend_limit_usd: float | None = None
    # E1 checkpoints stored the raw plan with no handle map.
    # "fail" refuses to resume (no second model call). "recall" pays for a new call.
    plan_resume_legacy_checkpoint: Literal["fail", "recall"] = "fail"
    # Off: keep the model's slots and record under-target days as review notes.
    # On: SlotAssigner may rearrange, but never into a disallowed meal role.
    plan_assigner_polish: bool = False


settings = Settings()

# Dict[AgentTask, str] — docs/2_SAD.md §6.1. Never hardcode model names in agent code.
MODEL_ROUTING: dict[AgentTask, str] = {
    AgentTask.CONVERSATION: settings.anthropic_model_agent,
    AgentTask.PLAN_GENERATION: settings.anthropic_model_agent,
    AgentTask.RECIPE_GENERATION: settings.anthropic_model_agent,
    AgentTask.RECIPE_IMPORT_IMAGE: settings.anthropic_model_agent,
    AgentTask.RECIPE_IMPORT_TEXT: settings.anthropic_model_fast,
    AgentTask.RECIPE_EXPAND: settings.anthropic_model_agent,
    AgentTask.PLAN_EXPLANATION: settings.anthropic_model_fast,
    AgentTask.CONVERSATION_SUMMARY: settings.anthropic_model_fast,
    AgentTask.NUTRITIONAL_PROFILE: settings.anthropic_model_fast,
}


def route_model(task: AgentTask) -> str:
    return MODEL_ROUTING[task]


# USD per 1_000_000 tokens, keyed by model name.
# Per-model keys: input, output, cache_write, cache_read.
# source https://docs.anthropic.com/en/docs/about-claude/pricing, date 2026-10-12
# Haiku 5.5 rates are for prompts up to 100k tokens (higher above that).
# 5-minute cache writes. Keys match settings.anthropic_model_agent and
# settings.anthropic_model_fast.
LLM_TOKEN_PRICES_USD_PER_MILLION: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-haiku-5-5": {
        "input": 0.10,
        "output": 0.50,
        "cache_write": 0.125,
        "cache_read": 0.01,
    },
}
