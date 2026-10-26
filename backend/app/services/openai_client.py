"""Lazy OpenAI client construction.

The OpenAI client is created on first use instead of at import time. This keeps
``import main`` working when ``OPENAI_API_KEY`` is not configured, so the
application can still boot, serve ``/health`` and return a precise HTTP 503
from the endpoints that genuinely need OpenAI.

No placeholder API key is ever used: if the key is missing the routes fail
with 503 rather than silently issuing unauthenticated calls.
"""

import os
from typing import Optional

from fastapi import HTTPException, status
from openai import OpenAI


class OpenAIUnavailableError(RuntimeError):
    """Raised when the OpenAI client cannot be constructed."""


_client: Optional[OpenAI] = None
_client_key: Optional[str] = None


def get_openai_client() -> OpenAI:
    """Return a cached OpenAI client, constructing it on first use.

    Raises:
        OpenAIUnavailableError: if ``OPENAI_API_KEY`` is not configured.
    """
    global _client, _client_key

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise OpenAIUnavailableError(
            "OPENAI_API_KEY is not configured. Set it in the environment "
            "(or backend/.env) to enable the OpenAI-backed endpoints."
        )

    # Rebuild the client if the key changed, so rotating the key takes effect
    # without restarting the process.
    if _client is None or _client_key != api_key:
        _client = OpenAI(api_key=api_key)
        _client_key = api_key

    return _client


def require_openai_client() -> OpenAI:
    """FastAPI dependency returning the OpenAI client, or HTTP 503.

    Use this as a route dependency so the failure is reported as a clear
    503 Service Unavailable instead of an unhandled startup crash.
    """
    try:
        return get_openai_client()
    except OpenAIUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
