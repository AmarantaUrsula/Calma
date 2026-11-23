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


def explain_ai_error(e: Exception) -> str:
    """A plain-English reason an AI call failed, safe to show staff (never includes the key)."""
    import logging

    from pydantic_ai.exceptions import ModelHTTPError

    log = logging.getLogger("calma.ai")
    if isinstance(e, RuntimeError) and "API_KEY" in str(e):
        log.error("AI not configured: %s", e)
        return "The AI isn't set up on this server: OPENAI_API_KEY is missing. Add it in the host's environment settings."
    if isinstance(e, ModelHTTPError):
        detail = ""
        if isinstance(e.body, dict):
            detail = str(e.body.get("message") or e.body.get("error", {}).get("message", ""))[:200]
        log.error("AI request failed: HTTP %s from model %s: %s", e.status_code, e.model_name, detail)
        reasons = {
            401: "OpenAI rejected the API key. Check OPENAI_API_KEY in the host's environment settings (no extra spaces, and not a key that was deleted or replaced).",
            403: "OpenAI says this API key isn't allowed to use this model or project. Check the key's project and permissions.",
            404: f"OpenAI doesn't recognize the model '{e.model_name}' for this key. Check OPENAI_MODEL.",
            429: "OpenAI says the usage limit or credit balance was reached, or there were too many requests. Check billing and limits in your OpenAI account, then try again.",
        }
        if e.status_code in reasons:
            return reasons[e.status_code]
        if e.status_code >= 500:
            return "OpenAI had a temporary problem. Please try again in a minute."
        return f"OpenAI returned an error (HTTP {e.status_code})."
    log.error("AI request failed: %s: %s", type(e).__name__, e)
    return f"The AI request failed ({type(e).__name__})."
