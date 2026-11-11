"""Replay sandbox fence for vertical engines.

Prevents outbound mutations against external enterprise systems (ERP, CRM, etc.)
when running in a replay or sandbox context.
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger("nce_verticals.replay_fence")


class ReplaySandboxFenceError(RuntimeError):
    """Raised when an outbound mutation is attempted within a replay sandbox context."""


def check_replay_sandbox_env(headers_or_kwargs: Any = None) -> bool:
    """Check if the current execution context or environment indicates a replay sandbox.

    Returns True if:
    - NCE_REPLAY_SANDBOX environment variable is truthy ('1', 'true', 'yes')
    - headers_or_kwargs contains 'is_replay_sandbox' (truthy)
    - headers_or_kwargs contains 'x-nce-replay-sandbox' (truthy)
    - headers_or_kwargs is an object with an 'is_replay_sandbox' attribute (truthy)
    """
    if os.getenv("NCE_REPLAY_SANDBOX", "").lower() in ("1", "true", "yes"):
        return True

    if headers_or_kwargs is None:
        return False

    if isinstance(headers_or_kwargs, dict):
        if headers_or_kwargs.get("is_replay_sandbox"):
            return True
        val = headers_or_kwargs.get("x-nce-replay-sandbox") or headers_or_kwargs.get(
            "X-NCE-Replay-Sandbox"
        )
        if val and str(val).lower() in ("1", "true", "yes"):
            return True
    else:
        if getattr(headers_or_kwargs, "is_replay_sandbox", False):
            return True

    return False


async def assert_not_replay_sandbox(
    context_or_conn: Any = None,
    *,
    namespace_id: Any = None,
    is_replay_sandbox: bool = False,
) -> None:
    """Assert that the current context is NOT a replay sandbox.

    Raises ReplaySandboxFenceError if replay sandbox mode is active.
    """
    if is_replay_sandbox:
        raise ReplaySandboxFenceError("Outbound mutations are blocked: is_replay_sandbox is True")

    if check_replay_sandbox_env(context_or_conn):
        raise ReplaySandboxFenceError(
            "Outbound mutations are blocked: replay sandbox environment detected"
        )

    if context_or_conn is not None and namespace_id is not None:
        try:
            if callable(getattr(context_or_conn, "fetchval", None)):
                res = await context_or_conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'namespaces' AND column_name = 'is_replay_sandbox'
                    )
                    """
                )
                if res:
                    is_sandbox = await context_or_conn.fetchval(
                        "SELECT is_replay_sandbox FROM namespaces WHERE id = $1",
                        namespace_id,
                    )
                    if is_sandbox:
                        raise ReplaySandboxFenceError(
                            f"Outbound mutations are blocked: namespace {namespace_id} is marked as replay sandbox"
                        )
        except ReplaySandboxFenceError:
            raise
        except Exception as exc:
            log.debug("Error checking namespace replay sandbox: %s", exc)


__all__ = [
    "ReplaySandboxFenceError",
    "check_replay_sandbox_env",
    "assert_not_replay_sandbox",
]
