"""One place to configure the AI model (course rules: model from OPENAI_MODEL, secrets from .env).

Routing:
  * CALMA_USE_PORTKEY=1  -> Portkey with PORTKEY_API_KEY (preferred once the key is renewed)
  * otherwise            -> OpenAI directly with OPENAI_API_KEY

Only fund policy text is ever sent to the model. Never patient data.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
# .env wins over the shell: the shell may hold stale or placeholder keys.
load_dotenv(ROOT.parent / ".env", override=True)  # workspace "AI for managers/.env"
load_dotenv(ROOT / ".env", override=True)         # optional project overrides

DEFAULT_MODEL = "gpt-5.6-luna"
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
PORTKEY_BASE_URL = os.environ.get("PORTKEY_BASE_URL", "https://api.portkey.ai/v1")


def model_name() -> str:
    return os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)


@lru_cache(maxsize=1)
def get_model():
    from pydantic_ai.models.openai import OpenAIResponsesModel
    from pydantic_ai.providers.openai import OpenAIProvider

    if os.environ.get("CALMA_USE_PORTKEY") == "1":
        key = os.environ.get("PORTKEY_API_KEY")
        if not key:
            raise RuntimeError("CALMA_USE_PORTKEY=1 but PORTKEY_API_KEY is not set.")
        provider = OpenAIProvider(api_key=key, base_url=PORTKEY_BASE_URL)
    else:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set (expected in 'AI for managers/.env').")
        provider = OpenAIProvider(api_key=key)
    # Responses API: gpt-5.6-luna only supports structured output (tool calls) there.
    return OpenAIResponsesModel(model_name(), provider=provider)
