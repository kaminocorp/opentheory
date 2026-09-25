"""Curated OpenRouter model catalog — the source of truth for the agent-model roster.

The platform routes (will route) agent work through OpenRouter. Rather than proxy its full
~300-model catalog, we pin a curated short list of the models we actually intend to assign to
research roles. This list is canonical for **both** sides of the feature:

- the assignment dropdown reads it via ``GET /agent-models/catalog``;
- a write (``PUT /projects/{id}/agent-models``) rejects any id not in :data:`VALID_MODEL_IDS`.

Keeping it in one place (backend) means the dropdown and the validation can never drift. Expanding
or trimming the roster is a one-line edit here — no migration, no frontend change. Order is
display order; ``provider`` is the dropdown group label.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ModelOption:
    """One selectable model. ``id`` is the OpenRouter slug stored on the project; ``name`` is the
    human label; ``provider`` groups the dropdown.

    ``usd_per_1k`` is an optional blended compute rate (0.19.0). ``0.28.0`` prefers
    live OpenRouter prompt/completion prices; this override is used only on the
    fallback path (missing key, timeout, unknown model) when set. When ``None``,
    ``settings.agent_token_rate_usd_per_1k`` is the fallback. Not exposed on the
    catalog read model — it is metering metadata, not a roster field.
    """

    id: str
    name: str
    provider: str
    usd_per_1k: Decimal | None = None


# Curated roster. Slugs follow OpenRouter's ``vendor/model`` convention. Bias: strong reasoning
# models for the lead roles, fast/cheap models for assistant work — but the role↔model policy is
# the operator's call, so every model is offered for every role.
OPENROUTER_MODELS: tuple[ModelOption, ...] = (
    # Anthropic
    ModelOption("anthropic/claude-opus-4.1", "Claude Opus 4.1", "Anthropic"),
    ModelOption("anthropic/claude-sonnet-4", "Claude Sonnet 4", "Anthropic"),
    ModelOption("anthropic/claude-3.7-sonnet", "Claude 3.7 Sonnet", "Anthropic"),
    ModelOption("anthropic/claude-3.5-haiku", "Claude 3.5 Haiku", "Anthropic"),
    # OpenAI
    ModelOption("openai/gpt-4.1", "GPT-4.1", "OpenAI"),
    ModelOption("openai/gpt-4o", "GPT-4o", "OpenAI"),
    ModelOption("openai/gpt-4o-mini", "GPT-4o mini", "OpenAI"),
    ModelOption("openai/o3", "o3", "OpenAI"),
    ModelOption("openai/o3-mini", "o3-mini", "OpenAI"),
    # Google
    ModelOption("google/gemini-2.5-pro", "Gemini 2.5 Pro", "Google"),
    ModelOption("google/gemini-2.5-flash", "Gemini 2.5 Flash", "Google"),
    ModelOption("google/gemini-2.0-flash-001", "Gemini 2.0 Flash", "Google"),
    # DeepSeek
    ModelOption("deepseek/deepseek-r1", "DeepSeek R1", "DeepSeek"),
    ModelOption("deepseek/deepseek-chat", "DeepSeek V3", "DeepSeek"),
    # Meta
    ModelOption("meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B", "Meta"),
    ModelOption("meta-llama/llama-3.1-405b-instruct", "Llama 3.1 405B", "Meta"),
    # Others
    ModelOption("mistralai/mistral-large-2411", "Mistral Large", "Mistral"),
    ModelOption("x-ai/grok-3", "Grok 3", "xAI"),
    ModelOption("qwen/qwen-2.5-72b-instruct", "Qwen2.5 72B", "Qwen"),
)

# Fast membership test for write validation. A previously-assigned id that later leaves the roster
# stays readable (the read schema is lenient) — only *new* assignments are checked against this set.
VALID_MODEL_IDS: frozenset[str] = frozenset(model.id for model in OPENROUTER_MODELS)
