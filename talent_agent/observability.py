"""Langfuse tracing. No-op decorator when keys are missing or the package is absent."""

from __future__ import annotations

import functools
import os


def _langfuse_enabled() -> bool:
    """Keys may live in .env / Streamlit secrets (read by Settings), so export them for the Langfuse SDK."""
    from talent_agent.config import get_settings

    s = get_settings()
    if not (s.langfuse_public_key and s.langfuse_secret_key):
        return False
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", s.langfuse_public_key)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", s.langfuse_secret_key)
    os.environ.setdefault("LANGFUSE_HOST", s.langfuse_host)
    return True


def observe(name: str | None = None):
    def decorator(fn):
        if _langfuse_enabled():
            try:
                from langfuse import observe as lf_observe

                return lf_observe(name=name or fn.__name__)(fn)
            except Exception:
                pass

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def flush() -> None:
    if not _langfuse_enabled():
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception:
        pass
