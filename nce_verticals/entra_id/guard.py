"""
nce_verticals/entra_id/guard.py
===============================
Compatibility shim re-exporting from nce_verticals.security.entra_id.
"""

from __future__ import annotations

from nce_verticals.security.entra_id import (
    EntraConfig,
    EntraIDAuthenticator,
    EntraPrincipal,
    EntraSecurityGate,
    EntraVerificationError,
    get_global_entra_gate,
    require_entra_identity,
)

__all__ = [
    "EntraConfig",
    "EntraIDAuthenticator",
    "EntraPrincipal",
    "EntraSecurityGate",
    "EntraVerificationError",
    "get_global_entra_gate",
    "require_entra_identity",
]
