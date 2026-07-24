from enum import StrEnum

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
    anthropic_model_fast: str = "claude-haiku-3-5"

    # Voyage AI
    voyage_api_key: str
    voyage_model: str = "voyage-3-lite"
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
    nutrition_reestimate_on_low_confidence: bool = True
    agent_max_tool_iterations: int = 10
    plan_max_repair_iterations: int = 3
    # docs/6_DATA_INTEGRITY.md DI-3 — cosine similarity floor for saved-recipe candidates
    recipe_similarity_threshold: float = 0.82


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
